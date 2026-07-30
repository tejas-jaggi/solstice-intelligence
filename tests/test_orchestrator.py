"""Deterministic orchestration tests (Phase E).

Uses FakeLLMClient (no network) but the REAL gate and executor, so the full
pipeline is exercised. Warehouse fixture has data so execution returns rows.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from app.config import Settings
from app.llm.client import FakeLLMClient
from app.llm.orchestrator import AnalyticsAssistant
from app.llm.prompts import build_system_prompt
from app.llm.result import PipelineStage
from app.metadata.warehouse_metadata import build_warehouse_metadata
from app.warehouse.connection import open_readonly
from app.warehouse.schema import introspect
from tests.test_warehouse_metadata_real import REAL_DDL


@pytest.fixture()
def env(tmp_path: Path):
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
    return schema, metadata, settings


def assistant(env, **client_kwargs):
    schema, metadata, settings = env
    client = FakeLLMClient(**client_kwargs)
    return AnalyticsAssistant(schema, metadata, client, settings)


# ---------------------------------------------------------- prompt -----------


def test_system_prompt_contains_schema_and_guidance(env):
    schema, metadata, _ = env
    prompt = build_system_prompt(schema, metadata)
    assert "PHYSICAL SCHEMA" in prompt
    assert "STRUCTURAL GUIDANCE" in prompt
    assert "Fact_Orders" in prompt
    assert "run_query" in prompt  # rules mention the tool
    assert "<UNRESOLVED>" not in prompt


# ---------------------------------------------------------- happy path -------


def test_completed_pipeline(env):
    a = assistant(env, sql="SELECT customer_key, net_revenue FROM Fact_Orders")
    r = a.ask("show revenue by customer")
    assert r.stage is PipelineStage.COMPLETED
    assert r.ok
    assert r.execution.rows_returned == 2
    assert r.candidate_sql is not None
    assert r.total_time_ms is not None
    assert r.model_name == "fake-model"


# ---------------------------------------------------- no query proposed ------


def test_no_tool_call_is_handled(env):
    a = assistant(env, sql=None, message="I can't answer that from this warehouse.")
    r = a.ask("what's the weather?")
    assert r.stage is PipelineStage.NO_QUERY_PROPOSED
    assert r.model_message and "can't" in r.model_message.lower()
    assert not r.ok


# --------------------------------------------------- validation rejected -----


def test_unsafe_sql_rejected_by_gate(env):
    a = assistant(env, sql="DROP TABLE Fact_Orders")
    r = a.ask("delete everything")
    assert r.stage is PipelineStage.VALIDATION_REJECTED
    assert r.validation is not None and not r.validation.approved
    assert r.execution is None  # executor never reached


def test_hallucinated_table_rejected(env):
    a = assistant(env, sql="SELECT * FROM Made_Up_Table")
    r = a.ask("query a fake table")
    assert r.stage is PipelineStage.VALIDATION_REJECTED


# --------------------------------------------------- execution failed --------


def test_execution_failure_surfaced(env):
    # Passes the gate structurally (real table) but errors at runtime (bad column
    # that is unqualified, so the conservative column check does not catch it).
    a = assistant(env, sql="SELECT SUM(not_a_real_col) FROM Fact_Orders")
    r = a.ask("sum a bad column")
    # Either validation catches it (if qualified) or execution does; here it is
    # unqualified so it reaches execution.
    assert r.stage in (PipelineStage.EXECUTION_FAILED, PipelineStage.VALIDATION_REJECTED)
    if r.stage is PipelineStage.EXECUTION_FAILED:
        assert r.validation.approved
        assert not r.execution.ok


# --------------------------------------------------- API error ---------------


def test_api_error_is_typed(env):
    a = assistant(env, raise_error=True)
    r = a.ask("anything")
    assert r.stage is PipelineStage.API_ERROR
    assert r.error_message
    assert r.validation is None and r.execution is None


# --------------------------------------------------- malformed args ----------


def test_empty_sql_treated_as_no_query(env):
    a = assistant(env, sql="")
    r = a.ask("empty")
    assert r.stage is PipelineStage.NO_QUERY_PROPOSED
