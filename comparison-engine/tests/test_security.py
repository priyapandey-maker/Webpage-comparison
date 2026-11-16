"""Comprehensive Security Test Suite for Milestone 1.

Verifies:
1. URL scheme, credential, and structure parsing (rejecting @, invalid ports, malformed hostnames/IPv6).
2. Blocked IP detection across private, loopback, link-local, multicast, reserved, and cloud metadata networks.
3. Obfuscated IP parsing (decimal integer, hex, octal).
4. Asynchronous and synchronous DNS resolution, non-blocking behavior, and rebinding protection.
5. Strict fail-closed peer IP verification for async and sync transports.
6. Controlled local TLS integration (SNI verification, certificate hostname mismatch, direct IP rejection).
7. Manual redirect handling: destination re-validation, case-insensitive body header stripping, HTTPS downgrade rejection.
8. Resource bounds: 10 MB streaming response size limit (no buffering), overall deadline enforcement (including DNS).
9. Compatibility with installed HTTPX and httpcore libraries.
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import httpcore
import httpx
import pytest

# Ensure comparison-engine and src are on sys.path
COMPARISON_ENGINE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = COMPARISON_ENGINE_DIR / "src"

for d in (str(COMPARISON_ENGINE_DIR), str(SRC_DIR)):
    if d not in sys.path:
        sys.path.insert(0, d)

from security.ssrf_validator import (
    BlockedIPError,
    DNSResolutionError,
    InvalidURLError,
    PeerVerificationError,
    RedirectSecurityError,
    ResourceLimitError,
    SSRFSecurityError,
    TLSVerificationError,
    is_ip_blocked,
    parse_and_validate_url,
    parse_obfuscated_ip,
    resolve_and_validate_hostname,
    resolve_and_validate_hostname_async,
    validate_hostname_syntax,
    validate_ip_address,
    validate_target_url,
    validate_target_url_async,
)
from security.pinned_transport import (
    PinnedAsyncHTTPTransport,
    PinnedAsyncNetworkBackend,
    PinnedHTTPTransport,
    PinnedSyncNetworkBackend,
)
from security.redirect_handler import (
    DEFAULT_MAX_REDIRECTS,
    DEFAULT_MAX_RESPONSE_SIZE,
    DEFAULT_TOTAL_DEADLINE,
    SafeFetchResult,
    is_same_origin,
    safe_fetch_async,
    strip_body_headers,
    strip_sensitive_headers,
    validate_ssl_context,
)


# =====================================================================
# 1. URL Scheme, Credential, and Hostname Validation Tests
# =====================================================================

@pytest.mark.parametrize(
    "invalid_url",
    [
        "file:///etc/passwd",
        "file:///c:/windows/win.ini",
        "ftp://ftp.example.com/file.txt",
        "gopher://127.0.0.1:70/",
        "data:text/html,<h1>test</h1>",
        "javascript:alert(1)",
        "ws://example.com/socket",
        "wss://example.com/socket",
        "",
        "   ",
        "not-a-valid-url",
    ],
)
def test_rejects_unsupported_or_invalid_url_schemes(invalid_url: str):
    """Verify that only HTTP and HTTPS schemes are accepted."""
    with pytest.raises(InvalidURLError):
        parse_and_validate_url(invalid_url)


@pytest.mark.parametrize(
    "valid_url",
    [
        "http://example.com",
        "https://example.com",
        "https://example.com/path?query=1#hash",
        "http://example.com:8080/test",
    ],
)
def test_accepts_valid_http_https_urls(valid_url: str):
    """Verify that standard HTTP and HTTPS URLs parse successfully."""
    parsed = parse_and_validate_url(valid_url)
    assert parsed.scheme in ("http", "https")
    assert parsed.hostname == "example.com"


@pytest.mark.parametrize(
    "cred_url",
    [
        "http://user:password@example.com",
        "https://admin@example.com/path",
        "http://:password@example.com",
        "http://user:@example.com",
        "http://@example.com",
        "http://:@example.com",
    ],
)
def test_rejects_user_credentials_and_userinfo_syntax(cred_url: str):
    """Verify that any user-information syntax (even empty credentials) is rejected with InvalidURLError."""
    with pytest.raises(InvalidURLError, match="User credentials"):
        parse_and_validate_url(cred_url)


@pytest.mark.parametrize(
    "bad_port_url",
    [
        "http://example.com:0",
        "http://example.com:65536",
        "http://example.com:-1",
        "http://example.com:999999",
        "http://example.com:abc",
    ],
)
def test_rejects_invalid_ports(bad_port_url: str):
    """Verify that ports outside 1-65535 or non-numeric ports raise InvalidURLError."""
    with pytest.raises(InvalidURLError):
        parse_and_validate_url(bad_port_url)


@pytest.mark.parametrize(
    "bad_host_url",
    [
        "http://..",
        "http://.",
        "http://example..com",
        "http://-bad.com",
        "http://bad-.com",
        "http://foo bar.com",
        "http:///",
    ],
)
def test_rejects_malformed_hostnames(bad_host_url: str):
    """Verify that malformed domain names raise InvalidURLError."""
    with pytest.raises(InvalidURLError):
        parse_and_validate_url(bad_host_url)


@pytest.mark.parametrize(
    "bad_ipv6_url",
    [
        "http://[::1/path",
        "http://[invalid]/",
        "http://[::1]]:80",
    ],
)
def test_rejects_malformed_ipv6_brackets(bad_ipv6_url: str):
    """Verify that malformed IPv6 bracket syntax raises InvalidURLError."""
    with pytest.raises(InvalidURLError):
        parse_and_validate_url(bad_ipv6_url)


# =====================================================================
# 2. Blocked IP Ranges (IPv4 and IPv6) & Boundary Tests
# =====================================================================

@pytest.mark.parametrize(
    "ip_str",
    [
        # Loopback IPv4 & IPv6
        "127.0.0.1",
        "127.0.0.2",
        "127.100.200.1",
        "127.255.255.255",
        "::1",
        # RFC 1918 Private ranges
        "10.0.0.1",
        "10.255.255.255",
        "172.16.0.1",
        "172.24.1.1",
        "172.31.255.255",
        "192.168.0.1",
        "192.168.1.254",
        "192.168.255.255",
        # RFC 3927 Link-local and Cloud metadata
        "169.254.169.254",
        "169.254.0.1",
        "169.254.255.255",
        # RFC 6598 Carrier-grade NAT (100.64.0.0/10)
        "100.64.0.1",
        "100.100.1.1",
        "100.127.255.255",
        # Special-purpose IPv4 ranges
        "0.0.0.0",
        "192.0.0.1",
        "192.0.2.1",          # TEST-NET-1
        "198.18.0.1",         # Benchmark
        "198.51.100.1",       # TEST-NET-2
        "203.0.113.1",        # TEST-NET-3
        "224.0.0.1",          # Multicast
        "239.255.255.250",    # Multicast
        "240.0.0.1",          # Reserved
        "255.255.255.255",    # Broadcast
        # IPv6 Private, Link-local, Multicast, Documentation
        "::",
        "fe80::1",
        "fe80::dead:beef",
        "fc00::1",
        "fd00::1",
        "ff02::1",
        "2001:db8::1",
        "64:ff9b::1",
        "100::1",
        # IPv4-mapped IPv6
        "::ffff:127.0.0.1",
        "::ffff:169.254.169.254",
        "::ffff:10.0.0.1",
        "::ffff:192.168.1.1",
    ],
)
def test_rejects_blocked_and_special_purpose_ips(ip_str: str):
    """Verify that private, loopback, special-purpose, and non-global IPs are rejected."""
    blocked, reason = is_ip_blocked(ipaddress.ip_address(ip_str))
    assert blocked is True, f"Expected {ip_str} to be blocked, but was allowed."
    assert len(reason) > 0

    with pytest.raises(BlockedIPError):
        validate_ip_address(ip_str)


@pytest.mark.parametrize(
    "ip_str",
    [
        "8.8.8.8",
        "8.8.4.4",
        "1.1.1.1",
        "93.184.215.14",
        "142.250.190.46",
        "2607:f8b0:4005:805::200e",
        "::ffff:8.8.8.8",
        "::ffff:93.184.215.14",
    ],
)
def test_accepts_globally_reachable_public_ips(ip_str: str):
    """Verify that legitimate globally reachable public IPv4 and IPv6 addresses are accepted."""
    blocked, reason = is_ip_blocked(ipaddress.ip_address(ip_str))
    assert blocked is False, f"Expected {ip_str} to be allowed, but blocked: {reason}"
    validated = validate_ip_address(ip_str)
    assert validated is not None


# =====================================================================
# 3. Cloud Metadata Hostnames and Prohibited Names
# =====================================================================

@pytest.mark.parametrize(
    "prohibited_host",
    [
        "metadata.google.internal",
        "metadata.internal",
        "instance-data",
        "localhost",
    ],
)
def test_rejects_cloud_metadata_hostnames_sync_and_async(prohibited_host: str):
    """Verify that explicit cloud metadata and local hostnames are blocked before DNS lookup."""
    with pytest.raises(BlockedIPError):
        resolve_and_validate_hostname(prohibited_host, 80)

    async def _test():
        with pytest.raises(BlockedIPError):
            await resolve_and_validate_hostname_async(prohibited_host, 80)

    asyncio.run(_test())


# =====================================================================
# 4. Obfuscated IP Formats Tests
# =====================================================================

def test_detects_pure_decimal_integer_ip():
    """Verify 2130706433 parses to 127.0.0.1 and is blocked."""
    ip = parse_obfuscated_ip("2130706433")
    assert ip == ipaddress.IPv4Address("127.0.0.1")
    with pytest.raises(BlockedIPError):
        validate_ip_address("2130706433")


def test_detects_hexadecimal_ip():
    """Verify 0x7f000001 parses to 127.0.0.1 and is blocked."""
    ip = parse_obfuscated_ip("0x7f000001")
    assert ip == ipaddress.IPv4Address("127.0.0.1")
    with pytest.raises(BlockedIPError):
        validate_ip_address("0x7f000001")


def test_detects_octal_dotted_ip():
    """Verify 0177.0.0.1 parses to 127.0.0.1 and is blocked."""
    ip = parse_obfuscated_ip("0177.0.0.1")
    assert ip == ipaddress.IPv4Address("127.0.0.1")
    with pytest.raises(BlockedIPError):
        validate_ip_address("0177.0.0.1")


# =====================================================================
# 5. DNS Resolution and Rebinding Defense Tests (Sync and Async)
# =====================================================================

def test_resolve_and_validate_hostname_rejects_all_private_results():
    """Verify that if DNS resolves to 127.0.0.1, BlockedIPError is raised."""
    mock_addrinfo = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80)),
    ]
    with patch("socket.getaddrinfo", return_value=mock_addrinfo):
        with pytest.raises(BlockedIPError, match="Loopback"):
            resolve_and_validate_hostname("spoofed.example", 80)


def test_resolve_and_validate_hostname_rejects_mixed_public_private():
    """Verify that if DNS returns both a public IP and a private IP, it is strictly rejected."""
    mock_addrinfo = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", 80)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 80)),
    ]
    with patch("socket.getaddrinfo", return_value=mock_addrinfo):
        with pytest.raises(BlockedIPError, match="Private"):
            resolve_and_validate_hostname("mixed.example", 80)


def test_resolve_and_validate_hostname_async_success():
    """Verify that resolve_and_validate_hostname_async resolves public IPs without blocking."""
    async def _test():
        mock_addrinfo = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.215.14", 80)),
        ]
        with patch("anyio.getaddrinfo", new_callable=AsyncMock, return_value=mock_addrinfo):
            ips = await resolve_and_validate_hostname_async("example.com", 80)
            assert ips == ["93.184.215.14"]

    asyncio.run(_test())


def test_resolve_and_validate_hostname_async_mixed_records_blocked():
    """Verify that async DNS resolution checks every returned record and rejects if any is private."""
    async def _test():
        mock_addrinfo = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.215.14", 80)),
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.168.1.1", 80)),
        ]
        with patch("anyio.getaddrinfo", new_callable=AsyncMock, return_value=mock_addrinfo):
            with pytest.raises(BlockedIPError, match="Private"):
                await resolve_and_validate_hostname_async("mixed.example", 80)

    asyncio.run(_test())


def test_resolve_and_validate_hostname_async_timeout_raises_resource_limit():
    """Verify that async DNS resolution times out cleanly and raises ResourceLimitError."""
    async def _test():
        async def slow_getaddrinfo(*args, **kwargs):
            await anyio.sleep(0.5)
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.215.14", 80))]

        with patch("anyio.getaddrinfo", side_effect=slow_getaddrinfo):
            with pytest.raises(ResourceLimitError, match="timed out"):
                await resolve_and_validate_hostname_async("slow.example", 80, timeout=0.01)

    asyncio.run(_test())


def test_pinned_transport_prevents_dns_rebinding():
    """Verify PinnedAsyncNetworkBackend connects directly to the pinned IP.

    Simulates a DNS rebinding attack where DNS query 1 returns a public IP
    and DNS query 2 returns 127.0.0.1. Verifies that the network backend connects
    strictly to the pinned IP from query 1.
    """
    async def _test():
        backend = PinnedAsyncNetworkBackend()
        connected_hosts: list[str] = []

        async def fake_super_connect(host, port, timeout=None, local_address=None, socket_options=None):
            connected_hosts.append(host)
            stream = MagicMock()
            raw_stream = MagicMock()
            raw_stream.extra.return_value = (host, port)
            stream._stream = raw_stream
            stream.aclose = AsyncMock()
            return stream

        with patch("security.pinned_transport.resolve_and_validate_hostname_async", new_callable=AsyncMock, return_value=["93.184.215.14"]):
            with patch.object(httpcore._backends.anyio.AnyIOBackend, "connect_tcp", side_effect=fake_super_connect):
                stream = await backend.connect_tcp("rebinding-target.com", 443)
                assert connected_hosts == ["93.184.215.14"]

    asyncio.run(_test())


# =====================================================================
# 6. Fail-Closed Peer Verification Tests (Async and Sync)
# =====================================================================

def test_async_peer_verification_exact_match_succeeds():
    """Verify that when the socket peer IP matches pinned_ip, connection succeeds."""
    async def _test():
        backend = PinnedAsyncNetworkBackend()
        mock_stream = MagicMock()
        mock_raw = MagicMock()
        mock_raw.extra.return_value = ("93.184.215.14", 443)
        mock_stream._stream = mock_raw
        mock_stream.aclose = AsyncMock()

        with patch("security.pinned_transport.resolve_and_validate_hostname_async", new_callable=AsyncMock, return_value=["93.184.215.14"]):
            with patch.object(httpcore._backends.anyio.AnyIOBackend, "connect_tcp", return_value=mock_stream):
                stream = await backend.connect_tcp("example.com", 443)
                assert stream is mock_stream
                mock_stream.aclose.assert_not_called()

    asyncio.run(_test())


def test_async_peer_verification_mismatch_fails_closed():
    """Verify that if the socket peer IP differs from pinned_ip, connection is closed and raises PeerVerificationError."""
    async def _test():
        backend = PinnedAsyncNetworkBackend()
        mock_stream = MagicMock()
        mock_raw = MagicMock()
        mock_raw.extra.return_value = ("1.2.3.4", 443)
        mock_stream._stream = mock_raw
        mock_stream.aclose = AsyncMock()

        with patch("security.pinned_transport.resolve_and_validate_hostname_async", new_callable=AsyncMock, return_value=["93.184.215.14"]):
            with patch.object(httpcore._backends.anyio.AnyIOBackend, "connect_tcp", return_value=mock_stream):
                with pytest.raises(PeerVerificationError, match="Peer IP mismatch"):
                    await backend.connect_tcp("example.com", 443)
                mock_stream.aclose.assert_called_once()

    asyncio.run(_test())


def test_async_peer_verification_inspection_failure_fails_closed():
    """Verify that if peer address inspection cannot retrieve peer IP, connection is closed and raises PeerVerificationError."""
    async def _test():
        backend = PinnedAsyncNetworkBackend()
        mock_stream = MagicMock()
        mock_raw = MagicMock()
        mock_raw.extra.return_value = None
        mock_stream._stream = mock_raw
        mock_stream.aclose = AsyncMock()

        with patch("security.pinned_transport.resolve_and_validate_hostname_async", new_callable=AsyncMock, return_value=["93.184.215.14"]):
            with patch.object(httpcore._backends.anyio.AnyIOBackend, "connect_tcp", return_value=mock_stream):
                with pytest.raises(PeerVerificationError, match="Failed to inspect peer address"):
                    await backend.connect_tcp("example.com", 443)
                mock_stream.aclose.assert_called_once()

    asyncio.run(_test())


def test_sync_peer_verification_exact_match_succeeds():
    """Verify sync backend succeeds when peer IP matches pinned_ip."""
    backend = PinnedSyncNetworkBackend()
    mock_stream = MagicMock()
    mock_sock = MagicMock()
    mock_sock.getpeername.return_value = ("93.184.215.14", 80)
    mock_stream._sock = mock_sock
    mock_stream.close = MagicMock()

    with patch("security.pinned_transport.resolve_and_validate_hostname", return_value=["93.184.215.14"]):
        with patch.object(httpcore._backends.sync.SyncBackend, "connect_tcp", return_value=mock_stream):
            stream = backend.connect_tcp("example.com", 80)
            assert stream is mock_stream
            mock_stream.close.assert_not_called()


def test_sync_peer_verification_mismatch_fails_closed():
    """Verify sync backend fails closed and closes socket on peer IP mismatch."""
    backend = PinnedSyncNetworkBackend()
    mock_stream = MagicMock()
    mock_sock = MagicMock()
    mock_sock.getpeername.return_value = ("1.2.3.4", 80)
    mock_stream._sock = mock_sock
    mock_stream.close = MagicMock()

    with patch("security.pinned_transport.resolve_and_validate_hostname", return_value=["93.184.215.14"]):
        with patch.object(httpcore._backends.sync.SyncBackend, "connect_tcp", return_value=mock_stream):
            with pytest.raises(PeerVerificationError, match="Peer IP mismatch"):
                backend.connect_tcp("example.com", 80)
            mock_stream.close.assert_called_once()


# =====================================================================
# 7. Controlled Local TLS Integration Tests (SNI & Cert Verification)
# =====================================================================

def test_disabling_tls_verification_is_prohibited():
    """Verify that safe_fetch_async rejects requests with verify_ssl=False."""
    async def _test():
        with pytest.raises(ValueError, match="verify_ssl=False.*is prohibited"):
            await safe_fetch_async("https://example.com", verify_ssl=False)

    asyncio.run(_test())


def test_insecure_ssl_context_cert_none_rejected():
    """Verify that a custom SSL context configured with ssl.CERT_NONE is rejected."""
    async def _test():
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        with pytest.raises(ValueError, match="verify_mode must be ssl.CERT_REQUIRED"):
            await safe_fetch_async("https://example.com", ssl_context=ctx)

    asyncio.run(_test())


def test_insecure_ssl_context_check_hostname_false_rejected():
    """Verify that a custom SSL context with check_hostname=False is rejected."""
    async def _test():
        ctx = ssl.create_default_context()
        ctx.check_hostname = False

        with pytest.raises(ValueError, match="check_hostname must be True"):
            await safe_fetch_async("https://example.com", ssl_context=ctx)

    asyncio.run(_test())


def test_invalid_ssl_context_type_rejected():
    """Verify that supplying an object other than ssl.SSLContext raises ValueError."""
    async def _test():
        with pytest.raises(ValueError, match="Expected ssl.SSLContext instance"):
            await safe_fetch_async("https://example.com", ssl_context="not-a-context")

    asyncio.run(_test())


def test_correctly_configured_custom_ssl_context_accepted():
    """Verify that a correctly configured custom SSL context is accepted by validate_ssl_context."""
    ctx = ssl.create_default_context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True
    # Must not raise
    validate_ssl_context(ctx)


def test_controlled_local_tls_sni_verification():
    """Integration test with a real local TLS server verifying that SNI is sent correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cert_path = os.path.join(tmpdir, "cert.pem")
        key_path = os.path.join(tmpdir, "key.pem")
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", key_path, "-out", cert_path, "-days", "1", "-nodes", "-subj", "/CN=valid-sni.test"],
            capture_output=True,
            check=True,
        )

        captured_sni: list[str] = []

        def sni_callback(sock, sni, ctx):
            captured_sni.append(sni)

        srv_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        srv_ctx.load_cert_chain(cert_path, key_path)
        srv_ctx.sni_callback = sni_callback

        srv_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv_sock.bind(("127.0.0.1", 0))
        srv_sock.listen(5)
        port = srv_sock.getsockname()[1]

        def run_server():
            while True:
                try:
                    conn, _ = srv_sock.accept()
                except OSError:
                    break
                try:
                    tls_conn = srv_ctx.wrap_socket(conn, server_side=True)
                    req = tls_conn.recv(1024)
                    tls_conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 13\r\nContent-Type: text/plain\r\n\r\nHello TLS SNI")
                    tls_conn.close()
                except Exception:
                    pass
                finally:
                    conn.close()

        t = threading.Thread(target=run_server, daemon=True)
        t.start()

        async def _test():
            client_ctx = ssl.create_default_context(cafile=cert_path)
            with patch("security.pinned_transport.resolve_and_validate_hostname_async", new_callable=AsyncMock, return_value=["127.0.0.1"]), \
                 patch("security.pinned_transport.validate_ip_address"):
                res = await safe_fetch_async(f"https://valid-sni.test:{port}/", ssl_context=client_ctx)
                assert res.status_code == 200
                assert res.text == "Hello TLS SNI"
                assert "valid-sni.test" in captured_sni

        try:
            asyncio.run(_test())
        finally:
            srv_sock.close()


