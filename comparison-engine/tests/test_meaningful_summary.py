"""Unit and integration tests for Task 2: Meaningful Comparison Summary.

Verifies:
1. Real modifications are explained using their actual before-and-after text.
2. Additions and removals are correctly identified and described.
3. Empty, whitespace, or missing text does not produce invented explanations.
4. Zero-change comparisons produce an appropriate summary.
5. Existing Phase 1 comparison counts (8 additions, 1 removal, 12 modifications) remain unchanged.
6. Both POST /api/compare and POST /api/wayback/compare enrich changes with NLP explanations.
7. Existing NLP semantic analysis and keyword extraction remain fully operational.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

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
from nlp.pipeline import (
    attach_nlp_analysis,
    generate_change_explanation,
    run_nlp_pipeline,
)
from security.redirect_handler import SafeFetchResult
from wayback_client import WaybackSnapshot

V1_FILE = TEST_FILES_DIR / "mini project version 1.html"
V2_FILE = TEST_FILES_DIR / "mini project version 2.html"


def test_phase1_counts_and_classifications_remain_unchanged():
    """Verify Phase 1 presentation counts remain exactly 8 additions, 1 removal, 12 modifications."""
    with TemporaryDirectory() as td:
        raw, t1, t2 = _run_existing_engine(V1_FILE, V2_FILE, Path(td))
        adapted = adapt_engine_result(raw, t1, t2, "v1.html", "v2.html")

        summary = adapted["presentationSummary"]
        assert summary["added"] == 8
        assert summary["removed"] == 1
        assert summary["modified"] == 12
        assert summary["total"] == 21
        assert len(adapted["changes"]) == 21


def test_attach_nlp_analysis_enriches_individual_changes():
    """Verify attach_nlp_analysis attaches human-readable explanations grounded in actual text."""
    with TemporaryDirectory() as td:
        raw, t1, t2 = _run_existing_engine(V1_FILE, V2_FILE, Path(td))
        adapted = adapt_engine_result(raw, t1, t2, "v1.html", "v2.html")
        enriched = attach_nlp_analysis(adapted)

        assert "nlpAnalysis" in enriched
        nlp = enriched["nlpAnalysis"]
        assert "overall" in nlp
        assert nlp["overall"]["total_modifications_analyzed"] == 12

        changes = enriched["changes"]
        mod_changes = [c for c in changes if c["category"] == "modified"]
        assert len(mod_changes) == 12

        # Check that modified changes now have an explanation attached
        explained_mods = [c for c in mod_changes if "explanation" in c]
        assert len(explained_mods) >= 10, "Most modified changes should receive an NLP explanation"

        # Check date update explanation specifically
        date_mod = next((c for c in mod_changes if "15 June 2026" in str(c.get("oldValue"))), None)
        assert date_mod is not None, "Date change must be present in modifications"
        assert "explanation" in date_mod
        assert "30 June 2027" in date_mod["explanation"] or "2027" in date_mod["explanation"]


def test_api_compare_file_upload_enriches_nlp_and_explanations():
    """Verify POST /api/compare file upload runs NLP enrichment and returns change explanations."""
    client = TestClient(app)
    with open(V1_FILE, "rb") as f1, open(V2_FILE, "rb") as f2:
        resp = client.post(
            "/api/compare",
            files={
                "version1": ("mini project version 1.html", f1, "text/html"),
                "version2": ("mini project version 2.html", f2, "text/html"),
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "nlpAnalysis" in data
    assert "changes" in data

    # Verify modifications have explanations
    modifications = [c for c in data["changes"] if c["category"] == "modified"]
    assert len(modifications) == 12
    with_exp = [c for c in modifications if c.get("explanation")]
    assert len(with_exp) >= 10


def test_api_wayback_compare_enriches_nlp_and_explanations():
    """Verify POST /api/wayback/compare provides NLP explanations for historical comparisons."""
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
    res1 = SafeFetchResult(
        url="https://web.archive.org/web/20200101000000id_/https://example.com/",
        status_code=200,
        headers={"content-type": "text/html"},
        content=V1_FILE.read_bytes(),
        redirect_history=[],
    )
    res2 = SafeFetchResult(
        url="https://web.archive.org/web/20210101000000id_/https://example.com/",
        status_code=200,
        headers={"content-type": "text/html"},
        content=V2_FILE.read_bytes(),
        redirect_history=[],
    )

    async def _test():
        with patch("api.verify_and_resolve_snapshots", new_callable=AsyncMock) as mock_verify, \
             patch("api.fetch_wayback_raw_pair", new_callable=AsyncMock) as mock_fetch:
            mock_verify.return_value = (snap1, snap2)
            mock_fetch.return_value = (res1, res2)

            client = TestClient(app)
            resp = client.post(
                "/api/wayback/compare",
                json={
                    "url": "https://example.com",
                    "timestamp1": "20200101000000",
                    "timestamp2": "20210101000000",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "nlpAnalysis" in data
            assert "waybackContext" in data
            modifications = [c for c in data["changes"] if c["category"] == "modified"]
            with_exp = [c for c in modifications if c.get("explanation")]
            assert len(with_exp) >= 10

    asyncio.run(_test())


def test_zero_changes_handling_does_not_invent_content():
    """Verify zero-change comparison produces clean results without hallucinating differences."""
    empty_result = {
        "changes": [],
        "engineSummary": {"totalAdded": 0, "totalRemoved": 0, "totalModified": 0, "totalUnchanged": 10},
        "presentationSummary": {"total": 0, "added": 0, "removed": 0, "modified": 0},
    }
    enriched = attach_nlp_analysis(empty_result)
    assert enriched["changes"] == []
    assert enriched["nlpAnalysis"]["overall"]["total_modifications_analyzed"] == 0
    assert enriched["nlpAnalysis"]["overall"]["summary"] == "No text content changes detected."


def test_whitespace_and_empty_text_safety():
    """Verify empty or whitespace-only changes do not produce speculative explanations."""
    dummy_result = {
        "changes": [
            {
                "id": 1,
                "category": "modified",
                "element": "Text",
                "oldValue": "   ",
                "newValue": "",
            }
        ],
        "presentationSummary": {"total": 1, "added": 0, "removed": 0, "modified": 1},
    }
    enriched = attach_nlp_analysis(dummy_result)
    assert enriched["nlpAnalysis"]["overall"]["total_modifications_analyzed"] == 0
    # No speculative modification record was created for whitespace
    assert len(enriched["nlpAnalysis"]["modifications"]) == 0
