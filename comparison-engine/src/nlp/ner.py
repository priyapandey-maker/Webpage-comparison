"""Named Entity Recognition (NER) Layer.

Identifies named entities (people, organizations, locations, dates, monetary values, etc.)
using spaCy, and compares entities between old and new text versions to detect added,
removed, and modified entity references.
"""

from __future__ import annotations

import re
from typing import Any

from .preprocessing import clean_html_text, is_empty_or_whitespace

# Common date and number patterns for regex fallback when model is unavailable
_MONTH_PATTERN = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b",
    re.IGNORECASE,
)
_YEAR_PATTERN = re.compile(r"\b(?:19|20)\d{2}\b")
_MONEY_PATTERN = re.compile(r"[\$€£¥]\s*\d+(?:,\d{3})*(?:\.\d+)?|\b\d+(?:,\d{3})*(?:\.\d+)?\s*(?:dollars|USD|EUR|GBP|INR)\b", re.IGNORECASE)
_PERCENT_PATTERN = re.compile(r"\b\d+(?:\.\d+)?%\b|\b\d+(?:\.\d+)?\s*percent\b", re.IGNORECASE)


def extract_entities_fallback(text: str) -> list[dict[str, str]]:
    """Heuristic fallback entity extraction for dates, money, and percentages when spaCy is unavailable."""
    if is_empty_or_whitespace(text):
        return []

    entities: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for match in _MONTH_PATTERN.finditer(text):
        val = match.group().strip()
        key = (val.lower(), "DATE")
        if key not in seen:
            seen.add(key)
            entities.append({"text": val, "label": "DATE"})

    for match in _YEAR_PATTERN.finditer(text):
        val = match.group().strip()
        key = (val.lower(), "DATE")
        if key not in seen:
            seen.add(key)
            entities.append({"text": val, "label": "DATE"})

    for match in _MONEY_PATTERN.finditer(text):
        val = match.group().strip()
        key = (val.lower(), "MONEY")
        if key not in seen:
            seen.add(key)
            entities.append({"text": val, "label": "MONEY"})

    for match in _PERCENT_PATTERN.finditer(text):
        val = match.group().strip()
        key = (val.lower(), "PERCENT")
        if key not in seen:
            seen.add(key)
            entities.append({"text": val, "label": "PERCENT"})

    return entities


def has_ner_component(nlp_model: Any) -> bool:
    """Check if the NLP model has a trained NER pipeline component."""
    if nlp_model is None:
        return False
    if hasattr(nlp_model, "has_pipe"):
        return nlp_model.has_pipe("ner")
    if hasattr(nlp_model, "pipe_names"):
        return "ner" in nlp_model.pipe_names
    return False


def extract_named_entities(
    text: str | None,
    nlp_model: Any = None,
) -> list[dict[str, str]]:
    """Extract named entities from text using spaCy with fallback heuristics.

    Returns a list of dicts: [{"text": str, "label": str}].
    If the supplied model has a trained NER component, its predictions are returned directly.
    If no trained NER component is available (e.g. blank sentencizer pipeline or None),
    heuristic regex fallback is used.
    """
    clean = clean_html_text(text)
    if not clean:
        return []

    # If the model has a trained NER component, run it
    if has_ner_component(nlp_model):
        try:
            doc = nlp_model(clean)
            entities: list[dict[str, str]] = []
            seen: set[tuple[str, str]] = set()

            for ent in doc.ents:
                clean_ent = ent.text.strip()
                if not clean_ent:
                    continue
                key = (clean_ent.lower(), ent.label_)
                if key not in seen:
                    seen.add(key)
                    entities.append({"text": clean_ent, "label": ent.label_})

            # Preserve valid model results even when no entities were detected in this snippet
            return entities
        except Exception:
            pass  # Fall back to heuristic pattern matching on unexpected model execution failure

    # If nlp_model is None or lacks a trained NER component (e.g., blank pipeline), use regex fallback
    return extract_entities_fallback(clean)


def compare_named_entities(
    old_text: str | None,
    new_text: str | None,
    nlp_model: Any = None,
) -> dict[str, Any]:
    """Compare named entities between old and new text versions.

    Returns:
    - added: Entities present in new_text but absent in old_text.
    - removed: Entities present in old_text but absent in new_text.
    - shared: Entities present in both versions.
    - by_label: Breakdown of additions and removals categorized by entity type (DATE, ORG, etc.).
    """
    old_entities = extract_named_entities(old_text, nlp_model=nlp_model)
    new_entities = extract_named_entities(new_text, nlp_model=nlp_model)

    old_keys = {(e["text"].lower(), e["label"]): e for e in old_entities}
    new_keys = {(e["text"].lower(), e["label"]): e for e in new_entities}

    added = [new_keys[k] for k in new_keys if k not in old_keys]
    removed = [old_keys[k] for k in old_keys if k not in new_keys]
    shared = [new_keys[k] for k in new_keys if k in old_keys]

    # Group additions and removals by entity label
    by_label: dict[str, dict[str, list[str]]] = {}
    for ent in added:
        lbl = ent["label"]
        by_label.setdefault(lbl, {"added": [], "removed": []})["added"].append(ent["text"])

    for ent in removed:
        lbl = ent["label"]
        by_label.setdefault(lbl, {"added": [], "removed": []})["removed"].append(ent["text"])

    return {
        "added": added,
        "removed": removed,
        "shared": shared,
        "by_label": by_label,
    }