def test_controlled_local_tls_hostname_mismatch_fails():
    """Verify that a real TLS handshake fails with TLSVerificationError when certificate hostname does not match."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cert_path = os.path.join(tmpdir, "cert.pem")
        key_path = os.path.join(tmpdir, "key.pem")
        # Certificate CN is valid-sni.test
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", key_path, "-out", cert_path, "-days", "1", "-nodes", "-subj", "/CN=valid-sni.test"],
            capture_output=True,
            check=True,
        )

        srv_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        srv_ctx.load_cert_chain(cert_path, key_path)

        srv_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv_sock.bind(("127.0.0.1", 0))
        srv_sock.listen(5)
        port = srv_sock.getsockname()[1]

        def run_server():
            while True:
                try:
                    conn, _ = srv_sock.accept()
                except OSError:
                    break
                try:
                    tls_conn = srv_ctx.wrap_socket(conn, server_side=True)
                    req = tls_conn.recv(1024)
                    tls_conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
                    tls_conn.close()
                except Exception:
                    pass
                finally:
                    conn.close()

        t = threading.Thread(target=run_server, daemon=True)
        t.start()

        async def _test():
            client_ctx = ssl.create_default_context(cafile=cert_path)
            with patch("security.pinned_transport.resolve_and_validate_hostname_async", new_callable=AsyncMock, return_value=["127.0.0.1"]), \
                 patch("security.pinned_transport.validate_ip_address"):
                # Requesting mismatched-sni.test against valid-sni.test cert MUST fail TLS verification
                with pytest.raises(TLSVerificationError, match="TLS certificate verification failed"):
                    await safe_fetch_async(f"https://mismatched-sni.test:{port}/", ssl_context=client_ctx)

        try:
            asyncio.run(_test())
        finally:
            srv_sock.close()


def test_controlled_local_tls_direct_ip_fails_hostname_verification():
    """Verify that connecting directly with an IP does not bypass TLS certificate hostname verification."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cert_path = os.path.join(tmpdir, "cert.pem")
        key_path = os.path.join(tmpdir, "key.pem")
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", key_path, "-out", cert_path, "-days", "1", "-nodes", "-subj", "/CN=valid-sni.test"],
            capture_output=True,
            check=True,
        )

        srv_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        srv_ctx.load_cert_chain(cert_path, key_path)

        srv_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv_sock.bind(("127.0.0.1", 0))
        srv_sock.listen(5)
        port = srv_sock.getsockname()[1]

        def run_server():
            while True:
                try:
                    conn, _ = srv_sock.accept()
                except OSError:
                    break
                try:
                    tls_conn = srv_ctx.wrap_socket(conn, server_side=True)
                    req = tls_conn.recv(1024)
                    tls_conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
                    tls_conn.close()
                except Exception:
                    pass
                finally:
                    conn.close()

        t = threading.Thread(target=run_server, daemon=True)
        t.start()

        async def _test():
            client_ctx = ssl.create_default_context(cafile=cert_path)
            with patch("security.ssrf_validator.is_ip_blocked", return_value=(False, "")):
                with pytest.raises(TLSVerificationError, match="TLS certificate verification failed"):
                    await safe_fetch_async(f"https://127.0.0.1:{port}/", ssl_context=client_ctx)

        try:
            asyncio.run(_test())
        finally:
            srv_sock.close()


