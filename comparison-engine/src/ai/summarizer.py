"""AI Explanation Layer for Webpage Comparison using local Ollama LLM.

Constructs grounded change payloads and queries a locally hosted LLM (qwen2.5:1.5b)
using CPU inference to produce structured executive summaries and topic groupings.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from pydantic import ValidationError

from .schemas import AIConfig, AISummary, TopicGroup

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an objective webpage comparison analyst explaining changes between two webpage versions.
Your task is to summarize and explain ONLY the structured change records provided to you.

Rules:
1. Grounding: Rely strictly and exclusively on the supplied change items. Do not invent, assume, or extrapolate changes that are not in the input data.
2. Grouping: Group related changes into 2 to 4 logical topic groups (e.g., 'Navigation Changes', 'New Content', 'Removed Content', 'Content Updates', 'Security and Technical Changes', 'Layout and Structure'). Do not force topics that have no supporting changes.
3. Change ID Tracking: For each topic group, include the exact integer change IDs that belong to it in the `change_ids` array. ONLY use change IDs that exist in the supplied data.
4. Technical Asset Clarity: If a change involves stylesheets, icons, scripts, or URLs, clearly explain it as a technical asset or infrastructure update rather than user-facing prose.
5. User-Friendly Wording: Never output raw internal DOM paths (e.g., /html/body/div...) or technical xpath fragments.
6. Significance: Assign 'high', 'medium', or 'low' significance to each topic group based on impact to user experience or page functionality.
7. Conciseness: Keep the executive_summary to 2 sentences, key_takeaways to at most 3 bullet points, and each topic group description to 1 concise sentence.
8. Output Format: Output MUST be valid JSON matching the exact schema requested, with no markdown wrapping or preamble.
"""


def _truncate_text(text: Any, max_len: int = 80) -> str:
    """Clean and truncate values to prevent excessive prompt token size."""
    if text is None:
        return ""
    s = " ".join(str(text).split())
    if len(s) > max_len:
        return f"{s[:max_len]}..."
    return s


def build_compact_changes_payload(
    changes: list[dict[str, Any]],
    version1_label: str = "Older Version",
    version2_label: str = "Newer Version",
    max_items: int = 35,
) -> tuple[str, set[int]]:
    """Construct a concise, token-efficient summary of detected changes for LLM grounding.

    Returns the formatted text prompt and the set of valid integer change IDs.
    """
    valid_ids: set[int] = set()
    change_lines: list[str] = []

    # First pass: collect all valid IDs
    for c in changes:
        raw_id = c.get("id")
        if raw_id is not None:
            try:
                valid_ids.add(int(raw_id))
            except (ValueError, TypeError):
                pass

    # Build compact representation for each change
    for c in changes[:max_items]:
        raw_id = c.get("id")
        if raw_id is None:
            continue
        try:
            cid = int(raw_id)
        except (ValueError, TypeError):
            continue

        cat = (c.get("category") or "unknown").upper()
        elem = c.get("element") or c.get("type") or "Element"
        desc = _truncate_text(c.get("description"), max_len=60)
        old_val = _truncate_text(c.get("oldValue"), max_len=70)
        new_val = _truncate_text(c.get("newValue"), max_len=70)
        explanation = _truncate_text(c.get("explanation"), max_len=70)

        parts = [f"[ID {cid}] {cat} {elem}"]
        if old_val and new_val:
            parts.append(f'"{old_val}" -> "{new_val}"')
        elif new_val:
            parts.append(f'Added: "{new_val}"')
        elif old_val:
            parts.append(f'Removed: "{old_val}"')

        note = explanation or desc
        if note and note != old_val and note != new_val:
            parts.append(f"({note})")

        change_lines.append("- " + " ".join(parts))

    remaining = len(changes) - max_items
    if remaining > 0:
        change_lines.append(f"... and {remaining} additional minor changes.")

    header = (
        f"Webpage Comparison Overview:\n"
        f"Version 1 (Older): {version1_label}\n"
        f"Version 2 (Newer): {version2_label}\n"
        f"Total Detected Changes: {len(changes)}\n\n"
        f"Detected Change Items:\n"
    )

    full_payload = header + "\n".join(change_lines)
    return full_payload, valid_ids


