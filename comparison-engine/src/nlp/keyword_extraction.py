"""Keyword and Key Phrase Extraction Layer.

Extracts meaningful keywords and noun phrases from text, filters out common stopwords,
and identifies newly introduced and removed keywords between two versions of text.
"""

from __future__ import annotations

import re
from typing import Any, Sequence

from .preprocessing import clean_html_text, is_empty_or_whitespace

# Comprehensive standard English stop words list
DEFAULT_STOP_WORDS = frozenset({
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down",
    "during", "each", "few", "for", "from", "further", "had", "hadn't", "has",
    "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her",
    "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's",
    "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it",
    "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my",
    "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other",
    "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "shan't",
    "she", "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
    "then", "there", "there's", "these", "they", "they'd", "they'll", "they're",
    "they've", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves", "will", "shall", "just", "also",
})

# Matches alphanumeric words, preserving hyphenated terms
_WORD_PATTERN = re.compile(r"\b[a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)*\b")

_TECHNICAL_EXTENSIONS = (
    ".css", ".js", ".ico", ".png", ".jpg", ".jpeg", ".svg", ".gif",
    ".woff", ".woff2", ".ttf", ".eot", ".map", ".json", ".xml",
)

_TECHNICAL_TERMS = frozenset({
    "href", "rel", "stylesheet", "shortcut", "icon", "static", "css", "img",
    "html", "body", "div", "span", "p", "a", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "li", "ol", "table", "tbody", "thead", "tr", "td", "th", "type", "image",
    "http", "https", "url", "uri", "ftp", "www",
    "paragraph", "footer", "header", "element",
})


def is_technical_noise(term: str) -> bool:
    """Filter obvious technical noise from user-facing semantic keywords.

    Filters:
    - DOM / XPath locators: starts with /html, contains brackets like [0]
    - URL paths / endpoints: starts with /, http://, https://, or contains #
    - Technical assets & filenames: ends with .css, .js, .ico, .png, etc.
    - HTML/CSS attribute artifacts: e.g. 'stylesheet', 'rel:', 'href:'
    """
    if not term:
        return True
    s = term.strip().lower()

    # 1. DOM paths or XPath locators
    if s.startswith("/html") or "body[" in s or "div[" in s or "p[" in s:
        return True

    # 2. URLs, URIs, query strings, and path fragments
    if (
        s.startswith(("http://", "https://", "ftp://", "/", "#", "//"))
        or s.endswith(("/", "\\"))
        or "/" in s
        or "\\" in s
    ):
        return True
    if re.search(r"https?://", s):
        return True

    # 3. File extensions (assets, stylesheets, images, scripts)
    for ext in _TECHNICAL_EXTENSIONS:
        if s.endswith(ext) or (ext + " ") in s:
            return True

    # 4. Attribute syntax or artifacts
    if "href:" in s or "rel:" in s or "type:" in s:
        return True

    # 5. Hexadecimal hashes / asset fingerprints / cache busters (e.g. 68dd615b61e5)
    if re.match(r"^[0-9a-f]{7,}$", s) and any(c.isdigit() for c in s):
        return True

    # 6. Standalone technical terms or HTML attribute artifacts
    cleaned_tokens = re.findall(r"\b[a-z0-9_-]+\b", s)
    if not cleaned_tokens:
        return True
    if all(tok in _TECHNICAL_TERMS or tok.isdigit() for tok in cleaned_tokens):
        return True

    # 7. Check if term (or stripped of punctuation) is a stopword
    stripped_word = s.strip("/\\-_.")
    if stripped_word in DEFAULT_STOP_WORDS:
        return True

    return False