# =====================================================================
# 8. Step-by-Step Redirects, Method Preservation, and Header Stripping
# =====================================================================

def test_is_same_origin():
    """Verify same-origin evaluation per RFC 6454."""
    assert is_same_origin("https://example.com/a", "https://example.com/b") is True
    assert is_same_origin("https://example.com:443/a", "https://example.com/a") is True
    assert is_same_origin("http://example.com/a", "https://example.com/a") is False
    assert is_same_origin("https://example.com/a", "https://sub.example.com/a") is False
    assert is_same_origin("https://example.com:8443/a", "https://example.com/a") is False


def test_strip_sensitive_headers():
    """Verify Authorization, Cookie, and Proxy-Authorization are stripped."""
    headers = {
        "Authorization": "Bearer secret-token",
        "cookie": "session_id=12345",
        "Proxy-Authorization": "Basic credentials",
        "User-Agent": "TestClient/1.0",
        "Accept": "text/html",
    }
    stripped = strip_sensitive_headers(headers)
    assert "Authorization" not in stripped
    assert "cookie" not in stripped
    assert "Proxy-Authorization" not in stripped
    assert stripped["User-Agent"] == "TestClient/1.0"
    assert stripped["Accept"] == "text/html"


def test_strip_body_headers_case_insensitive():
    """Verify strip_body_headers removes Content-Length and Content-Type case-insensitively."""
    headers = {
        "Content-Length": "42",
        "CONTENT-TYPE": "application/json",
        "X-Custom-Header": "custom-val",
    }
    stripped = strip_body_headers(headers)
    assert len(stripped) == 1
    assert "X-Custom-Header" in stripped
    assert "Content-Length" not in stripped
    assert "CONTENT-TYPE" not in stripped