async def generate_ai_summary(
    comparison_result: dict[str, Any],
    config: AIConfig | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any] | None:
    """Generate an AI-powered summary explaining detected changes via local Ollama LLM.

    Args:
        comparison_result: The adapted comparison dictionary containing 'changes', 'version1', etc.
        config: Optional AI configuration; defaults to loading from environment variables.
        client: Optional httpx.AsyncClient for connection pooling and mocking in tests.

    Returns:
        Structured dictionary matching AISummary, or None if disabled, unavailable, or invalid.
    """
    if config is None:
        config = AIConfig.from_env()

    if not config.enabled:
        logger.info("AI summary generation is disabled via configuration.")
        return None

    changes = comparison_result.get("changes", [])
    if not isinstance(changes, list) or len(changes) == 0:
        # Zero changes detected: return deterministic empty summary without LLM call
        return {
            "executive_summary": "No visual, structural, or text changes were detected between the compared webpage versions.",
            "key_takeaways": ["Both versions are identical in tracked content and structure."],
            "topic_groups": [],
        }

    v1_label = comparison_result.get("version1", {}).get("label") or "Older Version"
    v2_label = comparison_result.get("version2", {}).get("label") or "Newer Version"
    prompt_text, valid_ids = build_compact_changes_payload(changes, v1_label, v2_label)

    user_prompt = (
        f"Here are the detected changes between the two webpage versions:\n\n"
        f"{prompt_text}\n\n"
        f"Analyze these changes and provide your summary as JSON matching this exact structure:\n"
        f"{{\n"
        f'  "executive_summary": "A 2-3 sentence overview explaining what changed.",\n'
        f'  "key_takeaways": [\n'
        f'    "Clear bullet point 1",\n'
        f'    "Clear bullet point 2"\n'
        f"  ],\n"
        f'  "topic_groups": [\n'
        f"    {{\n"
        f'      "topic": "Topic Name (e.g. Navigation Changes, Content Updates, etc.)",\n'
        f'      "description": "Explanation of the changes in this group.",\n'
        f'      "change_ids": [1, 2],\n'
        f'      "significance": "high" | "medium" | "low"\n'
        f"    }}\n"
        f"  ]\n"
        f"}}"
    )

    chat_payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_gpu": 0,  # Enforce CPU inference based on hardware feasibility test
            "num_predict": 450,  # Bound generation length for full JSON schema on CPU
        },
    }

    url = f"{config.base_url.rstrip('/')}/api/chat"

    try:
        if client is not None:
            resp = await client.post(url, json=chat_payload, timeout=config.timeout_seconds)
            raw_content = _extract_response_content(resp)
        else:
            async with httpx.AsyncClient(timeout=config.timeout_seconds) as session:
                resp = await session.post(url, json=chat_payload)
                raw_content = _extract_response_content(resp)

        if not raw_content:
            logger.warning("Ollama returned an empty response body.")
            return None

        parsed_json = json.loads(raw_content)
        summary_model = AISummary.model_validate(parsed_json)

        # Enforce Grounding: reject or filter unknown change IDs
        filtered_topic_groups: list[TopicGroup] = []
        for group in summary_model.topic_groups:
            valid_group_ids = [cid for cid in group.change_ids if cid in valid_ids]
            if valid_group_ids:
                group.change_ids = valid_group_ids
                filtered_topic_groups.append(group)
            else:
                logger.info(
                    "Dropping topic group '%s' because none of its change IDs %s exist in detected changes.",
                    group.topic,
                    group.change_ids,
                )

        summary_model.topic_groups = filtered_topic_groups

        if not summary_model.executive_summary.strip():
            logger.warning("AI response contained empty executive_summary.")
            return None

        return summary_model.model_dump()

    except httpx.TimeoutException as err:
        logger.warning("Ollama AI summary request timed out after %.1fs: %s", config.timeout_seconds, err)
        return None
    except httpx.ConnectError as err:
        logger.warning("Unable to connect to Ollama service at %s: %s", config.base_url, err)
        return None
    except (json.JSONDecodeError, ValidationError) as err:
        logger.warning("Failed to parse or validate Ollama structured JSON response: %s", err)
        return None
    except Exception as err:
        logger.warning("Unexpected error during AI summary generation: %s", err, exc_info=True)
        return None


def _extract_response_content(resp: httpx.Response) -> str | None:
    """Extract message content from Ollama chat response."""
    if resp.status_code != 200:
        logger.warning("Ollama API returned HTTP %s: %s", resp.status_code, resp.text[:200])
        return None

    data = resp.json()
    message = data.get("message")
    if isinstance(message, dict):
        return message.get("content")
    return None
