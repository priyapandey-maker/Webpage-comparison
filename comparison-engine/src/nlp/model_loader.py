"""Lazy Singleton Model Loader and Lifecycle Management.

Encapsulates thread-safe lazy loading and caching for:
1. Sentence Transformers embedding models (default: all-MiniLM-L6-v2)
2. spaCy linguistic and NER models (default: en_core_web_sm)

Prevents repeated loading across request cycles and handles missing models gracefully.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_SENTENCE_MODEL_NAME = "all-MiniLM-L6-v2"
DEFAULT_SPACY_MODEL_NAME = "en_core_web_sm"


class ModelManager:
    """Thread-safe lazy manager for pretrained NLP models."""

    _instance: ModelManager | None = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._st_models: dict[str, Any] = {}
        self._spacy_models: dict[str, Any] = {}
        self._lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> ModelManager:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def get_sentence_transformer(
        self,
        model_name: str = DEFAULT_SENTENCE_MODEL_NAME,
        raise_on_error: bool = False,
    ) -> Any | None:
        """Lazily load and cache a SentenceTransformer model instance."""
        if model_name in self._st_models:
            return self._st_models[model_name]

        with self._lock:
            if model_name in self._st_models:
                return self._st_models[model_name]

            try:
                from sentence_transformers import SentenceTransformer
                model = SentenceTransformer(model_name)
                self._st_models[model_name] = model
                return model
            except Exception as exc:
                logger.warning(
                    "Failed to load SentenceTransformer model '%s': %s", model_name, exc
                )
                self._st_models[model_name] = None  # Cache failure to avoid repeated expensive attempts
                if raise_on_error:
                    raise
                return None

    def get_spacy_model(
        self,
        model_name: str = DEFAULT_SPACY_MODEL_NAME,
        raise_on_error: bool = False,
    ) -> Any | None:
        """Lazily load and cache a spaCy linguistic/NER model instance."""
        if model_name in self._spacy_models:
            return self._spacy_models[model_name]

        with self._lock:
            if model_name in self._spacy_models:
                return self._spacy_models[model_name]

            try:
                import spacy
                try:
                    nlp = spacy.load(model_name)
                except OSError:
                    # Model not installed locally, attempt blank English pipeline with sentencizer
                    nlp = spacy.blank("en")
                    if "sentencizer" not in nlp.pipe_names:
                        nlp.add_pipe("sentencizer")

                self._spacy_models[model_name] = nlp
                return nlp
            except Exception as exc:
                logger.warning("Failed to load spaCy model '%s': %s", model_name, exc)
                self._spacy_models[model_name] = None  # Cache failure to avoid repeated expensive attempts
                if raise_on_error:
                    raise
                return None

    def set_sentence_transformer(self, model_name: str, model: Any) -> None:
        """Inject a mock or pre-loaded SentenceTransformer (useful for testing)."""
        with self._lock:
            self._st_models[model_name] = model

    def set_spacy_model(self, model_name: str, model: Any) -> None:
        """Inject a mock or pre-loaded spaCy model (useful for testing)."""
        with self._lock:
            self._spacy_models[model_name] = model

    def clear(self) -> None:
        """Clear all loaded models to release memory during test cleanup."""
        with self._lock:
            self._st_models.clear()
            self._spacy_models.clear()


def get_model_manager() -> ModelManager:
    """Return the global ModelManager singleton."""
    return ModelManager.get_instance()

