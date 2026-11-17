"""HTML Response Validation Module.

Validates that fetched HTTP responses are successful (HTTP 200 OK), non-empty,
have supported HTML MIME types (with sniffing fallback), and contain a valid
<html> document root.

Shared across Wayback capture processing and webpage retrieval.
"""

from __future__ import annotations

import logging
from bs4 import BeautifulSoup

try:
    from .security.redirect_handler import SafeFetchResult
except ImportError:
    from security.redirect_handler import SafeFetchResult

logger = logging.getLogger(__name__)

# Standard HTML / XHTML MIME types
HTML_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
}

# Explicitly rejected non-HTML MIME prefixes or substrings
REJECTED_CONTENT_TYPES = (
    "application/json",
    "application/pdf",
    "application/xml",
    "text/xml",
    "image/",
    "audio/",
    "video/",
    "font/",
)


# ============================================================================
# Exception Hierarchy
# ============================================================================

class WebpageContentError(Exception):
    """Base exception for webpage content and validation operations."""


class LiveCompareError(WebpageContentError):
    """Backward-compatible base exception alias."""


class LiveFetchError(WebpageContentError):
    """Raised when fetching a target URL encounters a network, status, or security error."""

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


class HTMLValidationError(WebpageContentError):
    """Raised when a fetched response is empty, unsupported content-type, or malformed HTML."""

    def __init__(
        self,
        message: str,
        failed_url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.failed_url = failed_url


# ============================================================================
# Response Validation
# ============================================================================

def validate_html_response(result: SafeFetchResult, label: str = "URL") -> None:
    """Validate that a fetched response returned 200 OK, valid HTML MIME, non-empty, and valid HTML root."""
    # 1. HTTP Status check
    if result.status_code != 200:
        raise LiveFetchError(
            f"{label} returned HTTP status {result.status_code} (expected 200 OK).",
            failed_url=result.url,
            status_code=result.status_code,
        )

    # 2. Non-empty check
    if not result.content or not result.content.strip():
        raise HTMLValidationError(
            f"{label} returned empty content (0 bytes).",
            failed_url=result.url,
        )

    # 3. Content-Type inspection
    content_type_header = result.headers.get("content-type", "").lower()
    mime = content_type_header.split(";")[0].strip() if content_type_header else ""

    if mime:
        # Check against explicitly disallowed media types
        if any(mime.startswith(rejected) or rejected in mime for rejected in REJECTED_CONTENT_TYPES):
            raise HTMLValidationError(
                f"{label} returned unsupported Content-Type '{mime}'. Expected text/html or application/xhtml+xml.",
                failed_url=result.url,
            )
        # If Content-Type is specified but not standard HTML, verify HTML signature
        if mime not in HTML_CONTENT_TYPES:
            lower_content = result.content[:2048].lower()
            if not (b"<html" in lower_content or b"<!doctype html" in lower_content):
                raise HTMLValidationError(
                    f"{label} returned Content-Type '{mime}' without valid HTML markup.",
                    failed_url=result.url,
                )
    else:
        # No Content-Type header present: sniff first bytes for HTML signature
        lower_content = result.content[:2048].lower()
        if not (b"<html" in lower_content or b"<!doctype html" in lower_content):
            raise HTMLValidationError(
                f"{label} response has no Content-Type header and does not appear to be an HTML document.",
                failed_url=result.url,
            )

    # 4. HTML document root check (mirrors Phase 1 build_tree requirement)
    try:
        soup = BeautifulSoup(result.content, "html.parser")
        html_tag = soup.find("html")
        if not html_tag:
            raise HTMLValidationError(
                f"{label} does not contain a valid <html> document root.",
                failed_url=result.url,
            )
    except HTMLValidationError:
        raise
    except Exception as exc:
        raise HTMLValidationError(
            f"{label} failed HTML parsing: {exc}",
            failed_url=result.url,
        ) from exc
