"""Pydantic schemas and configuration for the AI explanation layer."""

from __future__ import annotations

import os
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator


class TopicGroup(BaseModel):
    """A logical grouping of detected webpage changes explained by AI."""

    topic: str
    description: str
    change_ids: list[int] = Field(default_factory=list)
    significance: Literal["high", "medium", "low"] = "medium"

    @field_validator("change_ids", mode="before")
    @classmethod
    def coerce_change_ids(cls, v: Any) -> list[int]:
        if not isinstance(v, list):
            return []
        coerced: list[int] = []
        seen: set[int] = set()
        for item in v:
            try:
                cid = int(item)
                if cid not in seen:
                    coerced.append(cid)
                    seen.add(cid)
            except (ValueError, TypeError):
                continue
        return coerced

    @field_validator("significance", mode="before")
    @classmethod
    def normalize_significance(cls, v: Any) -> str:
        if isinstance(v, str):
            clean = v.strip().lower()
            if clean in {"high", "medium", "low"}:
                return clean
        return "medium"


class AISummary(BaseModel):
    """Structured AI-generated summary grounded strictly in detected changes."""

    executive_summary: str
    key_takeaways: list[str] = Field(default_factory=list)
    topic_groups: list[TopicGroup] = Field(default_factory=list)

    @field_validator("key_takeaways", mode="before")
    @classmethod
    def clean_takeaways(cls, v: Any) -> list[str]:
        if not isinstance(v, list):
            return []

        SCHEMA_METADATA_NAMES = {
            "topic_groups",
            "change_ids",
            "executive_summary",
            "significance",
            "key_takeaways",
            "topic",
            "category",
            "description",
            "changes",
            "summary",
        }

        cleaned: list[str] = []
        for item in v:
            s = str(item).strip()
            # Strip markdown bullets or numbers if model prefixed them
            while s.startswith(("- ", "* ", "• ", "1. ", "2. ", "3. ")):
                s = s.split(" ", 1)[1].strip()
            # Reject raw schema artifacts or tokens
            clean_lower = s.lower().strip("`'\" :;{}[]")
            if clean_lower in SCHEMA_METADATA_NAMES or clean_lower.startswith("topic_groups"):
                continue
            if len(clean_lower) < 5 or clean_lower.startswith(("{", "}", "[", "]")):
                continue
            if s and s not in cleaned:
                cleaned.append(s)
            if len(cleaned) == 3:
                break
        return cleaned


class AIConfig(BaseModel):
    """Configuration for local Ollama LLM integration."""

    base_url: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5:1.5b"
    timeout_seconds: float = 90.0
    num_predict: int = 500
    max_queue_wait: float = 45.0
    max_waiters: int = 1
    enabled: bool = True

    @classmethod
    def from_env(cls) -> "AIConfig":
        """Load configuration from environment variables with sensible defaults."""
        enabled_env = os.environ.get("ENABLE_AI_SUMMARY", "true").strip().lower()
        enabled = enabled_env in {"1", "true", "yes", "on"}
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip() or "http://127.0.0.1:11434"
        model = os.environ.get("OLLAMA_MODEL", "qwen2.5:1.5b").strip() or "qwen2.5:1.5b"
        try:
            timeout_seconds = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "90.0"))
            if timeout_seconds <= 0:
                timeout_seconds = 90.0
        except ValueError:
            timeout_seconds = 90.0

        try:
            num_predict = int(os.environ.get("OLLAMA_NUM_PREDICT", "500"))
            if num_predict <= 0:
                num_predict = 500
        except ValueError:
            num_predict = 500

        try:
            max_queue_wait = float(os.environ.get("OLLAMA_MAX_QUEUE_WAIT", "45.0"))
            if max_queue_wait < 0:
                max_queue_wait = 45.0
        except ValueError:
            max_queue_wait = 45.0

        try:
            max_waiters = int(os.environ.get("OLLAMA_MAX_WAITERS", "1"))
            if max_waiters < 0:
                max_waiters = 1
        except ValueError:
            max_waiters = 1

        return cls(
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
            num_predict=num_predict,
            max_queue_wait=max_queue_wait,
            max_waiters=max_waiters,
            enabled=enabled,
        )
