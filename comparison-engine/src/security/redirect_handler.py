"""Safe HTTP Client and Manual Redirect Handler.

Coordinates DNS-pinned transports, step-by-step destination re-validation on every redirect hop,
sensitive header stripping on cross-origin redirects, streaming body consumption without buffering,
and strict resource constraints (10MB body size limit, strict overall deadline).
"""

from __future__ import annotations

import ssl
import time
import urllib.parse
from typing import Any, Mapping

import httpx

from .pinned_transport import PinnedAsyncHTTPTransport
from .ssrf_validator import (
    DNSResolutionError,
    InvalidURLError,
    RedirectSecurityError,
    ResourceLimitError,
    SSRFSecurityError,
    TLSVerificationError,
    parse_and_validate_url,
    validate_target_url,
)

DEFAULT_MAX_REDIRECTS = 5
DEFAULT_MAX_RESPONSE_SIZE = 10 * 1024 * 1024  # 10 MB
DEFAULT_TOTAL_DEADLINE = 20.0                 # 20.0 seconds total deadline
REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}

# Headers that must be stripped on cross-origin redirects (RFC 7230 / RFC 9110)
SENSITIVE_HEADERS = {"authorization", "cookie", "proxy-authorization"}

# Headers that must be stripped case-insensitively when redirect transformations discard the body
BODY_RELATED_HEADERS = {"content-length", "content-type"}


def is_same_origin(url1: str, url2: str) -> bool:
    """Determine whether two URLs share the exact same scheme, host, and port."""
    p1 = urllib.parse.urlsplit(url1)
    p2 = urllib.parse.urlsplit(url2)

    scheme1 = (p1.scheme or "").lower()
    scheme2 = (p2.scheme or "").lower()
    if scheme1 != scheme2:
        return False

    host1 = (p1.hostname or "").lower()
    host2 = (p2.hostname or "").lower()
    if host1 != host2:
        return False

    port1 = p1.port or (443 if scheme1 == "https" else 80)
    port2 = p2.port or (443 if scheme2 == "https" else 80)
    return port1 == port2


def strip_sensitive_headers(headers: dict[str, str]) -> dict[str, str]:
    """Return a new headers dict with Authorization, Cookie, and Proxy-Authorization removed."""
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in SENSITIVE_HEADERS
    }


def strip_body_headers(headers: dict[str, str]) -> dict[str, str]:
    """Return a new headers dict with Content-Length and Content-Type removed case-insensitively."""
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in BODY_RELATED_HEADERS
    }


def validate_ssl_context(ssl_context: Any) -> None:
    """Validate that a custom SSL context enforces strict certificate and hostname verification.

    Prevents callers from supplying insecure custom contexts that bypass verification
    (e.g. ssl.CERT_NONE, check_hostname=False).
    """
    if ssl_context is None:
        return

    if not isinstance(ssl_context, ssl.SSLContext):
        raise ValueError(
            f"Expected ssl.SSLContext instance, got {type(ssl_context).__name__}."
        )

    if ssl_context.verify_mode != ssl.CERT_REQUIRED:
        raise ValueError(
            f"Insecure SSL context: verify_mode must be ssl.CERT_REQUIRED (got {ssl_context.verify_mode})."
        )

    if not ssl_context.check_hostname:
        raise ValueError(
            "Insecure SSL context: check_hostname must be True to prevent hostname spoofing."
        )


class SafeFetchResult:
    """Encapsulates the result of a safe fetch operation."""

    def __init__(
        self,
        url: str,
        status_code: int,
        headers: Mapping[str, str],
        content: bytes,
        redirect_history: list[str],
    ) -> None:
        self.url = url
        self.status_code = status_code
        self.headers = headers
        self.content = content
        self.redirect_history = redirect_history

    @property
    def text(self) -> str:
        """Decode content using detected charset or fallback to utf-8."""
        content_type = self.headers.get("content-type", "")
        encoding = "utf-8"
        if "charset=" in content_type.lower():
            try:
                encoding = content_type.lower().split("charset=")[-1].split(";")[0].strip()
            except Exception:
                encoding = "utf-8"
        try:
            return self.content.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            return self.content.decode("utf-8", errors="replace")


