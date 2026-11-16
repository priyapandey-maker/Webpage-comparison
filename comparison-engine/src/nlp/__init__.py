"""
NLP-Based Semantic Analysis Module for Webpage Comparison.

Provides independent semantic analysis of text changes detected by the
structural comparison engine:
- Text preprocessing and normalization
- Semantic similarity scoring with Sentence Transformers
- Keyword & noun-phrase extraction (added/removed)
- Named Entity Recognition (NER) (added/removed entities by type)
- Human-readable change explanation and summarization
"""

from .preprocessing import (
    clean_html_text,
    normalize_text,
    is_empty_or_whitespace,
)

from .model_loader import (
    ModelManager,
    get_model_manager,
)

from .keyword_extraction import (
    extract_keywords,
    compare_keywords,
)

from .ner import (
    extract_named_entities,
    compare_named_entities,
)

from .semantic_similarity import (
    SimilarityResult,
    compute_semantic_similarity,
    categorize_similarity,
    compute_token_similarity_fallback,
)

from .pipeline import (
    analyze_text_modification,
    run_nlp_pipeline,
    attach_nlp_analysis,
)

__all__ = [
    "clean_html_text",
    "normalize_text",
    "is_empty_or_whitespace",
    "ModelManager",
    "get_model_manager",
    "extract_keywords",
    "compare_keywords",
    "extract_named_entities",
    "compare_named_entities",
    "SimilarityResult",
    "compute_semantic_similarity",
    "categorize_similarity",
    "compute_token_similarity_fallback",
    "analyze_text_modification",
    "run_nlp_pipeline",
    "attach_nlp_analysis",
]

