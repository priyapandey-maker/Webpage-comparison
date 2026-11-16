"""Convert the existing engine output into the frontend presentation schema.

This module does not compare HTML. It only reshapes facts already produced by
the comparison engine. Labels are based on generic HTML structure, never on
admissions-specific wording.
"""

from __future__ import annotations

from typing import Any


TAG_LABELS = {
    "a": "Link",
    "article": "Section",
    "aside": "Aside",
    "button": "Button",
    "div": "Container",
    "em": "Text",
    "footer": "Footer",
    "form": "Form",
    "h1": "Heading",
    "h2": "Heading",
    "h3": "Heading",
    "h4": "Heading",
    "h5": "Heading",
    "h6": "Heading",
    "header": "Header",
    "img": "Image",
    "input": "Input",
    "li": "List item",
    "ol": "List",
    "main": "Main content",
    "nav": "Navigation",
    "p": "Paragraph",
    "section": "Section",
    "select": "Selection field",
    "span": "Text",
    "strong": "Text",
    "table": "Table",
    "textarea": "Text area",
    "title": "Page title",
    "ul": "List",
}

SECTION_TAGS = {"section", "article", "header", "footer", "nav", "aside", "main", "form"}
ACTION_TAGS = {"button", "input", "select", "textarea"}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def _label_for(tag: str) -> str:
    clean_tag = (tag or "unknown").lower()
    return TAG_LABELS.get(clean_tag, f"{clean_tag} element" if clean_tag != "unknown" else "Element")


def _type_for(tag: str) -> str:
    clean_tag = (tag or "unknown").lower()
    if clean_tag in SECTION_TAGS:
        return "section"
    if clean_tag in ACTION_TAGS:
        return "action"
    if clean_tag == "a":
        return "link"
    if clean_tag in HEADING_TAGS:
        return "heading"
    if clean_tag == "p":
        return "paragraph"
    if clean_tag in {"ul", "ol"}:
        return "list"
    if clean_tag == "li":
        return "list_item"
    if clean_tag == "button":
        return "button"
    if clean_tag == "img":
        return "image"
    if clean_tag == "title":
        return "page_title"
    if clean_tag in {"img", "video", "audio", "picture"}:
        return "media"
    return "content"


def _format_attributes(attributes: dict[str, Any] | None) -> str:
    if not attributes:
        return ""
    return ", ".join(
        f"{key}: {', '.join(map(str, value)) if isinstance(value, list) else value}"
        for key, value in sorted(attributes.items())
    )


def _format_modified_value(text: str | None, attributes: dict[str, Any] | None) -> str | None:
    normalized_text = (text or "").strip()
    normalized_attributes = _format_attributes(attributes)
    if normalized_text and normalized_attributes:
        return f'{normalized_text} ({normalized_attributes})'
    return normalized_text or normalized_attributes or None


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _changed_attribute_names(
    old_attributes: dict[str, Any] | None,
    new_attributes: dict[str, Any] | None,
) -> set[str]:
    old_attributes = old_attributes or {}
    new_attributes = new_attributes or {}
    return {
        key
        for key in set(old_attributes) | set(new_attributes)
        if old_attributes.get(key) != new_attributes.get(key)
    }


def _flatten_tree(node: dict[str, Any], path: str = "/html", result: dict | None = None) -> dict:
    """Mirror change_detector.flatten_tree paths without altering the engine."""
    if result is None:
        result = {}
    result[path] = node
    tag_counts: dict[str, int] = {}
    for child in node.get("children", []):
        tag = child.get("tag", "unknown")
        index = tag_counts.get(tag, 0)
        tag_counts[tag] = index + 1
        _flatten_tree(child, f"{path}/{tag}[{index}]", result)
    return result


def _descendant_text(node: dict[str, Any]) -> list[str]:
    values: list[str] = []
    text = " ".join(str(node.get("text", "")).split())
    if text:
        values.append(text)
    for child in node.get("children", []):
        values.extend(_descendant_text(child))
    return values


