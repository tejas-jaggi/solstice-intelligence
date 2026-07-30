"""Hermetic tests for the execution engine (Phase D).

Unlike the gate tests, these need DATA, so the fixture inserts rows. Tests cover
success, empty results, SQL errors, the independent row-cap backstop (simulating
a gate LIMIT bug), non-approval refusal, and the read-only physical backstop
against a forged approval.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from app.config import Settings
from app.execution.executor import execute
from app.execution.result import ExecutionStatus
from app.validation.decision import ApprovedQuery


@pytest.fixture()
def warehouse(tmp_path: Path) -> Path:
    db = tmp_path / "w.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE Fact_Orders (order_key INTEGER, net_revenue DECIMAL(12,2))")
    con.executemany(
        "INSERT INTO Fact_Orders VALUES (?, ?)",
        [(i, i * 10.0) for i in range(1, 21)],  # 20 rows
    )
    con.close()
    return db


def cfg_for(db: Path, max_rows: int = 1000) -> Settings:
    return Settings(warehouse_path=db, openai_model="m", max_rows=max_rows, default_limit=100)


def test_successful_execution(warehouse):
    cfg = cfg_for(warehouse)
    r = execute(ApprovedQuery("SELECT order_key, net_revenue FROM Fact_Orders LIMIT 5"), cfg)
    assert r.ok
    assert r.status is ExecutionStatus.SUCCESS
    assert r.columns == ("order_key", "net_revenue")
    assert r.rows_returned == 5
    assert not r.truncated
    assert r.execution_time_ms is not None and r.execution_time_ms >= 0
    assert r.executed_sql is not None


def test_empty_result_set_is_success_not_error(warehouse):
    cfg = cfg_for(warehouse)
    r = execute(ApprovedQuery("SELECT order_key FROM Fact_Orders WHERE order_key = 9999"), cfg)
    assert r.ok
    assert r.rows_returned == 0
    assert r.rows == ()


def test_sql_error_returns_structured_error(warehouse):
    cfg = cfg_for(warehouse)
    # Column does not exist -> DuckDB errors at runtime; must be structured.
    r = execute(ApprovedQuery("SELECT nonexistent_column FROM Fact_Orders"), cfg)
    assert not r.ok
    assert r.status is ExecutionStatus.EXECUTION_ERROR
    assert r.error_message and "failed" in r.error_message.lower()


def test_row_cap_backstop_triggers_when_gate_limit_missing(warehouse):
    # Simulate a gate bug: approved SQL with NO limit, cap set below data size.
    cfg = cfg_for(warehouse, max_rows=5)
    r = execute(ApprovedQuery("SELECT order_key FROM Fact_Orders"), cfg)
    assert r.ok
    assert r.rows_returned == 5  # capped
    assert r.truncated is True  # honestly reported


def test_row_cap_not_triggered_when_under_cap(warehouse):
    cfg = cfg_for(warehouse, max_rows=100)
    r = execute(ApprovedQuery("SELECT order_key FROM Fact_Orders"), cfg)
    assert r.ok
    assert r.rows_returned == 20
    assert r.truncated is False


def test_none_approval_refused(warehouse):
    cfg = cfg_for(warehouse)
    r = execute(None, cfg)
    assert r.status is ExecutionStatus.NOT_APPROVED
    assert r.rows == ()


def test_empty_approval_refused(warehouse):
    cfg = cfg_for(warehouse)
    r = execute(ApprovedQuery(""), cfg)
    assert r.status is ExecutionStatus.NOT_APPROVED


def test_forged_write_approval_blocked_by_readonly(warehouse):
    # Even a hand-forged approval carrying a write cannot mutate: read-only conn.
    cfg = cfg_for(warehouse)
    r = execute(ApprovedQuery("CREATE TABLE evil (x INTEGER)"), cfg)
    assert not r.ok
    assert r.status is ExecutionStatus.EXECUTION_ERROR
    # confirm no table was created
    con = duckdb.connect(str(warehouse), read_only=True)
    tables = [
        t[0]
        for t in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
        ).fetchall()
    ]
    con.close()
    assert "evil" not in [t.lower() for t in tables]


def test_missing_warehouse_returns_connection_error(tmp_path):
    cfg = cfg_for(tmp_path / "does_not_exist.duckdb")
    r = execute(ApprovedQuery("SELECT 1"), cfg)
    assert r.status is ExecutionStatus.CONNECTION_ERROR
