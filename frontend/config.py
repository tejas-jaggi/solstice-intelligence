"""Frontend presentation/client configuration.

Contains ONLY presentation and client settings — no business logic, no secrets.
The OpenAI API key lives exclusively in the backend; the frontend can reach the
backend only through the REST API, which controls all token spending. This is a
security property of the two-tier split, not just tidiness.

Base URL comes from the environment so one codebase runs unchanged in
development (local API) and production (deployed API) — the twelve-factor
"config in the environment" principle.
"""
from __future__ import annotations

import os

# Where the FastAPI backend lives. Overridable per environment.
API_BASE_URL: str = os.environ.get("SOLSTICE_API_URL", "http://localhost:8000").rstrip("/")

# An analytics question is an LLM round-trip; allow generous time before timeout.
REQUEST_TIMEOUT_SECONDS: float = float(os.environ.get("SOLSTICE_API_TIMEOUT", "30"))

# Streamlit page presentation.
PAGE_TITLE: str = "Solstice Intelligence"
PAGE_ICON: str = "🌞"
PAGE_LAYOUT: str = "centered"
