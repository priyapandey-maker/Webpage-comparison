"""Live URL Webpage Comparison Fetcher & Validation Service.

Coordinates secure concurrent fetching of two webpage targets using the
SSRF-hardened transport, enforces HTML content-type and structure invariants,
and attributes partial failures with full exception transparency.

Independent of api.py to prevent circular imports.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Mapping

from bs4 import BeautifulSoup
from pydantic import BaseModel, field_validator

try:
    from .security.redirect_handler import (
        DEFAULT_MAX_REDIRECTS,
        DEFAULT_MAX_RESPONSE_SIZE,
        DEFAULT_TOTAL_DEADLINE,
        SafeFetchResult,
        safe_fetch_async,
    )
    from .security.ssrf_validator import (
        BlockedIPError,
        DNSResolutionError,
        InvalidURLError,
        RedirectSecurityError,
        ResourceLimitError,
        SSRFSecurityError,
        TLSVerificationError,
        validate_target_url,
    )
except ImportError:
    from security.redirect_handler import (
        DEFAULT_MAX_REDIRECTS,
        DEFAULT_MAX_RESPONSE_SIZE,
        DEFAULT_TOTAL_DEADLINE,
        SafeFetchResult,
        safe_fetch_async,
    )
    from security.ssrf_validator import (
        BlockedIPError,
        DNSResolutionError,
        InvalidURLError,
        RedirectSecurityError,
        ResourceLimitError,
        SSRFSecurityError,
        TLSVerificationError,
        validate_target_url,
    )

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

class LiveCompareError(Exception):
    """Base exception for live webpage comparison operations."""


class LiveFetchError(LiveCompareError):
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


class HTMLValidationError(LiveCompareError):
    """Raised when a fetched response is empty, unsupported content-type, or malformed HTML."""

    def __init__(
        self,
        message: str,
        failed_url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.failed_url = failed_url


# ============================================================================
# Request Model
# ============================================================================

class CompareURLsRequest(BaseModel):
    """Request payload for comparing two live webpage URLs."""

    url1: str
    url2: str

    @field_validator("url1", "url2")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL syntax, scheme, and non-empty hostname without blocking on DNS."""
        if not isinstance(v, str) or not v.strip():
            raise ValueError("URL must be a non-empty string.")
        cleaned = v.strip()
        try:
            validate_target_url(cleaned, resolve_dns=False)
        except SSRFSecurityError as exc:
            raise ValueError(str(exc)) from exc
        return cleaned


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


# ============================================================================
# Concurrent Fetching
# ============================================================================

async def fetch_live_url_pair(
    url1: str,
    url2: str,
    *,
    total_deadline: float = DEFAULT_TOTAL_DEADLINE,
    max_response_size: int = DEFAULT_MAX_RESPONSE_SIZE,
    headers: dict[str, str] | None = None,
) -> tuple[SafeFetchResult, SafeFetchResult]:
    """Fetch two URLs concurrently using the SSRF-protected async transport and validate both HTML responses.

    Returns (res1, res2) upon successful retrieval and validation of both pages.
    Attributes failures specifically to URL 1, URL 2, or both, and aborts immediately
    upon any partial or total failure.
    """
    # 1. Fast pre-validation of both URLs
    validate_target_url(url1, resolve_dns=False)
    validate_target_url(url2, resolve_dns=False)

    # 2. Launch concurrent fetches
    task1 = safe_fetch_async(
        url1,
        headers=headers,
        total_deadline=total_deadline,
        max_response_size=max_response_size,
    )
    task2 = safe_fetch_async(
        url2,
        headers=headers,
        total_deadline=total_deadline,
        max_response_size=max_response_size,
    )

    res1_or_exc, res2_or_exc = await asyncio.gather(task1, task2, return_exceptions=True)

    # 3. Handle partial or complete fetch failures
    exc1 = res1_or_exc if isinstance(res1_or_exc, BaseException) else None
    exc2 = res2_or_exc if isinstance(res2_or_exc, BaseException) else None

    if exc1 is not None and exc2 is not None:
        raise LiveFetchError(
            f"Both URL fetches failed. URL 1 ({url1}): {exc1}; URL 2 ({url2}): {exc2}",
            failed_url=f"{url1}, {url2}",
            cause=exc1,
        )
    if exc1 is not None:
        raise LiveFetchError(
            f"Failed to fetch URL 1 ({url1}): {exc1}",
            failed_url=url1,
            cause=exc1,
        )
    if exc2 is not None:
        raise LiveFetchError(
            f"Failed to fetch URL 2 ({url2}): {exc2}",
            failed_url=url2,
            cause=exc2,
        )

    res1: SafeFetchResult = res1_or_exc
    res2: SafeFetchResult = res2_or_exc

    # 4. Validate HTML response integrity for both
    validate_html_response(res1, label=f"URL 1 ({res1.url})")
    validate_html_response(res2, label=f"URL 2 ({res2.url})")

    return res1, res2

