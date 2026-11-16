"""Semantic Similarity Layer using Sentence Transformers.

Computes embeddings and cosine similarity between text snippets, assigns configurable
similarity tiers (identical, high, moderate, low, substantially_different), and provides
deterministic fallback similarity when embedding models are unavailable.
"""

from __future__ import annotations

import math
from typing import Any, NamedTuple, Sequence

from .model_loader import DEFAULT_SENTENCE_MODEL_NAME, get_model_manager
from .preprocessing import clean_html_text, is_empty_or_whitespace


class SimilarityResult(NamedTuple):
    """Structured result returned by compute_semantic_similarity."""

    score: float
    category: str
    method: str


# Configurable similarity category thresholds
DEFAULT_SIMILARITY_THRESHOLDS = {
    "identical": 0.999,
    "high": 0.80,
    "moderate": 0.50,
    "low": 0.25,
}

# Embedding in-memory cache to avoid repeated calculations: (id(model), model_name, text) -> embedding
_EMBEDDING_CACHE: dict[tuple[int, str, str], list[float]] = {}


def cosine_similarity(v1: Sequence[float], v2: Sequence[float]) -> float:
    """Compute cosine similarity between two numeric vectors, returning float in [-1.0, 1.0]."""
    if len(v1) != len(v2) or len(v1) == 0:
        return 0.0

    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))

    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0

    return max(-1.0, min(1.0, dot / (norm1 * norm2)))


def categorize_similarity(
    score: float,
    thresholds: dict[str, float] | None = None,
) -> str:
    """Categorize a similarity score into a human-interpretable category."""
    t = thresholds or DEFAULT_SIMILARITY_THRESHOLDS

    if score >= t.get("identical", 0.999):
        return "identical"
    if score >= t.get("high", 0.80):
        return "high"
    if score >= t.get("moderate", 0.50):
        return "moderate"
    if score >= t.get("low", 0.25):
        return "low"
    return "substantially_different"


def compute_fallback_similarity(text1: str, text2: str) -> float:
    """Deterministic token-level Jaccard similarity fallback when neural models are unavailable."""
    if text1 == text2:
        return 1.0
    if not text1 or not text2:
        return 0.0

    tokens1 = set(text1.lower().split())
    tokens2 = set(text2.lower().split())

    intersection = tokens1 & tokens2
    union = tokens1 | tokens2

    if not union:
        return 1.0 if text1 == text2 else 0.0

    return len(intersection) / len(union)


# Alias for backwards compatibility / descriptive clarity
compute_token_similarity_fallback = compute_fallback_similarity


def compute_semantic_similarity(
    old_text: str | None,
    new_text: str | None,
    model: Any = None,
    model_name: str = DEFAULT_SENTENCE_MODEL_NAME,
    thresholds: dict[str, float] | None = None,
) -> SimilarityResult:
    """Calculate semantic similarity between old and new text.

    Returns:
        SimilarityResult namedtuple (score, category, method)
        where:
        - score is clamped to [0.0, 1.0] and rounded to 4 decimals.
        - category is in {'identical', 'high', 'moderate', 'low', 'substantially_different'}.
        - method is in {'exact_match', 'sentence_transformer', 'token_jaccard_fallback'}.
    """
    clean_old = clean_html_text(old_text)
    clean_new = clean_html_text(new_text)

    # Fast-path 1: Identical strings detected directly
    if clean_old == clean_new:
        return SimilarityResult(1.0, "identical", "exact_match")

    # Fast-path 2: One string is empty, other is not (no overlap possible)
    if not clean_old or not clean_new:
        return SimilarityResult(0.0, "substantially_different", "token_jaccard_fallback")

    # Retrieve or resolve model
    sentence_model = model
    if sentence_model is None:
        sentence_model = get_model_manager().get_sentence_transformer(model_name)

    if sentence_model is not None:
        try:
            emb_old = _get_or_compute_embedding(clean_old, sentence_model, model_name)
            emb_new = _get_or_compute_embedding(clean_new, sentence_model, model_name)

            raw_sim = cosine_similarity(emb_old, emb_new)
            clamped = max(0.0, min(1.0, raw_sim))
            score = round(clamped, 4)
            category = categorize_similarity(score, thresholds)
            return SimilarityResult(score, category, "sentence_transformer")
        except Exception:
            pass  # Fall back gracefully to token similarity

    # Fallback path if model is unavailable or errored
    fallback_sim = compute_fallback_similarity(clean_old, clean_new)
    score = round(fallback_sim, 4)
    category = categorize_similarity(score, thresholds)
    return SimilarityResult(score, category, "token_jaccard_fallback")


def _get_or_compute_embedding(
    text: str,
    model: Any,
    model_name: str,
) -> list[float]:
    """Cache and return embedding vector for a given (model_instance, model_name, text) triple."""
    cache_key = (id(model), model_name, text)
    if cache_key in _EMBEDDING_CACHE:
        return _EMBEDDING_CACHE[cache_key]

    raw_emb = model.encode(text)
    if hasattr(raw_emb, "tolist"):
        emb_list = raw_emb.tolist()
    else:
        emb_list = [float(x) for x in raw_emb]

    # Limit cache size to 10,000 entries
    if len(_EMBEDDING_CACHE) > 10000:
        _EMBEDDING_CACHE.clear()

    _EMBEDDING_CACHE[cache_key] = emb_list
    return emb_list


def clear_embedding_cache() -> None:
    """Clear the embedding vector cache."""
    _EMBEDDING_CACHE.clear()