async def safe_fetch_async(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    max_response_size: int = DEFAULT_MAX_RESPONSE_SIZE,
    total_deadline: float = DEFAULT_TOTAL_DEADLINE,
    verify_ssl: bool = True,
    ssl_context: Any = None,
) -> SafeFetchResult:
    """Fetch a URL asynchronously with full SSRF, DNS pinning, redirect revalidation, and size limits.

    Enforces:
    - Mandatory TLS certificate verification (verify_ssl=False is prohibited).
    - Streaming request pipeline using client.build_request() and client.send(stream=True).
    - Immediate abort if Content-Length or streaming body exceeds max_response_size.
    - Strict overall request deadline covering DNS, TCP connect, redirects, and body streaming.
    - SSRF destination revalidation on every redirect hop.
    - Prohibition of HTTPS to HTTP downgrade redirects.
    - Case-insensitive stripping of Content-Length and Content-Type on body-discarding redirects.
    - Sensitive header stripping on cross-origin redirects.
    - Full DNS resolution and pinning revalidation on every redirect destination.
    """
    if not verify_ssl:
        raise ValueError("Disabling TLS verification (verify_ssl=False) is prohibited in production fetching.")

    validate_ssl_context(ssl_context)

    # Step 1: Pre-validate initial target URL (syntax, scheme, credentials, port, blocked IPs)
    validate_target_url(url, resolve_dns=False)

    current_url = url
    current_method = method.upper()
    current_body = body
    visited_urls: set[str] = {current_url}
    redirect_history: list[str] = []

    req_headers: dict[str, str] = {
        "User-Agent": "WebpageComparison/2.0 (Security-Checked Fetcher)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    if headers:
        req_headers.update(headers)

    deadline = time.monotonic() + total_deadline

    # All connections use the pinned transport with TLS verification enabled
    tls_verify = ssl_context if ssl_context is not None else True
    transport = PinnedAsyncHTTPTransport(verify=tls_verify)

    async with httpx.AsyncClient(
        transport=transport,
        follow_redirects=False,
    ) as client:
        redirect_count = 0

        while True:
            # Check remaining time budget before starting each hop
            remaining_time = deadline - time.monotonic()
            if remaining_time <= 0:
                raise ResourceLimitError(f"Overall request deadline ({total_deadline}s) exceeded.")

            hop_timeout = httpx.Timeout(
                timeout=remaining_time,
                connect=min(5.0, remaining_time),
                read=min(12.0, remaining_time),
            )

            # Build streaming request
            request = client.build_request(
                method=current_method,
                url=current_url,
                headers=req_headers,
                content=current_body if current_method in ("POST", "PUT", "PATCH") else None,
                timeout=hop_timeout,
            )

            # Send request using streaming mode to prevent premature response buffering
            try:
                response = await client.send(request, stream=True)
            except SSRFSecurityError:
                raise
            except httpx.TimeoutException as exc:
                raise ResourceLimitError(f"Request timeout exceeded: {exc}") from exc
            except httpx.ConnectError as exc:
                # Distinguish TLS / SSL failures from generic connection issues
                cause = getattr(exc, "__cause__", None)
                err_str = (str(exc) + " " + str(cause)).lower()
                if (
                    "certificate" in err_str
                    or "ssl" in err_str
                    or "hostname mismatch" in err_str
                    or "verify failed" in err_str
                    or (cause is not None and isinstance(cause, ssl.SSLError))
                ):
                    raise TLSVerificationError(f"TLS certificate verification failed: {exc}") from exc
                raise DNSResolutionError(f"Connection failed: {exc}") from exc
            except Exception as exc:
                raise SSRFSecurityError(f"Request failed: {exc}") from exc

            # Handle redirects
            if response.status_code in REDIRECT_STATUS_CODES:
                redirect_count += 1
                if redirect_count > max_redirects:
                    await response.aclose()
                    raise RedirectSecurityError(
                        f"Maximum redirect count of {max_redirects} exceeded."
                    )

                location = response.headers.get("location")
                if not location:
                    await response.aclose()
                    raise RedirectSecurityError(
                        f"Redirect status {response.status_code} received without Location header."
                    )

                # Resolve relative redirect URL against current URL
                new_url = urllib.parse.urljoin(current_url, location.strip())

                # Re-validate the new destination against all SSRF rules before navigating
                try:
                    validate_target_url(new_url, resolve_dns=False)
                except SSRFSecurityError as exc:
                    await response.aclose()
                    raise RedirectSecurityError(
                        f"Redirect destination '{new_url}' violates security rules: {exc}"
                    ) from exc

                # Prevent HTTPS to plain HTTP downgrade redirects
                current_scheme = urllib.parse.urlsplit(current_url).scheme.lower()
                new_scheme = urllib.parse.urlsplit(new_url).scheme.lower()
                if current_scheme == "https" and new_scheme == "http":
                    await response.aclose()
                    raise RedirectSecurityError(
                        f"Insecure redirect downgrade from HTTPS to HTTP is prohibited: '{current_url}' -> '{new_url}'."
                    )

                # Check for circular redirects
                if new_url in visited_urls:
                    await response.aclose()
                    raise RedirectSecurityError(
                        f"Circular redirect detected: '{new_url}' has already been visited."
                    )

                # Strip sensitive headers if redirect changes origin
                if not is_same_origin(current_url, new_url):
                    req_headers = strip_sensitive_headers(req_headers)

                # Manage HTTP method and body transformation per RFC 9110
                if response.status_code == 303:
                    # 303 See Other always switches to GET and discards body
                    current_method = "GET"
                    current_body = None
                    req_headers = strip_body_headers(req_headers)
                elif response.status_code in (301, 302):
                    # 301/302 conventionally rewrite non-GET/HEAD to GET and discard body
                    if current_method in ("POST", "PUT", "PATCH", "DELETE"):
                        current_method = "GET"
                        current_body = None
                        req_headers = strip_body_headers(req_headers)
                # For 307 and 308, method and body are preserved as-is

                visited_urls.add(new_url)
                redirect_history.append(current_url)
                current_url = new_url
                await response.aclose()
                continue

            # Non-redirect response: Validate Content-Length header before reading body
            content_length_header = response.headers.get("content-length")
            if content_length_header:
                try:
                    content_length = int(content_length_header)
                    if content_length > max_response_size:
                        await response.aclose()
                        raise ResourceLimitError(
                            f"Content-Length ({content_length} bytes) exceeds maximum "
                            f"allowed size of {max_response_size} bytes."
                        )
                except ValueError:
                    pass

            # Stream body in chunks and enforce size limit DURING streaming (no full buffering)
            body_chunks: list[bytes] = []
            total_bytes = 0

            try:
                async for chunk in response.aiter_bytes():
                    # Check overall deadline during streaming
                    if time.monotonic() > deadline:
                        raise ResourceLimitError(
                            f"Overall request deadline ({total_deadline}s) exceeded during body download."
                        )

                    total_bytes += len(chunk)
                    if total_bytes > max_response_size:
                        raise ResourceLimitError(
                            f"Response body exceeded maximum allowed limit of {max_response_size} bytes."
                        )
                    body_chunks.append(chunk)
            finally:
                await response.aclose()

            content = b"".join(body_chunks)

            return SafeFetchResult(
                url=current_url,
                status_code=response.status_code,
                headers=response.headers,
                content=content,
                redirect_history=redirect_history,
            )