def _deduplicate(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _complete_subtree_roots(
    raw_items: list[dict[str, Any]],
    tree_by_path: dict[str, dict[str, Any]],
) -> set[str]:
    """Find top-level roots whose complete subtree has one change status."""
    changed_paths = {item.get("path") for item in raw_items if item.get("path")}
    candidate_roots = set()

    for path in changed_paths:
        descendant_paths = [
            candidate_path
            for candidate_path in tree_by_path
            if candidate_path.startswith(f"{path}/")
        ]
        if descendant_paths and all(candidate in changed_paths for candidate in descendant_paths):
            candidate_roots.add(path)

    return {
        path
        for path in candidate_roots
        if not any(path.startswith(f"{other}/") for other in candidate_roots if other != path)
    }


def _has_grouped_ancestor(path: str, grouping_roots: set[str]) -> bool:
    return any(path.startswith(f"{root}/") for root in grouping_roots)


def _structural_value(item: dict[str, Any], node: dict[str, Any], path: str) -> str:
    text = _normalized_text(item.get("text")) or _normalized_text(node.get("text"))
    if text:
        return text

    attributes = _format_attributes(node.get("attributes"))
    return attributes or path


def _append_structural_changes(
    changes: list[dict[str, Any]],
    raw_items: list[dict[str, Any]],
    tree_by_path: dict[str, dict[str, Any]],
    category: str,
    next_id: int,
) -> int:
    grouping_roots = _complete_subtree_roots(raw_items, tree_by_path)

    for item in raw_items:
        path = item.get("path", "")
        if _has_grouped_ancestor(path, grouping_roots):
            continue

        tag = (item.get("tag") or "unknown").lower()
        node = tree_by_path.get(path, {})
        label = _label_for(tag)
        presentation_type = _type_for(tag)
        value = _structural_value(item, node, path)

        if path in grouping_roots:
            texts = _deduplicate(_descendant_text(node))
            value = "; ".join(texts) or value
            if tag in {"div", "section", "article"}:
                label = "Section"
                presentation_type = "section"

        changes.append({
            "id": next_id,
            "category": category,
            "type": presentation_type,
            "element": label,
            "oldValue": value if category == "removed" else None,
            "newValue": value if category == "added" else None,
            "description": f"{label} was {category}.",
            "sourcePath": path,
        })
        next_id += 1

    return next_id


def _modified_presentation(item: dict[str, Any]) -> tuple[str, str, Any, Any, str]:
    tag = (item.get("tag") or "unknown").lower()
    label = _label_for(tag)
    presentation_type = _type_for(tag)
    old_text = _normalized_text(item.get("old_text"))
    new_text = _normalized_text(item.get("new_text"))
    old_attributes = item.get("old_attributes") or {}
    new_attributes = item.get("new_attributes") or {}
    changed_attributes = _changed_attribute_names(old_attributes, new_attributes)
    text_changed = old_text != new_text

    if not text_changed and changed_attributes == {"href"} and tag == "a":
        return (
            "Link destination",
            "link_destination",
            old_attributes.get("href"),
            new_attributes.get("href"),
            "Link destination was updated.",
        )

    if not text_changed and changed_attributes == {"src"} and tag == "img":
        return (
            "Image source",
            "image_source",
            old_attributes.get("src"),
            new_attributes.get("src"),
            "Image source was updated.",
        )

    if text_changed and not changed_attributes:
        description = f"{label} was updated." if label == "Text" else f"{label} text was updated."
        return label, presentation_type, old_text or None, new_text or None, description

    if changed_attributes and not text_changed:
        return (
            label,
            presentation_type,
            _format_attributes(old_attributes) or None,
            _format_attributes(new_attributes) or None,
            f"{label} attributes were updated.",
        )

    return (
        label,
        presentation_type,
        _format_modified_value(old_text, old_attributes),
        _format_modified_value(new_text, new_attributes),
        f"{label} text and attributes were updated."
        if text_changed and changed_attributes
        else f"{label} was updated.",
    )


def adapt_engine_result(
    raw_changes: dict[str, Any],
    tree_v1: dict[str, Any],
    tree_v2: dict[str, Any],
    version1_name: str,
    version2_name: str,
) -> dict[str, Any]:
    """Return the exact shape consumed by ResultsPage."""
    tree_v1_by_path = _flatten_tree(tree_v1) if tree_v1 else {}
    tree_v2_by_path = _flatten_tree(tree_v2) if tree_v2 else {}
    raw_added = raw_changes.get("added", [])
    raw_removed = raw_changes.get("removed", [])

    changes: list[dict[str, Any]] = []
    next_id = _append_structural_changes(changes, raw_added, tree_v2_by_path, "added", 1)
    next_id = _append_structural_changes(
        changes,
        raw_removed,
        tree_v1_by_path,
        "removed",
        next_id,
    )

    for item in raw_changes.get("modified", []):
        label, presentation_type, old_value, new_value, description = _modified_presentation(item)
        changes.append({
            "id": next_id,
            "category": "modified",
            "type": presentation_type,
            "element": label,
            "oldValue": old_value,
            "newValue": new_value,
            "description": description,
            "sourcePath": item.get("path_v1", ""),
            "targetPath": item.get("path_v2", ""),
            "similarity": item.get("similarity"),
        })
        next_id += 1

    return {
        "version1": {"label": version1_name},
        "version2": {"label": version2_name},
        "changes": changes,
        "engineSummary": raw_changes.get("summary", {}),
        "presentationSummary": {
            "total": len(changes),
            "added": sum(item["category"] == "added" for item in changes),
            "removed": sum(item["category"] == "removed" for item in changes),
            "modified": sum(item["category"] == "modified" for item in changes),
        },
    }
