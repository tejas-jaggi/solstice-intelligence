"""FastAPI application factory.

Owns application lifecycle and cross-cutting concerns:
  * structured, metadata-only logging configured once, idempotently (ADR-013).
  * lifespan: construct the AnalyticsAssistant ONCE at startup (warehouse
    introspected once, client built once — no OpenAI call); drain in-flight
    requests and tear down cleanly on shutdown; emit structured lifecycle events.
  * fail-fast config validation at startup.
  * request-ID middleware: every request gets a correlation ID at the edge.
  * the Deployment Access Guard (ADR-012), constructed once on app.state.
  * a live readiness probe (ADR-013) on app.state.

Contains no business logic — that all lives in the frozen Milestone 1 backend.
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.api.access_guard import build_deployment_guard
from app.api.build_info import get_app_version
from app.api.logging_config import configure_logging
from app.api.readiness import check_warehouse_reachable
from app.api.routes import router
from app.config import load_settings
from app.llm.client import OpenAIClient
from app.llm.orchestrator import AnalyticsAssistant
from app.llm.tools import RUN_QUERY_TOOL
from app.metadata.warehouse_metadata import build_warehouse_metadata
from app.warehouse.connection import open_readonly
from app.warehouse.schema import introspect

logger = logging.getLogger("solstice.api")


class ConfigError(RuntimeError):
    """Raised at startup when mandatory configuration is missing/invalid."""


def _validate_config(settings) -> None:
    """Fail fast: verify mandatory configuration before serving any request."""
    problems: list[str] = []
    if not os.environ.get("OPENAI_API_KEY"):
        problems.append("OPENAI_API_KEY is not set")
    if not settings.openai_model:
        problems.append("OPENAI_MODEL is not set")
    if not settings.warehouse_path or not settings.warehouse_path.exists():
        problems.append(f"warehouse not found at {settings.warehouse_path}")
    if problems:
        raise ConfigError("Invalid configuration: " + "; ".join(problems))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Construct backend resources once at startup; drain + clean up at shutdown."""
    settings = load_settings()
    _validate_config(settings)  # fail-fast before we accept traffic

    conn = open_readonly(settings.warehouse_path)
    try:
        schema = introspect(conn)
    finally:
        conn.close()

    metadata = build_warehouse_metadata()
    client = OpenAIClient(model_name=settings.openai_model, tool_schema=RUN_QUERY_TOOL)
    assistant = AnalyticsAssistant(schema, metadata, client, settings)

    app.state.assistant = assistant
    app.state.warehouse_ok = True
    # Live readiness probe (ADR-013): bound to the configured warehouse path.
    app.state.readiness_probe = lambda: check_warehouse_reachable(settings.warehouse_path)

    # METADATA-ONLY startup diagnostics: table count only — no schema contents.
    logger.info(
        "startup complete",
        extra={"event": "startup", "stage": "ready"},
    )
    logger.info(
        "warehouse introspected",
        extra={"event": "startup_diagnostics"},
    )

    yield  # ---- application serves requests here ----

    # Graceful shutdown: uvicorn stops accepting new connections and lets in-flight
    # requests finish (bounded by the server's timeout-graceful-shutdown) before
    # this teardown runs.
    app.state.assistant = None
    app.state.readiness_probe = None
    logger.info("shutdown complete", extra={"event": "shutdown"})


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    configure_logging()  # deterministic + idempotent: one handler, however many calls

    app = FastAPI(
        title="Solstice Intelligence API",
        version=get_app_version(),
        summary="Governed natural-language analytics over a certified warehouse.",
        lifespan=lifespan,
    )

    # Deployment Access Guard (ADR-012): constructed once; a pass-through unless
    # enabled by environment.
    app.state.cost_guard = build_deployment_guard()

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        """Generate a correlation ID at the edge for EVERY request."""
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    app.include_router(router)
    return app


app = create_app()
