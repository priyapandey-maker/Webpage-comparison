"""Unit and integration tests for the AI explanation layer.

Verifies:
1. Input payload construction grounds exclusively on supplied changes.
2. Valid structured AI response parsing and validation.
3. Filtering and rejection of unknown change IDs.
4. Deduplication of change IDs across topic groups (single primary group assignment).
5. 100% change coverage through intelligent fallback grouping of unassigned changes.
6. Separation of technical assets (stylesheets/icons) and path normalizations.
7. Safe fallback on invalid JSON.
8. Safe fallback on Ollama connection errors / unavailable service.
9. Safe fallback on request timeout.
10. Immediate return of None when AI is disabled via configuration.
11. Handling of zero changes without unnecessary network calls.
12. Integration with POST /api/compare and POST /api/wayback/compare.
13. Complete preservation of existing Phase 1 counts and classifications.
14. Regression testing on multi-category change sets (e.g. IANA navigation and assets).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
from unittest.mock import AsyncMock, MagicMock, patch

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
    _get_ollama_lock,
    _reset_ollama_lock,
    build_compact_changes_payload,
    generate_ai_summary,
    is_navigation_change,
    is_path_normalization_change,
    is_protocol_upgrade_change,
    is_technical_asset_change,
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

SAMPLE_IANA_CHANGES = [
    {"id": 1, "category": "added", "type": "link", "element": "Link", "oldValue": None, "newValue": "RIR Allocation Data", "description": "Link was added.", "explanation": None},
    {"id": 2, "category": "added", "type": "list_item", "element": "List item", "oldValue": None, "newValue": "Abuse Information", "description": "List item was added.", "explanation": None},
    {"id": 3, "category": "removed", "type": "paragraph", "element": "Paragraph", "oldValue": "Empty paragraph in the footer", "newValue": None, "description": "Paragraph was removed.", "explanation": None},
    {"id": 4, "category": "removed", "type": "link", "element": "Link", "oldValue": "Contact Us", "newValue": None, "description": "Link was removed.", "explanation": None},
    {"id": 5, "category": "modified", "type": "link", "element": "Link destination", "oldValue": "/abuse", "newValue": "/help/abuse", "description": "Link destination was updated.", "explanation": "Link destination changed from '/abuse' to '/help/abuse'."},
    {"id": 6, "category": "modified", "type": "link", "element": "Link destination", "oldValue": "http://pti.icann.org", "newValue": "https://pti.icann.org", "description": "Link destination was updated.", "explanation": "Link destination changed from 'http://pti.icann.org' to 'https://pti.icann.org' (upgraded to secure HTTPS)."},
    {"id": 7, "category": "modified", "type": "link", "element": "Link destination", "oldValue": "http://www.icann.org/", "newValue": "https://www.icann.org/", "description": "Link destination was updated.", "explanation": "Link destination changed from 'http://www.icann.org/' to 'https://www.icann.org/' (upgraded to secure HTTPS)."},
    {"id": 8, "category": "modified", "type": "link", "element": "Link", "oldValue": "Abuse Information", "newValue": "Number Registries", "description": "Link text and attributes were updated.", "explanation": "Link label changed from 'Abuse Information' to 'Number Registries', and its destination changed from '/abuse' to '/numbers/registries'."},
    {"id": 9, "category": "modified", "type": "link", "element": "Link", "oldValue": "Presentations", "newValue": "News", "description": "Link text and attributes were updated.", "explanation": "Link label changed from 'Presentations' to 'News', and its destination changed from '/about/presentations' to '/news'."},
    {"id": 10, "category": "modified", "type": "link", "element": "Link", "oldValue": "Reports", "newValue": "Performance", "description": "Link text and attributes were updated.", "explanation": "Link label changed from 'Reports' to 'Performance', and its destination changed from '/reports' to '/performance'."},
    {"id": 11, "category": "modified", "type": "link", "element": "Link", "oldValue": "Performance", "newValue": "The Organization", "description": "Link text and attributes were updated.", "explanation": "Link label changed from 'Performance' to 'The Organization', and its destination changed from '/performance' to '/about/organization'."},
    {"id": 12, "category": "modified", "type": "link", "element": "Link", "oldValue": "Reviews", "newValue": "Archive", "description": "Link text and attributes were updated.", "explanation": "Link label changed from 'Reviews' to 'Archive', and its destination changed from '/reviews' to '/archive'."},
    {"id": 13, "category": "modified", "type": "link", "element": "Link", "oldValue": "Excellence", "newValue": "Contact Us", "description": "Link text and attributes were updated.", "explanation": "Link label changed from 'Excellence' to 'Contact Us', and its destination changed from '/about/excellence' to '/contact'."},
    {"id": 14, "category": "modified", "type": "link", "element": "Link destination", "oldValue": "about/", "newValue": "/about", "description": "Link destination was updated.", "explanation": "Link destination changed from 'about/' to '/about'."},
    {"id": 15, "category": "modified", "type": "link_element", "element": "link element", "oldValue": "href: /_css/2022/iana_website.css, rel: stylesheet", "newValue": "href: /static/css/iana_website.68dd615b61e5.css, rel: stylesheet", "description": "link element attributes were updated.", "explanation": "Technical asset reference updated (stylesheet)."},
    {"id": 16, "category": "modified", "type": "link_element", "element": "link element", "oldValue": "href: /_img/bookmark_icon.ico, rel: shortcut, icon", "newValue": "href: /static/img/bookmark_icon.e14a2530b3e9.ico, rel: shortcut, icon", "description": "link element attributes were updated.", "explanation": "Technical asset reference updated (shortcut icon)."},
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
    assert "[Change #1]" in payload
    assert "Navigation" in payload
    assert "research publications" in payload.lower()
    assert "[Change #2]" in payload
    assert "Removed Content" in payload
    assert "[Change #3]" in payload
    assert "30 June 2027" in payload


def test_build_compact_changes_payload_large_changes_neutral_wording():
    """Verify that when changes exceed max_items, neutral wording is used without calling them minor."""
    large_changes = [
        {"id": i, "category": "added", "type": "paragraph", "element": "Paragraph", "newValue": f"Item {i}"}
        for i in range(1, 45)
    ]
    payload, valid_ids = build_compact_changes_payload(large_changes, max_items=35)
    assert len(valid_ids) == 44
    assert "[Change #1]" in payload
    assert "[Change #35]" in payload
    assert "[Change #36]" not in payload
    assert "additional detected changes are not individually included in this prompt" in payload
    assert "minor" not in payload.lower()


def test_classification_helpers():
    """Verify classification helpers accurately partition assets, navigation, and path normalizations."""
    stylesheet_change = SAMPLE_IANA_CHANGES[14]
    favicon_change = SAMPLE_IANA_CHANGES[15]
    path_norm_change = SAMPLE_IANA_CHANGES[13]
    nav_change = SAMPLE_IANA_CHANGES[4]
    content_change = SAMPLE_IANA_CHANGES[1]

    # Technical assets
    assert is_technical_asset_change(stylesheet_change) is True
    assert is_technical_asset_change(favicon_change) is True
    assert is_technical_asset_change(path_norm_change) is False
    assert is_technical_asset_change(nav_change) is False

    # Path normalization
    assert is_path_normalization_change(path_norm_change) is True
    assert is_path_normalization_change(stylesheet_change) is False

    # Navigation
    assert is_navigation_change(nav_change) is True
    assert is_navigation_change(path_norm_change) is True
    assert is_navigation_change(stylesheet_change) is False
    assert is_navigation_change(content_change) is False


def test_technical_asset_genuine_vs_ordinary_text():
    """Verify that genuine technical assets are detected while ordinary text mentioning extensions is not."""
    # Genuine technical assets
    stylesheet = {
        "element": "link element",
        "type": "link_element",
        "oldValue": "href: /_css/2022/style.css, rel: stylesheet",
        "newValue": "href: /static/css/style.hash.css, rel: stylesheet",
        "explanation": "Technical asset reference updated (stylesheet).",
    }
    shortcut_icon = {
        "element": "link element",
        "type": "link_element",
        "oldValue": "href: /favicon.ico, rel: shortcut, icon",
        "newValue": "href: /static/favicon.hash.ico, rel: shortcut, icon",
        "explanation": "Technical asset reference updated (shortcut icon).",
    }
    script_elem = {
        "element": "script element",
        "type": "script_element",
        "oldValue": "src: /js/app.js",
        "newValue": "src: /static/js/app.hash.js",
        "explanation": "script element attributes were updated.",
    }
    style_elem = {
        "element": "style element",
        "type": "style_element",
        "oldValue": "body { margin: 0; }",
        "newValue": "body { margin: 8px; }",
        "explanation": "style element text updated.",
    }

    assert is_technical_asset_change(stylesheet) is True
    assert is_technical_asset_change(shortcut_icon) is True
    assert is_technical_asset_change(script_elem) is True
    assert is_technical_asset_change(style_elem) is True

    # Ordinary text mentioning file extensions MUST NOT be classified as technical assets
    paragraph_mentioning_css = {
        "element": "Paragraph",
        "type": "paragraph",
        "oldValue": "Check out tutorial.css and custom.css for examples.",
        "newValue": "Check out modern.css and custom.css for examples.",
        "explanation": "Paragraph text was updated.",
    }
    heading_mentioning_js = {
        "element": "Heading",
        "type": "heading",
        "oldValue": "Chapter 1: Getting Started with Node.js",
        "newValue": "Chapter 1: Getting Started with Deno.js and Node.js",
        "explanation": "Heading text was updated.",
    }
    article_mentioning_ico = {
        "element": "Article",
        "type": "article",
        "oldValue": "Icons can be saved as logo.ico or favicon.ico.",
        "newValue": "Icons should be saved as logo.svg or favicon.ico.",
        "explanation": "Article text was updated.",
    }
    anchor_link_to_svg = {
        "element": "Link",
        "type": "link",
        "oldValue": "Download vector icon (/downloads/icon.svg)",
        "newValue": "Download latest vector (/downloads/icon.svg)",
        "explanation": "Link text updated.",
    }
    user_image = {
        "element": "Image",
        "type": "image",
        "oldValue": "src: /images/banner.png, alt: Summer Sale",
        "newValue": "src: /images/banner.png, alt: Winter Sale",
        "explanation": "Image alt attribute updated.",
    }

    assert is_technical_asset_change(paragraph_mentioning_css) is False
    assert is_technical_asset_change(heading_mentioning_js) is False
    assert is_technical_asset_change(article_mentioning_ico) is False
    assert is_technical_asset_change(anchor_link_to_svg) is False
    assert is_technical_asset_change(user_image) is False


def test_protocol_upgrade_cases():
    """Verify strict protocol upgrade detection: same host/path HTTP->HTTPS vs destination changes."""
    # 1. Same host, HTTP to HTTPS -> True
    same_host_upgrade = {
        "element": "Link destination",
        "type": "link",
        "oldValue": "http://example.com/about",
        "newValue": "https://example.com/about",
    }
    assert is_protocol_upgrade_change(same_host_upgrade) is True

    # 2. Different hosts, HTTP to HTTPS -> False (destination change)
    diff_host = {
        "element": "Link destination",
        "type": "link",
        "oldValue": "http://example.org/about",
        "newValue": "https://example.com/about",
    }
    assert is_protocol_upgrade_change(diff_host) is False

    # 3. Different paths -> False (destination change)
    diff_path = {
        "element": "Link destination",
        "type": "link",
        "oldValue": "http://example.com/about",
        "newValue": "https://example.com/contact",
    }
    assert is_protocol_upgrade_change(diff_path) is False

    # 4. Query-string changes -> False (destination/parameter change)
    diff_query = {
        "element": "Link destination",
        "type": "link",
        "oldValue": "http://example.com/search?q=1",
        "newValue": "https://example.com/search?q=2",
    }
    assert is_protocol_upgrade_change(diff_query) is False

    # 5. Normalization edge cases:
    # Trailing slash normalization -> True
    trailing_slash = {
        "element": "Link destination",
        "type": "link",
        "oldValue": "http://example.com",
        "newValue": "https://example.com/",
    }
    assert is_protocol_upgrade_change(trailing_slash) is True

    # Standard default ports (80 for http, 443 for https) -> True
    default_ports = {
        "element": "Link destination",
        "type": "link",
        "oldValue": "http://example.com:80/docs",
        "newValue": "https://example.com/docs",
    }
    assert is_protocol_upgrade_change(default_ports) is True

    # Non-default ports -> False
    custom_ports = {
        "element": "Link destination",
        "type": "link",
        "oldValue": "http://example.com:8080/docs",
        "newValue": "https://example.com:8443/docs",
    }
    assert is_protocol_upgrade_change(custom_ports) is False

    # Different fragment -> False
    diff_fragment = {
        "element": "Link destination",
        "type": "link",
        "oldValue": "http://example.com/docs#intro",
        "newValue": "https://example.com/docs#summary",
    }
    assert is_protocol_upgrade_change(diff_fragment) is False


@pytest.mark.anyio
async def test_topic_assignment_deterministic_role_priority_overrides_ai_order():
    """Verify deterministic role classification overrides arbitrary AI group ordering.

    If the AI places a navigation change inside a 'Content Updates' group that appears first,
    deterministic classification priority ensures the navigation change is assigned to the
    'Navigation Changes' group instead.
    """
    ai_response_json = {
        "executive_summary": "Testing deterministic role priority over AI group ordering.",
        "key_takeaways": ["Takeaway"],
        "topic_groups": [
            {
                "topic": "Content Updates",
                "description": "Content group incorrectly claiming navigation ID 1.",
                "change_ids": [1, 2, 3],
                "significance": "medium",
            },
            {
                "topic": "Navigation Changes",
                "description": "Navigation group.",
                "change_ids": [4],
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

    changes = list(SAMPLE_CHANGES) + [
        {
            "id": 4,
            "category": "modified",
            "type": "link",
            "element": "Link",
            "oldValue": "Old Menu",
            "newValue": "New Menu",
            "explanation": "Navigation menu link updated.",
        }
    ]

    result = await generate_ai_summary({"changes": changes}, client=mock_client)
    assert result is not None

    content_group = next(g for g in result["topic_groups"] if g["topic"] == "Content Updates")
    nav_group = next(g for g in result["topic_groups"] if g["topic"] == "Navigation Changes")

    # Change ID 1 is a navigation link, so it MUST be in Navigation Changes, NOT Content Updates!
    assert 1 not in content_group["change_ids"]
    assert 1 in nav_group["change_ids"]
    assert 4 in nav_group["change_ids"]

    # Content changes 2 and 3 remain in Content Updates
    assert content_group["change_ids"] == [2, 3]

    # Every change ID appears in exactly one group
    all_assigned = [cid for g in result["topic_groups"] for cid in g["change_ids"]]
    assert sorted(all_assigned) == [1, 2, 3, 4]


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
async def test_ai_summary_deduplicates_change_ids_across_groups():
    """Verify change IDs appearing in multiple topic groups are deduplicated to their first group."""
    ai_response_json = {
        "executive_summary": "Summary with overlapping IDs across groups.",
        "key_takeaways": ["Takeaway 1"],
        "topic_groups": [
            {
                "topic": "Navigation Changes",
                "description": "Primary navigation updates.",
                "change_ids": [1],
                "significance": "high",
            },
            {
                "topic": "Content Updates",
                "description": "Content updates duplicating ID 1.",
                "change_ids": [1, 2, 3],
                "significance": "medium",
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
    # Group 1 keeps [1]
    assert result["topic_groups"][0]["change_ids"] == [1]
    # Group 2 has [1] deduplicated, keeping only [2, 3]
    assert result["topic_groups"][1]["change_ids"] == [2, 3]

    # Verify no ID appears twice across all groups
    all_cids = [cid for g in result["topic_groups"] for cid in g["change_ids"]]
    assert len(all_cids) == len(set(all_cids))


@pytest.mark.anyio
async def test_ai_summary_coverage_fallback_groups_unassigned_ids():
    """Verify that any detected change IDs omitted by the model are automatically grouped via fallback."""
    ai_response_json = {
        "executive_summary": "Model only returned topic group for change 1.",
        "key_takeaways": ["Takeaway 1"],
        "topic_groups": [
            {
                "topic": "Navigation Changes",
                "description": "Added research link.",
                "change_ids": [1],
                "significance": "high",
            }
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
    # All 3 changes must be represented
    all_cids = set(cid for g in result["topic_groups"] for cid in g["change_ids"])
    assert all_cids == {1, 2, 3}

    # Group 2 was created by fallback for content changes 2 and 3
    assert len(result["topic_groups"]) == 2
    assert result["topic_groups"][1]["topic"] == "Content Updates"
    assert result["topic_groups"][1]["change_ids"] == [2, 3]


@pytest.mark.anyio
async def test_ai_summary_enforces_technical_asset_separation():
    """Verify that technical assets incorrectly grouped into general content are moved to technical assets."""
    ai_response_json = {
        "executive_summary": "Model misclassified stylesheet as content update.",
        "key_takeaways": ["Takeaway 1"],
        "topic_groups": [
            {
                "topic": "Content Updates",
                "description": "Misclassified group containing stylesheet #15.",
                "change_ids": [2, 3, 15],
                "significance": "high",
            }
        ],
    }

    mock_resp = httpx.Response(
        status_code=200,
        json={"message": {"content": json.dumps(ai_response_json)}},
        request=httpx.Request("POST", "http://127.0.0.1:11434/api/chat"),
    )
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = mock_resp

    comparison = {"changes": SAMPLE_IANA_CHANGES}
    result = await generate_ai_summary(comparison, client=mock_client)

    assert result is not None
    content_group = next(g for g in result["topic_groups"] if g["topic"] == "Content Updates")
    # Stylesheet #15 must NOT be in Content Updates
    assert 15 not in content_group["change_ids"]

    # Stylesheet #15 and icon #16 must be in Technical Asset Updates
    asset_group = next(g for g in result["topic_groups"] if "Asset" in g["topic"])
    assert 15 in asset_group["change_ids"]
    assert 16 in asset_group["change_ids"]


@pytest.mark.anyio
async def test_ai_summary_filters_unknown_change_ids():
    """Verify that hallucinated or unknown change IDs are filtered out."""
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
    # All valid IDs {1, 2, 3} are present via valid groups + fallback
    all_cids = set(cid for g in result["topic_groups"] for cid in g["change_ids"])
    assert all_cids == {1, 2, 3}
    assert 999 not in all_cids
    assert 1000 not in all_cids
    assert 888 not in all_cids


@pytest.mark.anyio
async def test_iana_comparison_regression_classification():
    """Verify complete, grounded grouping for all 16 IANA changes."""
    ai_response_json = {
        "executive_summary": "The IANA homepage navigation was reorganized and asset references were updated.",
        "key_takeaways": [
            "Navigation menus across the site were reorganized.",
            "Technical assets including stylesheets and shortcut icons were updated.",
        ],
        "topic_groups": [
            {
                "topic": "Navigation Changes",
                "description": "Reorganization of menu links and destinations.",
                "change_ids": [1, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14],
                "significance": "high",
            },
            {
                "topic": "Technical Asset Updates",
                "description": "Updated stylesheet and favicon references.",
                "change_ids": [15, 16],
                "significance": "low",
            },
            {
                "topic": "Content Updates",
                "description": "Addition of abuse info and removal of empty footer paragraph.",
                "change_ids": [2, 3],
                "significance": "medium",
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

    comparison = {"changes": SAMPLE_IANA_CHANGES}
    result = await generate_ai_summary(comparison, client=mock_client)

    assert result is not None
    assert len(result["topic_groups"]) == 3

    # Group 1: Navigation Changes (IDs 1, 4-14, including path normalization 14)
    nav_group = next(g for g in result["topic_groups"] if g["topic"] == "Navigation Changes")
    assert set(nav_group["change_ids"]) == {1, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14}
    assert 14 in nav_group["change_ids"]

    # Group 2: Technical Asset Updates (IDs 15, 16)
    asset_group = next(g for g in result["topic_groups"] if "Asset" in g["topic"])
    assert set(asset_group["change_ids"]) == {15, 16}

    # Group 3: Content Updates (IDs 2, 3)
    content_group = next(g for g in result["topic_groups"] if g["topic"] == "Content Updates")
    assert set(content_group["change_ids"]) == {2, 3}

    # 100% coverage
    all_assigned = [cid for g in result["topic_groups"] for cid in g["change_ids"]]
    assert len(all_assigned) == 16
    assert set(all_assigned) == set(range(1, 17))


@pytest.mark.anyio
async def test_ai_summary_token_limit_reached_done_reason_length():
    """Verify safe handling and diagnostics when Ollama response hits the token limit with done_reason='length'."""
    # Simulates truncated JSON cut off mid-string when num_predict is reached
    truncated_content = '{"executive_summary": "The page was updated with new links and content", "key_takeaways": ["Takeaway 1", "Take'
    mock_resp = httpx.Response(
        status_code=200,
        json={
            "message": {"content": truncated_content},
            "done_reason": "length",
            "eval_count": 500,
        },
        request=httpx.Request("POST", "http://127.0.0.1:11434/api/chat"),
    )
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = mock_resp

    comparison = {"changes": SAMPLE_CHANGES}
    result = await generate_ai_summary(comparison, client=mock_client)
    assert result is None, "Truncated JSON from length cutoff must safely return None"


@pytest.mark.anyio
async def test_ai_summary_wikipedia_sized_35_changes_all_ids_represented():
    """Verify that a 35-change comparison accounts for 100% of supplied IDs across topic groups."""
    wiki_changes = [
        {
            "id": i,
            "category": "modified" if i % 2 == 0 else "added",
            "type": "link" if i <= 10 else ("link element" if i > 30 else "paragraph"),
            "element": "Link" if i <= 10 else ("link element" if i > 30 else "Paragraph"),
            "oldValue": f"Old content for item {i}" if i % 2 == 0 else None,
            "newValue": f"New content for item {i}",
            "explanation": f"Updated item {i} destination or content" if i % 2 == 0 else f"Added item {i}",
        }
        for i in range(1, 36)
    ]

    # AI returns 2 focused groups claiming only a subset of IDs (e.g. 1-5 and 11-15)
    mock_ai_response = {
        "executive_summary": "Wikipedia was updated with revised navigation links and content articles.",
        "key_takeaways": [
            "Navigation menus across the portal were reorganized.",
            "Content paragraphs and portal sections were updated.",
        ],
        "topic_groups": [
            {
                "topic": "Navigation Changes",
                "description": "Navigation links and portals were updated.",
                "change_ids": [1, 2, 3, 4, 5],
                "significance": "high",
            },
            {
                "topic": "Content Updates",
                "description": "Article paragraphs and sections were revised.",
                "change_ids": [11, 12, 13, 14, 15],
                "significance": "medium",
            },
        ],
    }

    mock_resp = httpx.Response(
        status_code=200,
        json={
            "message": {"content": json.dumps(mock_ai_response)},
            "done_reason": "stop",
            "eval_count": 280,
        },
        request=httpx.Request("POST", "http://127.0.0.1:11434/api/chat"),
    )
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = mock_resp

    comparison = {"changes": wiki_changes}
    result = await generate_ai_summary(comparison, client=mock_client)
    assert result is not None

    # Verify all 35 IDs are represented in topic_groups exactly once
    all_assigned = [cid for g in result["topic_groups"] for cid in g["change_ids"]]
    assert len(all_assigned) == 35, "All 35 change IDs must be assigned"
    assert len(set(all_assigned)) == 35, "No duplicate change IDs across topic groups"
    assert set(all_assigned) == set(range(1, 36))

    # Verify technical assets (changes 31-35) were separated into Technical Asset Updates
    asset_groups = [g for g in result["topic_groups"] if "technical" in g["topic"].lower() or "asset" in g["topic"].lower()]
    assert len(asset_groups) >= 1
    asset_ids = [cid for g in asset_groups for cid in g["change_ids"]]
    for cid in range(31, 36):
        assert cid in asset_ids


def test_ai_config_num_predict_defaults_to_500():
    """Verify default num_predict is 500."""
    cfg = AIConfig.from_env()
    assert cfg.num_predict == 500


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


# ============================================================================
# Concurrency & Concurrency Serialization Tests
# ============================================================================

@pytest.mark.anyio
async def test_concurrent_ai_summary_requests_serialized():
    """Verify that two concurrent summary requests never execute Ollama inference simultaneously."""
    _reset_ollama_lock()
    active_inferences = 0
    max_concurrent = 0

    valid_response_data = {
        "message": {
            "content": json.dumps({
                "executive_summary": "Concurrent test summary.",
                "key_takeaways": ["Takeaway 1", "Takeaway 2"],
                "topic_groups": [],
            })
        },
        "done_reason": "stop",
    }

    async def mock_post(*args, **kwargs):
        nonlocal active_inferences, max_concurrent
        active_inferences += 1
        if active_inferences > max_concurrent:
            max_concurrent = active_inferences
        await asyncio.sleep(0.08)
        active_inferences -= 1
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.json.return_value = valid_response_data
        return resp

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=mock_post)

    comp1 = {"changes": [{"id": 1, "category": "added", "element": "h1", "description": "Title added"}]}
    comp2 = {"changes": [{"id": 2, "category": "modified", "element": "p", "description": "Text changed"}]}

    task1 = asyncio.create_task(generate_ai_summary(comp1, client=mock_client, return_status=True))
    task2 = asyncio.create_task(generate_ai_summary(comp2, client=mock_client, return_status=True))

    res1, res2 = await asyncio.gather(task1, task2)

    assert max_concurrent == 1, f"Expected strictly 1 concurrent inference, but saw {max_concurrent}"
    assert res1[1] == "generated"
    assert res2[1] == "generated"
    assert _get_ollama_lock().locked() is False


@pytest.mark.anyio
async def test_second_request_http_timeout_starts_after_acquiring_lock():
    """Verify that the second request's HTTP timeout window starts only after acquiring the lock."""
    _reset_ollama_lock()
    req1_end_time = 0.0
    req2_start_time = 0.0

    valid_response_data = {
        "message": {
            "content": json.dumps({
                "executive_summary": "Sequential execution test.",
                "key_takeaways": ["Point 1", "Point 2"],
                "topic_groups": [],
            })
        },
        "done_reason": "stop",
    }

    async def mock_post_1(*args, **kwargs):
        nonlocal req1_end_time
        await asyncio.sleep(0.1)
        req1_end_time = time.monotonic()
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.json.return_value = valid_response_data
        return resp

    async def mock_post_2(*args, **kwargs):
        nonlocal req2_start_time
        req2_start_time = time.monotonic()
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.json.return_value = valid_response_data
        return resp

    client1 = AsyncMock()
    client1.post = AsyncMock(side_effect=mock_post_1)

    client2 = AsyncMock()
    client2.post = AsyncMock(side_effect=mock_post_2)

    comp = {"changes": [{"id": 1, "category": "added", "element": "h1", "description": "Title added"}]}

    t1 = asyncio.create_task(generate_ai_summary(comp, client=client1, return_status=True))
    await asyncio.sleep(0.01)  # Ensure t1 acquires the lock first
    t2 = asyncio.create_task(generate_ai_summary(comp, client=client2, return_status=True))

    await asyncio.gather(t1, t2)

    assert req2_start_time >= req1_end_time, "Request 2 HTTP request started before Request 1 finished!"
    assert _get_ollama_lock().locked() is False


