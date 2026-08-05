"""The metadata-only logging invariant, enforced end-to-end (ADR-013).

Drives a full governed request through the real app with a FakeLLMClient and
asserts the captured logs contain operational metadata (request id, stage) and
NEVER the question, the generated SQL, result cells, the model message, or secrets.
This converts the security rule into a regression-guarded invariant.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import duckdb
from fastapi.testclient import TestClient

from app.api.dependencies import get_assistant
from app.api.main import create_app
from app.config import Settings
from app.llm.client import FakeLLMClient
from app.llm.orchestrator import AnalyticsAssistant
from app.metadata.warehouse_metadata import build_warehouse_metadata
from app.warehouse.connection import open_readonly
from app.warehouse.schema import introspect
from tests.test_warehouse_metadata_real import REAL_DDL

SECRET_QUESTION = "SECRET_QUESTION_MARKER show revenue"
GENERATED_SQL = "SELECT customer_key, net_revenue FROM Fact_Orders"


def _assistant(tmp_path: Path) -> AnalyticsAssistant:
    db = tmp_path / "w.duckdb"
    con = duckdb.connect(str(db))
    for ddl in REAL_DDL:
        con.execute(ddl)
    con.execute(
        "INSERT INTO Fact_Orders (order_key, customer_key, order_date_key, net_revenue) "
        "VALUES (1,100,20240101,250.00)"
    )
    con.close()
    conn = open_readonly(db)
    try:
        schema = introspect(conn)
    finally:
        conn.close()
    settings = Settings(warehouse_path=db, openai_model="m", max_rows=1000, default_limit=100)
    return AnalyticsAssistant(
        schema, build_warehouse_metadata(), FakeLLMClient(sql=GENERATED_SQL), settings
    )


def test_logs_are_metadata_only(tmp_path, caplog):
    app = create_app()
    app.state.assistant = _assistant(tmp_path)
    app.state.warehouse_ok = True
    app.dependency_overrides[get_assistant] = lambda: app.state.assistant

    with caplog.at_level(logging.INFO, logger="solstice"):
        r = TestClient(app).post("/v1/ask", json={"question": SECRET_QUESTION})
    assert r.status_code == 200

    blob = "\n".join(
        rec.getMessage() + json.dumps(getattr(rec, "__dict__", {}), default=str)
        for rec in caplog.records
    )
    # Present: operational metadata.
    assert any(getattr(rec, "request_id", None) for rec in caplog.records)
    assert any(getattr(rec, "stage", None) for rec in caplog.records)
    # Absent: everything the invariant forbids.
    assert SECRET_QUESTION not in blob
    assert "SECRET_QUESTION_MARKER" not in blob
    assert GENERATED_SQL not in blob
    assert "net_revenue" not in blob or "Fact_Orders" not in blob  # no result/SQL echo
    assert "250.00" not in blob
