"""Unit tests for Milestone 5B: Backend Wayback Client & Verification Service.

Tests:
1. CDX parsing (normal, empty, header-only, malformed JSON, missing columns, invalid timestamps, non-200/non-HTML filtering).
2. Discovery ordering & limits (limit=-51, valid-row truncation detection is_limited, <=50 returned, year filtering,
   invalid row resilience).
3. Capture verification (exact point verification, missing snapshot, mismatched URL, non-200, non-HTML, identical timestamps).
4. Raw replay URL construction & retrieval (CDX original URL preservation, scheme/port/query handling, exact timestamp acceptance,
   fallback redirect rejection, off-host redirect rejection before navigation, unsafe original URL rejection,
   non-HTML/empty response rejection, anchored path timestamp validation, deceptive query/fragment rejection).
5. Concurrency & task lifecycle management (immediate cancellation of sibling tasks on failure, cleanup of cancelled tasks,
   transparent exception attribution).
6. Strict hostname allowlist (exact allowlist, rejection of arbitrary subdomains, rejection of suffix tricks,
   case-insensitivity, trailing-dot canonicalization).
7. Input models & validation (SSRF target validation, timestamp formats, year range ordering).

All tests mock upstream responses and do not depend on external Internet Archive network availability.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
from unittest.mock import AsyncMock, MagicMock, patch
import urllib.parse

import httpx
import pytest
from pydantic import ValidationError

# Ensure comparison-engine root and src are on sys.path
COMPARISON_ENGINE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = COMPARISON_ENGINE_DIR / "src"

for d in (str(COMPARISON_ENGINE_DIR), str(SRC_DIR)):
    if d not in sys.path:
        sys.path.insert(0, d)

import wayback_client
from wayback_client import (
    ALLOWED_WAYBACK_HOSTS,
    CDX_BASE_URL,
    FallbackRedirectError,
    InvalidWaybackURLError,
    OffHostRedirectError,
    SnapshotNotFoundError,
    WaybackCDXError,
    WaybackCompareRequest,
    WaybackContentError,
    WaybackError,
    WaybackFetchError,
    WaybackSnapshot,
    WaybackSnapshotsRequest,
    WaybackSnapshotsResponse,
    WaybackVerificationError,
    build_wayback_replay_url,
    discover_wayback_snapshots,
    extract_replay_timestamp,
    fetch_single_wayback_capture,
    fetch_wayback_raw_pair,
    format_timestamp,
    is_allowed_wayback_host,
    safe_fetch_wayback_async,
    validate_capture_original_url,
    validate_timestamp_format,
    validate_wayback_destination_host,
    verify_and_resolve_snapshots,
    verify_snapshot_timestamp,
)
from security.redirect_handler import SafeFetchResult
from security.ssrf_validator import (
    BlockedIPError,
    InvalidURLError,
    RedirectSecurityError,
    ResourceLimitError,
)

VALID_HTML_BYTES = b"<!DOCTYPE html><html><head><title>Test</title></head><body><h1>Hello</h1></body></html>"
VALID_HTML_BYTES_V2 = b"<!DOCTYPE html><html><head><title>Test V2</title></head><body><h1>Hello V2</h1></body></html>"


def make_mock_result(
    url: str,
    status_code: int = 200,
    content: bytes = b"",
    headers: dict[str, str] | None = None,
    redirect_history: list[str] | None = None,
) -> SafeFetchResult:
    """Helper to create a SafeFetchResult for testing."""
    hdrs = httpx.Headers({"content-type": "text/html; charset=utf-8"})
    if headers:
        hdrs.update(headers)
    return SafeFetchResult(
        url=url,
        status_code=status_code,
        headers=hdrs,
        content=content,
        redirect_history=redirect_history or [],
    )


# ============================================================================
# 1. CDX Parsing Tests
# ============================================================================

def test_cdx_parse_normal():
    """Verify normal 2D CDX JSON array is parsed into structured WaybackSnapshot models."""
    async def _test():
        cdx_data = [
            ["timestamp", "original", "mimetype", "statuscode", "length"],
            ["20020120142510", "http://example.com:80/", "text/html", "200", "1234"],
            ["20220615103000", "https://example.com/", "text/html", "200", "5678"],
        ]
        mock_res = make_mock_result(
            url="https://web.archive.org/cdx/search/cdx",
            status_code=200,
            content=json.dumps(cdx_data).encode("utf-8"),
            headers={"content-type": "application/json"},
        )
        mock_fetcher = AsyncMock(return_value=mock_res)

        req = WaybackSnapshotsRequest(url="https://example.com")
        resp = await discover_wayback_snapshots(req, fetcher=mock_fetcher)

        assert resp.url == "https://example.com"
        assert resp.total_returned == 2
        assert resp.is_limited is False
        assert resp.collapse == "monthly"
        assert len(resp.snapshots) == 2

        s1 = resp.snapshots[0]
        assert s1.timestamp == "20020120142510"
        assert s1.datetime == "2002-01-20T14:25:10Z"
        assert "Jan 20, 2002" in s1.display_date
        assert s1.original_url == "http://example.com:80/"
        assert s1.status_code == 200
        assert s1.mimetype == "text/html"

    asyncio.run(_test())


def test_cdx_parse_empty():
    """Verify empty string or '[]' response returns 0 snapshots without error."""
    async def _test():
        for empty_content in (b"", b"[]", b"  []  \n"):
            mock_res = make_mock_result(
                url="https://web.archive.org/cdx/search/cdx",
                status_code=200,
                content=empty_content,
            )
            mock_fetcher = AsyncMock(return_value=mock_res)
            req = WaybackSnapshotsRequest(url="https://example.com")
            resp = await discover_wayback_snapshots(req, fetcher=mock_fetcher)
            assert resp.total_returned == 0
            assert resp.is_limited is False
            assert resp.snapshots == []

    asyncio.run(_test())


def test_cdx_parse_header_only():
    """Verify CDX response with only the header row returns 0 snapshots."""
    async def _test():
        cdx_data = [["timestamp", "original", "mimetype", "statuscode", "length"]]
        mock_res = make_mock_result(
            url="https://web.archive.org/cdx/search/cdx",
            status_code=200,
            content=json.dumps(cdx_data).encode("utf-8"),
        )
        mock_fetcher = AsyncMock(return_value=mock_res)
        req = WaybackSnapshotsRequest(url="https://example.com")
        resp = await discover_wayback_snapshots(req, fetcher=mock_fetcher)
        assert resp.total_returned == 0
        assert resp.is_limited is False
        assert resp.snapshots == []

    asyncio.run(_test())


def test_cdx_parse_malformed_json():
    """Verify non-JSON CDX response raises WaybackCDXError."""
    async def _test():
        mock_res = make_mock_result(
            url="https://web.archive.org/cdx/search/cdx",
            status_code=200,
            content=b"<!DOCTYPE html><html><body>Error 500 Server Error</body></html>",
        )
        mock_fetcher = AsyncMock(return_value=mock_res)
        req = WaybackSnapshotsRequest(url="https://example.com")
        with pytest.raises(WaybackCDXError, match="malformed JSON"):
            await discover_wayback_snapshots(req, fetcher=mock_fetcher)

    asyncio.run(_test())


def test_cdx_parse_missing_columns():
    """Verify CDX header missing required column raises WaybackCDXError."""
    async def _test():
        cdx_data = [
            ["timestamp", "mimetype", "statuscode"],  # Missing 'original'
            ["20020120142510", "text/html", "200"],
        ]
        mock_res = make_mock_result(
            url="https://web.archive.org/cdx/search/cdx",
            status_code=200,
            content=json.dumps(cdx_data).encode("utf-8"),
        )
        mock_fetcher = AsyncMock(return_value=mock_res)
        req = WaybackSnapshotsRequest(url="https://example.com")
        with pytest.raises(WaybackCDXError, match="missing required column 'original'"):
            await discover_wayback_snapshots(req, fetcher=mock_fetcher)

    asyncio.run(_test())


def test_cdx_parse_invalid_timestamp():
    """Verify rows with invalid or malformed timestamps are filtered out."""
    async def _test():
        cdx_data = [
            ["timestamp", "original", "mimetype", "statuscode", "length"],
            ["not-a-timestamp", "https://example.com/", "text/html", "200", "123"],
            ["20021332142510", "https://example.com/", "text/html", "200", "123"],  # Invalid month 13
            ["20020120142510", "https://example.com/", "text/html", "200", "123"],  # Valid
        ]
        mock_res = make_mock_result(
            url="https://web.archive.org/cdx/search/cdx",
            status_code=200,
            content=json.dumps(cdx_data).encode("utf-8"),
        )
        mock_fetcher = AsyncMock(return_value=mock_res)
        req = WaybackSnapshotsRequest(url="https://example.com")
        resp = await discover_wayback_snapshots(req, fetcher=mock_fetcher)
        assert resp.total_returned == 1
        assert resp.snapshots[0].timestamp == "20020120142510"

    asyncio.run(_test())


def test_cdx_parse_non_200_and_non_html():
    """Verify non-200 or non-HTML rows returned by CDX are filtered out."""
    async def _test():
        cdx_data = [
            ["timestamp", "original", "mimetype", "statuscode", "length"],
            ["20020120142510", "https://example.com/", "text/html", "302", "123"],  # Non-200
            ["20030120142510", "https://example.com/", "application/pdf", "200", "123"],  # Non-HTML
            ["20040120142510", "https://example.com/", "image/png", "200", "123"],  # Non-HTML
            ["20050120142510", "https://example.com/", "text/html; charset=utf-8", "200", "123"],  # Valid
        ]
        mock_res = make_mock_result(
            url="https://web.archive.org/cdx/search/cdx",
            status_code=200,
            content=json.dumps(cdx_data).encode("utf-8"),
        )
        mock_fetcher = AsyncMock(return_value=mock_res)
        req = WaybackSnapshotsRequest(url="https://example.com")
        resp = await discover_wayback_snapshots(req, fetcher=mock_fetcher)
        assert resp.total_returned == 1
        assert resp.snapshots[0].timestamp == "20050120142510"

    asyncio.run(_test())


# ============================================================================
# 2. Discovery Ordering, Limits & Valid Row Truncation (Correction 4)
# ============================================================================

def test_discovery_query_parameters():
    """Verify CDX discovery query uses limit=-51, collapse=timestamp:6, and filter parameters."""
    async def _test():
        captured_urls: list[str] = []

        async def mock_fetcher(url: str, **kwargs):
            captured_urls.append(url)
            return make_mock_result(url=url, content=b"[]")

        req = WaybackSnapshotsRequest(url="https://example.com/test", from_year=2000, to_year=2010)
        await discover_wayback_snapshots(req, fetcher=mock_fetcher)

        assert len(captured_urls) == 1
        called_url = captured_urls[0]
        parsed = urllib.parse.urlsplit(called_url)
        qs = urllib.parse.parse_qs(parsed.query)

        assert qs["limit"] == ["-51"]
        assert qs["collapse"] == ["timestamp:6"]
        assert qs["output"] == ["json"]
        assert qs["fl"] == ["timestamp,original,mimetype,statuscode,length"]
        assert qs["from"] == ["20000101000000"]
        assert qs["to"] == ["20101231235959"]
        assert "statuscode:200" in qs["filter"]
        assert "mimetype:text/html" in qs["filter"]

    asyncio.run(_test())


def test_discovery_51_valid_rows_is_limited_true():
    """Correction 4: 51 valid rows returns 50, is_limited=True."""
    async def _test():
        header = ["timestamp", "original", "mimetype", "statuscode", "length"]
        rows = []
        for i in range(1, 52):  # 51 valid rows
            ts = f"20{i:02d}0101120000"
            rows.append([ts, "https://example.com/", "text/html", "200", "100"])

        cdx_data = [header] + rows
        mock_res = make_mock_result(
            url="https://web.archive.org/cdx/search/cdx",
            status_code=200,
            content=json.dumps(cdx_data).encode("utf-8"),
        )
        mock_fetcher = AsyncMock(return_value=mock_res)
        req = WaybackSnapshotsRequest(url="https://example.com")
        resp = await discover_wayback_snapshots(req, fetcher=mock_fetcher)

        assert resp.total_returned == 50
        assert len(resp.snapshots) == 50
        assert resp.is_limited is True
        assert resp.snapshots[0].timestamp == "20010101120000"
        assert resp.snapshots[-1].timestamp == "20500101120000"

    asyncio.run(_test())


def test_discovery_50_valid_rows_is_limited_false():
    """Correction 4: 50 valid rows returns 50, is_limited=False."""
    async def _test():
        header = ["timestamp", "original", "mimetype", "statuscode", "length"]
        rows = []
        for i in range(1, 51):  # exactly 50 valid rows
            ts = f"20{i:02d}0101120000"
            rows.append([ts, "https://example.com/", "text/html", "200", "100"])

        cdx_data = [header] + rows
        mock_res = make_mock_result(
            url="https://web.archive.org/cdx/search/cdx",
            status_code=200,
            content=json.dumps(cdx_data).encode("utf-8"),
        )
        mock_fetcher = AsyncMock(return_value=mock_res)
        req = WaybackSnapshotsRequest(url="https://example.com")
        resp = await discover_wayback_snapshots(req, fetcher=mock_fetcher)

        assert resp.total_returned == 50
        assert len(resp.snapshots) == 50
        assert resp.is_limited is False

    asyncio.run(_test())


def test_discovery_51_raw_rows_with_invalid_entries_is_limited_false():
    """Correction 4: 51 raw rows with invalid entries resulting in < 51 valid snapshots yields is_limited=False."""
    async def _test():
        header = ["timestamp", "original", "mimetype", "statuscode", "length"]
        rows = []
        # 45 valid rows
        for i in range(1, 46):
            ts = f"20{i:02d}0101120000"
            rows.append([ts, "https://example.com/", "text/html", "200", "100"])
        # 6 invalid rows (making 51 total raw rows)
        for i in range(46, 52):
            rows.append(["corrupted_ts", "https://example.com/", "application/pdf", "404", "100"])

        cdx_data = [header] + rows
        mock_res = make_mock_result(
            url="https://web.archive.org/cdx/search/cdx",
            status_code=200,
            content=json.dumps(cdx_data).encode("utf-8"),
        )
        mock_fetcher = AsyncMock(return_value=mock_res)
        req = WaybackSnapshotsRequest(url="https://example.com")
        resp = await discover_wayback_snapshots(req, fetcher=mock_fetcher)

        assert resp.total_returned == 45
        assert len(resp.snapshots) == 45
        assert resp.is_limited is False

    asyncio.run(_test())


def test_discovery_invalid_51st_raw_row_is_limited_false():
    """Correction 4: 50 valid rows followed by an invalid 51st row yields is_limited=False."""
    async def _test():
        header = ["timestamp", "original", "mimetype", "statuscode", "length"]
        rows = []
        for i in range(1, 51):  # 50 valid
            ts = f"20{i:02d}0101120000"
            rows.append([ts, "https://example.com/", "text/html", "200", "100"])
        # 51st row is non-HTML
        rows.append(["20510101120000", "https://example.com/", "image/png", "200", "100"])

        cdx_data = [header] + rows
        mock_res = make_mock_result(
            url="https://web.archive.org/cdx/search/cdx",
            status_code=200,
            content=json.dumps(cdx_data).encode("utf-8"),
        )
        mock_fetcher = AsyncMock(return_value=mock_res)
        req = WaybackSnapshotsRequest(url="https://example.com")
        resp = await discover_wayback_snapshots(req, fetcher=mock_fetcher)

        assert resp.total_returned == 50
        assert len(resp.snapshots) == 50
        assert resp.is_limited is False

    asyncio.run(_test())


def test_discovery_invalid_rows_before_valid_rows_preserved():
    """Correction 4: Invalid rows occurring before valid rows do not discard valid snapshots."""
    async def _test():
        header = ["timestamp", "original", "mimetype", "statuscode", "length"]
        rows = [
            ["invalid_timestamp_1", "https://example.com/", "text/html", "200", "100"],
            ["20010101120000", "https://example.com/", "text/html", "200", "100"],
            ["20020101120000", "https://example.com/", "application/pdf", "200", "100"],
            ["20030101120000", "https://example.com/", "text/html", "200", "100"],
        ]
        cdx_data = [header] + rows
        mock_res = make_mock_result(
            url="https://web.archive.org/cdx/search/cdx",
            status_code=200,
            content=json.dumps(cdx_data).encode("utf-8"),
        )
        mock_fetcher = AsyncMock(return_value=mock_res)
        req = WaybackSnapshotsRequest(url="https://example.com")
        resp = await discover_wayback_snapshots(req, fetcher=mock_fetcher)

        assert resp.total_returned == 2
        assert [s.timestamp for s in resp.snapshots] == ["20010101120000", "20030101120000"]

    asyncio.run(_test())


# ============================================================================
# 3. Capture Verification Tests
# ============================================================================

def test_verify_snapshots_success():
    """Verify that verify_and_resolve_snapshots confirms both timestamps against CDX."""
    async def _test():
        def mock_fetcher_side_effect(url: str, **kwargs):
            if "from=20020120142510" in url:
                data = [
                    ["timestamp", "original", "mimetype", "statuscode", "length"],
                    ["20020120142510", "http://example.com:80/", "text/html", "200", "1000"],
                ]
            elif "from=20220120142510" in url:
                data = [
                    ["timestamp", "original", "mimetype", "statuscode", "length"],
                    ["20220120142510", "https://example.com/", "text/html", "200", "2000"],
                ]
            else:
                data = []
            return make_mock_result(url=url, content=json.dumps(data).encode("utf-8"))

        mock_fetcher = AsyncMock(side_effect=mock_fetcher_side_effect)

        snap1, snap2 = await verify_and_resolve_snapshots(
            url="https://example.com",
            timestamp1="20020120142510",
            timestamp2="20220120142510",
            fetcher=mock_fetcher,
        )

        assert snap1.timestamp == "20020120142510"
        assert snap1.original_url == "http://example.com:80/"
        assert snap2.timestamp == "20220120142510"
        assert snap2.original_url == "https://example.com/"

    asyncio.run(_test())


def test_verify_snapshot_not_found():
    """Verify that absent timestamp in CDX raises SnapshotNotFoundError."""
    async def _test():
        mock_res = make_mock_result(
            url="https://web.archive.org/cdx/search/cdx",
            status_code=200,
            content=b"[]",
        )
        mock_fetcher = AsyncMock(return_value=mock_res)

        with pytest.raises(SnapshotNotFoundError, match="not found"):
            await verify_snapshot_timestamp("https://example.com", "20020120142510", fetcher=mock_fetcher)

    asyncio.run(_test())


def test_verify_snapshot_timestamp_mismatch():
    """Verify that CDX returning a different timestamp than requested raises SnapshotNotFoundError."""
    async def _test():
        cdx_data = [
            ["timestamp", "original", "mimetype", "statuscode", "length"],
            ["20020120142500", "https://example.com/", "text/html", "200", "1000"],
        ]
        mock_res = make_mock_result(
            url="https://web.archive.org/cdx/search/cdx",
            status_code=200,
            content=json.dumps(cdx_data).encode("utf-8"),
        )
        mock_fetcher = AsyncMock(return_value=mock_res)

        with pytest.raises(SnapshotNotFoundError, match="Exact timestamp '20020120142510' not found"):
            await verify_snapshot_timestamp("https://example.com", "20020120142510", fetcher=mock_fetcher)

    asyncio.run(_test())


def test_verify_snapshot_non_200():
    """Verify that CDX capture with non-200 status raises WaybackVerificationError."""
    async def _test():
        cdx_data = [
            ["timestamp", "original", "mimetype", "statuscode", "length"],
            ["20020120142510", "https://example.com/", "text/html", "404", "1000"],
        ]
        mock_res = make_mock_result(
            url="https://web.archive.org/cdx/search/cdx",
            status_code=200,
            content=json.dumps(cdx_data).encode("utf-8"),
        )
        mock_fetcher = AsyncMock(return_value=mock_res)

        with pytest.raises(WaybackVerificationError, match="non-successful HTTP status code 404"):
            await verify_snapshot_timestamp("https://example.com", "20020120142510", fetcher=mock_fetcher)

    asyncio.run(_test())


def test_verify_snapshot_non_html():
    """Verify that CDX capture with non-HTML MIME raises WaybackVerificationError."""
    async def _test():
        cdx_data = [
            ["timestamp", "original", "mimetype", "statuscode", "length"],
            ["20020120142510", "https://example.com/", "application/pdf", "200", "1000"],
        ]
        mock_res = make_mock_result(
            url="https://web.archive.org/cdx/search/cdx",
            status_code=200,
            content=json.dumps(cdx_data).encode("utf-8"),
        )
        mock_fetcher = AsyncMock(return_value=mock_res)

        with pytest.raises(WaybackVerificationError, match="non-HTML MIME type 'application/pdf'"):
            await verify_snapshot_timestamp("https://example.com", "20020120142510", fetcher=mock_fetcher)

    asyncio.run(_test())


def test_verify_identical_timestamps_rejected():
    """Verify that comparing identical timestamps raises ValueError."""
    async def _test():
        with pytest.raises(ValueError, match="identical timestamps"):
            await verify_and_resolve_snapshots(
                url="https://example.com",
                timestamp1="20020120142510",
                timestamp2="20020120142510",
            )

    asyncio.run(_test())


# ============================================================================
# 4. Strict Hostname Allowlist & Port Restriction Tests
# ============================================================================

def test_hostname_allowlist_accepted_host():
    """Verify web.archive.org is accepted, and apex archive.org is rejected."""
    assert is_allowed_wayback_host("web.archive.org") is True
    assert is_allowed_wayback_host("archive.org") is False


def test_hostname_allowlist_subdomains_rejected():
    """Verify arbitrary subdomains of archive.org are rejected."""
    unauthorized = [
        "attacker.archive.org",
        "evil.archive.org",
        "ia800102.us.archive.org",
        "web-archive.org",
        "fake-archive.org",
    ]
    for host in unauthorized:
        assert is_allowed_wayback_host(host) is False


def test_hostname_allowlist_suffix_tricks_rejected():
    """Verify suffix spoofing such as web.archive.org.evil.com is rejected."""
    tricks = [
        "web.archive.org.evil.com",
        "archive.org.attacker.com",
        "web.archive.org.local",
    ]
    for host in tricks:
        assert is_allowed_wayback_host(host) is False


def test_hostname_allowlist_case_and_trailing_dot():
    """Verify mixed-case and trailing DNS dots are canonicalized consistently."""
    assert is_allowed_wayback_host("WEB.ARCHIVE.ORG") is True
    assert is_allowed_wayback_host("web.archive.org.") is True
    assert is_allowed_wayback_host("ARCHIVE.ORG.") is False
    assert is_allowed_wayback_host("attacker.archive.org.") is False


def test_validate_destination_host_https_accepted():
    """Verify HTTPS web.archive.org with no port or explicit 443 is accepted."""
    validate_wayback_destination_host("https://web.archive.org/web")
    validate_wayback_destination_host("https://web.archive.org:443/web")
    validate_wayback_destination_host("https://WEB.ARCHIVE.ORG/web")
    validate_wayback_destination_host("https://web.archive.org./web")


def test_validate_destination_host_unexpected_ports_rejected():
    """Verify unexpected ports such as 8080, 8443, and 444 are rejected."""
    unexpected_ports = [8080, 8443, 444, 80, 8000, 22]
    for port in unexpected_ports:
        with pytest.raises(OffHostRedirectError, match=f"Unexpected port {port}"):
            validate_wayback_destination_host(f"https://web.archive.org:{port}/web")


def test_validate_destination_host_malformed_port_rejected():
    """Verify malformed ports (e.g. non-numeric or out-of-range) are rejected."""
    for bad_url in ("https://web.archive.org:invalid/web", "https://web.archive.org:99999/web"):
        with pytest.raises(OffHostRedirectError, match="Malformed destination URL"):
            validate_wayback_destination_host(bad_url)


def test_validate_destination_host_unsupported_schemes_rejected():
    """Verify unsupported schemes (HTTP, FTP, etc.) are rejected."""
    for bad_scheme_url in (
        "http://web.archive.org/web",
        "http://web.archive.org:80/web",
        "ftp://web.archive.org/web",
    ):
        with pytest.raises(OffHostRedirectError, match="Unsupported scheme"):
            validate_wayback_destination_host(bad_scheme_url)


def test_validate_destination_host_missing_hostname_rejected():
    """Verify URLs missing a hostname are rejected."""
    with pytest.raises(OffHostRedirectError, match="unauthorized host"):
        validate_wayback_destination_host("https:///web")


def test_validate_destination_host_rejects_unauthorized_hosts():
    """Verify validate_wayback_destination_host raises OffHostRedirectError on unauthorized hosts."""
    unauthorized_urls = [
        "https://archive.org/web",
        "https://attacker.archive.org/web",
        "https://evil.com/page",
        "https://web.archive.org.evil.com/web",
    ]
    for u in unauthorized_urls:
        with pytest.raises(OffHostRedirectError, match="unauthorized host"):
            validate_wayback_destination_host(u)


# ============================================================================
# 5. Anchored Replay Path Timestamp Tests (Correction 2)
# ============================================================================

def test_replay_timestamp_correct_anchored_path_accepted():
    """Correction 2: Correct replay path /web/{timestamp}id_/ is extracted."""
    url = "https://web.archive.org/web/20020120142510id_/http://example.com:80/"
    assert extract_replay_timestamp(url) == "20020120142510"


def test_replay_timestamp_in_query_rejected():
    """Correction 2: Timestamp appearing only in query string is rejected (returns None)."""
    url = "https://web.archive.org/web/fallback_error?orig=/web/20020120142510id_/"
    assert extract_replay_timestamp(url) is None


def test_replay_timestamp_in_fragment_rejected():
    """Correction 2: Timestamp appearing only in URL fragment is rejected."""
    url = "https://web.archive.org/web/fallback_error#/web/20020120142510id_/"
    assert extract_replay_timestamp(url) is None


def test_replay_timestamp_in_unrelated_path_rejected():
    """Correction 2: Timestamp in unrelated path segment is rejected."""
    url = "https://web.archive.org/errors/404/web/20020120142510id_/"
    assert extract_replay_timestamp(url) is None


def test_replay_deceptive_url_rejected_by_fetch():
    """Correction 2: Deceptive query timestamp triggers FallbackRedirectError during fetch."""
    async def _test():
        snapshot = WaybackSnapshot(
            timestamp="20020120142510",
            datetime="2002-01-20T14:25:10Z",
            display_date="Jan 20, 2002",
            original_url="http://example.com/",
            status_code=200,
            mimetype="text/html",
        )
        # Resolved URL has requested timestamp in query parameter, not path!
        mock_res = make_mock_result(
            url="https://web.archive.org/web/fallback?fake=/web/20020120142510id_/",
            status_code=200,
            content=VALID_HTML_BYTES,
        )
        mock_fetcher = AsyncMock(return_value=mock_res)

        with pytest.raises(FallbackRedirectError, match="redirected to fallback timestamp 'unknown'"):
            await fetch_single_wayback_capture(snapshot, fetcher=mock_fetcher)

    asyncio.run(_test())


# ============================================================================
# 6. Concurrency & Task Cancellation Tests (Correction 3)
# ============================================================================

def test_fetch_pair_snapshot1_fails_cancels_snapshot2():
    """Correction 3: When snapshot 1 fails immediately, snapshot 2 is cancelled and awaited."""
    async def _test():
        snap1 = WaybackSnapshot(
            timestamp="20020120142510",
            datetime="2002-01-20T14:25:10Z",
            display_date="Jan 20, 2002",
            original_url="http://example.com/1",
            status_code=200,
            mimetype="text/html",
        )
        snap2 = WaybackSnapshot(
            timestamp="20220120142510",
            datetime="2022-01-20T14:25:10Z",
            display_date="Jan 20, 2022",
            original_url="http://example.com/2",
            status_code=200,
            mimetype="text/html",
        )

        task2_was_cancelled = False

        async def mock_fetcher(url: str, **kwargs):
            nonlocal task2_was_cancelled
            if "20020120142510" in url:
                # Snapshot 1 fails immediately
                raise WaybackFetchError("Snapshot 1 connection broke", failed_url=url)
            # Snapshot 2 is a slow task
            try:
                await asyncio.sleep(5.0)
                return make_mock_result(url=url, content=VALID_HTML_BYTES)
            except asyncio.CancelledError:
                task2_was_cancelled = True
                raise

        with pytest.raises(WaybackFetchError, match="Snapshot 1 connection broke"):
            await fetch_wayback_raw_pair(snap1, snap2, fetcher=mock_fetcher)

        assert task2_was_cancelled is True, "Snapshot 2 task should have been cancelled immediately!"

    asyncio.run(_test())


def test_fetch_pair_snapshot2_fails_cancels_snapshot1():
    """Correction 3: When snapshot 2 fails immediately, snapshot 1 is cancelled and awaited."""
    async def _test():
        snap1 = WaybackSnapshot(
            timestamp="20020120142510",
            datetime="2002-01-20T14:25:10Z",
            display_date="Jan 20, 2002",
            original_url="http://example.com/1",
            status_code=200,
            mimetype="text/html",
        )
        snap2 = WaybackSnapshot(
            timestamp="20220120142510",
            datetime="2022-01-20T14:25:10Z",
            display_date="Jan 20, 2022",
            original_url="http://example.com/2",
            status_code=200,
            mimetype="text/html",
        )

        task1_was_cancelled = False

        async def mock_fetcher(url: str, **kwargs):
            nonlocal task1_was_cancelled
            if "20220120142510" in url:
                # Snapshot 2 fails immediately
                raise WaybackFetchError("Snapshot 2 TLS error", failed_url=url)
            # Snapshot 1 is slow
            try:
                await asyncio.sleep(5.0)
                return make_mock_result(url=url, content=VALID_HTML_BYTES)
            except asyncio.CancelledError:
                task1_was_cancelled = True
                raise

        with pytest.raises(WaybackFetchError, match="Snapshot 2 TLS error"):
            await fetch_wayback_raw_pair(snap1, snap2, fetcher=mock_fetcher)

        assert task1_was_cancelled is True, "Snapshot 1 task should have been cancelled immediately!"

    asyncio.run(_test())


def test_verify_snapshots_cancellation_on_failure():
    """Correction 3: In verify_and_resolve_snapshots, if one verification fails, sibling is cancelled."""
    async def _test():
        task2_was_cancelled = False

        async def mock_fetcher(url: str, **kwargs):
            nonlocal task2_was_cancelled
            if "from=20020120142510" in url:
                # Return empty response -> raises SnapshotNotFoundError
                return make_mock_result(url=url, content=b"[]")
            try:
                await asyncio.sleep(5.0)
                return make_mock_result(url=url, content=b"[]")
            except asyncio.CancelledError:
                task2_was_cancelled = True
                raise

        with pytest.raises(SnapshotNotFoundError):
            await verify_and_resolve_snapshots(
                url="https://example.com",
                timestamp1="20020120142510",
                timestamp2="20220120142510",
                fetcher=mock_fetcher,
            )

        assert task2_was_cancelled is True, "Sibling verification task should have been cancelled!"

    asyncio.run(_test())


# ============================================================================
# 7. Replay URL Construction & Retrieval Tests
# ============================================================================

def test_replay_url_uses_cdx_original():
    """Verify replay URL is constructed with exact original URL from CDX record."""
    url = build_wayback_replay_url("20020120142510", "http://example.com:80/")
    assert url == "https://web.archive.org/web/20020120142510id_/http://example.com:80/"


def test_replay_url_preserves_scheme_port_query():
    """Verify replay URL preserves custom port, scheme, and query strings."""
    url = build_wayback_replay_url("20150310120000", "http://site.org:8080/path/test?q=hello&page=2")
    assert url == "https://web.archive.org/web/20150310120000id_/http://site.org:8080/path/test?q=hello&page=2"


def test_replay_unsafe_original_rejected():
    """Verify malformed, credentialed, or non-HTTP original URLs are rejected."""
    unsafe_urls = [
        "javascript:alert(1)",
        "http://user:pass@example.com/",
        "ftp://example.com/file.html",
        "http://example.com\r\ninvalid",
        "",
        "http://example.com:99999/",  # Invalid port
    ]
    for u in unsafe_urls:
        with pytest.raises(InvalidWaybackURLError):
            build_wayback_replay_url("20020120142510", u)


def test_replay_exact_timestamp_accepted():
    """Verify replay fetch succeeds when resolved URL matches exact requested timestamp."""
    async def _test():
        snapshot = WaybackSnapshot(
            timestamp="20020120142510",
            datetime="2002-01-20T14:25:10Z",
            display_date="Jan 20, 2002",
            original_url="http://example.com:80/",
            status_code=200,
            mimetype="text/html",
        )
        mock_res = make_mock_result(
            url="https://web.archive.org/web/20020120142510id_/http://example.com:80/",
            status_code=200,
            content=VALID_HTML_BYTES,
        )
        mock_fetcher = AsyncMock(return_value=mock_res)

        res = await fetch_single_wayback_capture(snapshot, fetcher=mock_fetcher)
        assert res.status_code == 200
        assert res.content == VALID_HTML_BYTES

    asyncio.run(_test())


def test_replay_fallback_redirect_rejected():
    """Verify that Wayback replay redirecting to a nearest fallback timestamp is rejected."""
    async def _test():
        snapshot = WaybackSnapshot(
            timestamp="20020120142511",  # Requested timestamp 11
            datetime="2002-01-20T14:25:11Z",
            display_date="Jan 20, 2002",
            original_url="http://example.com/",
            status_code=200,
            mimetype="text/html",
        )
        # Replay returned fallback timestamp 10
        mock_res = make_mock_result(
            url="https://web.archive.org/web/20020120142510id_/http://example.com/",
            status_code=200,
            content=VALID_HTML_BYTES,
        )
        mock_fetcher = AsyncMock(return_value=mock_res)

        with pytest.raises(FallbackRedirectError, match="redirected to fallback timestamp '20020120142510'"):
            await fetch_single_wayback_capture(snapshot, fetcher=mock_fetcher)

    asyncio.run(_test())


def test_replay_off_host_redirect_rejected_before_request():
    """Verify that a redirect targeting an unauthorized off-host domain raises OffHostRedirectError
    BEFORE the request to the off-host domain is sent.
    """
    async def _test():
        redirect_res = httpx.Response(
            status_code=302,
            headers={"location": "https://evil.com/malicious"},
            request=httpx.Request("GET", "https://web.archive.org/web/20020120142510id_/http://example.com"),
        )

        with patch("httpx.AsyncClient.send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = redirect_res

            with pytest.raises(OffHostRedirectError, match="unauthorized host 'evil.com'"):
                await safe_fetch_wayback_async("https://web.archive.org/web/20020120142510id_/http://example.com")

            # Confirm send was only called ONCE (the initial request), NOT for evil.com!
            assert mock_send.call_count == 1
            first_call_request = mock_send.call_args[0][0]
            assert first_call_request.url.host == "web.archive.org"

    asyncio.run(_test())


def test_replay_non_html_rejected():
    """Verify that replay returning non-HTML MIME or binary data raises WaybackContentError."""
    async def _test():
        snapshot = WaybackSnapshot(
            timestamp="20020120142510",
            datetime="2002-01-20T14:25:10Z",
            display_date="Jan 20, 2002",
            original_url="http://example.com/",
            status_code=200,
            mimetype="text/html",
        )
        mock_res = make_mock_result(
            url="https://web.archive.org/web/20020120142510id_/http://example.com/",
            status_code=200,
            content=b"%PDF-1.4 binary data...",
            headers={"content-type": "application/pdf"},
        )
        mock_fetcher = AsyncMock(return_value=mock_res)

        with pytest.raises(WaybackContentError, match="failed HTML validation"):
            await fetch_single_wayback_capture(snapshot, fetcher=mock_fetcher)

    asyncio.run(_test())


def test_replay_empty_content_rejected():
    """Verify that replay returning 0 bytes raises WaybackContentError."""
    async def _test():
        snapshot = WaybackSnapshot(
            timestamp="20020120142510",
            datetime="2002-01-20T14:25:10Z",
            display_date="Jan 20, 2002",
            original_url="http://example.com/",
            status_code=200,
            mimetype="text/html",
        )
        mock_res = make_mock_result(
            url="https://web.archive.org/web/20020120142510id_/http://example.com/",
            status_code=200,
            content=b"",
        )
        mock_fetcher = AsyncMock(return_value=mock_res)

        with pytest.raises(WaybackContentError, match="failed HTML validation"):
            await fetch_single_wayback_capture(snapshot, fetcher=mock_fetcher)

    asyncio.run(_test())


def test_fetch_wayback_raw_pair_success():
    """Verify concurrent retrieval of both snapshots preserves raw bytes."""
    async def _test():
        snap1 = WaybackSnapshot(
            timestamp="20020120142510",
            datetime="2002-01-20T14:25:10Z",
            display_date="Jan 20, 2002",
            original_url="http://example.com/1",
            status_code=200,
            mimetype="text/html",
        )
        snap2 = WaybackSnapshot(
            timestamp="20220120142510",
            datetime="2022-01-20T14:25:10Z",
            display_date="Jan 20, 2022",
            original_url="http://example.com/2",
            status_code=200,
            mimetype="text/html",
        )

        async def mock_fetcher(url: str, **kwargs):
            if "20020120142510" in url:
                return make_mock_result(url=url, content=VALID_HTML_BYTES)
            return make_mock_result(url=url, content=VALID_HTML_BYTES_V2)

        res1, res2 = await fetch_wayback_raw_pair(snap1, snap2, fetcher=mock_fetcher)
        assert res1.content == VALID_HTML_BYTES
        assert res2.content == VALID_HTML_BYTES_V2

    asyncio.run(_test())


# ============================================================================
# 8. Pydantic Models & Input Validation Tests
# ============================================================================

def test_snapshots_request_validation():
    """Verify WaybackSnapshotsRequest validates URL, limits, and year bounds."""
    # Valid
    req = WaybackSnapshotsRequest(url="https://example.com", limit=25, from_year=2000, to_year=2010)
    assert req.url == "https://example.com"
    assert req.limit == 25
    assert req.from_year == 2000
    assert req.to_year == 2010

    # Invalid URL scheme
    with pytest.raises(ValidationError):
        WaybackSnapshotsRequest(url="ftp://example.com")

    # Private IP / localhost target blocked
    with pytest.raises(ValidationError):
        WaybackSnapshotsRequest(url="http://127.0.0.1:8080")

    # Inverted year order
    with pytest.raises(ValidationError, match="from_year .* must be <= to_year"):
        WaybackSnapshotsRequest(url="https://example.com", from_year=2020, to_year=2010)

    # Limit out of bounds
    with pytest.raises(ValidationError):
        WaybackSnapshotsRequest(url="https://example.com", limit=0)

    with pytest.raises(ValidationError):
        WaybackSnapshotsRequest(url="https://example.com", limit=101)


def test_compare_request_validation():
    """Verify WaybackCompareRequest validates URL and timestamps."""
    # Valid
    req = WaybackCompareRequest(
        url="https://example.com",
        timestamp1="20020120142510",
        timestamp2="20220120142510",
    )
    assert req.timestamp1 == "20020120142510"
    assert req.timestamp2 == "20220120142510"

    # Identical timestamps rejected
    with pytest.raises(ValidationError, match="identical timestamps"):
        WaybackCompareRequest(
            url="https://example.com",
            timestamp1="20020120142510",
            timestamp2="20020120142510",
        )

    # Invalid timestamp (not 14 digits)
    with pytest.raises(ValidationError):
        WaybackCompareRequest(
            url="https://example.com",
            timestamp1="20020120",
            timestamp2="20220120142510",
        )

    # Invalid timestamp (invalid calendar date)
    with pytest.raises(ValidationError):
        WaybackCompareRequest(
            url="https://example.com",
            timestamp1="20021399142510",
            timestamp2="20220120142510",
        )


# ============================================================================
# 9. Strict Overall Deadline & Response Cleanup Tests
# ============================================================================

def test_wayback_fetcher_stalled_response_cancelled_by_deadline_and_closed():
    """Verify that a stalled streaming response in safe_fetch_wayback_async is cancelled
    when the overall deadline expires and that the response is closed after cancellation."""
    async def _test():
        async def mock_aiter():
            yield b"<html>"
            await asyncio.sleep(5)
            yield b"</html>"

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.aiter_bytes = mock_aiter
        mock_resp.aclose = AsyncMock()

        with patch.object(httpx.AsyncClient, "send", return_value=mock_resp):
            with pytest.raises(ResourceLimitError, match="deadline"):
                await safe_fetch_wayback_async(
                    "https://web.archive.org/web/20200101000000id_/https://example.com",
                    total_deadline=0.25,
                )
            assert mock_resp.aclose.called, "Active Wayback response was not closed after deadline expiration"

    asyncio.run(_test())


def test_wayback_fetcher_overall_deadline_applies_across_multiple_redirect_hops():
    """Verify that the strict overall deadline in safe_fetch_wayback_async applies
    cumulatively across multiple redirect hops on web.archive.org."""
    async def _test():
        resp1 = MagicMock(spec=httpx.Response)
        resp1.status_code = 302
        resp1.headers = {
            "location": "https://web.archive.org/web/20200101000000id_/https://example.com/hop2"
        }
        resp1.aclose = AsyncMock()

        resp2 = MagicMock(spec=httpx.Response)
        resp2.status_code = 200
        resp2.headers = {"content-type": "text/html"}
        async def slow_aiter():
            yield b"<html>"
            await asyncio.sleep(5)
        resp2.aiter_bytes = slow_aiter
        resp2.aclose = AsyncMock()

        call_count = 0
        async def mock_send(request, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                await asyncio.sleep(0.1)
                return resp1
            return resp2

        with patch.object(httpx.AsyncClient, "send", side_effect=mock_send):
            with pytest.raises(ResourceLimitError, match="deadline"):
                await safe_fetch_wayback_async(
                    "https://web.archive.org/web/20200101000000id_/https://example.com/hop1",
                    total_deadline=0.25,
                )
            assert resp1.aclose.called, "Hop 1 response was not closed"
            assert resp2.aclose.called, "Hop 2 response was not closed"

    asyncio.run(_test())