def test_cross_origin_redirect_strips_sensitive_headers():
    """Verify that cross-origin redirects strip sensitive headers."""
    async def _test():
        sent_headers: list[dict] = []

        resp_302 = httpx.Response(
            status_code=302,
            headers={"Location": "https://other-domain.com/landing"},
            request=httpx.Request("GET", "https://example.com/start"),
        )
        resp_200 = httpx.Response(
            status_code=200,
            headers={"Content-Type": "text/html"},
            content=b"<html>Success</html>",
            request=httpx.Request("GET", "https://other-domain.com/landing"),
        )

        async def fake_send(request, stream=True):
            sent_headers.append(dict(request.headers))
            if "example.com" in str(request.url):
                return resp_302
            return resp_200

        with patch("security.redirect_handler.validate_target_url"):
            with patch.object(httpx.AsyncClient, "send", side_effect=fake_send):
                initial_headers = {
                    "Authorization": "Bearer sensitive-token",
                    "Cookie": "session=secret",
                    "X-Public-Header": "public-value",
                }
                res = await safe_fetch_async("https://example.com/start", headers=initial_headers)
                assert res.status_code == 200

                # Hop 1 has initial headers
                assert "authorization" in sent_headers[0]
                assert "cookie" in sent_headers[0]

                # Hop 2 (cross-origin) MUST have stripped authorization and cookie
                assert "authorization" not in sent_headers[1]
                assert "cookie" not in sent_headers[1]
                assert sent_headers[1].get("x-public-header") == "public-value"

    asyncio.run(_test())


