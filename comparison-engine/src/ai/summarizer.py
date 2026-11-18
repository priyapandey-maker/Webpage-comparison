"""AI Explanation Layer for Webpage Comparison using local Ollama LLM.

Constructs grounded change payloads and queries a locally hosted LLM (qwen2.5:1.5b)
using CPU inference to produce structured executive summaries and topic groupings.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from .schemas import AIConfig, AISummary, TopicGroup

logger = logging.getLogger(__name__)

# Module-level synchronization for local Ollama single-slot inference
_OLLAMA_LOCK: asyncio.Lock | None = None
_OLLAMA_LOCK_LOOP: asyncio.AbstractEventLoop | None = None
_OLLAMA_WAITERS_COUNT: int = 0


def _get_ollama_lock() -> asyncio.Lock:
    """Return the singleton asyncio.Lock for the current running event loop."""
    global _OLLAMA_LOCK, _OLLAMA_LOCK_LOOP
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _OLLAMA_LOCK is None or _OLLAMA_LOCK_LOOP != current_loop:
        _OLLAMA_LOCK = asyncio.Lock()
        _OLLAMA_LOCK_LOOP = current_loop
    return _OLLAMA_LOCK


def _reset_ollama_lock() -> None:
    """Reset the Ollama lock and waiter count (used for test isolation)."""
    global _OLLAMA_LOCK, _OLLAMA_LOCK_LOOP, _OLLAMA_WAITERS_COUNT
    _OLLAMA_LOCK = None
    _OLLAMA_LOCK_LOOP = None
    _OLLAMA_WAITERS_COUNT = 0

SYSTEM_PROMPT = """You are an objective webpage comparison analyst explaining changes between two webpage versions.
Your goal is to explain what changed in clear, natural language written for a general audience, not a technical report.

Scope and Analysis Boundaries:
- You receive at most 35 individually described changes from the detected change set.
- When more than 35 changes exist, additional detected changes are not individually included in this prompt and will be categorized through deterministic classification post-processing.
- Do NOT claim or imply that you have individually analysed every single detected change when only a subset was supplied.
- Base your executive summary and key takeaways strictly on the changes provided without extrapolating beyond the supplied data.

Required Structure & Brevity Guidelines:
1. Executive Summary:
   - Write exactly 1 to 2 concise sentences explaining the primary changes in plain English.
2. Key Takeaways:
   - Provide exactly 2 concise bullet points highlighting the most notable updates.
   - Describe only concrete, observable additions, removals, or revisions to webpage elements (links, text, headings, buttons, assets).
   - Do NOT make speculative assumptions about layout shifts, hidden sidebars, user intentions, or unstated features.
   - Never output internal JSON schema field names (such as 'topic_groups', 'change_ids', 'key_takeaways', or 'executive_summary') as takeaways or text content.
3. Topic Groups:
   - Organize changes into 2 to 3 focused topic groups based on their functional role (e.g., 'Navigation Changes', 'Content Updates', 'Technical Asset Updates'). Do not create empty groups.
   - Each group description must be 1 concise sentence describing the specific changes in that group.
4. Change ID Tracking:
   - Assign each supplied change ID to its ONE primary topic group in `change_ids`. Every change ID from the input must be included in exactly one group with NO duplicate IDs across groups.
   - Assign grounded significance ('high', 'medium', or 'low') based on user impact: major navigation reorganizations or primary content additions/removals are 'high' or 'medium'; technical asset updates, path normalizations, and minor formatting are 'low'.
5. Technical Asset Clarity:
   - Treat stylesheets, icons/favicons, and script references strictly as technical asset updates. NEVER classify stylesheets or favicon icons as general content updates.
6. Realistic Security Claims:
   - If an external link was updated from HTTP to HTTPS, describe it factually as an HTTPS link update. Do NOT make exaggerated claims such as declaring the website more secure.
7. Output Format:
   - Output MUST be valid JSON matching the exact schema requested, with no markdown code fences, preambles, or postscripts.
