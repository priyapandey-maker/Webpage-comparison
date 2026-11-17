"""Unit and integration tests for HTML response validation and endpoint regression.

Tests:
- validate_html_response HTTP status checking, empty body handling, MIME type enforcement, sniffing fallback, and HTML root validation
- POST /api/compare-urls is retired and returns HTTP 404
- POST /api/compare baseline file upload regression continues to work identically
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys

import httpx
import pytest

# Ensure comparison-engine root and src are on sys.path
COMPARISON_ENGINE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = COMPARISON_ENGINE_DIR / "src"
REPO_ROOT = COMPARISON_ENGINE_DIR.parent
TEST_FILES_DIR = REPO_ROOT / "test-files"

for d in (str(COMPARISON_ENGINE_DIR), str(SRC_DIR)):
    if d not in sys.path:
        sys.path.insert(0, d)

from html_validator import (
    HTML_CONTENT_TYPES,
    REJECTED_CONTENT_TYPES,
    HTMLValidationError,
    LiveFetchError,
    validate_html_response,
)
from api import app
from security.redirect_handler import SafeFetchResult

V1_FILE = TEST_FILES_DIR / "mini project version 1.html"
V2_FILE = TEST_FILES_DIR / "mini project version 2.html"


# ============================================================================
# 1. validate_html_response Tests
# ============================================================================

def test_validate_html_response_valid():
    res = SafeFetchResult(
        url="https://example.com/valid",
        status_code=200,
        headers={"content-type": "text/html; charset=utf-8"},
        content=b"<!DOCTYPE html><html><head><title>Test</title></head><body><p>Hello</p></body></html>",
        redirect_history=[],
    )
    validate_html_response(res, label="Test URL")


def test_validate_html_response_valid_xhtml():
    res = SafeFetchResult(
        url="https://example.com/valid-xhtml",
        status_code=200,
        headers={"content-type": "application/xhtml+xml"},
        content=b'<?xml version="1.0" encoding="UTF-8"?><html><head><title>XHTML</title></head><body>Hello</body></html>',
        redirect_history=[],
    )
    validate_html_response(res, label="XHTML URL")


def test_validate_html_response_missing_content_type_with_html_markup():
    res = SafeFetchResult(
        url="https://example.com/sniffed",
        status_code=200,
        headers={},
        content=b"<!DOCTYPE html><html><body><h1>Sniffed HTML</h1></body></html>",
        redirect_history=[],
    )
    validate_html_response(res, label="Sniffed URL")


def test_validate_html_response_non_200_status():
    for code in (400, 403, 404, 500, 502, 503):
        res = SafeFetchResult(
            url="https://example.com/error",
            status_code=code,
            headers={"content-type": "text/html"},
            content=b"<html><body>Error page</body></html>",
            redirect_history=[],
        )
        with pytest.raises(LiveFetchError) as exc:
            validate_html_response(res, label="Error URL")
        assert f"HTTP status {code}" in str(exc.value)
        assert exc.value.status_code == code


def test_validate_html_response_empty_body():
    res = SafeFetchResult(
        url="https://example.com/empty",
        status_code=200,
        headers={"content-type": "text/html"},
        content=b"",
        redirect_history=[],
    )
    with pytest.raises(HTMLValidationError) as exc:
        validate_html_response(res, label="Empty URL")
    assert "empty content" in str(exc.value)


def test_validate_html_response_whitespace_only_body():
    res = SafeFetchResult(
        url="https://example.com/whitespace",
        status_code=200,
        headers={"content-type": "text/html"},
        content=b"   \n\t  \r\n  ",
        redirect_history=[],
    )
    with pytest.raises(HTMLValidationError) as exc:
        validate_html_response(res, label="Whitespace URL")
    assert "empty content" in str(exc.value)


def test_validate_html_response_unsupported_content_types():
    unsupported = [
        "application/json",
        "application/pdf",
        "application/xml",
        "text/xml",
        "image/png",
        "image/jpeg",
        "audio/mpeg",
        "video/mp4",
    ]
    for mime in unsupported:
        res = SafeFetchResult(
            url="https://example.com/data",
            status_code=200,
            headers={"content-type": mime},
            content=b'{"key": "value"}',
            redirect_history=[],
        )
        with pytest.raises(HTMLValidationError) as exc:
            validate_html_response(res, label="Non-HTML URL")
        assert "unsupported content-type" in str(exc.value).lower()


def test_validate_html_response_malformed_html_missing_html_tag():
    res = SafeFetchResult(
        url="https://example.com/fragment",
        status_code=200,
        headers={"content-type": "text/html"},
        content=b"<p>Just a stray paragraph without html root tag</p>",
        redirect_history=[],
    )
    with pytest.raises(HTMLValidationError) as exc:
        validate_html_response(res, label="Fragment URL")
    assert "valid <html> document root" in str(exc.value)


def test_live_compare_backward_compatibility_reexports():
    """Verify live_compare still re-exports shared validation symbols."""
    import live_compare

    assert hasattr(live_compare, "validate_html_response")
    assert hasattr(live_compare, "HTMLValidationError")
    assert hasattr(live_compare, "LiveFetchError")
    assert live_compare.validate_html_response is validate_html_response


# ============================================================================
# 2. Endpoint Retirement & Regression Tests
# ============================================================================

def test_compare_urls_endpoint_is_retired():
    """Verify that POST /api/compare-urls has been retired and returns HTTP 404."""
    async def _test():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/compare-urls",
                json={"url1": "https://example.com/1", "url2": "https://example.com/2"},
            )
            assert resp.status_code == 404

    asyncio.run(_test())


def test_api_existing_upload_compare_regression():
    """Verify that existing POST /api/compare file upload endpoint continues to work identically."""
    async def _test():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            files = {
                "version1": ("mini project version 1.html", V1_FILE.read_bytes(), "text/html"),
                "version2": ("mini project version 2.html", V2_FILE.read_bytes(), "text/html"),
            }
            resp = await client.post("/api/compare", files=files)
            assert resp.status_code == 200
            data = resp.json()

            assert data["presentationSummary"]["total"] == 21
            assert data["presentationSummary"]["added"] == 8
            assert data["presentationSummary"]["removed"] == 1
            assert data["presentationSummary"]["modified"] == 12
            assert data["version1"]["label"] == "mini project version 1.html"
            assert data["version2"]["label"] == "mini project version 2.html"

    asyncio.run(_test())