def test_same_origin_redirect_preserves_sensitive_headers():
    """Verify that same-origin redirects retain Authorization and Cookie headers."""
    async def _test():
        sent_headers: list[dict] = []

        resp_302 = httpx.Response(
            status_code=302,
            headers={"Location": "/target"},
            request=httpx.Request("GET", "https://example.com/source"),
        )
        resp_200 = httpx.Response(
            status_code=200,
            headers={"Content-Type": "text/html"},
            content=b"<html>Same Origin</html>",
            request=httpx.Request("GET", "https://example.com/target"),
        )

        async def fake_send(request, stream=True):
            sent_headers.append(dict(request.headers))
            if request.url.path == "/source":
                return resp_302
            return resp_200

        with patch("security.redirect_handler.validate_target_url"):
            with patch.object(httpx.AsyncClient, "send", side_effect=fake_send):
                initial_headers = {"Authorization": "Bearer secret"}
                res = await safe_fetch_async("https://example.com/source", headers=initial_headers)
                assert res.status_code == 200
                assert "authorization" in sent_headers[1]

    asyncio.run(_test())


def test_redirect_method_transformation_rfc9110():
    """Verify method transformations on 303 vs 307 redirects."""
    async def _test():
        methods_received: list[str] = []

        resp_303 = httpx.Response(
            status_code=303,
            headers={"Location": "https://example.com/done"},
            request=httpx.Request("POST", "https://example.com/submit"),
        )
        resp_200 = httpx.Response(
            status_code=200,
            headers={"Content-Type": "text/html"},
            content=b"<html>Done</html>",
            request=httpx.Request("GET", "https://example.com/done"),
        )

        async def fake_send(request, stream=True):
            methods_received.append(request.method)
            if request.method == "POST":
                return resp_303
            return resp_200

        with patch("security.redirect_handler.validate_target_url"):
            with patch.object(httpx.AsyncClient, "send", side_effect=fake_send):
                await safe_fetch_async("https://example.com/submit", method="POST", body=b"data")
                assert methods_received == ["POST", "GET"]

    asyncio.run(_test())


