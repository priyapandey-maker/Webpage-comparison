"""Wayback Machine Client & Verification Service for Historical Webpage Comparison.

Handles:
1. CDX Server API snapshot discovery with monthly collapsing and truncation detection.
2. Exact snapshot verification against CDX point queries.
3. Safe raw replay URL construction preserving CDX original URLs.
4. Concurrent fetching using DNS-pinned, TLS-verified transport with host allowlist enforcement.
5. Rejection of fallback timestamp redirects, off-host redirects, and non-HTML payloads.

Independent of api.py to prevent circular imports.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import re
import ssl
import time
from typing import Any, Mapping
import urllib.parse

import anyio
import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, field_validator, model_validator

try:
    from .security.pinned_transport import PinnedAsyncHTTPTransport
    from .security.redirect_handler import (
        DEFAULT_MAX_REDIRECTS,
        DEFAULT_MAX_RESPONSE_SIZE,
        DEFAULT_TOTAL_DEADLINE,
        SafeFetchResult,
        is_same_origin,
        strip_body_headers,
        strip_sensitive_headers,
        validate_ssl_context,
    )
    from .security.ssrf_validator import (
        BlockedIPError,
        DNSResolutionError,
        InvalidURLError,
        RedirectSecurityError,
        ResourceLimitError,
        SSRFSecurityError,
        TLSVerificationError,
        parse_and_validate_url,
        validate_target_url,
    )
    from .html_validator import HTMLValidationError, LiveFetchError, validate_html_response
except ImportError:
    from security.pinned_transport import PinnedAsyncHTTPTransport
    from security.redirect_handler import (
        DEFAULT_MAX_REDIRECTS,
        DEFAULT_MAX_RESPONSE_SIZE,
        DEFAULT_TOTAL_DEADLINE,
        SafeFetchResult,
        is_same_origin,
        strip_body_headers,
        strip_sensitive_headers,
        validate_ssl_context,
    )
    from security.ssrf_validator import (
        BlockedIPError,
        DNSResolutionError,
        InvalidURLError,
        RedirectSecurityError,
        ResourceLimitError,
        SSRFSecurityError,
        TLSVerificationError,
        parse_and_validate_url,
        validate_target_url,
    )
    from html_validator import HTMLValidationError, LiveFetchError, validate_html_response

logger = logging.getLogger(__name__)

# Base endpoints
CDX_BASE_URL = "https://web.archive.org/cdx/search/cdx"
WAYBACK_REPLAY_BASE = "https://web.archive.org/web"

# Hostnames authorized for CDX queries and replay fetches
ALLOWED_WAYBACK_HOSTS = {
    "web.archive.org",
}

# Standard HTTP redirect status codes (RFC 9110)
REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}

# Standard HTML / XHTML MIME types
HTML_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
}

# 14-digit Wayback timestamp format (YYYYMMDDhhmmss)
TIMESTAMP_REGEX = re.compile(r"^\d{14}$")
# Anchored to the start of the URL path to prevent matching deceptive query/fragment timestamps
PATH_REPLAY_TIMESTAMP_REGEX = re.compile(r"^/web/([0-9]{14})id_/")


# ============================================================================
# Exception Hierarchy
# ============================================================================

class WaybackError(Exception):
    """Base exception for all Wayback operations."""


class InvalidWaybackURLError(WaybackError):
    """Raised when the target URL or capture original URL is invalid, malformed, or violates security policies."""

    def __init__(self, message: str, url: str | None = None) -> None:
        super().__init__(message)
        self.url = url


class SnapshotNotFoundError(WaybackError):
    """Raised when no archive snapshot is found for the given URL or timestamp."""

    def __init__(self, message: str, timestamp: str | None = None, url: str | None = None) -> None:
        super().__init__(message)
        self.timestamp = timestamp
        self.url = url


class WaybackCDXError(WaybackError):
    """Raised when the CDX API returns an invalid, malformed, or unparseable response."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.cause = cause