"""


TECHNICAL_DOM_ELEMENTS = {
    "link element",
    "link_element",
    "script element",
    "script_element",
    "style element",
    "style_element",
}


def is_technical_asset_change(change: dict[str, Any]) -> bool:
    """Determine whether a change record represents a technical asset (stylesheet, icon, script).

    Restricts classification to actual technical DOM elements (<link>, <script>, <style>)
    and explicit adapter metadata. Ordinary user-facing content (paragraphs, headings,
    anchors, user images) that mentions file extensions (.css, .js, .svg, .png) is NOT
    classified as a technical asset.
    """
    elem = (change.get("element") or change.get("type") or "").strip().lower()
    exp = (change.get("explanation") or "").lower()
    old_val = str(change.get("oldValue") or "")
    new_val = str(change.get("newValue") or "")

    # 1. Structured metadata or adapter explanation
    if "technical asset" in exp:
        return True

    # 2. Strict DOM element classification for technical tags in <head> or scripts
    if elem in TECHNICAL_DOM_ELEMENTS:
        combined_val = (old_val + " " + new_val).lower()
        if any(rel in combined_val for rel in ("stylesheet", "icon", "preload", "dns-prefetch")):
            return True
        if any(ext in combined_val for ext in (".css", ".ico", ".js")):
            return True
        if "script" in elem or "style" in elem:
            return True
        return True

    # 3. Explicit link element attributes indicating stylesheets or shortcut icons
    combined_val_lower = (old_val + " " + new_val).lower()
    if (
        "rel: stylesheet" in combined_val_lower
        or "rel: shortcut" in combined_val_lower
        or "rel: icon" in combined_val_lower
    ):
        return True

    return False


def is_path_normalization_change(change: dict[str, Any]) -> bool:
    """Determine whether a change is a link path normalization (e.g. 'about/' -> '/about')."""
    elem = (change.get("element") or change.get("type") or "").lower()
    exp = (change.get("explanation") or "").lower()
    old_val = str(change.get("oldValue") or "").strip()
    new_val = str(change.get("newValue") or "").strip()

    if "path normalization" in exp:
        return True
    if "link destination" in elem:
        clean_old = old_val.strip("/")
        clean_new = new_val.strip("/")
        if clean_old and clean_old == clean_new and old_val != new_val:
            return True
    return False


def is_protocol_upgrade_change(change: dict[str, Any]) -> bool:
    """Determine whether a change is strictly an HTTP -> HTTPS protocol upgrade for the same destination.

    Requires that:
    1. The old URL uses http:// and the new URL uses https://.
    2. The hostname is identical (case-insensitive).
    3. The path, query parameters, and fragments are equivalent (allowing trailing slash normalization).

    If the hostname, path, or query string differs, it represents a destination change
    rather than an in-place protocol upgrade.
    """
    old_val = str(change.get("oldValue") or "").strip()
    new_val = str(change.get("newValue") or "").strip()

    if not (old_val.startswith("http://") and new_val.startswith("https://")):
        return False

    try:
        u_old = urlsplit(old_val)
        u_new = urlsplit(new_val)
    except Exception:
        return False

    # Verify schemes
    if u_old.scheme.lower() != "http" or u_new.scheme.lower() != "https":
        return False

    # Hostname comparison (case-insensitive)
    host_old = (u_old.hostname or "").lower()
    host_new = (u_new.hostname or "").lower()
    if not host_old or not host_new or host_old != host_new:
        return False

    # Ports check (default port 80 for http, 443 for https)
    port_old = u_old.port
    port_new = u_new.port
    norm_port_old = None if port_old in (None, 80) else port_old
    norm_port_new = None if port_new in (None, 443) else port_new
    if norm_port_old != norm_port_new:
        return False

    # Path comparison (allowing trailing slash normalization)
    path_old = u_old.path.rstrip("/")
    path_new = u_new.path.rstrip("/")
    if path_old != path_new:
        return False

    # Query and fragment must match exactly
    if u_old.query != u_new.query:
        return False
    if u_old.fragment != u_new.fragment:
        return False

    return True


def is_navigation_change(change: dict[str, Any]) -> bool:
    """Determine whether a change represents navigation, menus, buttons, or hyperlinks."""
    if is_technical_asset_change(change):
        return False
    elem = (change.get("element") or change.get("type") or "").lower()
    t = (change.get("type") or "").lower()
    exp = (change.get("explanation") or "").lower()
    path1 = str(change.get("sourcePath") or "").lower()
    path2 = str(change.get("targetPath") or "").lower()
    paths = path1 + " " + path2

    if (
        "link" in elem
        or "nav" in elem
        or "button" in elem
        or "menu" in elem
        or t in ("link", "button", "nav")
        or "navigation" in exp
        or "link label" in exp
        or "link destination" in exp
        or "menu" in exp
        or "/nav" in paths
        or "/menu" in paths
        or is_path_normalization_change(change)
        or is_protocol_upgrade_change(change)
    ):
        return True
    return False


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
    """Construct a concise, token-efficient, role-annotated summary of detected changes.

    Returns the formatted text prompt and the set of valid integer change IDs.
    """
    valid_ids: set[int] = set()
    change_lines: list[str] = []

    # First pass: collect all valid integer IDs
    for c in changes:
        raw_id = c.get("id")
        if raw_id is not None:
            try:
                valid_ids.add(int(raw_id))
            except (ValueError, TypeError):
                pass

    # Build structured representation for each change
    for c in changes[:max_items]:
        raw_id = c.get("id")
        if raw_id is None:
            continue
        try:
            cid = int(raw_id)
        except (ValueError, TypeError):
            continue

        cat = (c.get("category") or "").lower()
        elem = (c.get("element") or c.get("type") or "element").strip()
        old_val = c.get("oldValue")
        new_val = c.get("newValue")
        explanation = c.get("explanation")

        if is_technical_asset_change(c):
            classification = "Technical Asset"
            if "stylesheet" in (explanation or "").lower() or ".css" in str(new_val).lower():
                detail = f"Stylesheet reference updated to versioned asset '{_truncate_text(new_val, 55)}'"
            elif "icon" in (explanation or "").lower() or ".ico" in str(new_val).lower():
                detail = f"Shortcut/favicon icon updated to versioned asset '{_truncate_text(new_val, 55)}'"
            else:
                detail = _truncate_text(explanation, 70) or f"Technical asset updated: '{_truncate_text(new_val, 55)}'"
        elif is_path_normalization_change(c):
            classification = "Navigation (Path Normalization)"
            detail = f"Link path normalized from '{_truncate_text(old_val, 50)}' to '{_truncate_text(new_val, 50)}'"
        elif is_protocol_upgrade_change(c):
            classification = "Navigation (Protocol Update)"
            detail = f"External link destination upgraded from HTTP to HTTPS: '{_truncate_text(old_val, 50)}' -> '{_truncate_text(new_val, 50)}'"
        elif is_navigation_change(c):
            classification = "Navigation"
            if explanation:
                detail = _truncate_text(explanation, 75)
            elif cat == "added":
                detail = f"Added navigation link: '{_truncate_text(new_val, 55)}'"
            elif cat == "removed":
                detail = f"Removed navigation link: '{_truncate_text(old_val, 55)}'"
            else:
                detail = f"Link updated: '{_truncate_text(old_val, 45)}' -> '{_truncate_text(new_val, 45)}'"
        elif cat == "added":
            classification = "New Content"
            detail = _truncate_text(explanation, 75) or f"Added {elem}: '{_truncate_text(new_val, 60)}'"
        elif cat == "removed":
            classification = "Removed Content"
            detail = _truncate_text(explanation, 75) or f"Removed {elem}: '{_truncate_text(old_val, 60)}'"
        else:
            classification = "Content Update"
            detail = _truncate_text(explanation, 75) or f"{elem} updated: '{_truncate_text(old_val, 45)}' -> '{_truncate_text(new_val, 45)}'"

        change_lines.append(f"- [Change #{cid}] ({classification}) {detail}")

    remaining = len(changes) - max_items
    if remaining > 0:
        change_lines.append(
            f"... Note: {remaining} additional detected changes are not individually included in this prompt."
        )

    header = (
        f"Webpage Comparison Overview:\n"
        f"Version 1 (Older): {version1_label}\n"
        f"Version 2 (Newer): {version2_label}\n"
        f"Total Detected Changes: {len(changes)}\n\n"
        f"Detected Changes:\n"
    )

    full_payload = header + "\n".join(change_lines)
    return full_payload, valid_ids


async def generate_ai_summary(
    comparison_result: dict[str, Any],
    config: AIConfig | None = None,
    client: httpx.AsyncClient | None = None,
    return_status: bool = False,
) -> dict[str, Any] | None | tuple[dict[str, Any] | None, str]:
    """Generate an AI-powered summary explaining detected changes via local Ollama LLM.

    Args:
        comparison_result: The adapted comparison dictionary containing 'changes', 'version1', etc.
        config: Optional AI configuration; defaults to loading from environment variables.
        client: Optional httpx.AsyncClient for connection pooling and mocking in tests.
        return_status: When True, returns a tuple of (summary_dict | None, status_str).
                       When False (default), returns summary_dict | None for backward compatibility.

    Returns:
        Structured dictionary matching AISummary, or None if disabled, unavailable, or invalid.
        If return_status=True, returns (data, status) where status is one of:
        'generated', 'busy', 'timeout', 'unavailable', 'invalid_response'.
    """
    def _res(data: dict[str, Any] | None, status: str) -> dict[str, Any] | None | tuple[dict[str, Any] | None, str]:
        return (data, status) if return_status else data

    if config is None:
        config = AIConfig.from_env()

    if not config.enabled:
        logger.info("AI summary generation is disabled via configuration.")
        return _res(None, "unavailable")

    changes = comparison_result.get("changes", [])
    if not isinstance(changes, list) or len(changes) == 0:
        # Zero changes detected: return deterministic empty summary without LLM call
        return _res(
            {
                "executive_summary": "No visual, structural, or text changes were detected between the compared webpage versions.",
                "key_takeaways": ["Both versions are identical in tracked content and structure."],
                "topic_groups": [],
            },
            "generated",
        )

    v1_label = comparison_result.get("version1", {}).get("label") or "Older Version"
    v2_label = comparison_result.get("version2", {}).get("label") or "Newer Version"
    prompt_text, valid_ids = build_compact_changes_payload(changes, v1_label, v2_label)

    total_count = len(changes)
    scope_note = (
        f"Scope Note: This prompt provides {min(total_count, 35)} individually described changes out of {total_count} total detected changes. "
        f"Do not claim to have individually analysed every change beyond those supplied here.\n\n"
        if total_count > 35
        else ""
    )

    user_prompt = (
        f"Here are the detected changes between the two webpage versions:\n\n"
        f"{prompt_text}\n\n"
        f"{scope_note}"
        f"Analyze these changes and provide your explanation as JSON matching this exact structure:\n"
        f"{{\n"
        f'  "executive_summary": "One concise 1-2 sentence overview of the primary changes.",\n'
        f'  "key_takeaways": [\n'
        f'    "Concise key takeaway bullet 1",\n'
        f'    "Concise key takeaway bullet 2"\n'
        f"  ],\n"
        f'  "topic_groups": [\n'
        f"    {{\n"
        f'      "topic": "Topic Name (e.g. Navigation Changes, Content Updates, or Technical Asset Updates)",\n'
        f'      "description": "Concise 1-sentence description of updates in this group.",\n'
        f'      "change_ids": [1, 2],\n'
        f'      "significance": "high"\n'
        f"    }},\n"
        f"    {{\n"
        f'      "topic": "Second Topic Name",\n'
        f'      "description": "Concise 1-sentence description.",\n'
        f'      "change_ids": [3],\n'
        f'      "significance": "low"\n'
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
            "num_predict": config.num_predict,  # Bound generation length for full JSON schema on CPU
        },
    }

    url = f"{config.base_url.rstrip('/')}/api/chat"
    raw_content: str | None = None
    done_reason: str | None = None

    # Concurrency serialization: Acquire single-slot lock before starting inference timer
    lock = _get_ollama_lock()
    global _OLLAMA_WAITERS_COUNT

    if lock.locked() and _OLLAMA_WAITERS_COUNT >= config.max_waiters:
        logger.warning(
            "Ollama inference queue is full (%d already waiting); returning busy.",
            _OLLAMA_WAITERS_COUNT,
        )
        return _res(None, "busy")

    acquired = False
    _OLLAMA_WAITERS_COUNT += 1
    try:
        try:
            await asyncio.wait_for(lock.acquire(), timeout=config.max_queue_wait)
            acquired = True
        except TimeoutError:
            logger.warning(
                "Ollama inference engine is busy (queue wait timeout of %.1fs exceeded).",
                config.max_queue_wait,
            )
            return _res(None, "busy")
        except asyncio.CancelledError:
            logger.info("Waiting for Ollama inference lock was cancelled.")
            raise
    finally:
        _OLLAMA_WAITERS_COUNT = max(0, _OLLAMA_WAITERS_COUNT - 1)

    try:
        try:
            if client is not None:
                resp = await client.post(url, json=chat_payload, timeout=config.timeout_seconds)
                raw_content, done_reason = _extract_ollama_response(resp)
            else:
                async with httpx.AsyncClient(timeout=config.timeout_seconds) as session:
                    resp = await session.post(url, json=chat_payload)
                    raw_content, done_reason = _extract_ollama_response(resp)
        except httpx.TimeoutException as err:
            logger.warning("Ollama AI summary request timed out after %.1fs: %s", config.timeout_seconds, err)
            return _res(None, "timeout")
        except httpx.ConnectError as err:
            logger.warning("Unable to connect to Ollama service at %s: %s", config.base_url, err)
            return _res(None, "unavailable")
        except asyncio.CancelledError:
            logger.info("Ollama AI inference task was cancelled.")
            raise
        except Exception as err:
            logger.warning("Unexpected network error communicating with Ollama: %s", err, exc_info=True)
            return _res(None, "unavailable")

        if not raw_content:
            logger.warning(
                "Ollama returned an empty response body (finish_reason=%s).",
                done_reason or "unknown",
            )
            return _res(None, "invalid_response")

        if done_reason == "length":
            logger.warning(
                "Ollama generation reached the token limit (num_predict=%d, finish_reason='length', response_length=%d, preview=%.150r).",
                config.num_predict,
                len(raw_content),
                raw_content[:150],
            )

        try:
            parsed_json = json.loads(raw_content)
            summary_model = AISummary.model_validate(parsed_json)
        except (json.JSONDecodeError, ValidationError) as err:
            resp_len = len(raw_content) if raw_content else 0
            finish = done_reason or "unknown"
            preview = raw_content[:150] if raw_content else ""
            logger.warning(
                "Failed to parse or validate Ollama structured JSON response: %s "
                "(response_length=%d, finish_reason=%s, preview=%.150r)",
                err,
                resp_len,
                finish,
                preview,
            )
            return _res(None, "invalid_response")

        changes_by_id: dict[int, dict[str, Any]] = {
            int(c["id"]): c for c in changes if c.get("id") is not None
        }

        # Enforce deterministic role-priority topic grouping:
        # Technical assets must belong to an asset group, navigation to navigation, content to content.
        # AI group order cannot override deterministic role boundaries.
        ROLE_ASSET = "asset"
        ROLE_NAV = "navigation"
        ROLE_CONTENT = "content"

        def get_change_role(change: dict[str, Any]) -> str:
            if is_technical_asset_change(change):
                return ROLE_ASSET
            if is_navigation_change(change):
                return ROLE_NAV
            return ROLE_CONTENT

        def get_group_role(topic: str) -> str:
            t = topic.strip().lower()
            if any(k in t for k in ("asset", "technical", "infrastructure", "stylesheet", "favicon")):
                return ROLE_ASSET
            if any(k in t for k in ("nav", "menu", "link", "destination")):
                return ROLE_NAV
            return ROLE_CONTENT

        # Prepare AI candidate groups
        ai_groups: list[TopicGroup] = []
        for g in summary_model.topic_groups:
            ai_groups.append(
                TopicGroup(
                    topic=g.topic.strip() or "Content Updates",
                    description=g.description.strip(),
                    change_ids=[],
                    significance=g.significance,
                )
            )

        # Fallback groups created when no matching AI group exists, or for distinct roles in large comparisons
        fallback_groups: dict[str, TopicGroup] = {}

        def get_or_create_fallback(role: str, category: str | None = None) -> TopicGroup:
            is_large = len(changes) > 35
            key = f"{role}_{category}" if (role == ROLE_CONTENT and category and is_large) else role
            if key in fallback_groups:
                return fallback_groups[key]

            if role == ROLE_ASSET:
                fg = TopicGroup(
                    topic="Technical Asset Updates",
                    description="Updates to stylesheet, favicon, and technical asset references.",
                    change_ids=[],
                    significance="low",
                )
            elif role == ROLE_NAV:
                fg = TopicGroup(
                    topic="Navigation Changes",
                    description="Updates to page navigation links, destinations, and paths.",
                    change_ids=[],
                    significance="medium",
                )
            elif is_large and category == "added":
                fg = TopicGroup(
                    topic="New Content & Sections",
                    description="New structural sections, headings, lists, and content added to the page.",
                    change_ids=[],
                    significance="medium",
                )
            elif is_large and category == "removed":
                fg = TopicGroup(
                    topic="Removed Webpage Content",
                    description="Sections, elements, and content pruned from the newer version.",
                    change_ids=[],
                    significance="medium",
                )
            else:
                fg = TopicGroup(
                    topic="Content Updates",
                    description="Additions, removals, and revisions to page content items.",
                    change_ids=[],
                    significance="medium",
                )
            fallback_groups[key] = fg
            return fg

        # Map each valid CID to the original AI group index/indices that claimed it
        ai_claims_by_cid: dict[int, list[int]] = {cid: [] for cid in valid_ids}
        for g_idx, orig_g in enumerate(summary_model.topic_groups):
            for raw_cid in orig_g.change_ids:
                if raw_cid in ai_claims_by_cid:
                    ai_claims_by_cid[raw_cid].append(g_idx)

        is_large_comparison = len(changes) > 35

        # Assign each change ID to exactly one group with role priority
        for cid in sorted(valid_ids):
            c_obj = changes_by_id[cid]
            c_role = get_change_role(c_obj)
            c_cat = (c_obj.get("category") or "").lower()

            # Find matching AI groups for this role
            matching_g_indices = [
                idx for idx, g in enumerate(ai_groups)
                if get_group_role(g.topic) == c_role
            ]

            assigned_group: TopicGroup | None = None

            if matching_g_indices:
                # 1. Did the AI claim this CID in one of the matching groups?
                claimed_matching = [
                    idx for idx in ai_claims_by_cid[cid]
                    if idx in matching_g_indices
                ]
                if claimed_matching:
                    assigned_group = ai_groups[claimed_matching[0]]
                elif not is_large_comparison:
                    # Small comparisons: allocate unassigned CID to the matching AI group
                    assigned_group = ai_groups[matching_g_indices[0]]
                else:
                    # Large comparisons: differentiate content additions, removals, and updates
                    if c_role == ROLE_CONTENT and c_cat in ("added", "removed"):
                        assigned_group = get_or_create_fallback(c_role, c_cat)
                    else:
                        assigned_group = ai_groups[matching_g_indices[0]]
            else:
                # 2. No AI group exists for this role -> assign to fallback group
                assigned_group = get_or_create_fallback(c_role, c_cat)

            assigned_group.change_ids.append(cid)

        # Finalize groups: keep populated AI groups and populated fallback groups (omit empty groups)
        final_groups: list[TopicGroup] = []
        for g in ai_groups:
            if g.change_ids:
                g.change_ids.sort()
                if not g.description:
                    role = get_group_role(g.topic)
                    if role == ROLE_ASSET:
                        g.description = "Updates to technical asset and resource references."
                    elif role == ROLE_NAV:
                        g.description = "Updates to navigation links and destinations."
                    else:
                        g.description = "Additions, removals, and revisions to page content."
                final_groups.append(g)

        for fg in fallback_groups.values():
            if fg.change_ids:
                fg.change_ids.sort()
                final_groups.append(fg)

        summary_model.topic_groups = [g for g in final_groups if len(g.change_ids) > 0]

        if not summary_model.executive_summary.strip():
            logger.warning("AI response contained empty executive_summary.")
            return _res(None, "invalid_response")

        return _res(summary_model.model_dump(), "generated")

    finally:
        if acquired:
            lock.release()


def _extract_ollama_response(resp: httpx.Response) -> tuple[str | None, str | None]:
    """Extract message content and finish reason (done_reason) from Ollama chat response.

    Returns:
        (content, done_reason) where done_reason is e.g. 'stop', 'length', or None.
    """
    if resp.status_code != 200:
        logger.warning("Ollama API returned HTTP %s: %s", resp.status_code, resp.text[:200])
        return None, None

    try:
        data = resp.json()
    except Exception as err:
        logger.warning("Failed to parse Ollama HTTP response as JSON: %s", err)
        return None, None

    message = data.get("message")
    content: str | None = None
    if isinstance(message, dict):
        content = message.get("content")

    done_reason = data.get("done_reason")
    return content, str(done_reason) if done_reason else None


def _extract_response_content(resp: httpx.Response) -> str | None:
    """Extract message content from Ollama chat response (backward-compatible helper)."""
    content, _ = _extract_ollama_response(resp)
    return content
