"""Deterministic API tests (Phase G).

Every test uses a FakeLLMClient-backed assistant injected via dependency
override, so no test touches the network or spends OpenAI credit. The real
lifespan (which builds real resources) is bypassed; we set app state directly
and override the DI provider.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_assistant
from app.api.routes import router
from app.config import Settings
from app.llm.client import FakeLLMClient
from app.llm.orchestrator import AnalyticsAssistant
from app.metadata.warehouse_metadata import build_warehouse_metadata
from app.warehouse.connection import open_readonly
from app.warehouse.schema import introspect
from tests.test_warehouse_metadata_real import REAL_DDL


def build_assistant(tmp_path: Path, **client_kwargs) -> AnalyticsAssistant:
    db = tmp_path / "w.duckdb"
    con = duckdb.connect(str(db))
    for ddl in REAL_DDL:
        con.execute(ddl)
    con.execute(
        "INSERT INTO Fact_Orders (order_key, customer_key, order_date_key, net_revenue) "
        "VALUES (1,100,20240101,250.00),(2,101,20240102,80.00)"
    )
    con.close()
    conn = open_readonly(db)
    try:
        schema = introspect(conn)
    finally:
        conn.close()
    metadata = build_warehouse_metadata()
    settings = Settings(warehouse_path=db, openai_model="m", max_rows=1000, default_limit=100)
    client = FakeLLMClient(**client_kwargs)
    return AnalyticsAssistant(schema, metadata, client, settings)


def make_app(assistant) -> FastAPI:
    """Build a test app WITHOUT the real lifespan; inject the fake assistant."""
    import uuid

    app = FastAPI()

    @app.middleware("http")
    async def add_request_id(request, call_next):
        request.state.request_id = str(uuid.uuid4())
        resp = await call_next(request)
        resp.headers["X-Request-ID"] = request.state.request_id
        return resp

    app.include_router(router)
    app.state.assistant = assistant
    app.state.warehouse_ok = True
    app.dependency_overrides[get_assistant] = lambda: assistant
    return app


@pytest.fixture()
def client_factory(tmp_path):
    def _make(**client_kwargs):
        return TestClient(make_app(build_assistant(tmp_path, **client_kwargs)))

    return _make


# ---------------------------------------------------------------- ask --------


def test_ask_success_returns_200_and_structured_answer(client_factory):
    c = client_factory(sql="SELECT customer_key, net_revenue FROM Fact_Orders")
    r = c.post("/v1/ask", json={"question": "show revenue"})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["status"] == "success"
    assert body["answer"]["columns"] == ["customer_key", "net_revenue"]
    assert len(body["answer"]["rows"]) == 2
    assert body["executed_sql"] is not None
    # implementation details must NOT leak into the contract
    assert "model_name" not in body["metadata"]
    assert "model" not in body["metadata"]
    assert body["metadata"]["request_id"]
    # correlation id echoed in header
    assert r.headers.get("X-Request-ID")


def test_validation_rejection_is_200_not_error(client_factory):
    c = client_factory(sql="DROP TABLE Fact_Orders")
    r = c.post("/v1/ask", json={"question": "delete everything"})
    assert r.status_code == 200  # a refusal is a successful response
    body = r.json()
    assert body["success"] is False
    assert body["status"] == "validation_rejected"
    assert body["answer"] is None
    assert body["metadata"]["validation_passed"] is False


def test_no_query_is_200(client_factory):
    c = client_factory(sql=None, message="I can't answer that.")
    r = c.post("/v1/ask", json={"question": "weather?"})
    assert r.status_code == 200
    assert r.json()["status"] == "no_query"


def test_malformed_request_is_422(client_factory):
    c = client_factory(sql="SELECT 1 FROM Fact_Orders")
    r = c.post("/v1/ask", json={})  # missing 'question'
    assert r.status_code == 422
    r2 = c.post("/v1/ask", json={"question": ""})  # empty
    assert r2.status_code == 422


# --------------------------------------------------------------- ops ---------


def test_health_is_liveness_only(client_factory):
    c = client_factory(sql="SELECT 1 FROM Fact_Orders")
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "alive"


def test_ready_true_when_warehouse_ok(client_factory):
    c = client_factory(sql="SELECT 1 FROM Fact_Orders")
    r = c.get("/ready")
    assert r.status_code == 200
    assert r.json()["ready"] is True


def test_ready_503_when_assistant_missing(tmp_path):
    # App with no assistant on state -> not ready.
    app = make_app(build_assistant(tmp_path, sql="SELECT 1"))
    app.state.assistant = None
    app.dependency_overrides = {}
    r = TestClient(app).get("/ready")
    assert r.status_code == 503
    assert r.json()["ready"] is False


def test_version_returns_app_and_milestone(client_factory):
    c = client_factory(sql="SELECT 1 FROM Fact_Orders")
    r = c.get("/version")
    assert r.status_code == 200
    body = r.json()
    assert body["app_version"] and body["milestone"]


# --------------------------------------------------- routing / schema --------


def test_unknown_route_is_404(client_factory):
    c = client_factory(sql="SELECT 1 FROM Fact_Orders")
    assert c.get("/does-not-exist").status_code == 404
    # unversioned ask must not exist
    assert c.post("/ask", json={"question": "x"}).status_code == 404


def test_openapi_schema_generates(client_factory):
    c = client_factory(sql="SELECT 1 FROM Fact_Orders")
    r = c.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    assert "/v1/ask" in schema["paths"]
    # examples we attached should be present
    assert "components" in schema
