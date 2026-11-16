"""NLP Pipeline for Webpage Comparison Semantic Analysis.

Coordinates preprocessing, semantic similarity calculation, keyword extraction,
and named entity recognition (NER) across detected webpage changes.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Sequence

from .keyword_extraction import compare_keywords, extract_keywords
from .model_loader import (
    DEFAULT_SENTENCE_MODEL_NAME,
    DEFAULT_SPACY_MODEL_NAME,
    get_model_manager,
)
from .ner import compare_named_entities, extract_named_entities
from .preprocessing import clean_html_text, is_empty_or_whitespace
from .semantic_similarity import compute_semantic_similarity

logger = logging.getLogger(__name__)


def generate_change_explanation(
    original_text: str,
    updated_text: str,
    similarity_category: str,
    added_keywords: list[str],
    removed_keywords: list[str],
    added_entities: list[dict[str, str]],
    removed_entities: list[dict[str, str]],
) -> str:
    """Generate a simple, clear human-readable explanation of the text change."""
    if similarity_category == "identical":
        return "The text content is semantically identical."

    parts: list[str] = []

    # Category phrasing
    if similarity_category == "high":
        parts.append("Minor wording or phrasing change with high semantic overlap.")
    elif similarity_category == "moderate":
        parts.append("Moderate content update with noticeable semantic difference.")
    elif similarity_category == "low":
        parts.append("Substantial revision with low semantic overlap.")
    else:
        parts.append("Major rewrite or replacement with completely different content.")

    # Entity changes (e.g., dates, money, organizations)
    added_dates = [e["text"] for e in added_entities if e["label"] == "DATE"]
    removed_dates = [e["text"] for e in removed_entities if e["label"] == "DATE"]
    if removed_dates and added_dates:
        parts.append(
            f"Date updated from '{', '.join(removed_dates)}' to '{', '.join(added_dates)}'."
        )
    elif added_dates:
        parts.append(f"New date mentioned: '{', '.join(added_dates)}'.")
    elif removed_dates:
        parts.append(f"Date reference removed: '{', '.join(removed_dates)}'.")

    added_money = [e["text"] for e in added_entities if e["label"] == "MONEY"]
    removed_money = [e["text"] for e in removed_entities if e["label"] == "MONEY"]
    if removed_money and added_money:
        parts.append(
            f"Monetary value updated from '{', '.join(removed_money)}' to '{', '.join(added_money)}'."
        )
    elif added_money:
        parts.append(f"New monetary value mentioned: '{', '.join(added_money)}'.")
    elif removed_money:
        parts.append(f"Monetary value reference removed: '{', '.join(removed_money)}'.")

    # Important keyword additions and removals
    if added_keywords:
        parts.append(f"Added keywords: {', '.join(added_keywords[:4])}.")
    if removed_keywords:
        parts.append(f"Removed keywords: {', '.join(removed_keywords[:4])}.")

    return " ".join(parts)


def analyze_text_modification(
    old_text: str | None,
    new_text: str | None,
    sentence_model: Any = None,
    spacy_model: Any = None,
    similarity_thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Analyze a single text modification pair across similarity, keywords, and entities."""
    clean_old = clean_html_text(old_text)
    clean_new = clean_html_text(new_text)

    # 1. Semantic Similarity
    sim_res = compute_semantic_similarity(
        clean_old,
        clean_new,
        model=sentence_model,
        thresholds=similarity_thresholds,
    )
    sim_score = sim_res.score
    sim_category = sim_res.category
    sim_method = sim_res.method

    # 2. Keyword Extraction & Diffing
    kw_diff = compare_keywords(clean_old, clean_new, nlp_model=spacy_model)

    # 3. Named Entity Recognition & Diffing
    ner_diff = compare_named_entities(clean_old, clean_new, nlp_model=spacy_model)

    # 4. Human-readable explanation
    explanation = generate_change_explanation(
        clean_old,
        clean_new,
        sim_category,
        kw_diff["added"],
        kw_diff["removed"],
        ner_diff["added"],
        ner_diff["removed"],
    )

    return {
        "original_text": clean_old,
        "updated_text": clean_new,
        "similarity_score": sim_score,
        "similarity_category": sim_category,
        "similarity_method": sim_method,
        "added_keywords": kw_diff["added"],
        "removed_keywords": kw_diff["removed"],
        "shared_keywords": kw_diff["shared"],
        "added_entities": ner_diff["added"],
        "removed_entities": ner_diff["removed"],
        "entity_breakdown": ner_diff["by_label"],
        "explanation": explanation,
    }


