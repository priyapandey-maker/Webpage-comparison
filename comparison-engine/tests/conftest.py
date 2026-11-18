"""Global test configuration and fixtures for comparison-engine tests.

Ensures ordinary backend tests run in complete isolation from live external services
(e.g., local Ollama daemon) unless specifically testing AI functionality.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_backend_tests(monkeypatch, request):
    """Disable AI summary generation by default in ordinary backend test suites.

    Ordinary tests (Wayback endpoints, live compare, security SSRF, Phase 1 regressions)
    run with ENABLE_AI_SUMMARY=false to prevent unmocked endpoint tests from making
    real HTTP connections to a running local Ollama daemon.

    Tests in test_ai_summary.py retain the default ENABLE_AI_SUMMARY=true and use
    controlled mocks.
    """
    module_name = getattr(request.module, "__name__", "")
    if "test_ai_summary" not in module_name:
        monkeypatch.setenv("ENABLE_AI_SUMMARY", "false")
