"""Unit and integration tests for Milestone 5C: Wayback Machine FastAPI endpoints.

Tests:
1. GET /api/wayback/snapshots:
   - Successful snapshot discovery with full response schema validation.
   - Empty snapshot history handling.
   - Valid year filtering (from_year, to_year).
   - Inverted year range rejection (from_year > to_year -> 400).
   - Out-of-bounds year rejection (< 1996 or > 2099 -> 400).
   - Invalid URL and missing scheme rejection (400).
   - Blocked private IP / SSRF rejection (400).
   - Upstream CDX failure mapping (502).
   - Off-host redirect rejection (502).
   - Request timeout mapping (504).

2. POST /api/wayback/compare:
   - End-to-end historical comparison with verified snapshot labels and NLP enrichment.
   - Identical timestamps rejection (400).
   - Malformed timestamp format rejection (400).
   - Snapshot not found mapping (404).
   - Fallback/nearest timestamp redirect conflict mapping (409).
   - Non-HTML / empty captured content mapping (422).
   - Snapshot verification failure mapping (422).
   - Off-host redirect violation mapping (502).
   - Upstream network / CDX fetch error mapping (502).
   - Request timeout mapping (504).
   - Temporary directory cleanup on success and failure.
   - NLP failure safe fallback preservation.

3. Regressions & Endpoint Retirement:
   - Baseline file upload POST /api/compare.
   - Retirement verification for POST /api/compare-urls (returns 404).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import tempfile
from unittest.mock import AsyncMock, patch

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

from api import app
import api
from security.redirect_handler import SafeFetchResult
from security.ssrf_validator import ResourceLimitError
from wayback_client import (
    FallbackRedirectError,
    OffHostRedirectError,
    SnapshotNotFoundError,
    WaybackCDXError,
    WaybackContentError,
    WaybackFetchError,
    WaybackSnapshot,
    WaybackSnapshotsResponse,
    WaybackVerificationError,
)

V1_FILE = TEST_FILES_DIR / "mini project version 1.html"
V2_FILE = TEST_FILES_DIR / "mini project version 2.html"


# ============================================================================
# 1. GET /api/wayback/snapshots Discovery Endpoint Tests
# ============================================================================

def test_api_snapshots_discovery_success():
    """Verify successful snapshot discovery and full response schema conformity."""
    async def _test():
        mock_response = WaybackSnapshotsResponse(
            url="https://example.com/page",
            total_returned=2,
            is_limited=False,
            collapse="monthly",
            snapshots=[
                WaybackSnapshot(
                    timestamp="20200115120000",
                    datetime="2020-01-15T12:00:00Z",
                    display_date="Jan 15, 2020 12:00 UTC",
                    original_url="https://example.com/page",
                    status_code=200,
                    mimetype="text/html",
                ),
                WaybackSnapshot(
                    timestamp="20210620183000",
                    datetime="2021-06-20T18:30:00Z",
                    display_date="Jun 20, 2021 18:30 UTC",
                    original_url="https://example.com/page",
                    status_code=200,
                    mimetype="text/html",
                ),
            ],
        )

        with patch("api.discover_wayback_snapshots", new_callable=AsyncMock) as mock_discover:
            mock_discover.return_value = mock_response

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/wayback/snapshots", params={"url": "https://example.com/page"})
                assert resp.status_code == 200
                data = resp.json()

                assert data["url"] == "https://example.com/page"
                assert data["total_returned"] == 2
                assert data["is_limited"] is False
                assert data["collapse"] == "monthly"
                assert len(data["snapshots"]) == 2

                snap1 = data["snapshots"][0]
                assert snap1["timestamp"] == "20200115120000"
                assert snap1["datetime"] == "2020-01-15T12:00:00Z"
                assert snap1["display_date"] == "Jan 15, 2020 12:00 UTC"
                assert snap1["original_url"] == "https://example.com/page"
                assert snap1["status_code"] == 200
                assert snap1["mimetype"] == "text/html"

    asyncio.run(_test())


def test_api_snapshots_discovery_empty():
    """Verify empty snapshot history returns 200 with empty list."""
    async def _test():
        mock_response = WaybackSnapshotsResponse(
            url="https://rare-page.com",
            total_returned=0,
            is_limited=False,
            collapse="monthly",
            snapshots=[],
        )

        with patch("api.discover_wayback_snapshots", new_callable=AsyncMock) as mock_discover:
            mock_discover.return_value = mock_response

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/wayback/snapshots", params={"url": "https://rare-page.com"})
                assert resp.status_code == 200
                data = resp.json()
                assert data["total_returned"] == 0
                assert data["snapshots"] == []
                assert data["is_limited"] is False

    asyncio.run(_test())


def test_api_snapshots_discovery_year_filtering():
    """Verify valid from_year and to_year query parameters are parsed and passed."""
    async def _test():
        mock_response = WaybackSnapshotsResponse(
            url="https://example.com",
            total_returned=1,
            is_limited=False,
            collapse="monthly",
            snapshots=[
                WaybackSnapshot(
                    timestamp="20050505120000",
                    datetime="2005-05-05T12:00:00Z",
                    display_date="May 05, 2005 12:00 UTC",
                    original_url="https://example.com/",
                    status_code=200,
                    mimetype="text/html",
                )
            ],
        )

        with patch("api.discover_wayback_snapshots", new_callable=AsyncMock) as mock_discover:
            mock_discover.return_value = mock_response

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    "/api/wayback/snapshots",
                    params={"url": "https://example.com", "from_year": 2000, "to_year": 2010},
                )
                assert resp.status_code == 200
                assert mock_discover.call_count == 1
                req_arg = mock_discover.call_args[0][0]
                assert req_arg.from_year == 2000
                assert req_arg.to_year == 2010

    asyncio.run(_test())


def test_api_snapshots_discovery_invalid_year_range():
    """Verify from_year > to_year returns 400 Bad Request."""
    async def _test():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/wayback/snapshots",
                params={"url": "https://example.com", "from_year": 2020, "to_year": 2010},
            )
            assert resp.status_code == 400
            assert "from_year" in resp.json()["detail"].lower()

    asyncio.run(_test())


def test_api_snapshots_discovery_out_of_bounds_year():
    """Verify years outside 1996-2099 return 400 Bad Request."""
    async def _test():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Year before 1996
            r1 = await client.get("/api/wayback/snapshots", params={"url": "https://example.com", "from_year": 1990})
            assert r1.status_code == 400
            assert "1996-2099" in r1.json()["detail"]

            # Year after 2099
            r2 = await client.get("/api/wayback/snapshots", params={"url": "https://example.com", "to_year": 2150})
            assert r2.status_code == 400
            assert "1996-2099" in r2.json()["detail"]

    asyncio.run(_test())


def test_api_snapshots_discovery_invalid_url():
    """Verify malformed URLs and unsupported schemes return 400 Bad Request."""
    async def _test():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Missing scheme
            r1 = await client.get("/api/wayback/snapshots", params={"url": "example.com"})
            assert r1.status_code == 400
            assert "scheme" in r1.json()["detail"].lower()

            # FTP scheme
            r2 = await client.get("/api/wayback/snapshots", params={"url": "ftp://example.com"})
            assert r2.status_code == 400
            assert "scheme" in r2.json()["detail"].lower()

            # Empty string
            r3 = await client.get("/api/wayback/snapshots", params={"url": "   "})
            assert r3.status_code == 400
            assert "non-empty string" in r3.json()["detail"].lower()

    asyncio.run(_test())


def test_api_snapshots_discovery_blocked_ips():
    """Verify SSRF/private IPs and localhost return 400 Bad Request."""
    async def _test():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r1 = await client.get("/api/wayback/snapshots", params={"url": "http://127.0.0.1:8000"})
            assert r1.status_code == 400
            assert "forbidden" in r1.json()["detail"].lower() or "loopback" in r1.json()["detail"].lower()

            r2 = await client.get("/api/wayback/snapshots", params={"url": "http://localhost/test"})
            assert r2.status_code == 400
            assert "blocked" in r2.json()["detail"].lower() or "prohibited" in r2.json()["detail"].lower()

    asyncio.run(_test())


def test_api_snapshots_discovery_upstream_failure():
    """Verify CDX errors map cleanly to 502 Bad Gateway."""
    async def _test():
        with patch("api.discover_wayback_snapshots", new_callable=AsyncMock) as mock_discover:
            mock_discover.side_effect = WaybackCDXError("CDX service returned HTTP 500.", status_code=500)

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/wayback/snapshots", params={"url": "https://example.com"})
                assert resp.status_code == 502
                assert "Upstream CDX service error" in resp.json()["detail"]

    asyncio.run(_test())


def test_api_snapshots_discovery_off_host_redirect():
    """Verify off-host redirects map cleanly to 502 Bad Gateway."""
    async def _test():
        with patch("api.discover_wayback_snapshots", new_callable=AsyncMock) as mock_discover:
            mock_discover.side_effect = OffHostRedirectError("Redirected to evil.com", destination_url="https://evil.com")

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/wayback/snapshots", params={"url": "https://example.com"})
                assert resp.status_code == 502
                assert "Wayback security violation" in resp.json()["detail"]

    asyncio.run(_test())


def test_api_snapshots_discovery_timeout():
    """Verify timeout errors map cleanly to 504 Gateway Timeout."""
    async def _test():
        with patch("api.discover_wayback_snapshots", new_callable=AsyncMock) as mock_discover:
            mock_discover.side_effect = ResourceLimitError("Overall request deadline (15.0s) exceeded.")

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/wayback/snapshots", params={"url": "https://example.com"})
                assert resp.status_code == 504
                assert "Gateway timeout" in resp.json()["detail"]

    asyncio.run(_test())


# ============================================================================
# 2. POST /api/wayback/compare Comparison Endpoint Tests
# ============================================================================

def test_api_wayback_compare_success_and_labels():
    """Verify end-to-end historical comparison, exact version labels, and NLP enrichment."""
    async def _test():
        snap1 = WaybackSnapshot(
            timestamp="20020120142510",
            datetime="2002-01-20T14:25:10Z",
            display_date="Jan 20, 2002 14:25 UTC",
            original_url="http://example.com:80/",
            status_code=200,
            mimetype="text/html",
        )
        snap2 = WaybackSnapshot(
            timestamp="20220120142510",
            datetime="2022-01-20T14:25:10Z",
            display_date="Jan 20, 2022 14:25 UTC",
            original_url="http://example.com/",
            status_code=200,
            mimetype="text/html",
        )

        res1 = SafeFetchResult(
            url="https://web.archive.org/web/20020120142510id_/http://example.com:80/",
            status_code=200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=V1_FILE.read_bytes(),
            redirect_history=[],
        )
        res2 = SafeFetchResult(
            url="https://web.archive.org/web/20220120142510id_/http://example.com/",
            status_code=200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=V2_FILE.read_bytes(),
            redirect_history=[],
        )

        with patch("api.verify_and_resolve_snapshots", new_callable=AsyncMock) as mock_verify, \
             patch("api.fetch_wayback_raw_pair", new_callable=AsyncMock) as mock_fetch:

            mock_verify.return_value = (snap1, snap2)
            mock_fetch.return_value = (res1, res2)

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/wayback/compare",
                    json={
                        "url": "https://example.com",
                        "timestamp1": "20020120142510",
                        "timestamp2": "20220120142510",
                    },
                )

                assert resp.status_code == 200
                data = resp.json()

                # Verify descriptive version labels using snapshot metadata
                expected_label1 = "http://example.com:80/ (20020120142510 - Jan 20, 2002 14:25 UTC)"
                expected_label2 = "http://example.com/ (20220120142510 - Jan 20, 2022 14:25 UTC)"
                assert data["version1"]["label"] == expected_label1
                assert data["version2"]["label"] == expected_label2
                assert data["version1"]["timestamp"] == "20020120142510"
                assert data["version1"]["displayDate"] == "Jan 20, 2002 14:25 UTC"
                assert data["version2"]["timestamp"] == "20220120142510"
                assert data["version2"]["displayDate"] == "Jan 20, 2022 14:25 UTC"

                # Verify exact snapshot verification context and replay URLs
                assert "waybackContext" in data
                assert data["waybackContext"]["targetUrl"] == "https://example.com"
                assert data["waybackContext"]["version1"]["timestamp"] == "20020120142510"
                assert data["waybackContext"]["version2"]["timestamp"] == "20220120142510"
                assert data["waybackContext"]["version1"]["replayUrl"].startswith("https://web.archive.org/web/20020120142510/")
                assert data["waybackContext"]["version2"]["replayUrl"].startswith("https://web.archive.org/web/20220120142510/")
                assert data["waybackContext"]["version1"]["rawReplayUrl"].startswith("https://web.archive.org/web/20020120142510id_/")
                assert data["waybackContext"]["version2"]["rawReplayUrl"].startswith("https://web.archive.org/web/20220120142510id_/")

                # Verify structural engine results match test files
                assert data["presentationSummary"]["total"] == 21
                assert data["presentationSummary"]["added"] == 8
                assert data["presentationSummary"]["removed"] == 1
                assert data["presentationSummary"]["modified"] == 12

                # Verify NLP semantic analysis layer attached
                assert "nlpAnalysis" in data
                assert "overall" in data["nlpAnalysis"]
                assert data["nlpAnalysis"]["overall"]["total_modifications_analyzed"] == 12

    asyncio.run(_test())


def test_api_wayback_compare_identical_timestamps():
    """Verify comparing identical timestamps returns 400 Bad Request."""
    async def _test():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/wayback/compare",
                json={
                    "url": "https://example.com",
                    "timestamp1": "20200101120000",
                    "timestamp2": "20200101120000",
                },
            )
            assert resp.status_code == 400
            assert "different" in resp.json()["detail"].lower()

    asyncio.run(_test())


def test_api_wayback_compare_invalid_timestamps():
    """Verify malformed timestamps return 400 Bad Request."""
    async def _test():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Too short
            r1 = await client.post(
                "/api/wayback/compare",
                json={"url": "https://example.com", "timestamp1": "20200101", "timestamp2": "20210101120000"},
            )
            assert r1.status_code == 400
            assert "14 digits" in r1.json()["detail"]

            # Non-digits
            r2 = await client.post(
                "/api/wayback/compare",
                json={"url": "https://example.com", "timestamp1": "202001011200ab", "timestamp2": "20210101120000"},
            )
            assert r2.status_code == 400
            assert "14 digits" in r2.json()["detail"]

    asyncio.run(_test())


def test_api_wayback_compare_missing_snapshot_404():
    """Verify missing snapshot in CDX maps to 404 Not Found."""
    async def _test():
        with patch("api.verify_and_resolve_snapshots", new_callable=AsyncMock) as mock_verify:
            mock_verify.side_effect = SnapshotNotFoundError("Snapshot for timestamp '19990101120000' not found.")

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/wayback/compare",
                    json={
                        "url": "https://example.com",
                        "timestamp1": "19990101120000",
                        "timestamp2": "20210101120000",
                    },
                )
                assert resp.status_code == 404
                assert "Snapshot not found" in resp.json()["detail"]

    asyncio.run(_test())


def test_api_wayback_compare_fallback_redirect_409():
    """Verify fallback nearest-timestamp redirect maps to 409 Conflict."""
    async def _test():
        snap1 = WaybackSnapshot(
            timestamp="20200101120000",
            datetime="2020-01-01T12:00:00Z",
            display_date="Jan 01, 2020 12:00 UTC",
            original_url="https://example.com/",
            status_code=200,
            mimetype="text/html",
        )
        snap2 = WaybackSnapshot(
            timestamp="20210101120000",
            datetime="2021-01-01T12:00:00Z",
            display_date="Jan 01, 2021 12:00 UTC",
            original_url="https://example.com/",
            status_code=200,
            mimetype="text/html",
        )

        with patch("api.verify_and_resolve_snapshots", new_callable=AsyncMock) as mock_verify, \
             patch("api.fetch_wayback_raw_pair", new_callable=AsyncMock) as mock_fetch:

            mock_verify.return_value = (snap1, snap2)
            mock_fetch.side_effect = FallbackRedirectError(
                "Snapshot 1 redirected to fallback timestamp '20200102000000' instead of '20200101120000'.",
                requested_timestamp="20200101120000",
                resolved_url="https://web.archive.org/web/20200102000000id_/https://example.com/",
            )

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/wayback/compare",
                    json={
                        "url": "https://example.com",
                        "timestamp1": "20200101120000",
                        "timestamp2": "20210101120000",
                    },
                )
                assert resp.status_code == 409
                assert "Exact capture unavailable" in resp.json()["detail"]

    asyncio.run(_test())


def test_api_wayback_compare_non_html_response_422():
    """Verify non-HTML captured replay maps to 422 Unprocessable Entity."""
    async def _test():
        snap1 = WaybackSnapshot(
            timestamp="20200101120000",
            datetime="2020-01-01T12:00:00Z",
            display_date="Jan 01, 2020 12:00 UTC",
            original_url="https://example.com/",
            status_code=200,
            mimetype="text/html",
        )
        snap2 = WaybackSnapshot(
            timestamp="20210101120000",
            datetime="2021-01-01T12:00:00Z",
            display_date="Jan 01, 2021 12:00 UTC",
            original_url="https://example.com/",
            status_code=200,
            mimetype="text/html",
        )

        with patch("api.verify_and_resolve_snapshots", new_callable=AsyncMock) as mock_verify, \
             patch("api.fetch_wayback_raw_pair", new_callable=AsyncMock) as mock_fetch:

            mock_verify.return_value = (snap1, snap2)
            mock_fetch.side_effect = WaybackContentError(
                "Snapshot 1 (20200101120000) failed HTML validation: Non-HTML MIME type 'application/pdf'."
            )

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/wayback/compare",
                    json={
                        "url": "https://example.com",
                        "timestamp1": "20200101120000",
                        "timestamp2": "20210101120000",
                    },
                )
                assert resp.status_code == 422
                assert "Archived HTML validation failed" in resp.json()["detail"]

    asyncio.run(_test())


def test_api_wayback_compare_verification_failed_422():
    """Verify verification failure (non-200 or non-HTML in CDX) maps to 422."""
    async def _test():
        with patch("api.verify_and_resolve_snapshots", new_callable=AsyncMock) as mock_verify:
            mock_verify.side_effect = WaybackVerificationError(
                "Snapshot '20200101120000' has non-successful HTTP status code 404.",
                timestamp="20200101120000",
                status_code=404,
            )

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/wayback/compare",
                    json={
                        "url": "https://example.com",
                        "timestamp1": "20200101120000",
                        "timestamp2": "20210101120000",
                    },
                )
                assert resp.status_code == 422
                assert "Snapshot verification failed" in resp.json()["detail"]

    asyncio.run(_test())


def test_api_wayback_compare_off_host_redirect_502():
    """Verify off-host redirect rejection maps to 502 Bad Gateway."""
    async def _test():
        with patch("api.verify_and_resolve_snapshots", new_callable=AsyncMock) as mock_verify:
            mock_verify.side_effect = OffHostRedirectError(
                "Wayback request to unauthorized host 'attacker.com' is rejected.",
                destination_url="https://attacker.com/evil",
            )

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/wayback/compare",
                    json={
                        "url": "https://example.com",
                        "timestamp1": "20200101120000",
                        "timestamp2": "20210101120000",
                    },
                )
                assert resp.status_code == 502
                assert "Wayback security violation" in resp.json()["detail"]

    asyncio.run(_test())


def test_api_wayback_compare_upstream_failure_502():
    """Verify upstream fetch errors map cleanly to 502 Bad Gateway."""
    async def _test():
        with patch("api.verify_and_resolve_snapshots", new_callable=AsyncMock) as mock_verify:
            mock_verify.side_effect = WaybackFetchError("Wayback server connection reset.")

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/wayback/compare",
                    json={
                        "url": "https://example.com",
                        "timestamp1": "20200101120000",
                        "timestamp2": "20210101120000",
                    },
                )
                assert resp.status_code == 502
                assert "Upstream Wayback service failed" in resp.json()["detail"]

    asyncio.run(_test())


def test_api_wayback_compare_timeout_504():
    """Verify comparison deadline timeout maps to 504 Gateway Timeout."""
    async def _test():
        with patch("api.verify_and_resolve_snapshots", new_callable=AsyncMock) as mock_verify:
            mock_verify.side_effect = ResourceLimitError("Overall request deadline (15.0s) exceeded.")

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/wayback/compare",
                    json={
                        "url": "https://example.com",
                        "timestamp1": "20200101120000",
                        "timestamp2": "20210101120000",
                    },
                )
                assert resp.status_code == 504
                assert "Gateway timeout" in resp.json()["detail"]

    asyncio.run(_test())


def test_api_wayback_compare_tempdir_cleanup():
    """Verify TemporaryDirectory is cleaned up on both success and engine failure."""
    async def _test():
        snap1 = WaybackSnapshot(
            timestamp="20020120142510",
            datetime="2002-01-20T14:25:10Z",
            display_date="Jan 20, 2002 14:25 UTC",
            original_url="http://example.com:80/",
            status_code=200,
            mimetype="text/html",
        )
        snap2 = WaybackSnapshot(
            timestamp="20220120142510",
            datetime="2022-01-20T14:25:10Z",
            display_date="Jan 20, 2022 14:25 UTC",
            original_url="http://example.com/",
            status_code=200,
            mimetype="text/html",
        )

        res1 = SafeFetchResult(
            url="https://web.archive.org/web/20020120142510id_/http://example.com:80/",
            status_code=200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=V1_FILE.read_bytes(),
            redirect_history=[],
        )
        res2 = SafeFetchResult(
            url="https://web.archive.org/web/20220120142510id_/http://example.com/",
            status_code=200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=V2_FILE.read_bytes(),
            redirect_history=[],
        )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            temp_root = Path(tempfile.gettempdir())
            before_dirs = set(temp_root.glob("webpage-compare-wayback-*"))

            # 1. Success case
            with patch("api.verify_and_resolve_snapshots", new_callable=AsyncMock) as mock_verify, \
                 patch("api.fetch_wayback_raw_pair", new_callable=AsyncMock) as mock_fetch:

                mock_verify.return_value = (snap1, snap2)
                mock_fetch.return_value = (res1, res2)

                resp = await client.post(
                    "/api/wayback/compare",
                    json={"url": "https://example.com", "timestamp1": "20020120142510", "timestamp2": "20220120142510"},
                )
                assert resp.status_code == 200

            after_success = set(temp_root.glob("webpage-compare-wayback-*"))
            assert len(after_success - before_dirs) == 0

            # 2. Failure during engine execution
            with patch("api.verify_and_resolve_snapshots", new_callable=AsyncMock) as mock_verify, \
                 patch("api.fetch_wayback_raw_pair", new_callable=AsyncMock) as mock_fetch, \
                 patch("api._run_existing_engine", side_effect=RuntimeError("Engine failure")):

                mock_verify.return_value = (snap1, snap2)
                mock_fetch.return_value = (res1, res2)

                resp = await client.post(
                    "/api/wayback/compare",
                    json={"url": "https://example.com", "timestamp1": "20020120142510", "timestamp2": "20220120142510"},
                )
                assert resp.status_code == 500

            after_failure = set(temp_root.glob("webpage-compare-wayback-*"))
            assert len(after_failure - before_dirs) == 0

    asyncio.run(_test())


def test_api_wayback_compare_nlp_failure_fallback():
    """Verify that unexpected NLP failure preserves valid structural comparison results."""
    async def _test():
        snap1 = WaybackSnapshot(
            timestamp="20020120142510",
            datetime="2002-01-20T14:25:10Z",
            display_date="Jan 20, 2002 14:25 UTC",
            original_url="http://example.com:80/",
            status_code=200,
            mimetype="text/html",
        )
        snap2 = WaybackSnapshot(
            timestamp="20220120142510",
            datetime="2022-01-20T14:25:10Z",
            display_date="Jan 20, 2022 14:25 UTC",
            original_url="http://example.com/",
            status_code=200,
            mimetype="text/html",
        )

        res1 = SafeFetchResult(
            url="https://web.archive.org/web/20020120142510id_/http://example.com:80/",
            status_code=200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=V1_FILE.read_bytes(),
            redirect_history=[],
        )
        res2 = SafeFetchResult(
            url="https://web.archive.org/web/20220120142510id_/http://example.com/",
            status_code=200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=V2_FILE.read_bytes(),
            redirect_history=[],
        )

        with patch("api.verify_and_resolve_snapshots", new_callable=AsyncMock) as mock_verify, \
             patch("api.fetch_wayback_raw_pair", new_callable=AsyncMock) as mock_fetch, \
             patch("api.attach_nlp_analysis", side_effect=Exception("Unexpected NLP pipeline crash")):

            mock_verify.return_value = (snap1, snap2)
            mock_fetch.return_value = (res1, res2)

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/wayback/compare",
                    json={"url": "https://example.com", "timestamp1": "20020120142510", "timestamp2": "20220120142510"},
                )

                # Status is still 200 because structural comparison succeeded
                assert resp.status_code == 200
                data = resp.json()
                assert data["presentationSummary"]["total"] == 21

    asyncio.run(_test())


# ============================================================================
# 3. Regression Tests for Existing Endpoints
# ============================================================================

def test_regression_existing_upload_compare():
    """Verify existing multipart file upload POST /api/compare continues to work."""
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


def test_compare_urls_endpoint_is_retired():
    """Verify that the retired two-URL endpoint POST /api/compare-urls is no longer exposed (returns 404)."""
    async def _test():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/compare-urls",
                json={"url1": "https://example.com/live-v1", "url2": "https://example.com/live-v2"},
            )
            assert resp.status_code == 404

    asyncio.run(_test())