@pytest.mark.anyio
async def test_lock_released_on_timeout_and_exception():
    """Verify that the inference lock is safely released on httpx timeout or connection exception."""
    _reset_ollama_lock()

    # 1. TimeoutException releases lock
    mock_timeout_client = AsyncMock()
    mock_timeout_client.post.side_effect = httpx.TimeoutException("Read timeout after 90s")

    comp = {"changes": [{"id": 1, "category": "added", "element": "h1", "description": "Title added"}]}
    res, status = await generate_ai_summary(comp, client=mock_timeout_client, return_status=True)
    assert res is None
    assert status == "timeout"
    assert _get_ollama_lock().locked() is False

    # 2. ConnectError releases lock
    mock_conn_client = AsyncMock()
    mock_conn_client.post.side_effect = httpx.ConnectError("Connection refused")

    res, status = await generate_ai_summary(comp, client=mock_conn_client, return_status=True)
    assert res is None
    assert status == "unavailable"
    assert _get_ollama_lock().locked() is False


@pytest.mark.anyio
async def test_cancelled_waiting_request_does_not_cancel_active_request():
    """Verify that a cancelled waiting request does not cancel the currently active inference."""
    _reset_ollama_lock()
    active_finished = False

    valid_response_data = {
        "message": {
            "content": json.dumps({
                "executive_summary": "Active task completed.",
                "key_takeaways": ["Active ok", "No cancel"],
                "topic_groups": [],
            })
        },
        "done_reason": "stop",
    }

    async def mock_post_active(*args, **kwargs):
        nonlocal active_finished
        await asyncio.sleep(0.15)
        active_finished = True
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.json.return_value = valid_response_data
        return resp

    client_active = AsyncMock()
    client_active.post = AsyncMock(side_effect=mock_post_active)

    client_waiting = AsyncMock()

    comp = {"changes": [{"id": 1, "category": "added", "element": "h1", "description": "Title added"}]}

    task_active = asyncio.create_task(generate_ai_summary(comp, client=client_active, return_status=True))
    await asyncio.sleep(0.02)  # Give task_active time to acquire the lock

    task_waiting = asyncio.create_task(generate_ai_summary(comp, client=client_waiting, return_status=True))
    await asyncio.sleep(0.02)  # task_waiting is now waiting on lock

    # Cancel the waiting task
    task_waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task_waiting

    # Active task must complete cleanly
    res_active, status_active = await task_active
    assert active_finished is True
    assert status_active == "generated"
    assert res_active is not None
    assert _get_ollama_lock().locked() is False