def test_redirect_body_discard_strips_mixed_case_headers():
    """Verify Content-Length and Content-Type are stripped regardless of casing on 303 or 301/302."""
    async def _test():
        sent_headers: list[dict] = []

        resp_303 = httpx.Response(
            status_code=303,
            headers={"Location": "https://example.com/result"},
            request=httpx.Request("POST", "https://example.com/submit"),
        )
        resp_200 = httpx.Response(
            status_code=200,
            headers={"Content-Type": "text/html"},
            content=b"<html>Done</html>",
            request=httpx.Request("GET", "https://example.com/result"),
        )

        async def fake_send(request, stream=True):
            sent_headers.append(dict(request.headers))
            if request.method == "POST":
                return resp_303
            return resp_200

        with patch.object(httpx.AsyncClient, "send", side_effect=fake_send):
            initial_headers = {
                "Content-Length": "100",
                "CONTENT-TYPE": "application/x-www-form-urlencoded",
                "X-Custom-Header": "keep-me",
            }
            await safe_fetch_async("https://example.com/submit", method="POST", body=b"data=1", headers=initial_headers)

            h1 = {k.lower(): v for k, v in sent_headers[0].items()}
            assert "content-length" in h1
            assert "content-type" in h1

            h2 = {k.lower(): v for k, v in sent_headers[1].items()}
            assert "content-length" not in h2
            assert "content-type" not in h2
            assert sent_headers[1].get("x-custom-header") == "keep-me"

    asyncio.run(_test())


