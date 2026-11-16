"""Unit and integration tests for Milestone 3: Live URL comparison fetcher, validation service, and API endpoint.

Tests:
- CompareURLsRequest schema validation, scheme restrictions, credentials prohibition, blocked hostnames
- validate_html_response HTTP status checking, empty body handling, MIME type enforcement, and HTML root validation
- fetch_live_url_pair concurrent fetching, partial failure attribution, total failure handling, and byte preservation
- POST /api/compare-urls end-to-end integration, redirect labels, NLP enrichment, error mapping, and tempdir cleanup
- POST /api/compare baseline file upload regression
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import tempfile
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pydantic import ValidationError

# Ensure comparison-engine root and src are on sys.path
COMPARISON_ENGINE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = COMPARISON_ENGINE_DIR / "src"
REPO_ROOT = COMPARISON_ENGINE_DIR.parent
TEST_FILES_DIR = REPO_ROOT / "test-files"

for d in (str(COMPARISON_ENGINE_DIR), str(SRC_DIR)):
    if d not in sys.path:
        sys.path.insert(0, d)

import live_compare
from live_compare import (
    CompareURLsRequest,
    HTMLValidationError,
    LiveCompareError,
    LiveFetchError,
    fetch_live_url_pair,
    validate_html_response,
)
from api import app
from security.redirect_handler import SafeFetchResult
from security.ssrf_validator import (
    BlockedIPError,
    DNSResolutionError,
    InvalidURLError,
    ResourceLimitError,
)

V1_FILE = TEST_FILES_DIR / "mini project version 1.html"
V2_FILE = TEST_FILES_DIR / "mini project version 2.html"


# ============================================================================
# 1. CompareURLsRequest Validation Tests
# ============================================================================

def test_compare_urls_request_valid():
    req = CompareURLsRequest(
        url1="https://example.com/v1",
        url2="https://example.com/v2",
    )
    assert req.url1 == "https://example.com/v1"
    assert req.url2 == "https://example.com/v2"


def test_compare_urls_request_whitespace_stripping():
    req = CompareURLsRequest(
        url1="  https://example.com/page1  ",
        url2="\thttps://example.com/page2\n",
    )
    assert req.url1 == "https://example.com/page1"
    assert req.url2 == "https://example.com/page2"


def test_compare_urls_request_empty_or_whitespace():
    with pytest.raises(ValidationError) as exc:
        CompareURLsRequest(url1="", url2="https://example.com")
    assert "non-empty string" in str(exc.value).lower()

    with pytest.raises(ValidationError) as exc:
        CompareURLsRequest(url1="https://example.com", url2="   ")
    assert "non-empty string" in str(exc.value).lower()


def test_compare_urls_request_forbidden_schemes():
    forbidden = [
        "ftp://example.com/resource",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "gopher://example.com",
        "data:text/html,<h1>Hi</h1>",
    ]
    for bad_url in forbidden:
        with pytest.raises(ValidationError) as exc:
            CompareURLsRequest(url1=bad_url, url2="https://example.com")
        assert "unsupported scheme" in str(exc.value).lower() or "scheme" in str(exc.value).lower()


def test_compare_urls_request_embedded_credentials():
    with pytest.raises(ValidationError) as exc:
        CompareURLsRequest(
            url1="https://user:pass@example.com/page",
            url2="https://example.com",
        )
    assert "credentials" in str(exc.value).lower()


def test_compare_urls_request_blocked_hostnames_and_ips():
    blocked = [
        "http://localhost/test",
        "http://127.0.0.1/test",
        "http://169.254.169.254/latest/meta-data/",
        "http://192.168.1.1/admin",
        "http://10.0.0.1/",
        "http://metadata.google.internal/",
    ]
    for bad_url in blocked:
        with pytest.raises(ValidationError) as exc:
            CompareURLsRequest(url1=bad_url, url2="https://example.com")
        err_msg = str(exc.value).lower()
        assert "forbidden" in err_msg or "blocked" in err_msg or "loopback" in err_msg or "private" in err_msg


# ============================================================================
# 2. validate_html_response Tests
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
        content=b"<html xmlns='http://www.w3.org/1999/xhtml'><head><title>XHTML</title></head><body><h1>Content</h1></body></html>",
        redirect_history=[],
    )
    validate_html_response(res, label="XHTML URL")


def test_validate_html_response_missing_content_type_with_html_markup():
    res = SafeFetchResult(
        url="https://example.com/no-ct",
        status_code=200,
        headers={},
        content=b"<!DOCTYPE html><html><body><h1>Sniffed HTML</h1></body></html>",
        redirect_history=[],
    )
    validate_html_response(res, label="Sniffed URL")


def test_validate_html_response_non_200_status():
    for code in (404, 403, 500, 502, 503):
        res = SafeFetchResult(
            url="https://example.com/error",
            status_code=code,
            headers={"content-type": "text/html"},
            content=b"<html><body>Error page</body></html>",
            redirect_history=[],
        )
        with pytest.raises(LiveFetchError) as exc:
            validate_html_response(res, label="Error URL")
        assert exc.value.status_code == code
        assert f"HTTP status {code}" in str(exc.value)
        assert exc.value.failed_url == "https://example.com/error"


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
    assert "empty" in str(exc.value).lower()
    assert exc.value.failed_url == "https://example.com/empty"


def test_validate_html_response_whitespace_only_body():
    res = SafeFetchResult(
        url="https://example.com/whitespace",
        status_code=200,
        headers={"content-type": "text/html"},
        content=b"   \r\n\t   ",
        redirect_history=[],
    )
    with pytest.raises(HTMLValidationError) as exc:
        validate_html_response(res, label="Whitespace URL")
    assert "empty" in str(exc.value).lower()


def test_validate_html_response_unsupported_content_types():
    unsupported = [
        ("application/json", b'{"message": "Not HTML"}'),
        ("application/pdf", b"%PDF-1.4 binary data"),
        ("image/png", b"\x89PNG\r\n\x1a\n binary image"),
        ("application/xml", b"<?xml version='1.0'?><data><item>value</item></data>"),
    ]
    for mime, body in unsupported:
        res = SafeFetchResult(
            url="https://example.com/non-html",
            status_code=200,
            headers={"content-type": mime},
            content=body,
            redirect_history=[],
        )
        with pytest.raises(HTMLValidationError) as exc:
            validate_html_response(res, label="Non-HTML URL")
        assert "unsupported content-type" in str(exc.value).lower() or "markup" in str(exc.value).lower()


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


# ============================================================================
# 3. fetch_live_url_pair Tests
# ============================================================================

def test_fetch_live_url_pair_success():
    async def _test():
        res1_mock = SafeFetchResult(
            url="https://example.com/v1",
            status_code=200,
            headers={"content-type": "text/html"},
            content=b"<!DOCTYPE html><html><body><h1>Version 1</h1></body></html>",
            redirect_history=[],
        )
        res2_mock = SafeFetchResult(
            url="https://example.com/v2",
            status_code=200,
            headers={"content-type": "text/html"},
            content=b"<!DOCTYPE html><html><body><h1>Version 2</h1></body></html>",
            redirect_history=[],
        )

        with patch.object(live_compare, "safe_fetch_async", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = [res1_mock, res2_mock]

            r1, r2 = await fetch_live_url_pair("https://example.com/v1", "https://example.com/v2")

            assert r1.url == "https://example.com/v1"
            assert r2.url == "https://example.com/v2"
            assert r1.content == res1_mock.content
            assert r2.content == res2_mock.content
            assert mock_fetch.call_count == 2

    asyncio.run(_test())


def test_fetch_live_url_pair_tracks_resolved_redirect_urls():
    async def _test():
        res1_redirected = SafeFetchResult(
            url="https://example.com/final-v1",
            status_code=200,
            headers={"content-type": "text/html"},
            content=b"<!DOCTYPE html><html><body><h1>Redirected V1</h1></body></html>",
            redirect_history=["https://example.com/initial-v1"],
        )
        res2_normal = SafeFetchResult(
            url="https://example.com/v2",
            status_code=200,
            headers={"content-type": "text/html"},
            content=b"<!DOCTYPE html><html><body><h1>Normal V2</h1></body></html>",
            redirect_history=[],
        )

        with patch.object(live_compare, "safe_fetch_async", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = [res1_redirected, res2_normal]

            r1, r2 = await fetch_live_url_pair("https://example.com/initial-v1", "https://example.com/v2")

            assert r1.url == "https://example.com/final-v1"
            assert r1.redirect_history == ["https://example.com/initial-v1"]
            assert r2.url == "https://example.com/v2"

    asyncio.run(_test())


def test_fetch_live_url_pair_partial_failure_url1():
    async def _test():
        res2_mock = SafeFetchResult(
            url="https://example.com/v2",
            status_code=200,
            headers={"content-type": "text/html"},
            content=b"<!DOCTYPE html><html><body><h1>V2</h1></body></html>",
            redirect_history=[],
        )

        with patch.object(live_compare, "safe_fetch_async", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = [
                DNSResolutionError("DNS lookup failed for invalid.domain"),
                res2_mock,
            ]

            with pytest.raises(LiveFetchError) as exc:
                await fetch_live_url_pair("https://invalid.domain/v1", "https://example.com/v2")

            assert "URL 1" in str(exc.value)
            assert exc.value.failed_url == "https://invalid.domain/v1"
            assert isinstance(exc.value.cause, DNSResolutionError)

    asyncio.run(_test())


def test_fetch_live_url_pair_partial_failure_url2():
    async def _test():
        res1_mock = SafeFetchResult(
            url="https://example.com/v1",
            status_code=200,
            headers={"content-type": "text/html"},
            content=b"<!DOCTYPE html><html><body><h1>V1</h1></body></html>",
            redirect_history=[],
        )

        with patch.object(live_compare, "safe_fetch_async", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = [
                res1_mock,
                ResourceLimitError("Overall request deadline (20.0s) exceeded."),
            ]

            with pytest.raises(LiveFetchError) as exc:
                await fetch_live_url_pair("https://example.com/v1", "https://slow.server/v2")

            assert "URL 2" in str(exc.value)
            assert exc.value.failed_url == "https://slow.server/v2"
            assert isinstance(exc.value.cause, ResourceLimitError)

    asyncio.run(_test())


def test_fetch_live_url_pair_both_fail():
    async def _test():
        with patch.object(live_compare, "safe_fetch_async", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = [
                DNSResolutionError("DNS error 1"),
                DNSResolutionError("DNS error 2"),
            ]

            with pytest.raises(LiveFetchError) as exc:
                await fetch_live_url_pair("https://bad1.com", "https://bad2.com")

            assert "Both URL fetches failed" in str(exc.value)

    asyncio.run(_test())


def test_fetch_live_url_pair_validation_failure_on_url1():
    async def _test():
        res1_404 = SafeFetchResult(
            url="https://example.com/404",
            status_code=404,
            headers={"content-type": "text/html"},
            content=b"<!DOCTYPE html><html><body><h1>Not Found</h1></body></html>",
            redirect_history=[],
        )
        res2_ok = SafeFetchResult(
            url="https://example.com/v2",
            status_code=200,
            headers={"content-type": "text/html"},
            content=b"<!DOCTYPE html><html><body><h1>V2</h1></body></html>",
            redirect_history=[],
        )

        with patch.object(live_compare, "safe_fetch_async", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = [res1_404, res2_ok]

            with pytest.raises(LiveFetchError) as exc:
                await fetch_live_url_pair("https://example.com/404", "https://example.com/v2")

            assert "URL 1" in str(exc.value)
            assert exc.value.status_code == 404

    asyncio.run(_test())


def test_fetch_live_url_pair_validation_failure_on_url2():
    async def _test():
        res1_ok = SafeFetchResult(
            url="https://example.com/v1",
            status_code=200,
            headers={"content-type": "text/html"},
            content=b"<!DOCTYPE html><html><body><h1>V1</h1></body></html>",
            redirect_history=[],
        )
        res2_json = SafeFetchResult(
            url="https://example.com/data.json",
            status_code=200,
            headers={"content-type": "application/json"},
            content=b'{"error": "no html"}',
            redirect_history=[],
        )

        with patch.object(live_compare, "safe_fetch_async", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = [res1_ok, res2_json]

            with pytest.raises(HTMLValidationError) as exc:
                await fetch_live_url_pair("https://example.com/v1", "https://example.com/data.json")

            assert "URL 2" in str(exc.value)
            assert "unsupported Content-Type" in str(exc.value)

    asyncio.run(_test())


# ============================================================================
# 4. POST /api/compare-urls Endpoint Integration Tests
# ============================================================================

def test_api_compare_urls_success_and_redirect_labels():
    """Verify successful end-to-end comparison, redirect URL labelling, and NLP payload attachment."""
    async def _test():
        res1 = SafeFetchResult(
            url="https://example.com/resolved-v1",
            status_code=200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=V1_FILE.read_bytes(),
            redirect_history=["https://example.com/initial-v1"],
        )
        res2 = SafeFetchResult(
            url="https://example.com/resolved-v2",
            status_code=200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=V2_FILE.read_bytes(),
            redirect_history=[],
        )

        with patch.object(live_compare, "safe_fetch_async", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = [res1, res2]

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/compare-urls",
                    json={
                        "url1": "https://example.com/initial-v1",
                        "url2": "https://example.com/resolved-v2",
                    },
                )

                assert resp.status_code == 200
                data = resp.json()

                # Verify labels use final resolved URLs
                assert data["version1"]["label"] == "https://example.com/resolved-v1"
                assert data["version2"]["label"] == "https://example.com/resolved-v2"

                # Verify Phase 1 structural contract
                assert data["presentationSummary"]["total"] == 21
                assert data["presentationSummary"]["added"] == 8
                assert data["presentationSummary"]["removed"] == 1
                assert data["presentationSummary"]["modified"] == 12

                # Verify Milestone 2 NLP enrichment
                assert "nlpAnalysis" in data
                nlp = data["nlpAnalysis"]
                assert "overall" in nlp
                assert nlp["overall"]["total_modifications_analyzed"] == 12
                assert nlp["overall"]["total_additions_analyzed"] == 8
                assert nlp["overall"]["total_removals_analyzed"] == 1
                assert nlp["overall"]["average_semantic_similarity"] is not None

    asyncio.run(_test())


def test_api_compare_urls_failure_attribution_url1():
    """Verify that failure on URL 1 returns 502 with clear attribution."""
    async def _test():
        res1_404 = SafeFetchResult(
            url="https://example.com/notfound-v1",
            status_code=404,
            headers={"content-type": "text/html"},
            content=b"<!DOCTYPE html><html><body><h1>Not Found</h1></body></html>",
            redirect_history=[],
        )
        res2_ok = SafeFetchResult(
            url="https://example.com/v2",
            status_code=200,
            headers={"content-type": "text/html"},
            content=V2_FILE.read_bytes(),
            redirect_history=[],
        )

        with patch.object(live_compare, "safe_fetch_async", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = [res1_404, res2_ok]

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/compare-urls",
                    json={"url1": "https://example.com/notfound-v1", "url2": "https://example.com/v2"},
                )

                assert resp.status_code == 502
                assert "HTTP 404" in resp.json()["detail"]
                assert "notfound-v1" in resp.json()["detail"]

    asyncio.run(_test())


def test_api_compare_urls_failure_attribution_url2():
    """Verify that failure on URL 2 returns 502 with clear attribution."""
    async def _test():
        res1_ok = SafeFetchResult(
            url="https://example.com/v1",
            status_code=200,
            headers={"content-type": "text/html"},
            content=V1_FILE.read_bytes(),
            redirect_history=[],
        )
        res2_500 = SafeFetchResult(
            url="https://example.com/error-v2",
            status_code=500,
            headers={"content-type": "text/html"},
            content=b"<!DOCTYPE html><html><body><h1>Error</h1></body></html>",
            redirect_history=[],
        )

        with patch.object(live_compare, "safe_fetch_async", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = [res1_ok, res2_500]

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/compare-urls",
                    json={"url1": "https://example.com/v1", "url2": "https://example.com/error-v2"},
                )

                assert resp.status_code == 502
                assert "HTTP 500" in resp.json()["detail"]
                assert "error-v2" in resp.json()["detail"]

    asyncio.run(_test())


def test_api_compare_urls_blocked_ip_and_invalid_url():
    """Verify that blocked IPs, localhost, and non-HTTP schemes return 400 Bad Request."""
    async def _test():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Loopback IP
            r1 = await client.post("/api/compare-urls", json={"url1": "http://127.0.0.1", "url2": "https://example.com"})
            assert r1.status_code == 400
            assert "forbidden" in r1.json()["detail"].lower() or "loopback" in r1.json()["detail"].lower()

            # Localhost
            r2 = await client.post("/api/compare-urls", json={"url1": "http://localhost/test", "url2": "https://example.com"})
            assert r2.status_code == 400
            assert "blocked" in r2.json()["detail"].lower() or "prohibited" in r2.json()["detail"].lower()

            # Forbidden Scheme
            r3 = await client.post("/api/compare-urls", json={"url1": "ftp://example.com", "url2": "https://example.com"})
            assert r3.status_code == 400
            assert "scheme" in r3.json()["detail"].lower()

            # Embedded credentials
            r4 = await client.post("/api/compare-urls", json={"url1": "https://user:pass@example.com", "url2": "https://example.com"})
            assert r4.status_code == 400
            assert "credentials" in r4.json()["detail"].lower()

    asyncio.run(_test())


def test_api_compare_urls_timeout():
    """Verify that deadline expiration maps to 504 Gateway Timeout."""
    async def _test():
        with patch.object(live_compare, "safe_fetch_async", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = ResourceLimitError("Overall request deadline (20.0s) exceeded.")

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/compare-urls",
                    json={"url1": "https://slow.com/1", "url2": "https://slow.com/2"},
                )

                assert resp.status_code == 504
                assert "timeout" in resp.json()["detail"].lower()

    asyncio.run(_test())


def test_api_compare_urls_oversized_response():
    """Verify that response size exceeding 10MB maps to 413 Payload Too Large."""
    async def _test():
        with patch.object(live_compare, "safe_fetch_async", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = ResourceLimitError("Response body exceeded maximum allowed limit of 10485760 bytes.")

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/compare-urls",
                    json={"url1": "https://huge.com/1", "url2": "https://example.com/2"},
                )

                assert resp.status_code == 413
                assert "payload too large" in resp.json()["detail"].lower()

    asyncio.run(_test())


def test_api_compare_urls_non_html_and_malformed():
    """Verify that unsupported media types return 415 and empty/malformed HTML return 422."""
    async def _test():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Non-HTML MIME (JSON) -> 415
            res_json = SafeFetchResult(
                url="https://example.com/api.json",
                status_code=200,
                headers={"content-type": "application/json"},
                content=b'{"error": "no html"}',
                redirect_history=[],
            )
            res_ok = SafeFetchResult(
                url="https://example.com/v1",
                status_code=200,
                headers={"content-type": "text/html"},
                content=V1_FILE.read_bytes(),
                redirect_history=[],
            )
            with patch.object(live_compare, "safe_fetch_async", new_callable=AsyncMock) as mock_fetch:
                mock_fetch.side_effect = [res_ok, res_json]
                r_json = await client.post("/api/compare-urls", json={"url1": "https://example.com/1", "url2": "https://example.com/2"})
                assert r_json.status_code == 415
                assert "content-type" in r_json.json()["detail"].lower()

            # 2. Empty Body -> 422
            res_empty = SafeFetchResult(
                url="https://example.com/empty",
                status_code=200,
                headers={"content-type": "text/html"},
                content=b"",
                redirect_history=[],
            )
            with patch.object(live_compare, "safe_fetch_async", new_callable=AsyncMock) as mock_fetch:
                mock_fetch.side_effect = [res_empty, res_ok]
                r_empty = await client.post("/api/compare-urls", json={"url1": "https://example.com/1", "url2": "https://example.com/2"})
                assert r_empty.status_code == 422
                assert "empty" in r_empty.json()["detail"].lower()

            # 3. Missing <html> root tag -> 422
            res_malformed = SafeFetchResult(
                url="https://example.com/malformed",
                status_code=200,
                headers={"content-type": "text/html"},
                content=b"<p>Floating paragraph without html root tag</p>",
                redirect_history=[],
            )
            with patch.object(live_compare, "safe_fetch_async", new_callable=AsyncMock) as mock_fetch:
                mock_fetch.side_effect = [res_malformed, res_ok]
                r_mal = await client.post("/api/compare-urls", json={"url1": "https://example.com/1", "url2": "https://example.com/2"})
                assert r_mal.status_code == 422
                assert "<html>" in r_mal.json()["detail"]

    asyncio.run(_test())


def test_api_compare_urls_temporary_directory_cleanup():
    """Verify that TemporaryDirectory is cleaned up after both success and failure."""
    async def _test():
        res1 = SafeFetchResult(
            url="https://example.com/v1",
            status_code=200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=V1_FILE.read_bytes(),
            redirect_history=[],
        )
        res2 = SafeFetchResult(
            url="https://example.com/v2",
            status_code=200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=V2_FILE.read_bytes(),
            redirect_history=[],
        )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            temp_root = Path(tempfile.gettempdir())

            # Baseline count before request
            before_dirs = set(temp_root.glob("webpage-compare-urls-*"))

            with patch.object(live_compare, "safe_fetch_async", new_callable=AsyncMock) as mock_fetch:
                mock_fetch.side_effect = [res1, res2]
                resp = await client.post("/api/compare-urls", json={"url1": "https://example.com/1", "url2": "https://example.com/2"})
                assert resp.status_code == 200

            # Count after success
            after_success = set(temp_root.glob("webpage-compare-urls-*"))
            assert len(after_success - before_dirs) == 0

            # Count after failure
            with patch.object(live_compare, "safe_fetch_async", new_callable=AsyncMock) as mock_fetch:
                mock_fetch.side_effect = DNSResolutionError("DNS error")
                resp = await client.post("/api/compare-urls", json={"url1": "https://example.com/1", "url2": "https://example.com/2"})
                assert resp.status_code == 502

            after_failure = set(temp_root.glob("webpage-compare-urls-*"))
            assert len(after_failure - before_dirs) == 0

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