@pytest.mark.anyio
async def test_queue_wait_timeout_returns_busy():
    """Verify that exceeding max_queue_wait returns status='busy' gracefully."""
    _reset_ollama_lock()
    config = AIConfig(max_queue_wait=0.05)

    async def slow_post(*args, **kwargs):
        await asyncio.sleep(0.2)
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.json.return_value = {
            "message": {"content": '{"executive_summary":"ok","key_takeaways":["a","b"],"topic_groups":[]}'},
            "done_reason": "stop",
        }
        return resp

    client1 = AsyncMock()
    client1.post = AsyncMock(side_effect=slow_post)

    client2 = AsyncMock()

    comp = {"changes": [{"id": 1, "category": "added", "element": "h1", "description": "Title added"}]}

    t1 = asyncio.create_task(generate_ai_summary(comp, config=config, client=client1, return_status=True))
    await asyncio.sleep(0.01)

    t2 = asyncio.create_task(generate_ai_summary(comp, config=config, client=client2, return_status=True))

    res2, status2 = await t2
    assert res2 is None
    assert status2 == "busy"

    res1, status1 = await t1
    assert status1 == "generated"
    assert _get_ollama_lock().locked() is False


def test_api_ai_failure_preserves_comparison_and_sets_status():
    """Verify that AI failure returns aiSummary=None, preserves comparison results, and populates aiStatus."""
    client = TestClient(app)

    # 1. Test busy status preservation
    with patch("api.generate_ai_summary", new=AsyncMock(return_value=(None, "busy"))):
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
    assert data["aiSummary"] is None
    assert data["aiStatus"] == "busy"
    assert data["presentationSummary"]["total"] == 21
    assert len(data["changes"]) == 21

    # 2. Test timeout status preservation
    with patch("api.generate_ai_summary", new=AsyncMock(return_value=(None, "timeout"))):
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
    assert data["aiSummary"] is None
    assert data["aiStatus"] == "timeout"
    assert data["presentationSummary"]["total"] == 21