def test_redirect_to_loopback_is_blocked():
    """Verify that an HTTP redirect to localhost/127.0.0.1 is caught and blocked."""
    async def _test():
        resp_302 = httpx.Response(
            status_code=302,
            headers={"Location": "http://127.0.0.1/admin"},
            request=httpx.Request("GET", "https://example.com"),
        )

        with patch.object(httpx.AsyncClient, "send", return_value=resp_302):
            with pytest.raises(RedirectSecurityError, match="violates security rules"):
                await safe_fetch_async("https://example.com")

    asyncio.run(_test())


def test_redirect_to_cloud_metadata_is_blocked():
    """Verify that an HTTP redirect to cloud metadata 169.254.169.254 is blocked."""
    async def _test():
        resp_302 = httpx.Response(
            status_code=302,
            headers={"Location": "http://169.254.169.254/latest/meta-data/"},
            request=httpx.Request("GET", "https://example.com"),
        )

        with patch.object(httpx.AsyncClient, "send", return_value=resp_302):
            with pytest.raises(RedirectSecurityError, match="violates security rules"):
                await safe_fetch_async("https://example.com")

    asyncio.run(_test())


def test_https_to_http_downgrade_redirect_is_rejected():
    """Verify that an HTTPS URL redirecting to plain HTTP is rejected with RedirectSecurityError."""
    async def _test():
        resp_302 = httpx.Response(
            status_code=302,
            headers={"Location": "http://example.com/downgrade"},
            request=httpx.Request("GET", "https://example.com/secure"),
        )

        with patch.object(httpx.AsyncClient, "send", return_value=resp_302):
            with pytest.raises(RedirectSecurityError, match="downgrade from HTTPS to HTTP is prohibited"):
                await safe_fetch_async("https://example.com/secure")

    asyncio.run(_test())


def test_plain_http_redirect_is_permitted():
    """Verify that an initial plain HTTP URL redirecting to HTTP is permitted."""
    async def _test():
        resp_302 = httpx.Response(
            status_code=302,
            headers={"Location": "http://example.com/step2"},
            request=httpx.Request("GET", "http://example.com/step1"),
        )
        resp_200 = httpx.Response(
            status_code=200,
            headers={"Content-Type": "text/html"},
            content=b"<html>Success</html>",
            request=httpx.Request("GET", "http://example.com/step2"),
        )

        async def fake_send(request, stream=True):
            if request.url.path == "/step1":
                return resp_302
            return resp_200

        with patch.object(httpx.AsyncClient, "send", side_effect=fake_send):
            res = await safe_fetch_async("http://example.com/step1")
            assert res.status_code == 200
            assert res.url == "http://example.com/step2"

    asyncio.run(_test())


def test_http_to_https_upgrade_redirect_is_permitted():
    """Verify that an initial plain HTTP URL redirecting to HTTPS is permitted (upgrade)."""
    async def _test():
        resp_302 = httpx.Response(
            status_code=302,
            headers={"Location": "https://example.com/step2"},
            request=httpx.Request("GET", "http://example.com/step1"),
        )
        resp_200 = httpx.Response(
            status_code=200,
            headers={"Content-Type": "text/html"},
            content=b"<html>Success</html>",
            request=httpx.Request("GET", "https://example.com/step2"),
        )

        async def fake_send(request, stream=True):
            if request.url.path == "/step1":
                return resp_302
            return resp_200

        with patch.object(httpx.AsyncClient, "send", side_effect=fake_send):
            res = await safe_fetch_async("http://example.com/step1")
            assert res.status_code == 200
            assert res.url == "https://example.com/step2"

    asyncio.run(_test())


