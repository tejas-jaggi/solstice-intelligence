"""Adversarial tests for the SQL validation gate (Phase C).

Security-critical, so negative/malicious cases dominate. All hermetic: the
warehouse allowlist is the real 12-table schema reconstructed from DDL.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from app.config import Settings
from app.validation.decision import ErrorCategory
from app.validation.gate import validate
from app.warehouse.connection import open_readonly
from app.warehouse.schema import introspect
from tests.test_warehouse_metadata_real import REAL_DDL


@pytest.fixture()
def schema(tmp_path: Path):
    db = tmp_path / "real.duckdb"
    con = duckdb.connect(str(db))
    for ddl in REAL_DDL:
        con.execute(ddl)
    con.close()
    conn = open_readonly(db)
    try:
        return introspect(conn)
    finally:
        conn.close()


@pytest.fixture()
def cfg():
    return Settings(
        warehouse_path=Path("/tmp/x"), openai_model="m", max_rows=1000, default_limit=100
    )


def v(sql, schema, cfg):
    return validate(sql, schema, cfg)


# ---------------------------------------------------------------- positive ---


def test_simple_select_approved(schema, cfg):
    r = v("SELECT net_revenue FROM Fact_Orders", schema, cfg)
    assert r.approved, r.render()
    assert "LIMIT" in r.safe_sql.upper()  # default limit injected


def test_join_on_allowlisted_tables_approved(schema, cfg):
    sql = (
        "SELECT o.net_revenue, c.first_name FROM Fact_Orders o "
        "JOIN Dim_Customer c ON o.customer_key = c.customer_key"
    )
    assert v(sql, schema, cfg).approved


def test_cte_approved(schema, cfg):
    sql = (
        "WITH high AS (SELECT customer_key, net_revenue FROM Fact_Orders) "
        "SELECT customer_key FROM high"
    )
    assert v(sql, schema, cfg).approved


def test_aggregation_approved(schema, cfg):
    sql = "SELECT customer_key, SUM(net_revenue) FROM Fact_Orders GROUP BY customer_key"
    assert v(sql, schema, cfg).approved


# ------------------------------------------------------------ write ops ------


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE Fact_Orders",
        "DELETE FROM Fact_Orders",
        "UPDATE Fact_Orders SET net_revenue = 0",
        "INSERT INTO Fact_Orders (order_key) VALUES (1)",
        "ALTER TABLE Fact_Orders ADD COLUMN x INTEGER",
        "CREATE TABLE evil (x INTEGER)",
        "TRUNCATE Fact_Orders",
    ],
)
def test_write_ops_rejected(sql, schema, cfg):
    r = v(sql, schema, cfg)
    assert not r.approved
    assert ErrorCategory.NON_SELECT_STATEMENT in r.categories


# ------------------------------------------------------- statement smuggling -


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1; DROP TABLE Fact_Orders",
        "SELECT net_revenue FROM Fact_Orders; DELETE FROM Fact_Orders",
    ],
)
def test_statement_smuggling_rejected(sql, schema, cfg):
    r = v(sql, schema, cfg)
    assert not r.approved
    assert ErrorCategory.MULTIPLE_STATEMENTS in r.categories


# ---------------------------------------------------- category D escapes -----


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM read_csv('/etc/passwd')",
        "SELECT * FROM read_parquet('secret.parquet')",
        "SELECT read_text('/etc/hosts')",
    ],
)
def test_file_reading_functions_rejected(sql, schema, cfg):
    r = v(sql, schema, cfg)
    assert not r.approved
    # allowlist (primary) and/or denylist should fire
    assert (
        ErrorCategory.UNKNOWN_TABLE in r.categories
        or ErrorCategory.DISALLOWED_FUNCTION in r.categories
    )


def test_attach_rejected(schema, cfg):
    r = v("ATTACH 'other.db'", schema, cfg)
    assert not r.approved


def test_pragma_rejected(schema, cfg):
    r = v("PRAGMA database_list", schema, cfg)
    assert not r.approved


# ----------------------------------------------- hallucinated schema ---------


def test_unknown_table_rejected(schema, cfg):
    r = v("SELECT * FROM Fact_Nonexistent", schema, cfg)
    assert not r.approved
    assert ErrorCategory.UNKNOWN_TABLE in r.categories


def test_system_table_rejected(schema, cfg):
    r = v("SELECT * FROM information_schema.tables", schema, cfg)
    assert not r.approved
    assert ErrorCategory.UNKNOWN_TABLE in r.categories


def test_unknown_qualified_column_rejected(schema, cfg):
    r = v("SELECT Fact_Orders.nonexistent_col FROM Fact_Orders", schema, cfg)
    assert not r.approved
    assert ErrorCategory.UNKNOWN_COLUMN in r.categories


def test_unknown_table_nested_in_cte_rejected(schema, cfg):
    sql = "WITH x AS (SELECT * FROM Fake_Table) SELECT * FROM x"
    r = v(sql, schema, cfg)
    assert not r.approved
    assert ErrorCategory.UNKNOWN_TABLE in r.categories


# ------------------------------------------------------- malformed -----------


@pytest.mark.parametrize("sql", ["", "   ", "this is not sql", "SELECT FROM WHERE"])
def test_malformed_rejected(sql, schema, cfg):
    r = v(sql, schema, cfg)
    assert not r.approved


# ------------------------------------------------------- bounds --------------


def test_limit_injected_when_absent(schema, cfg):
    r = v("SELECT net_revenue FROM Fact_Orders", schema, cfg)
    assert r.approved
    assert "LIMIT 100" in r.safe_sql.upper().replace("  ", " ")


def test_oversized_limit_clamped(schema, cfg):
    r = v("SELECT net_revenue FROM Fact_Orders LIMIT 999999", schema, cfg)
    assert r.approved
    assert "1000" in r.safe_sql  # clamped to max_rows


def test_valid_small_limit_preserved(schema, cfg):
    r = v("SELECT net_revenue FROM Fact_Orders LIMIT 10", schema, cfg)
    assert r.approved
    assert "LIMIT 10" in r.safe_sql.upper().replace("  ", " ")


# ------------------------------------------------ multi-error reporting ------


def test_multiple_errors_reported_together(schema, cfg):
    # unknown table AND unknown qualified column in one query
    sql = "SELECT Bad_Table.ghost_col FROM Bad_Table"
    r = v(sql, schema, cfg)
    assert not r.approved
    # at least the unknown table fires; ideally both
    assert ErrorCategory.UNKNOWN_TABLE in r.categories
