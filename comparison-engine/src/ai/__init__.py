"""AI module providing an explanation layer for detected webpage comparison changes."""

from .schemas import AIConfig, AISummary, TopicGroup
from .summarizer import build_compact_changes_payload, generate_ai_summary

__all__ = [
    "AIConfig",
    "AISummary",
    "TopicGroup",
    "build_compact_changes_payload",
    "generate_ai_summary",
]