def analyze_text_addition(
    text: str | None,
    spacy_model: Any = None,
) -> dict[str, Any]:
    """Analyze newly introduced text (without inventing a missing counterpart)."""
    clean = clean_html_text(text)
    keywords = extract_keywords(clean, nlp_model=spacy_model)
    entities = extract_named_entities(clean, nlp_model=spacy_model)

    return {
        "text": clean,
        "keywords": keywords,
        "entities": entities,
    }


def analyze_text_removal(
    text: str | None,
    spacy_model: Any = None,
) -> dict[str, Any]:
    """Analyze removed text (without inventing a missing counterpart)."""
    clean = clean_html_text(text)
    keywords = extract_keywords(clean, nlp_model=spacy_model)
    entities = extract_named_entities(clean, nlp_model=spacy_model)

    return {
        "text": clean,
        "keywords": keywords,
        "entities": entities,
    }


def run_nlp_pipeline(
    changes: list[dict[str, Any]],
    sentence_model: Any = None,
    spacy_model: Any = None,
    similarity_thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Run the complete NLP pipeline over a collection of comparison changes.

    Accepts changes from either adapt_engine_result ("changes" list) or raw_changes.
    Returns a self-contained, structured NLP analysis object.
    Only loads NLP models if there are relevant items to analyze.
    """
    model_mgr = get_model_manager()

    # Avoid loading SentenceTransformer if there are no modified text items to compare
    has_modifications = any(
        item.get("category") == "modified"
        and (
            not is_empty_or_whitespace(item.get("oldValue") or item.get("old_text"))
            or not is_empty_or_whitespace(item.get("newValue") or item.get("new_text"))
        )
        for item in changes
    )

    has_any_items = has_modifications or any(
        (item.get("category") == "added" and not is_empty_or_whitespace(item.get("newValue") or item.get("text")))
        or (item.get("category") == "removed" and not is_empty_or_whitespace(item.get("oldValue") or item.get("text")))
        for item in changes
    )

    st_model = None
    if has_modifications:
        st_model = sentence_model if sentence_model is not None else model_mgr.get_sentence_transformer()

    sp_model = None
    if has_any_items:
        sp_model = spacy_model if spacy_model is not None else model_mgr.get_spacy_model()

    analyzed_modifications: list[dict[str, Any]] = []
    analyzed_additions: list[dict[str, Any]] = []
    analyzed_removals: list[dict[str, Any]] = []

    similarity_scores: list[float] = []
    category_counts: Counter[str] = Counter()

    all_added_keywords: list[str] = []
    all_removed_keywords: list[str] = []
    all_added_entities: list[dict[str, str]] = []
    all_removed_entities: list[dict[str, str]] = []

    for item in changes:
        category = item.get("category")

        if category == "modified":
            # Extract old and new text values from either adapted or raw schema
            old_val = item.get("oldValue") if "oldValue" in item else item.get("old_text")
            new_val = item.get("newValue") if "newValue" in item else item.get("new_text")

            # Only analyze if at least one side has meaningful text
            if not is_empty_or_whitespace(old_val) or not is_empty_or_whitespace(new_val):
                mod_nlp = analyze_text_modification(
                    old_val,
                    new_val,
                    sentence_model=st_model,
                    spacy_model=sp_model,
                    similarity_thresholds=similarity_thresholds,
                )
                mod_record = {
                    "change_id": item.get("id"),
                    "element": item.get("element", item.get("tag", "Text")),
                    "source_path": item.get("sourcePath", item.get("path_v1", "")),
                    "target_path": item.get("targetPath", item.get("path_v2", "")),
                    **mod_nlp,
                }
                analyzed_modifications.append(mod_record)

                similarity_scores.append(mod_nlp["similarity_score"])
                category_counts[mod_nlp["similarity_category"]] += 1

                all_added_keywords.extend(mod_nlp["added_keywords"])
                all_removed_keywords.extend(mod_nlp["removed_keywords"])
                all_added_entities.extend(mod_nlp["added_entities"])
                all_removed_entities.extend(mod_nlp["removed_entities"])

        elif category == "added":
            val = item.get("newValue") if "newValue" in item else item.get("text")
            if not is_empty_or_whitespace(val):
                add_nlp = analyze_text_addition(val, spacy_model=sp_model)
                add_record = {
                    "change_id": item.get("id"),
                    "element": item.get("element", item.get("tag", "Element")),
                    "path": item.get("sourcePath", item.get("path", "")),
                    **add_nlp,
                }
                analyzed_additions.append(add_record)
                all_added_keywords.extend(add_nlp["keywords"])
                all_added_entities.extend(add_nlp["entities"])

        elif category == "removed":
            val = item.get("oldValue") if "oldValue" in item else item.get("text")
            if not is_empty_or_whitespace(val):
                rem_nlp = analyze_text_removal(val, spacy_model=sp_model)
                rem_record = {
                    "change_id": item.get("id"),
                    "element": item.get("element", item.get("tag", "Element")),
                    "path": item.get("sourcePath", item.get("path", "")),
                    **rem_nlp,
                }
                analyzed_removals.append(rem_record)
                all_removed_keywords.extend(rem_nlp["keywords"])
                all_removed_entities.extend(rem_nlp["entities"])

    # Aggregate top keywords and entities by frequency
    top_added_kw = [kw for kw, _ in Counter(k.lower() for k in all_added_keywords).most_common(10)]
    top_removed_kw = [kw for kw, _ in Counter(k.lower() for k in all_removed_keywords).most_common(10)]

    avg_sim: float | None = (
        round(sum(similarity_scores) / len(similarity_scores), 4)
        if similarity_scores
        else None
    )

    overall_summary = _build_overall_summary(
        len(analyzed_modifications),
        len(analyzed_additions),
        len(analyzed_removals),
        avg_sim,
        category_counts,
        top_added_kw,
        top_removed_kw,
    )

    return {
        "overall": {
            "total_modifications_analyzed": len(analyzed_modifications),
            "total_additions_analyzed": len(analyzed_additions),
            "total_removals_analyzed": len(analyzed_removals),
            "average_semantic_similarity": avg_sim,
            "similarity_distribution": dict(category_counts),
            "top_added_keywords": top_added_kw,
            "top_removed_keywords": top_removed_kw,
            "summary": overall_summary,
        },
        "modifications": analyzed_modifications,
        "additions": analyzed_additions,
        "removals": analyzed_removals,
    }


def _build_overall_summary(
    mod_count: int,
    add_count: int,
    rem_count: int,
    avg_sim: float | None,
    distribution: Counter[str],
    top_added: list[str],
    top_removed: list[str],
) -> str:
    """Compose a concise natural-language summary of the comparison changes."""
    if mod_count == 0 and add_count == 0 and rem_count == 0:
        return "No text content changes detected."

    parts = []
    if mod_count > 0:
        sim_str = f"{avg_sim:.1%}" if avg_sim is not None else "N/A"
        parts.append(
            f"Analyzed {mod_count} text modification{'s' if mod_count > 1 else ''} with an average semantic similarity of {sim_str}."
        )
    elif add_count > 0 or rem_count > 0:
        parts.append("No text modifications were present to assess semantic similarity.")

    if add_count > 0:
        parts.append(f"Found {add_count} new text addition{'s' if add_count > 1 else ''}.")
    if rem_count > 0:
        parts.append(f"Found {rem_count} text removal{'s' if rem_count > 1 else ''}.")

    if top_added:
        parts.append(f"Key additions include: {', '.join(top_added[:5])}.")
    if top_removed:
        parts.append(f"Key removals include: {', '.join(top_removed[:5])}.")

    return " ".join(parts)


def attach_nlp_analysis(
    comparison_result: dict[str, Any],
    sentence_model: Any = None,
    spacy_model: Any = None,
) -> dict[str, Any]:
    """Safely enrich an existing comparison result with an nlpAnalysis payload.

    Preserves all existing fields, counts, and structural results untouched.
    Fails safely if NLP processing encounters an unexpected error.
    """
    try:
        changes = comparison_result.get("changes", [])
        nlp_payload = run_nlp_pipeline(
            changes,
            sentence_model=sentence_model,
            spacy_model=spacy_model,
        )
        comparison_result["nlpAnalysis"] = nlp_payload
    except Exception as exc:
        logger.error("NLP analysis failed safely: %s", exc, exc_info=True)
        comparison_result["nlpAnalysis"] = {
            "error": str(exc),
            "status": "failed",
        }

    return comparison_result
