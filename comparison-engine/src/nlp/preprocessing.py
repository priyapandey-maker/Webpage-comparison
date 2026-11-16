"""Text Preprocessing Layer for HTML-derived Content.

Cleans and normalizes text extracted from HTML nodes, strips residual markup and entities,
normalizes whitespace, and handles edge cases (empty strings, None values, whitespace-only).
Preserves meaningful text, capitalization, and punctuation for downstream NLP tasks.
"""

from __future__ import annotations

import html
import re
import unicodedata

# Matches HTML tags if any residual tags survived parsing
_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")

# Matches consecutive whitespace characters (including newlines, tabs, non-breaking spaces)
_WHITESPACE_PATTERN = re.compile(r"\s+")

# Matches unprintable control characters except standard punctuation and word chars
_CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def is_empty_or_whitespace(text: str | None) -> bool:
    """Return True if text is None, empty, or consists exclusively of whitespace."""
    if text is None:
        return True
    if not isinstance(text, str):
        return True
    return len(text.strip()) == 0


def clean_html_text(text: str | None) -> str:
    """Clean and normalize HTML-derived text for linguistic and semantic processing.

    - Unescapes HTML entities (e.g., &amp; -> &, &nbsp; -> space).
    - Removes residual HTML tags.
    - Strips non-printable control characters.
    - Normalizes Unicode characters via NFKC.
    - Collapses consecutive whitespace into a single space and trims.
    - Preserves meaningful punctuation, case, and alphanumeric characters.
    - Returns empty string for None or empty inputs.
    """
    if text is None:
        return ""

    if not isinstance(text, str):
        text = str(text)

    if not text.strip():
        return ""

    # 1. Unescape HTML entities (&nbsp;, &gt;, &quot;, &#39;, etc.)
    unescaped = html.unescape(text)

    # 2. Replace non-breaking spaces (\xa0, \u200b) with standard space
    unescaped = unescaped.replace("\xa0", " ").replace("\u200b", " ")

    # 3. Strip any residual HTML/XML tags
    cleaned = _HTML_TAG_PATTERN.sub(" ", unescaped)

    # 4. Remove unprintable control characters (replace with space to prevent word joining)
    cleaned = _CONTROL_CHAR_PATTERN.sub(" ", cleaned)

    # 5. Unicode normalization (NFKC)
    normalized = unicodedata.normalize("NFKC", cleaned)

    # 6. Collapse redundant whitespace and trim
    collapsed = _WHITESPACE_PATTERN.sub(" ", normalized).strip()

    return collapsed


def normalize_whitespace(text: str | None) -> str:
    """Collapse all whitespace sequences in text to single spaces and strip outer whitespace."""
    if is_empty_or_whitespace(text):
        return ""
    return _WHITESPACE_PATTERN.sub(" ", str(text)).strip()


def normalize_text(text: str | None) -> str:
    """Convenience alias for clean_html_text."""
    return clean_html_text(text)