# ============================================================================
# Summary Quality, Topic Grouping & Schema Artifact Regression Tests
# ============================================================================

def test_clean_takeaways_filters_internal_schema_tokens():
    """Verify that AISummary rejects schema field names and syntax artifacts from takeaways."""
    # 1. Internal schema tokens
    raw_takeaways = [
        "The newer version features new content, including a header and navigation.",
        "The main menu layout has been updated.",
        "topic_groups",
        "`topic_groups`",
        "change_ids",
        "executive_summary",
        "{}",
        "[]",
    ]
    summary = AISummary(
        executive_summary="Valid summary.",
        key_takeaways=raw_takeaways,
        topic_groups=[],
    )
    assert len(summary.key_takeaways) == 2
    assert "topic_groups" not in summary.key_takeaways
    assert "`topic_groups`" not in summary.key_takeaways
    assert "change_ids" not in summary.key_takeaways
    assert summary.key_takeaways[0].startswith("The newer version")
    assert summary.key_takeaways[1].startswith("The main menu")


@pytest.mark.anyio
async def test_ai_summary_empty_topic_groups_removed():
    """Verify that any topic group with 0 assigned changes is excluded from the final topic_groups list."""
    _reset_ollama_lock()
    changes = [
        {"id": 1, "category": "added", "element": "h1", "description": "Title added"},
        {"id": 2, "category": "modified", "element": "p", "description": "Text updated"},
    ]

    # AI returns 3 topic groups, but group 2 and 3 have no valid changes
    mock_response = {
        "executive_summary": "Two content changes were made.",
        "key_takeaways": ["Heading was added.", "Paragraph was revised."],
        "topic_groups": [
            {
                "topic": "Content Updates",
                "description": "Text updates.",
                "change_ids": [1, 2],
                "significance": "medium",
            },
            {
                "topic": "Navigation Changes",
                "description": "Navigation links.",
                "change_ids": [],  # Empty group
                "significance": "high",
            },
            {
                "topic": "Technical Asset Updates",
                "description": "Stylesheet updates.",
                "change_ids": [999],  # Unknown ID only
                "significance": "low",
            },
        ],
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "message": {"content": json.dumps(mock_response)},
        "done_reason": "stop",
    }
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp

    comp = {"changes": changes}
    res, status = await generate_ai_summary(comp, client=mock_client, return_status=True)

    assert status == "generated"
    assert res is not None
    # Empty groups must be excluded
    assert len(res["topic_groups"]) == 1
    assert res["topic_groups"][0]["topic"] == "Content Updates"
    assert res["topic_groups"][0]["change_ids"] == [1, 2]


