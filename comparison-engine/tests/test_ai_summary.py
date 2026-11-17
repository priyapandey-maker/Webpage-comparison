"""Unit and integration tests for the AI explanation layer.

Verifies:
1. Input payload construction grounds exclusively on supplied changes.
2. Valid structured AI response parsing and validation.
3. Filtering and rejection of unknown change IDs.
4. Safe fallback on invalid JSON.
5. Safe fallback on Ollama connection errors / unavailable service.
6. Safe fallback on request timeout.
7. Immediate return of None when AI is disabled via configuration.
8. Handling of zero changes without unnecessary network calls.
9. Integration with POST /api/compare and POST /api/wayback/compare.
10. Complete preservation of existing Phase 1 counts and classifications.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

COMPARISON_ENGINE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = COMPARISON_ENGINE_DIR / "src"
REPO_ROOT = COMPARISON_ENGINE_DIR.parent
TEST_FILES_DIR = REPO_ROOT / "test-files"

for d in (str(COMPARISON_ENGINE_DIR), str(SRC_DIR)):
    if d not in sys.path:
        sys.path.insert(0, d)

from api import app, _run_existing_engine
from result_adapter import adapt_engine_result
from ai.schemas import AIConfig, AISummary, TopicGroup
from ai.summarizer import (
    build_compact_changes_payload,
    generate_ai_summary,
    _truncate_text,
)
from security.redirect_handler import SafeFetchResult
from wayback_client import WaybackSnapshot

V1_FILE = TEST_FILES_DIR / "mini project version 1.html"
V2_FILE = TEST_FILES_DIR / "mini project version 2.html"


SAMPLE_CHANGES = [
    {
        "id": 1,
        "category": "added",
        "type": "link",
        "element": "Link",
        "oldValue": None,
        "newValue": "Research Publications (/research)",
        "description": "Link was added.",
        "explanation": "Added link to research publications.",
    },
    {
        "id": 2,
        "category": "removed",
        "type": "section",
        "element": "Section",
        "oldValue": "Archived 2021 announcements and notices",
        "newValue": None,
        "description": "Section was removed.",
    },
    {
        "id": 3,
        "category": "modified",
        "type": "paragraph",
        "element": "Paragraph",
        "oldValue": "Application deadline: 15 June 2026",
        "newValue": "Application deadline: 30 June 2027",
        "description": "Paragraph text was updated.",
        "explanation": "Application deadline was updated from 15 June 2026 to 30 June 2027.",
    },
]


def test_truncate_text():
    assert _truncate_text(None) == ""
    assert _truncate_text("Short text") == "Short text"
    long_text = "A" * 300
    truncated = _truncate_text(long_text, max_len=50)
    assert len(truncated) == 53  # 50 chars + "..."
    assert truncated.endswith("...")


def test_build_compact_changes_payload():
    payload, valid_ids = build_compact_changes_payload(
        SAMPLE_CHANGES,
        version1_label="2022 Snapshot",
        version2_label="2026 Snapshot",
    )

    assert valid_ids == {1, 2, 3}
    assert "2022 Snapshot" in payload
    assert "2026 Snapshot" in payload
    assert "Total Detected Changes: 3" in payload
    assert "[ID 1] ADDED Link" in payload
    assert "Research Publications" in payload
    assert "[ID 2] REMOVED Section" in payload
    assert "[ID 3] MODIFIED Paragraph" in payload
    assert "30 June 2027" in payload


@pytest.mark.anyio
async def test_ai_summary_valid_response():
    ai_response_json = {
        "executive_summary": "The webpage was updated with new research navigation and an extended application deadline.",
        "key_takeaways": [
            "Added Research Publications navigation link.",
            "Removed legacy 2021 announcements section.",
            "Updated application deadline to 30 June 2027.",
        ],
        "topic_groups": [
            {
                "topic": "Navigation Changes",
                "description": "Added new link to research publications.",
                "change_ids": [1],
                "significance": "medium",
            },
            {
                "topic": "Content Updates",
                "description": "Extended deadline and pruned archived announcements.",
                "change_ids": [2, 3],
                "significance": "high",
            },
        ],
    }

    mock_resp = httpx.Response(
        status_code=200,
        json={"message": {"content": json.dumps(ai_response_json)}},
        request=httpx.Request("POST", "http://127.0.0.1:11434/api/chat"),
    )

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = mock_resp

    comparison = {"changes": SAMPLE_CHANGES}
    config = AIConfig(enabled=True)

    result = await generate_ai_summary(comparison, config=config, client=mock_client)
    assert result is not None
    assert result["executive_summary"] == ai_response_json["executive_summary"]
    assert len(result["key_takeaways"]) == 3
    assert len(result["topic_groups"]) == 2
    assert result["topic_groups"][0]["change_ids"] == [1]
    assert result["topic_groups"][1]["change_ids"] == [2, 3]


@pytest.mark.anyio
async def test_ai_summary_filters_unknown_change_ids():
    ai_response_json = {
        "executive_summary": "Summary with hallucinated and valid IDs.",
        "key_takeaways": ["Takeaway 1"],
        "topic_groups": [
            {
                "topic": "Valid and Invalid Group",
                "description": "Contains valid ID 1 and hallucinated IDs 999, 1000.",
                "change_ids": [1, 999, 1000],
                "significance": "low",
            },
            {
                "topic": "Entirely Hallucinated Group",
                "description": "Contains only unknown ID 888.",
                "change_ids": [888],
                "significance": "low",
            },
        ],
    }

    mock_resp = httpx.Response(
        status_code=200,
        json={"message": {"content": json.dumps(ai_response_json)}},
        request=httpx.Request("POST", "http://127.0.0.1:11434/api/chat"),
    )
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = mock_resp

    comparison = {"changes": SAMPLE_CHANGES}
    result = await generate_ai_summary(comparison, client=mock_client)

    assert result is not None
    # Group with unknown IDs must filter out 999 and 1000, keeping only 1
    # Group with only 888 must be dropped entirely
    assert len(result["topic_groups"]) == 1
    assert result["topic_groups"][0]["topic"] == "Valid and Invalid Group"
    assert result["topic_groups"][0]["change_ids"] == [1]


@pytest.mark.anyio
async def test_ai_summary_invalid_json_handling():
    mock_resp = httpx.Response(
        status_code=200,
        json={"message": {"content": "This is raw text, not valid JSON."}},
        request=httpx.Request("POST", "http://127.0.0.1:11434/api/chat"),
    )
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = mock_resp

    comparison = {"changes": SAMPLE_CHANGES}
    result = await generate_ai_summary(comparison, client=mock_client)
    assert result is None


@pytest.mark.anyio
async def test_ai_summary_schema_validation_failure():
    mock_resp = httpx.Response(
        status_code=200,
        json={"message": {"content": json.dumps({"unrelated_key": "data"})}},
        request=httpx.Request("POST", "http://127.0.0.1:11434/api/chat"),
    )
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = mock_resp

    comparison = {"changes": SAMPLE_CHANGES}
    result = await generate_ai_summary(comparison, client=mock_client)
    assert result is None


@pytest.mark.anyio
async def test_ai_summary_ollama_unavailable():
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = httpx.ConnectError("Connection refused to 127.0.0.1:11434")

    comparison = {"changes": SAMPLE_CHANGES}
    result = await generate_ai_summary(comparison, client=mock_client)
    assert result is None


@pytest.mark.anyio
async def test_ai_summary_request_timeout():
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = httpx.TimeoutException("Read timed out")

    comparison = {"changes": SAMPLE_CHANGES}
    result = await generate_ai_summary(comparison, client=mock_client)
    assert result is None


@pytest.mark.anyio
async def test_ai_summary_disabled_via_config():
    config = AIConfig(enabled=False)
    comparison = {"changes": SAMPLE_CHANGES}
    # No client passed; should return None immediately without attempting HTTP connection
    result = await generate_ai_summary(comparison, config=config)
    assert result is None


@pytest.mark.anyio
async def test_ai_summary_zero_changes():
    comparison = {"changes": []}
    result = await generate_ai_summary(comparison)
    assert result is not None
    assert "No visual, structural, or text changes" in result["executive_summary"]
    assert result["topic_groups"] == []


def test_api_compare_file_upload_with_ai_mock():
    """Verify POST /api/compare attaches aiSummary while preserving Phase 1 counts."""
    mock_ai = {
        "executive_summary": "Version 2 updates the mini project with revised text and styling.",
        "key_takeaways": ["12 modifications updated deadlines and terms."],
        "topic_groups": [
            {
                "topic": "Content Updates",
                "description": "Deadlines updated.",
                "change_ids": [1],
                "significance": "medium",
            }
        ],
    }

    client = TestClient(app)
    with patch("api.generate_ai_summary", new=AsyncMock(return_value=mock_ai)):
        with open(V1_FILE, "rb") as f1, open(V2_FILE, "rb") as f2:
            resp = client.post(
                "/api/compare",
                files={
                    "version1": ("v1.html", f1, "text/html"),
                    "version2": ("v2.html", f2, "text/html"),
                },
            )

    assert resp.status_code == 200
    data = resp.json()

    # Verify aiSummary is attached
    assert "aiSummary" in data
    assert data["aiSummary"] == mock_ai

    # Verify Phase 1 presentation counts remain exact
    summary = data["presentationSummary"]
    assert summary["added"] == 8
    assert summary["removed"] == 1
    assert summary["modified"] == 12
    assert summary["total"] == 21
    assert len(data["changes"]) == 21


def test_api_compare_file_upload_ai_fallback_on_failure():
    """Verify POST /api/compare returns aiSummary=None when AI summary fails."""
    client = TestClient(app)
    with patch("api.generate_ai_summary", new=AsyncMock(return_value=None)):
        with open(V1_FILE, "rb") as f1, open(V2_FILE, "rb") as f2:
            resp = client.post(
                "/api/compare",
                files={
                    "version1": ("v1.html", f1, "text/html"),
                    "version2": ("v2.html", f2, "text/html"),
                },
            )

    assert resp.status_code == 200
    data = resp.json()
    assert "aiSummary" in data
    assert data["aiSummary"] is None

    # Normal comparison and NLP analysis remain intact
    assert "nlpAnalysis" in data
    assert data["presentationSummary"]["total"] == 21


def test_api_wayback_compare_with_ai_mock():
    """Verify POST /api/wayback/compare attaches aiSummary alongside waybackContext and nlpAnalysis."""
    snap1 = WaybackSnapshot(
        timestamp="20200101000000",
        datetime="2020-01-01T00:00:00Z",
        display_date="Jan 01, 2020 00:00 UTC",
        original_url="https://example.com/",
        status_code=200,
        mimetype="text/html",
    )
    snap2 = WaybackSnapshot(
        timestamp="20210101000000",
        datetime="2021-01-01T00:00:00Z",
        display_date="Jan 01, 2021 00:00 UTC",
        original_url="https://example.com/",
        status_code=200,
        mimetype="text/html",
    )

    fetch_res1 = SafeFetchResult(
        url="https://web.archive.org/web/20200101000000id_/https://example.com/",
        status_code=200,
        headers={"content-type": "text/html; charset=utf-8"},
        content=V1_FILE.read_bytes(),
        redirect_history=[],
    )
    fetch_res2 = SafeFetchResult(
        url="https://web.archive.org/web/20210101000000id_/https://example.com/",
        status_code=200,
        headers={"content-type": "text/html; charset=utf-8"},
        content=V2_FILE.read_bytes(),
        redirect_history=[],
    )

    mock_ai = {
        "executive_summary": "Historical comparison reveals updated policies and dates.",
        "key_takeaways": ["Pruned announcements."],
        "topic_groups": [],
    }

    client = TestClient(app)
    with patch("api.verify_and_resolve_snapshots", new=AsyncMock(return_value=(snap1, snap2))), \
         patch("api.fetch_wayback_raw_pair", new=AsyncMock(return_value=(fetch_res1, fetch_res2))), \
         patch("api.generate_ai_summary", new=AsyncMock(return_value=mock_ai)):
        resp = client.post(
            "/api/wayback/compare",
            json={
                "url": "https://example.com/",
                "timestamp1": "20200101000000",
                "timestamp2": "20210101000000",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "aiSummary" in data
    assert data["aiSummary"] == mock_ai
    assert "waybackContext" in data
    assert "nlpAnalysis" in data
    assert data["presentationSummary"]["total"] == 21


def test_api_wayback_compare_ai_fallback_on_failure():
    """Verify POST /api/wayback/compare continues safely with aiSummary=None on AI failure."""
    snap1 = WaybackSnapshot(
        timestamp="20200101000000",
        datetime="2020-01-01T00:00:00Z",
        display_date="Jan 01, 2020 00:00 UTC",
        original_url="https://example.com/",
        status_code=200,
        mimetype="text/html",
    )
    snap2 = WaybackSnapshot(
        timestamp="20210101000000",
        datetime="2021-01-01T00:00:00Z",
        display_date="Jan 01, 2021 00:00 UTC",
        original_url="https://example.com/",
        status_code=200,
        mimetype="text/html",
    )

    fetch_res1 = SafeFetchResult(
        url="https://web.archive.org/web/20200101000000id_/https://example.com/",
        status_code=200,
        headers={"content-type": "text/html; charset=utf-8"},
        content=V1_FILE.read_bytes(),
        redirect_history=[],
    )
    fetch_res2 = SafeFetchResult(
        url="https://web.archive.org/web/20210101000000id_/https://example.com/",
        status_code=200,
        headers={"content-type": "text/html; charset=utf-8"},
        content=V2_FILE.read_bytes(),
        redirect_history=[],
    )

    client = TestClient(app)
    with patch("api.verify_and_resolve_snapshots", new=AsyncMock(return_value=(snap1, snap2))), \
         patch("api.fetch_wayback_raw_pair", new=AsyncMock(return_value=(fetch_res1, fetch_res2))), \
         patch("api.generate_ai_summary", new=AsyncMock(return_value=None)):
        resp = client.post(
            "/api/wayback/compare",
            json={
                "url": "https://example.com/",
                "timestamp1": "20200101000000",
                "timestamp2": "20210101000000",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "aiSummary" in data
    assert data["aiSummary"] is None
    assert data["presentationSummary"]["total"] == 21
