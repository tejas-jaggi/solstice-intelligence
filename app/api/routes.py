"""API routes.

Thin HTTP handlers. They own transport concerns only: receive a validated
request, invoke the injected assistant, map the result to the public contract,
return it. No business, SQL, validation, or presentation logic lives here.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, Response, status

from app.api import mapping
from app.api.access_guard import enforce_deployment_guard
from app.api.build_info import get_app_version, get_milestone
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


@router.post(
    "/v1/ask",
    response_model=AskResponse,
    tags=["ask"],
    dependencies=[Depends(enforce_deployment_guard)],
)
def ask(
    body: AskRequest,
    request: Request,
    assistant: AnalyticsAssistant = Depends(get_assistant),
) -> AskResponse:
    """Answer a natural-language question through the governed pipeline.

    Pipeline outcomes (including refusals and timeouts) return 200 with a status
    field. The Deployment Access Guard (ADR-012) protects this endpoint against
    unbounded OpenAI spend.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    result = assistant.ask(body.question)

    # METADATA-ONLY (ADR-013): request id + pipeline stage. Never the question,
    # the SQL, the rows, or the model response.
    logger.info(
        "ask handled",
        extra={"request_id": request_id, "stage": result.stage.value, "event": "ask"},
    )

    return mapping.to_ask_response(result, request_id)


@router.get("/health", response_model=HealthResponse, tags=["ops"])
def health() -> HealthResponse:
    """Liveness: the process is running. No dependencies checked, no I/O."""
    return HealthResponse(status="alive")


@router.get("/ready", response_model=ReadyResponse, tags=["ops"])
def ready(request: Request, response: Response) -> ReadyResponse:
    """Readiness: can the service serve a request right now? (ADR-013)

    Live but inexpensive: a trivial SELECT 1 on the existing read-only warehouse
    connection. No metadata scan, no expensive query, and NEVER an LLM call.
    """
    assistant = getattr(request.app.state, "assistant", None)
    if assistant is None:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadyResponse(ready=False, detail="Assistant not initialized.")

    probe = getattr(request.app.state, "readiness_probe", None)
    if probe is None:
        # No probe wired (e.g. minimal test app): fall back to the startup flag.
        if not getattr(request.app.state, "warehouse_ok", False):
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return ReadyResponse(ready=False, detail="Warehouse not reachable.")
        return ReadyResponse(ready=True, detail="ok")

    if not probe():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadyResponse(ready=False, detail="Warehouse not reachable.")
    return ReadyResponse(ready=True, detail="ok")


@router.get("/version", response_model=VersionResponse, tags=["ops"])
def version() -> VersionResponse:
    """Application version and milestone, single-sourced from pyproject.toml."""
    return VersionResponse(app_version=get_app_version(), milestone=get_milestone())
