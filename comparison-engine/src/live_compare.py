"""Backward-compatibility module re-exporting shared HTML validation symbols from html_validator.

The two-URL live comparison workflow has been retired in Milestone 1.
Shared validation functions used by Wayback and other modules reside in html_validator.py.
"""

from __future__ import annotations

try:
    from .html_validator import (
        HTML_CONTENT_TYPES,
        REJECTED_CONTENT_TYPES,
        HTMLValidationError,
        LiveCompareError,
        LiveFetchError,
        WebpageContentError,
        validate_html_response,
    )
except ImportError:
    from html_validator import (
        HTML_CONTENT_TYPES,
        REJECTED_CONTENT_TYPES,
        HTMLValidationError,
        LiveCompareError,
        LiveFetchError,
        WebpageContentError,
        validate_html_response,
    )

__all__ = [
    "HTML_CONTENT_TYPES",
    "REJECTED_CONTENT_TYPES",
    "HTMLValidationError",
    "LiveCompareError",
    "LiveFetchError",
    "WebpageContentError",
    "validate_html_response",
]