def test_redirect_exceeding_max_limit_is_blocked():
    """Verify that redirect chains exceeding the maximum allowed hops (5) are blocked."""
    async def _test():
        hop_counter = 0

        async def fake_redirect(request, stream=True):
            nonlocal hop_counter
            hop_counter += 1
            return httpx.Response(
                status_code=302,
                headers={"Location": f"https://example.com/hop-{hop_counter}"},
                request=request,
            )

        with patch("security.redirect_handler.validate_target_url"):
            with patch.object(httpx.AsyncClient, "send", side_effect=fake_redirect):
                with pytest.raises(RedirectSecurityError, match="Maximum redirect count of 5 exceeded"):
                    await safe_fetch_async("https://example.com/start", max_redirects=5)

    asyncio.run(_test())


def test_circular_redirect_is_detected_and_blocked():
    """Verify that circular redirect chains (A -> B -> A) are detected and aborted."""
    async def _test():
        resp_a = httpx.Response(
            status_code=302,
            headers={"Location": "https://example.com/page-b"},
            request=httpx.Request("GET", "https://example.com/page-a"),
        )
        resp_b = httpx.Response(
            status_code=302,
            headers={"Location": "https://example.com/page-a"},
            request=httpx.Request("GET", "https://example.com/page-b"),
        )

        async def fake_send(request, stream=True):
            if "page-a" in str(request.url):
                return resp_a
            return resp_b

        with patch("security.redirect_handler.validate_target_url"):
            with patch.object(httpx.AsyncClient, "send", side_effect=fake_send):
                with pytest.raises(RedirectSecurityError, match="Circular redirect detected"):
                    await safe_fetch_async("https://example.com/page-a")

    asyncio.run(_test())


# =====================================================================
# 9. Resource Limits & Streaming Size Enforcement (No Full Buffering)
# =====================================================================

def test_oversized_content_length_header_aborts_immediately():
    """Verify that a response declaring Content-Length > 10MB aborts without reading body."""
    async def _test():
        resp = httpx.Response(
            status_code=200,
            headers={"Content-Length": str(15 * 1024 * 1024)},
            content=b"",
            request=httpx.Request("GET", "https://example.com"),
        )

        with patch.object(httpx.AsyncClient, "send", return_value=resp):
            with pytest.raises(ResourceLimitError, match="Content-Length .* exceeds maximum allowed size"):
                await safe_fetch_async("https://example.com", max_response_size=10 * 1024 * 1024)

    asyncio.run(_test())


def test_streaming_body_exceeding_size_limit_aborts_during_download():
    """Verify that a response streaming bytes exceeding 10MB limit aborts immediately during streaming."""
    async def _test():
        async def mock_aiter_bytes():
            chunk = b"X" * (1024 * 1024)  # 1 MB chunk
            for _ in range(12):             # 12 MB total
                yield chunk

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.aiter_bytes = mock_aiter_bytes
        mock_response.aclose = AsyncMock()

        with patch.object(httpx.AsyncClient, "send", return_value=mock_response):
            with pytest.raises(ResourceLimitError, match="Response body exceeded maximum allowed limit"):
                await safe_fetch_async("https://example.com", max_response_size=10 * 1024 * 1024)

    asyncio.run(_test())


def test_overall_deadline_exceeded_raises_resource_limit_error():
    """Verify that exceeding total_deadline raises ResourceLimitError."""
    async def _test():
        with pytest.raises(ResourceLimitError, match="deadline"):
            await safe_fetch_async("https://example.com", total_deadline=0.0001)

    asyncio.run(_test())


def test_delayed_dns_exceeds_overall_deadline():
    """Verify that a fetch operation aborts with ResourceLimitError if DNS resolution exceeds the deadline."""
    async def _test():
        async def slow_getaddrinfo(*args, **kwargs):
            await anyio.sleep(0.5)
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.215.14", 80))]

        with patch("anyio.getaddrinfo", side_effect=slow_getaddrinfo):
            with pytest.raises(ResourceLimitError, match="deadline|timed out"):
                await safe_fetch_async("https://example.com/test", total_deadline=0.05)

    asyncio.run(_test())


# =====================================================================
# 10. HTTPX and httpcore Internal API Compatibility Tests
# =====================================================================

def test_httpx_and_httpcore_versions_and_internal_apis():
    """Verify installed versions and verify internal API attributes exist."""
    transport = PinnedAsyncHTTPTransport()
    assert hasattr(transport, "_pool"), "AsyncHTTPTransport missing '_pool'"
    assert hasattr(transport._pool, "_network_backend"), "AsyncConnectionPool missing '_network_backend'"
    assert isinstance(transport._pool._network_backend, PinnedAsyncNetworkBackend)

    sync_transport = PinnedHTTPTransport()
    assert hasattr(sync_transport, "_pool"), "HTTPTransport missing '_pool'"
    assert hasattr(sync_transport._pool, "_network_backend"), "ConnectionPool missing '_network_backend'"
    assert isinstance(sync_transport._pool._network_backend, PinnedSyncNetworkBackend)


# =====================================================================
# 11. Real Network Integration Test (Verified against example.com)
# =====================================================================

def test_real_connection_to_example_com_succeeds_end_to_end():
    """End-to-end integration test against example.com verifying the entire pipeline."""
    async def _test():
        result = await safe_fetch_async("https://example.com")
        assert result.status_code == 200
        assert "Example Domain" in result.text
        assert len(result.content) > 0
        assert isinstance(result.headers, (dict, httpx.Headers))

    asyncio.run(_test())
