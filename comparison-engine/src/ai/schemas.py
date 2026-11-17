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
        for item in v:
            try:
                coerced.append(int(item))
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
        return [str(item).strip() for item in v if str(item).strip()]


class AIConfig(BaseModel):
    """Configuration for local Ollama LLM integration."""

    base_url: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5:1.5b"
    timeout_seconds: float = 90.0
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

        return cls(
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
            enabled=enabled,
        )
