"""API routes.

Thin HTTP handlers. They own transport concerns only: receive a validated
request, invoke the injected assistant, map the result to the public contract,
return it. No business, SQL, validation, or presentation logic lives here.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, Response, status

from app.api import mapping
from app.api.dependencies import get_assistant
from app.api.models import (
    AskRequest,
    AskResponse,
    HealthResponse,
    ReadyResponse,
    VersionResponse,
)
from app.llm.orchestrator import AnalyticsAssistant

logger = logging.getLogger("solstice.api")

router = APIRouter()

APP_VERSION = "1.2.0"
MILESTONE = "milestone-2-phase-h"


@router.post("/v1/ask", response_model=AskResponse, tags=["ask"])
def ask(
    body: AskRequest,
    request: Request,
    assistant: AnalyticsAssistant = Depends(get_assistant),
) -> AskResponse:
    """Answer a natural-language question through the governed pipeline.

    Pipeline outcomes (including refusals) return 200 with a status field.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    result = assistant.ask(body.question)

    # Log system behavior only — never the question text, answer, or secrets.
    logger.info(
        "ask handled",
        extra={"request_id": request_id, "stage": result.stage.value},
    )

    return mapping.to_ask_response(result, request_id)


@router.get("/health", response_model=HealthResponse, tags=["ops"])
def health() -> HealthResponse:
    """Liveness: the process is running. No dependencies checked, no I/O."""
    return HealthResponse(status="alive")


@router.get("/ready", response_model=ReadyResponse, tags=["ops"])
def ready(request: Request, response: Response) -> ReadyResponse:
    """Readiness: the assistant is constructed and the warehouse is reachable.

    Never calls OpenAI — readiness must be free to poll.
    """
    assistant = getattr(request.app.state, "assistant", None)
    if assistant is None:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadyResponse(ready=False, detail="Assistant not initialized.")

    # Cheap warehouse reachability check (no OpenAI, no tokens spent).
    try:
        warehouse_ok = getattr(request.app.state, "warehouse_ok", True)
    except Exception:  # pragma: no cover
        warehouse_ok = False

    if not warehouse_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadyResponse(ready=False, detail="Warehouse not reachable.")

    return ReadyResponse(ready=True, detail="ok")


@router.get("/version", response_model=VersionResponse, tags=["ops"])
def version() -> VersionResponse:
    """Application version and repository milestone. Static, no I/O."""
    return VersionResponse(app_version=APP_VERSION, milestone=MILESTONE)
