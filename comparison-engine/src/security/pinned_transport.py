"""DNS-Pinned HTTP Transports and Network Backends.

Enforces connection pinning to prevent DNS rebinding attacks while preserving
TLS certificate verification, SNI, and Host header semantics.
Includes strict fail-closed peer IP verification on all established sockets.

Supported and verified library versions:
- httpx: >= 0.27.0, <= 0.28.x (Installed: 0.28.1)
- httpcore: >= 1.0.0, <= 1.0.x (Installed: 1.0.9)
"""

from __future__ import annotations

import ipaddress
import typing
from typing import Any

import anyio
import httpcore
import httpcore._backends.anyio
import httpcore._backends.sync
import httpx

from .ssrf_validator import (
    DNSResolutionError,
    PeerVerificationError,
    SSRFSecurityError,
    resolve_and_validate_hostname,
    resolve_and_validate_hostname_async,
    validate_ip_address,
)

SOCKET_OPTION = typing.Tuple[int, int, int]


class PinnedAsyncNetworkBackend(httpcore._backends.anyio.AnyIOBackend):
    """Async network backend that resolves DNS asynchronously with deadline enforcement,
    validates every resolved IP against blocked IPs, establishes the connection directly
    to the pinned IP address, and verifies that the connected peer IP strictly matches the
    pinned IP (fail-closed)."""

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: typing.Iterable[SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        # Non-blocking, deadline-aware asynchronous DNS resolution & SSRF validation
        validated_ips = await resolve_and_validate_hostname_async(host, port, timeout=timeout)
        if not validated_ips:
            raise DNSResolutionError(f"No valid IP address available for '{host}'.")

        # Pin connection to the first validated safe IP
        pinned_ip = validated_ips[0]
        try:
            expected_ip = ipaddress.ip_address(pinned_ip)
        except ValueError as exc:
            raise DNSResolutionError(f"Malformed pinned IP address '{pinned_ip}': {exc}") from exc

        # Connect directly to the pinned IP to eliminate DNS rebinding window
        stream = await super().connect_tcp(
            host=pinned_ip,
            port=port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

        # Fail-closed post-connect verification of physical remote peer IP
        try:
            raw_stream = getattr(stream, "_stream", stream)
            if not hasattr(raw_stream, "extra"):
                await stream.aclose()
                raise PeerVerificationError(
                    f"Underlying stream for '{host}' does not support peer address inspection. "
                    "Connection rejected (fail-closed)."
                )

            remote_addr = raw_stream.extra(anyio.abc.SocketAttribute.remote_address)
            if not remote_addr or not isinstance(remote_addr, (tuple, list)) or len(remote_addr) < 2:
                await stream.aclose()
                raise PeerVerificationError(
                    f"Failed to inspect peer address for socket connection to '{host}'. "
                    "Connection rejected (fail-closed)."
                )

            peer_ip_str = str(remote_addr[0])
            peer_ip = ipaddress.ip_address(peer_ip_str)

            # Strict comparison: Peer IP must exactly match the pinned IP
            if peer_ip != expected_ip:
                await stream.aclose()
                raise PeerVerificationError(
                    f"Peer IP mismatch: socket connected to {peer_ip}, but pinned IP was {expected_ip}. "
                    "Connection aborted (fail-closed)."
                )

            # Double-check that peer IP is not in any blocked range
            validate_ip_address(peer_ip)

        except SSRFSecurityError:
            # Re-raise explicit security errors
            raise
        except Exception as exc:
            # Any unexpected error during inspection must close the stream and fail closed
            await stream.aclose()
            raise PeerVerificationError(
                f"Peer verification failed for '{host}': {exc}. Connection rejected (fail-closed)."
            ) from exc

        return stream


class PinnedSyncNetworkBackend(httpcore._backends.sync.SyncBackend):
    """Sync network backend that resolves DNS once, validates against blocked IPs,
    establishes the connection directly to the pinned IP address, and verifies that the
    connected peer IP strictly matches the pinned IP (fail-closed)."""

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: typing.Iterable[SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        validated_ips = resolve_and_validate_hostname(host, port)
        if not validated_ips:
            raise DNSResolutionError(f"No valid IP address available for '{host}'.")

        pinned_ip = validated_ips[0]
        try:
            expected_ip = ipaddress.ip_address(pinned_ip)
        except ValueError as exc:
            raise DNSResolutionError(f"Malformed pinned IP address '{pinned_ip}': {exc}") from exc

        stream = super().connect_tcp(
            host=pinned_ip,
            port=port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

        # Fail-closed post-connect verification
        try:
            raw_sock = getattr(stream, "_sock", None)
            if raw_sock is None or not hasattr(raw_sock, "getpeername"):
                stream.close()
                raise PeerVerificationError(
                    f"Underlying sync socket for '{host}' does not support getpeername. "
                    "Connection rejected (fail-closed)."
                )

            peer_addr = raw_sock.getpeername()
            if not peer_addr or not isinstance(peer_addr, (tuple, list)) or len(peer_addr) < 2:
                stream.close()
                raise PeerVerificationError(
                    f"Failed to inspect peer address for sync socket connection to '{host}'. "
                    "Connection rejected (fail-closed)."
                )

            peer_ip_str = str(peer_addr[0])
            peer_ip = ipaddress.ip_address(peer_ip_str)

            # Strict comparison: Peer IP must exactly match the pinned IP
            if peer_ip != expected_ip:
                stream.close()
                raise PeerVerificationError(
                    f"Peer IP mismatch: socket connected to {peer_ip}, but pinned IP was {expected_ip}. "
                    "Connection aborted (fail-closed)."
                )

            validate_ip_address(peer_ip)

        except SSRFSecurityError:
            raise
        except Exception as exc:
            stream.close()
            raise PeerVerificationError(
                f"Peer verification failed for '{host}': {exc}. Connection rejected (fail-closed)."
            ) from exc

        return stream


class PinnedAsyncHTTPTransport(httpx.AsyncHTTPTransport):
    """Async HTTP transport enforcing DNS pinning and SSRF defense on all connections."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        # Verify internal API compatibility with installed httpcore / httpx
        if not hasattr(self, "_pool"):
            raise RuntimeError(
                f"Incompatible HTTPX version ({httpx.__version__}): "
                "AsyncHTTPTransport does not have the expected '_pool' attribute."
            )
        if not hasattr(self._pool, "_network_backend"):
            raise RuntimeError(
                f"Incompatible httpcore version ({httpcore.__version__}): "
                "AsyncConnectionPool does not have the expected '_network_backend' attribute."
            )

        self._pool._network_backend = PinnedAsyncNetworkBackend()


class PinnedHTTPTransport(httpx.HTTPTransport):
    """Sync HTTP transport enforcing DNS pinning and SSRF defense on all connections."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        if not hasattr(self, "_pool"):
            raise RuntimeError(
                f"Incompatible HTTPX version ({httpx.__version__}): "
                "HTTPTransport does not have the expected '_pool' attribute."
            )
        if not hasattr(self._pool, "_network_backend"):
            raise RuntimeError(
                f"Incompatible httpcore version ({httpcore.__version__}): "
                "ConnectionPool does not have the expected '_network_backend' attribute."
            )

        self._pool._network_backend = PinnedSyncNetworkBackend()