class WaybackVerificationError(WaybackError):
    """Raised when a selected snapshot fails verification (non-200, non-HTML, or mismatched URL)."""

    def __init__(
        self,
        message: str,
        timestamp: str | None = None,
        status_code: int | None = None,
        mimetype: str | None = None,
    ) -> None:
        super().__init__(message)
        self.timestamp = timestamp
        self.status_code = status_code
        self.mimetype = mimetype


class FallbackRedirectError(WaybackError):
    """Raised when Wayback replays a fallback/nearest capture instead of the exact requested timestamp."""

    def __init__(
        self,
        message: str,
        requested_timestamp: str | None = None,
        resolved_url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.requested_timestamp = requested_timestamp
        self.resolved_url = resolved_url


class OffHostRedirectError(WaybackError):
    """Raised when a Wayback request or redirect targets an unauthorized host."""

    def __init__(self, message: str, destination_url: str | None = None) -> None:
        super().__init__(message)
        self.destination_url = destination_url


class WaybackFetchError(WaybackError):
    """Raised when network, timeout, or HTTP error occurs during a Wayback request."""

    def __init__(
        self,
        message: str,
        failed_url: str | None = None,
        status_code: int | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.failed_url = failed_url
        self.status_code = status_code
        self.cause = cause


class WaybackContentError(WaybackError):
    """Raised when an archived HTML response is empty, malformed, or non-HTML."""

    def __init__(self, message: str, failed_url: str | None = None) -> None:
        super().__init__(message)
        self.failed_url = failed_url


# ============================================================================
# Helpers & Validators
# ============================================================================

def validate_timestamp_format(timestamp: str) -> None:
    """Validate that timestamp is exactly 14 digits and represents a valid calendar datetime."""
    if not isinstance(timestamp, str) or not TIMESTAMP_REGEX.match(timestamp):
        raise ValueError(f"Invalid timestamp '{timestamp}': must be exactly 14 digits (YYYYMMDDhhmmss).")
    year = int(timestamp[0:4])
    month = int(timestamp[4:6])
    day = int(timestamp[6:8])
    hour = int(timestamp[8:10])
    minute = int(timestamp[10:12])
    second = int(timestamp[12:14])
    if not (1996 <= year <= 2099):
        raise ValueError(f"Timestamp year {year} is out of valid range (1996-2099).")
    try:
        datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError(f"Timestamp '{timestamp}' is not a valid date/time: {exc}") from exc


def format_timestamp(timestamp: str) -> tuple[str, str]:
    """Convert 14-digit timestamp to (ISO-8601 UTC string, human-readable display string)."""
    year = int(timestamp[0:4])
    month = int(timestamp[4:6])
    day = int(timestamp[6:8])
    hour = int(timestamp[8:10])
    minute = int(timestamp[10:12])
    second = int(timestamp[12:14])
    dt = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
    iso_str = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    display_str = dt.strftime("%b %d, %Y %H:%M UTC")
    return iso_str, display_str


def is_allowed_wayback_host(hostname: str | None) -> bool:
    """Check if hostname belongs strictly to the authorized Internet Archive host allowlist.

    Enforces case-insensitivity, canonicalizes trailing DNS dots, and rejects
    wildcards or arbitrary subdomains (e.g. attacker.archive.org).
    """
    if not hostname or not isinstance(hostname, str):
        return False
    h = hostname.lower().rstrip(".")
    if not h:
        return False
    return h in ALLOWED_WAYBACK_HOSTS


def validate_wayback_destination_host(url: str) -> None:
    """Ensure target URL scheme, host, and port strictly adhere to Wayback security policies.

    Enforces:
    - Scheme must be HTTPS.
    - Host must be strictly 'web.archive.org' (case-insensitive, trailing dot canonicalized).
    - Port must be standard HTTPS port 443 or omitted (default).
    - Rejects unexpected ports, malformed ports, unsupported schemes, and missing hostnames.
    """
    try:
        parsed = urllib.parse.urlsplit(url)
        scheme = (parsed.scheme or "").lower()
        port = parsed.port
    except Exception as exc:
        raise OffHostRedirectError(
            f"Malformed destination URL '{url}': {exc}",
            destination_url=url,
        ) from exc

    if scheme != "https":
        raise OffHostRedirectError(
            f"Unsupported scheme '{scheme}' for Wayback destination '{url}'. Only HTTPS is permitted.",
            destination_url=url,
        )

    hostname = parsed.hostname
    if not hostname or not is_allowed_wayback_host(hostname):
        raise OffHostRedirectError(
            f"Wayback request/redirect to unauthorized host '{hostname}' is rejected.",
            destination_url=url,
        )

    if port is not None and port != 443:
        raise OffHostRedirectError(
            f"Unexpected port {port} for Wayback destination '{url}'. Only standard HTTPS port 443 is permitted.",
            destination_url=url,
        )


def validate_capture_original_url(original_url: str) -> None:
    """Validate the CDX 'original' URL for valid syntax, http/https scheme, and no credentials."""
    if not isinstance(original_url, str) or not original_url.strip():
        raise InvalidWaybackURLError("Capture original URL is empty.")
    cleaned = original_url.strip()
    if any(c in cleaned for c in "\r\n\t\x00"):
        raise InvalidWaybackURLError("Capture original URL contains control characters.", url=cleaned)
    try:
        parsed = urllib.parse.urlsplit(cleaned)
        port = parsed.port
    except ValueError as exc:
        raise InvalidWaybackURLError(f"Capture original URL has invalid syntax or port: {exc}", url=cleaned) from exc
    if parsed.scheme.lower() not in ("http", "https"):
        raise InvalidWaybackURLError(
            f"Capture original URL has unsupported scheme '{parsed.scheme}'. Only http and https allowed.",
            url=cleaned,
        )
    if not parsed.hostname:
        raise InvalidWaybackURLError("Capture original URL is missing a hostname.", url=cleaned)
    if parsed.username or parsed.password:
        raise InvalidWaybackURLError("Capture original URL contains prohibited user credentials.", url=cleaned)
    if port is not None and not (1 <= port <= 65535):
        raise InvalidWaybackURLError(f"Capture original URL port {port} is out of range.", url=cleaned)


def extract_replay_timestamp(url: str) -> str | None:
    """Extract 14-digit timestamp from the beginning of the URL path only.

    Strictly anchors to the start of urlsplit(url).path (^/web/{timestamp}id_/)
    and ignores query strings, fragments, and unrelated path segments.
    """
    try:
        parsed = urllib.parse.urlsplit(url)
    except Exception:
        return None
    match = PATH_REPLAY_TIMESTAMP_REGEX.match(parsed.path)
    return match.group(1) if match else None


def build_wayback_replay_url(timestamp: str, original_url: str) -> str:
    """Construct a raw replay URL using the verified timestamp and CDX original URL."""
    validate_timestamp_format(timestamp)
    validate_capture_original_url(original_url)
    return f"{WAYBACK_REPLAY_BASE}/{timestamp}id_/{original_url}"


# ============================================================================
# Pydantic Request & Response Models
# ============================================================================

class WaybackSnapshot(BaseModel):
    """Structured metadata for a single historical Wayback snapshot."""

    timestamp: str
    datetime: str
    display_date: str
    original_url: str
    status_code: int = 200
    mimetype: str = "text/html"


class WaybackSnapshotsRequest(BaseModel):
    """Request payload for discovering historical snapshots of a URL."""

    url: str
    limit: int = 50
    from_year: int | None = None
    to_year: int | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("URL must be a non-empty string.")
        cleaned = v.strip()
        try:
            validate_target_url(cleaned, resolve_dns=False)
        except SSRFSecurityError as exc:
            raise ValueError(str(exc)) from exc
        return cleaned

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, v: int) -> int:
        if v < 1 or v > 100:
            raise ValueError("Limit must be between 1 and 100.")
        return v

    @field_validator("from_year", "to_year")
    @classmethod
    def validate_year(cls, v: int | None) -> int | None:
        if v is not None and not (1996 <= v <= 2099):
            raise ValueError(f"Year {v} is out of valid range (1996-2099).")
        return v

    @model_validator(mode="after")
    def validate_year_order(self) -> WaybackSnapshotsRequest:
        if self.from_year is not None and self.to_year is not None:
            if self.from_year > self.to_year:
                raise ValueError(f"from_year ({self.from_year}) must be <= to_year ({self.to_year}).")
        return self


class WaybackSnapshotsResponse(BaseModel):
    """Response payload containing discovered historical snapshots."""

    url: str
    total_returned: int
    is_limited: bool
    collapse: str = "monthly"
    snapshots: list[WaybackSnapshot]


class WaybackCompareRequest(BaseModel):
    """Request payload for comparing two historical Wayback captures of a URL."""

    url: str
    timestamp1: str
    timestamp2: str

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("URL must be a non-empty string.")
        cleaned = v.strip()
        try:
            validate_target_url(cleaned, resolve_dns=False)
        except SSRFSecurityError as exc:
            raise ValueError(str(exc)) from exc
        return cleaned

    @field_validator("timestamp1", "timestamp2")
    @classmethod
    def validate_ts(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Timestamp must be a non-empty string.")
        ts = v.strip()
        try:
            validate_timestamp_format(ts)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return ts

    @model_validator(mode="after")
    def validate_different_timestamps(self) -> WaybackCompareRequest:
        if self.timestamp1 == self.timestamp2:
            raise ValueError("Selected timestamps must be different (cannot compare identical timestamps).")
        return self


# ============================================================================
# Safe Wayback Transport with Pre-Hop Hostname Allowlist Check
# ============================================================================

async def safe_fetch_wayback_async(
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
    """Fetch a Wayback resource asynchronously with full SSRF, DNS pinning, TLS verification,
    strict host-allowlist enforcement BEFORE every hop, and strict overall deadline enforcement.

    Rejects any redirect to a host other than web.archive.org / archive.org BEFORE the
    redirected request is initiated.
    """
    if not verify_ssl:
        raise ValueError("Disabling TLS verification is prohibited.")

    validate_ssl_context(ssl_context)

    # 1. Enforce allowed Wayback host BEFORE initial request
    validate_wayback_destination_host(url)

    # 2. SSRF validate initial target URL
    validate_target_url(url, resolve_dns=False)

    current_url = url
    current_method = method.upper()
    current_body = body
    visited_urls: set[str] = {current_url}
    redirect_history: list[str] = []

    req_headers: dict[str, str] = {
        "User-Agent": "HistoricalWebpageComparison/2.0 (Security-Checked Fetcher)",
        "Accept": "text/html,application/xhtml+xml,application/json,*/*;q=0.8",
    }
    if headers:
        req_headers.update(headers)

    deadline = time.monotonic() + total_deadline
    tls_verify = ssl_context if ssl_context is not None else True

    active_response: httpx.Response | None = None
    try:
        with anyio.fail_after(total_deadline):
            transport = PinnedAsyncHTTPTransport(verify=tls_verify)

            async with httpx.AsyncClient(
                transport=transport,
                follow_redirects=False,
            ) as client:
                redirect_count = 0
                while True:
                    remaining_time = deadline - time.monotonic()
                    if remaining_time <= 0:
                        raise ResourceLimitError(f"Overall request deadline ({total_deadline}s) exceeded.")

                    hop_timeout = httpx.Timeout(
                        timeout=remaining_time,
                        connect=min(5.0, remaining_time),
                        read=min(25.0, remaining_time),
                    )

                    request = client.build_request(
                        method=current_method,
                        url=current_url,
                        headers=req_headers,
                        content=current_body if current_method in ("POST", "PUT", "PATCH") else None,
                        timeout=hop_timeout,
                    )

                    try:
                        response = await client.send(request, stream=True)
                        active_response = response
                    except (SSRFSecurityError, TimeoutError):
                        raise
                    except httpx.TimeoutException as exc:
                        raise ResourceLimitError(f"Request timeout exceeded: {exc}") from exc
                    except httpx.ConnectError as exc:
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
                            active_response = None
                            raise RedirectSecurityError(f"Maximum redirect count of {max_redirects} exceeded.")

                        location = response.headers.get("location")
                        if not location:
                            await response.aclose()
                            active_response = None
                            raise RedirectSecurityError(
                                f"Redirect status {response.status_code} received without Location header."
                            )

                        new_url = urllib.parse.urljoin(current_url, location.strip())

                        # CRITICAL: Validate host BEFORE sending request or navigating
                        try:
                            validate_wayback_destination_host(new_url)
                        except OffHostRedirectError:
                            await response.aclose()
                            active_response = None
                            raise

                        # Re-validate destination against SSRF
                        try:
                            validate_target_url(new_url, resolve_dns=False)
                        except SSRFSecurityError as exc:
                            await response.aclose()
                            active_response = None
                            raise RedirectSecurityError(
                                f"Redirect destination '{new_url}' violates security rules: {exc}"
                            ) from exc

                        # Prevent HTTPS to HTTP downgrade
                        current_scheme = urllib.parse.urlsplit(current_url).scheme.lower()
                        new_scheme = urllib.parse.urlsplit(new_url).scheme.lower()
                        if current_scheme == "https" and new_scheme == "http":
                            await response.aclose()
                            active_response = None
                            raise RedirectSecurityError(
                                f"Insecure redirect downgrade from HTTPS to HTTP: '{current_url}' -> '{new_url}'."
                            )

                        if new_url in visited_urls:
                            await response.aclose()
                            active_response = None
                            raise RedirectSecurityError(f"Circular redirect detected: '{new_url}'.")

                        if not is_same_origin(current_url, new_url):
                            req_headers = strip_sensitive_headers(req_headers)

                        if response.status_code == 303:
                            current_method = "GET"
                            current_body = None
                            req_headers = strip_body_headers(req_headers)
                        elif response.status_code in (301, 302):
                            if current_method in ("POST", "PUT", "PATCH", "DELETE"):
                                current_method = "GET"
                                current_body = None
                                req_headers = strip_body_headers(req_headers)

                        visited_urls.add(new_url)
                        redirect_history.append(current_url)
                        current_url = new_url
                        await response.aclose()
                        active_response = None
                        continue

                    # Non-redirect response: Content-Length check
                    content_length_header = response.headers.get("content-length")
                    if content_length_header:
                        try:
                            content_length = int(content_length_header)
                            if content_length > max_response_size:
                                await response.aclose()
                                active_response = None
                                raise ResourceLimitError(
                                    f"Content-Length ({content_length} bytes) exceeds maximum allowed size of {max_response_size} bytes."
                                )
                        except ValueError:
                            pass

                    # Stream body with size limits
                    body_chunks: list[bytes] = []
                    total_bytes = 0
                    try:
                        async for chunk in response.aiter_bytes():
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
                        active_response = None

                    return SafeFetchResult(
                        url=current_url,
                        status_code=response.status_code,
                        headers=response.headers,
                        content=b"".join(body_chunks),
                        redirect_history=redirect_history,
                    )
    except TimeoutError as exc:
        if active_response is not None:
            try:
                await active_response.aclose()
            except Exception:
                pass
        raise ResourceLimitError(f"Overall request deadline ({total_deadline}s) exceeded.") from exc
    except httpx.TimeoutException as exc:
        if active_response is not None:
            try:
                await active_response.aclose()
            except Exception:
                pass
        raise ResourceLimitError(f"Request timeout exceeded: {exc}") from exc


# ============================================================================
# Snapshot Discovery Service (CDX API)
# ============================================================================

async def discover_wayback_snapshots(
    request: WaybackSnapshotsRequest,
    *,
    fetcher = safe_fetch_wayback_async,
) -> WaybackSnapshotsResponse:
    """Discover available monthly historical snapshots for a validated target URL via CDX API.

    Queries with limit=-51 (requesting latest 51 monthly captures in reverse order) to
    determine if results were truncated while returning at most 50 captures.
    """
    params: dict[str, Any] = {
        "url": request.url,
        "output": "json",
        "fl": "timestamp,original,mimetype,statuscode,length",
        "filter": ["statuscode:200", "mimetype:text/html"],
        "collapse": "timestamp:6",
        "limit": "-51",
    }
    if request.from_year is not None:
        params["from"] = f"{request.from_year:04d}0101000000"
    if request.to_year is not None:
        params["to"] = f"{request.to_year:04d}1231235959"

    # Construct query string preserving multiple filter params
    query_parts: list[str] = []
    for k, v in params.items():
        if isinstance(v, list):
            for item in v:
                query_parts.append(f"{urllib.parse.quote_plus(k)}={urllib.parse.quote_plus(str(item))}")
        else:
            query_parts.append(f"{urllib.parse.quote_plus(k)}={urllib.parse.quote_plus(str(v))}")
    cdx_url = f"{CDX_BASE_URL}?{'&'.join(query_parts)}"

    try:
        res = await fetcher(cdx_url)
    except (SSRFSecurityError, ResourceLimitError, OffHostRedirectError, WaybackError):
        raise
    except Exception as exc:
        raise WaybackFetchError(
            f"CDX discovery request failed: {exc}",
            failed_url=cdx_url,
            cause=exc,
        ) from exc

    if res.status_code != 200:
        raise WaybackCDXError(
            f"Wayback CDX API returned HTTP status {res.status_code}.",
            status_code=res.status_code,
        )

    text = res.text.strip()
    if not text or text == "[]":
        return WaybackSnapshotsResponse(
            url=request.url,
            total_returned=0,
            is_limited=False,
            collapse="monthly",
            snapshots=[],
        )

    try:
        data = json.loads(text)
    except Exception as exc:
        raise WaybackCDXError(f"Wayback CDX returned malformed JSON: {exc}", cause=exc) from exc

    if not isinstance(data, list):
        raise WaybackCDXError("Wayback CDX returned invalid structure: expected JSON array.")

    if len(data) == 0:
        return WaybackSnapshotsResponse(
            url=request.url,
            total_returned=0,
            is_limited=False,
            collapse="monthly",
            snapshots=[],
        )

    header = data[0]
    if not isinstance(header, list):
        raise WaybackCDXError("Wayback CDX header row is malformed.")

    col_map = {col.lower(): idx for idx, col in enumerate(header) if isinstance(col, str)}
    required_cols = ("timestamp", "original", "mimetype", "statuscode")
    for req_col in required_cols:
        if req_col not in col_map:
            raise WaybackCDXError(f"Wayback CDX response missing required column '{req_col}'.")

    raw_rows = data[1:]

    valid_snapshots: list[WaybackSnapshot] = []
    for row in raw_rows:
        if not isinstance(row, list) or len(row) < len(required_cols):
            continue
        ts = str(row[col_map["timestamp"]]).strip()
        orig = str(row[col_map["original"]]).strip()
        mime = str(row[col_map["mimetype"]]).strip()
        status_str = str(row[col_map["statuscode"]]).strip()

        # Validate timestamp
        try:
            validate_timestamp_format(ts)
        except ValueError:
            continue

        # Status must be 200
        if status_str != "200":
            continue

        # MIME must be HTML
        lower_mime = mime.lower().split(";")[0].strip()
        if lower_mime not in HTML_CONTENT_TYPES:
            continue

        iso_dt, display_date = format_timestamp(ts)
        valid_snapshots.append(
            WaybackSnapshot(
                timestamp=ts,
                datetime=iso_dt,
                display_date=display_date,
                original_url=orig,
                status_code=200,
                mimetype=mime,
            )
        )

    is_limited = len(valid_snapshots) > 50
    snapshots = valid_snapshots[:50]

    return WaybackSnapshotsResponse(
        url=request.url,
        total_returned=len(snapshots),
        is_limited=is_limited,
        collapse="monthly",
        snapshots=snapshots,
    )


# ============================================================================
# Snapshot Verification Service
# ============================================================================

async def verify_snapshot_timestamp(
    url: str,
    timestamp: str,
    *,
    fetcher = safe_fetch_wayback_async,
) -> WaybackSnapshot:
    """Verify that an exact timestamp exists for target URL in CDX and return verified record."""
    validate_timestamp_format(timestamp)
    params = {
        "url": url,
        "output": "json",
        "fl": "timestamp,original,mimetype,statuscode,length",
        "from": timestamp,
        "to": timestamp,
        "limit": "1",
    }
    query_str = urllib.parse.urlencode(params)
    cdx_url = f"{CDX_BASE_URL}?{query_str}"

    try:
        res = await fetcher(cdx_url)
    except (SSRFSecurityError, ResourceLimitError, OffHostRedirectError, WaybackError):
        raise
    except Exception as exc:
        raise WaybackFetchError(
            f"CDX verification request failed for timestamp {timestamp}: {exc}",
            failed_url=cdx_url,
            cause=exc,
        ) from exc

    if res.status_code != 200:
        raise WaybackCDXError(
            f"CDX verification returned HTTP status {res.status_code}.",
            status_code=res.status_code,
        )

    text = res.text.strip()
    if not text or text == "[]":
        raise SnapshotNotFoundError(
            f"Snapshot for timestamp '{timestamp}' not found on URL '{url}'.",
            timestamp=timestamp,
            url=url,
        )

    try:
        data = json.loads(text)
    except Exception as exc:
        raise WaybackCDXError(f"CDX verification returned malformed JSON: {exc}", cause=exc) from exc

    if not isinstance(data, list) or len(data) < 2:
        raise SnapshotNotFoundError(
            f"Snapshot for timestamp '{timestamp}' not found on URL '{url}'.",
            timestamp=timestamp,
            url=url,
        )

    header = data[0]
    row = data[1]
    col_map = {col.lower(): idx for idx, col in enumerate(header) if isinstance(col, str)}

    rec_ts = str(row[col_map.get("timestamp", 0)]).strip()
    rec_orig = str(row[col_map.get("original", 1)]).strip()
    rec_mime = str(row[col_map.get("mimetype", 2)]).strip()
    rec_status = str(row[col_map.get("statuscode", 3)]).strip()

    if rec_ts != timestamp:
        raise SnapshotNotFoundError(
            f"Exact timestamp '{timestamp}' not found (got '{rec_ts}').",
            timestamp=timestamp,
            url=url,
        )

    if rec_status != "200":
        raise WaybackVerificationError(
            f"Snapshot '{timestamp}' has non-successful HTTP status code {rec_status}.",
            timestamp=timestamp,
            status_code=int(rec_status) if rec_status.isdigit() else None,
            mimetype=rec_mime,
        )

    lower_mime = rec_mime.lower().split(";")[0].strip()
    if lower_mime not in HTML_CONTENT_TYPES:
        raise WaybackVerificationError(
            f"Snapshot '{timestamp}' has non-HTML MIME type '{rec_mime}'.",
            timestamp=timestamp,
            status_code=200,
            mimetype=rec_mime,
        )

    # Validate CDX original URL syntax and safety
    validate_capture_original_url(rec_orig)

    iso_dt, display_date = format_timestamp(rec_ts)
    return WaybackSnapshot(
        timestamp=rec_ts,
        datetime=iso_dt,
        display_date=display_date,
        original_url=rec_orig,
        status_code=200,
        mimetype=rec_mime,
    )


async def verify_and_resolve_snapshots(
    url: str,
    timestamp1: str,
    timestamp2: str,
    *,
    fetcher = safe_fetch_wayback_async,
) -> tuple[WaybackSnapshot, WaybackSnapshot]:
    """Concurrently verify two requested timestamps against CDX point queries.

    If either verification fails, cancels pending sibling work immediately,
    awaits cancelled tasks to prevent orphaned coroutines, and attributes
    the failure transparently.
    """
    if timestamp1 == timestamp2:
        raise ValueError("Cannot compare identical timestamps.")

    task1 = asyncio.create_task(verify_snapshot_timestamp(url, timestamp1, fetcher=fetcher))
    task2 = asyncio.create_task(verify_snapshot_timestamp(url, timestamp2, fetcher=fetcher))

    try:
        done, pending = await asyncio.wait(
            {task1, task2},
            return_when=asyncio.FIRST_EXCEPTION,
        )
    except asyncio.CancelledError:
        for t in (task1, task2):
            if not t.done():
                t.cancel()
        await asyncio.gather(task1, task2, return_exceptions=True)
        raise

    exceptions: list[BaseException] = []
    for t in done:
        if t.cancelled():
            exceptions.append(asyncio.CancelledError())
        elif t.exception() is not None:
            exceptions.append(t.exception())

    if exceptions:
        for t in pending:
            t.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        raise exceptions[0]

    return task1.result(), task2.result()


# ============================================================================
# Raw Replay Retrieval Service
# ============================================================================

async def fetch_single_wayback_capture(
    snapshot: WaybackSnapshot,
    label: str = "Snapshot",
    *,
    fetcher = safe_fetch_wayback_async,
    total_deadline: float = DEFAULT_TOTAL_DEADLINE,
    max_response_size: int = DEFAULT_MAX_RESPONSE_SIZE,
) -> SafeFetchResult:
    """Fetch raw replay HTML capture for a verified snapshot and validate integrity."""
    replay_url = build_wayback_replay_url(snapshot.timestamp, snapshot.original_url)

    try:
        res = await fetcher(
            replay_url,
            total_deadline=total_deadline,
            max_response_size=max_response_size,
        )
    except OffHostRedirectError:
        raise
    except (SSRFSecurityError, ResourceLimitError, WaybackError):
        raise
    except Exception as exc:
        raise WaybackFetchError(
            f"{label} (timestamp {snapshot.timestamp}) failed during retrieval: {exc}",
            failed_url=replay_url,
            cause=exc,
        ) from exc

    # Confirm final resolved URL contains exact requested timestamp (reject fallback redirect)
    final_ts = extract_replay_timestamp(res.url)
    if final_ts != snapshot.timestamp:
        raise FallbackRedirectError(
            f"{label} redirected to fallback timestamp '{final_ts or 'unknown'}' "
            f"instead of requested exact timestamp '{snapshot.timestamp}'.",
            requested_timestamp=snapshot.timestamp,
            resolved_url=res.url,
        )

    # Validate HTML response using existing HTML validator
    try:
        validate_html_response(res, label=f"{label} ({snapshot.timestamp})")
    except (HTMLValidationError, LiveFetchError) as exc:
        raise WaybackContentError(
            f"{label} ({snapshot.timestamp}) failed HTML validation: {exc}",
            failed_url=res.url,
        ) from exc

    return res


async def fetch_wayback_raw_pair(
    snapshot1: WaybackSnapshot,
    snapshot2: WaybackSnapshot,
    *,
    fetcher = safe_fetch_wayback_async,
    total_deadline: float = DEFAULT_TOTAL_DEADLINE,
    max_response_size: int = DEFAULT_MAX_RESPONSE_SIZE,
) -> tuple[SafeFetchResult, SafeFetchResult]:
    """Fetch two raw Wayback captures concurrently with strict task lifecycle management.

    If either fetch fails, immediately cancels any pending sibling task, awaits
    its cancellation to cleanly close connections and prevent orphaned background tasks,
    and attributes the failure specifically to that snapshot.
    """
    task1 = asyncio.create_task(
        fetch_single_wayback_capture(
            snapshot1,
            label="Snapshot 1",
            fetcher=fetcher,
            total_deadline=total_deadline,
            max_response_size=max_response_size,
        )
    )
    task2 = asyncio.create_task(
        fetch_single_wayback_capture(
            snapshot2,
            label="Snapshot 2",
            fetcher=fetcher,
            total_deadline=total_deadline,
            max_response_size=max_response_size,
        )
    )

    try:
        done, pending = await asyncio.wait(
            {task1, task2},
            return_when=asyncio.FIRST_EXCEPTION,
        )
    except asyncio.CancelledError:
        for t in (task1, task2):
            if not t.done():
                t.cancel()
        await asyncio.gather(task1, task2, return_exceptions=True)
        raise

    exceptions: list[BaseException] = []
    for t in done:
        if t.cancelled():
            exceptions.append(asyncio.CancelledError())
        elif t.exception() is not None:
            exceptions.append(t.exception())

    if exceptions:
        for t in pending:
            t.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        raise exceptions[0]

    return task1.result(), task2.result()
