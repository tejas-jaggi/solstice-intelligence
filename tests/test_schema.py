"""Independent tests for warehouse connection and schema introspection (Phase A).

These build a throwaway DuckDB fixture and verify the introspection layer
against it. They deliberately do NOT touch the real certified warehouse: the
assistant is a read-only consumer, and tests must never depend on or mutate
production data.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from app.warehouse import schema as S
from app.warehouse.connection import WarehouseUnavailableError, open_readonly


@pytest.fixture()
def fixture_db(tmp_path: Path) -> Path:
    """Create a small warehouse-shaped DuckDB file for testing."""
    db_path = tmp_path / "fixture.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute(
        "CREATE TABLE Dim_Customer (customer_key INTEGER, customer_name VARCHAR, segment VARCHAR)"
    )
    con.execute(
        "CREATE TABLE Fact_Orders "
        "(order_key INTEGER, customer_key INTEGER, order_date DATE, "
        "revenue DECIMAL(12,2))"
    )
    con.close()
    return db_path


def test_introspection_finds_all_tables(fixture_db: Path) -> None:
    conn = open_readonly(fixture_db)
    try:
        sch = S.introspect(conn)
    finally:
        conn.close()
    assert sch.table_names == frozenset({"dim_customer", "fact_orders"})


def test_column_membership_is_case_insensitive(fixture_db: Path) -> None:
    conn = open_readonly(fixture_db)
    try:
        sch = S.introspect(conn)
    finally:
        conn.close()
    assert sch.has_column("fact_orders", "REVENUE")
    assert sch.has_column("Fact_Orders", "revenue")
    assert not sch.has_column("fact_orders", "not_a_column")
    assert not sch.has_column("no_such_table", "revenue")


def test_prompt_text_lists_every_table(fixture_db: Path) -> None:
    conn = open_readonly(fixture_db)
    try:
        sch = S.introspect(conn)
    finally:
        conn.close()
    text = sch.to_prompt_text()
    assert "Dim_Customer(" in text
    assert "Fact_Orders(" in text
    assert "revenue" in text


def test_readonly_connection_blocks_writes(fixture_db: Path) -> None:
    conn = open_readonly(fixture_db)
    try:
        with pytest.raises(duckdb.Error):
            conn.execute("CREATE TABLE should_fail (x INTEGER)")
    finally:
        conn.close()


def test_missing_warehouse_fails_loudly(tmp_path: Path) -> None:
    missing = tmp_path / "nope.duckdb"
    with pytest.raises(WarehouseUnavailableError):
        open_readonly(missing)