def extract_keywords_fallback(
    text: str,
    stop_words: frozenset[str] = DEFAULT_STOP_WORDS,
    min_length: int = 3,
    top_n: int = 15,
    max_keywords: int | None = None,
) -> list[str]:
    """Fallback keyword extraction using regex tokenization and first-seen ordering."""
    if is_empty_or_whitespace(text):
        return []

    words = _WORD_PATTERN.findall(text)
    keywords: list[str] = []
    seen: set[str] = set()

    limit = max_keywords if max_keywords is not None else top_n

    for word in words:
        clean_word = word.strip()
        lower_word = clean_word.lower()

        if len(lower_word) < min_length:
            continue
        if lower_word in stop_words:
            continue
        if is_technical_noise(clean_word):
            continue
        if lower_word.isdigit():
            # Keep numbers if 4 digits (e.g. years like 2026) or meaningful
            if len(lower_word) != 4:
                continue

        if lower_word not in seen:
            seen.add(lower_word)
            keywords.append(clean_word)
            if limit is not None and len(keywords) >= limit:
                break

    return keywords


def extract_keywords(
    text: str | None,
    nlp_model: Any = None,
    stop_words: frozenset[str] = DEFAULT_STOP_WORDS,
    min_length: int = 3,
    include_noun_chunks: bool = True,
) -> list[str]:
    """Extract significant keywords and noun phrases from text.

    If spaCy nlp_model is provided, uses POS tagging and noun chunk extraction.
    Otherwise falls back to tokenization and stopword filtering.
    Preserves first-seen ordering and deduplicates case-insensitively.
    """
    clean = clean_html_text(text)
    if not clean:
        return []

    if nlp_model is not None:
        try:
            doc = nlp_model(clean)
            keywords: list[str] = []
            seen: set[str] = set()

            # 1. First extract noun chunks if enabled (e.g. 'examination announcement')
            if include_noun_chunks and hasattr(doc, "noun_chunks"):
                for chunk in doc.noun_chunks:
                    clean_chunk = chunk.text.strip()
                    lower_chunk = clean_chunk.lower()
                    # Strip leading stop words in chunks (e.g. "the college" -> "college")
                    chunk_tokens = [
                        t.text for t in chunk
                        if not t.is_stop and t.lower_ not in stop_words and len(t.text) >= min_length
                    ]
                    if chunk_tokens:
                        filtered_chunk = " ".join(chunk_tokens)
                        if not is_technical_noise(filtered_chunk) and filtered_chunk.lower() not in seen:
                            seen.add(filtered_chunk.lower())
                            keywords.append(filtered_chunk)

            # 2. Extract significant individual tokens (NOUN, PROPN, ADJ, VERB)
            for token in doc:
                lower = token.lower_
                if (
                    not token.is_stop
                    and lower not in stop_words
                    and not is_technical_noise(token.text)
                    and not token.is_punct
                    and not token.is_space
                    and len(token.text) >= min_length
                    and (not token.pos_ or token.pos_ in ("NOUN", "PROPN", "ADJ", "VERB", "NUM"))
                ):
                    if lower not in seen:
                        seen.add(lower)
                        keywords.append(token.text)

            if keywords:
                return keywords
        except Exception:
            pass  # Fall back to token-based extraction on any error

    return extract_keywords_fallback(clean, stop_words=stop_words, min_length=min_length)


def compare_keywords(
    old_text: str | None,
    new_text: str | None,
    nlp_model: Any = None,
    stop_words: frozenset[str] = DEFAULT_STOP_WORDS,
) -> dict[str, list[str]]:
    """Compare keywords between old and new text versions.

    Returns:
    - added: Keywords present in new_text but absent in old_text.
    - removed: Keywords present in old_text but absent in new_text.
    - shared: Keywords present in both versions.
    """
    old_kw = extract_keywords(old_text, nlp_model=nlp_model, stop_words=stop_words)
    new_kw = extract_keywords(new_text, nlp_model=nlp_model, stop_words=stop_words)

    old_map = {kw.lower(): kw for kw in old_kw}
    new_map = {kw.lower(): kw for kw in new_kw}

    added = [new_map[k] for k in new_map if k not in old_map]
    removed = [old_map[k] for k in old_map if k not in new_map]
    shared = [new_map[k] for k in new_map if k in old_map]

    return {
        "added": added,
        "removed": removed,
        "shared": shared,
    }
