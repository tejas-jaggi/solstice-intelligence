"""Dependency injection for the API layer.

FastAPI's dependency-injection system lets route handlers declare what they need
(``assistant: AnalyticsAssistant = Depends(get_assistant)``) without knowing how
it was built. This is what makes the API testable: in tests we override
``get_assistant`` to return a FakeLLMClient-backed assistant, so no route ever
touches the network.

The assistant is constructed ONCE in the lifespan (main.py) and stored on
app state; this provider simply hands out that single instance per request
(construct-once / inject-per-request).
"""
from __future__ import annotations

from fastapi import Request

from app.llm.orchestrator import AnalyticsAssistant


def get_assistant(request: Request) -> AnalyticsAssistant:
    """Return the process-wide AnalyticsAssistant from app state."""
    assistant = getattr(request.app.state, "assistant", None)
    if assistant is None:  # pragma: no cover - guarded by readiness/lifespan
        # This should never happen if lifespan ran; surfaced as 503 by the route.
        raise RuntimeError("Assistant is not initialized.")
    return assistant
