"""FastAPI application factory.

Owns application lifecycle and cross-cutting concerns:
  * lifespan: construct the AnalyticsAssistant ONCE at startup (warehouse
    introspected once, client built once — no OpenAI call), tear down cleanly.
  * fail-fast config validation at startup.
  * request-ID middleware: every request gets a correlation ID at the edge.
  * the Deployment Access Guard (ADR-012), constructed once and stored on
    app.state for the /v1/ask route dependency.

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
    """Construct backend resources once at startup; clean up at shutdown."""
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
    logger.info("startup complete", extra={"tables": len(schema.tables)})

    yield  # ---- application serves requests here ----

    app.state.assistant = None
    logger.info("shutdown complete")


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    app = FastAPI(
        title="Solstice Intelligence API",
        version=get_app_version(),
        summary="Governed natural-language analytics over a certified warehouse.",
        lifespan=lifespan,
    )

    # Deployment Access Guard (ADR-012): constructed once; a pass-through unless
    # enabled by environment. Stored on app.state for the /v1/ask dependency.
    app.state.cost_guard = build_deployment_guard()

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        """Generate a correlation ID at the edge for EVERY request.

        Placed in middleware (not a route) so requests that fail before reaching
        a handler (e.g. 422 validation errors) still get a traceable ID.
        """
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    app.include_router(router)
    return app


app = create_app()