@pytest.mark.anyio
async def test_large_comparison_beyond_35_changes_preserves_all_ids_and_distinguishes_roles():
    """Verify that in a large comparison (>35 changes), all IDs are preserved, 0 duplicates occur,
    and unassigned additions, removals, modifications, and technical assets are properly grouped."""
    _reset_ollama_lock()
    large_changes = []
    # 5 technical assets
    for i in range(1, 6):
        large_changes.append({
            "id": i,
            "category": "modified",
            "element": "link element",
            "type": "link_element",
            "oldValue": "rel: stylesheet",
            "newValue": f"stylesheet_{i}.css",
            "description": "Stylesheet updated.",
        })
    # 15 navigation links
    for i in range(6, 21):
        large_changes.append({
            "id": i,
            "category": "modified",
            "element": "Link",
            "type": "link",
            "sourcePath": f"/html/body/header/nav/ul/li[{i}]/a[0]",
            "oldValue": f"/old-link-{i}",
            "newValue": f"/new-link-{i}",
            "description": "Navigation link updated.",
        })
    # 30 added content items
    for i in range(21, 51):
        large_changes.append({
            "id": i,
            "category": "added",
            "element": "Paragraph",
            "type": "paragraph",
            "sourcePath": "",
            "targetPath": f"/html/body/main/section/p[{i}]",
            "oldValue": None,
            "newValue": f"New paragraph {i}",
            "description": "Paragraph added.",
        })
    # 25 removed content items
    for i in range(51, 76):
        large_changes.append({
            "id": i,
            "category": "removed",
            "element": "Paragraph",
            "type": "paragraph",
            "sourcePath": f"/html/body/main/section/p[{i}]",
            "targetPath": "",
            "oldValue": f"Old paragraph {i}",
            "newValue": None,
            "description": "Paragraph removed.",
        })
    # 25 modified content items (total 100 changes)
    for i in range(76, 101):
        large_changes.append({
            "id": i,
            "category": "modified",
            "element": "Heading",
            "type": "heading",
            "oldValue": f"Old heading {i}",
            "newValue": f"New heading {i}",
            "description": "Heading updated.",
        })

    assert len(large_changes) == 100

    # Model only received the first 35 changes and returns 2 AI groups
    mock_response = {
        "executive_summary": "The site was updated with revised navigation links and content sections.",
        "key_takeaways": [
            "Navigation menus across the portal were updated.",
            "Content sections and assets were revised.",
        ],
        "topic_groups": [
            {
                "topic": "Navigation Changes",
                "description": "Navigation links were updated.",
                "change_ids": [6, 7, 8, 9, 10],
                "significance": "high",
            },
            {
                "topic": "Technical Asset Updates",
                "description": "Stylesheets updated.",
                "change_ids": [1, 2],
                "significance": "low",
            },
        ],
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "message": {"content": json.dumps(mock_response)},
        "done_reason": "stop",
    }
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp

    comp = {"changes": large_changes}
    res, status = await generate_ai_summary(comp, client=mock_client, return_status=True)

    assert status == "generated"
    assert res is not None

    # 1. 100% of the 100 change IDs are assigned
    all_assigned = [cid for g in res["topic_groups"] for cid in g["change_ids"]]
    assert len(all_assigned) == 100, f"Expected 100 assigned changes, got {len(all_assigned)}"
    assert len(set(all_assigned)) == 100, "Must have zero duplicate change IDs"
    assert set(all_assigned) == set(range(1, 101))

    # 2. Distinct roles are formed: Asset, Nav, Added, Removed, Modified
    group_topics = [g["topic"] for g in res["topic_groups"]]
    assert "Navigation Changes" in group_topics
    assert "Technical Asset Updates" in group_topics
    assert any("new content" in t.lower() or "added" in t.lower() for t in group_topics)
    assert any("removed" in t.lower() for t in group_topics)

    # 3. No empty groups
    for g in res["topic_groups"]:
        assert len(g["change_ids"]) > 0
