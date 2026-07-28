"""Tests for the structural metadata layer (Phase B)."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from app.warehouse.connection import open_readonly
from app.warehouse.schema import introspect
from app.metadata.metadata import (
    UNRESOLVED, DimensionMetadata, FactMetadata, MetadataDriftError,
    Relationship, WarehouseMetadata,
)
from app.semantic.grounding import build_grounding_context


@pytest.fixture()
def schema(tmp_path: Path):
    db = tmp_path / "w.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE Dim_Customer (customer_key INTEGER, name VARCHAR)")
    con.execute("CREATE TABLE Dim_Date (date_key INTEGER, full_date DATE)")
    con.execute("CREATE TABLE Fact_Orders (order_key INTEGER, customer_key INTEGER, date_key INTEGER, net_revenue DECIMAL(12,2))")
    con.close()
    conn = open_readonly(db)
    try:
        return introspect(conn)
    finally:
        conn.close()


def _valid() -> WarehouseMetadata:
    return WarehouseMetadata(
        facts=(FactMetadata(
            table="Fact_Orders", grain="one row per order",
            business_event="A customer places an order.",
            primary_time_key="date_key", measures=("net_revenue",),
            relationships=(
                Relationship("Dim_Customer", "customer_key", "customer_key"),
                Relationship("Dim_Date", "date_key", "date_key"),
            )),),
        dimensions=(
            DimensionMetadata("Dim_Customer", "Customers", "customer_key"),
            DimensionMetadata("Dim_Date", "Calendar", "date_key"),
        ),
    )


def test_valid_metadata_is_shippable(schema):
    r = _valid().validate(schema)
    assert r.is_shippable and not r.has_errors and not r.has_unresolved
    assert set(r.tables_validated) == {"Fact_Orders", "Dim_Customer", "Dim_Date"}


def test_raise_if_invalid_passes_on_valid(schema):
    assert _valid().raise_if_invalid(schema).is_shippable


def test_unresolved_reported_not_shippable(schema):
    md = WarehouseMetadata(facts=(FactMetadata(
        table="Fact_Orders", grain="g", business_event="x",
        primary_time_key=UNRESOLVED, measures=("net_revenue",), relationships=()),))
    r = md.validate(schema)
    assert r.has_unresolved and not r.is_shippable
    with pytest.raises(MetadataDriftError):
        md.raise_if_invalid(schema)


def test_missing_column_is_error(schema):
    md = WarehouseMetadata(facts=(FactMetadata(
        table="Fact_Orders", grain="g", business_event="x",
        primary_time_key="date_key", measures=("nope",), relationships=()),))
    assert md.validate(schema).has_errors


def test_missing_table_is_error(schema):
    md = WarehouseMetadata(facts=(FactMetadata(
        table="Fact_Nope", grain="g", business_event="x",
        primary_time_key="date_key", measures=(), relationships=()),))
    r = md.validate(schema)
    assert "Fact_Nope" in r.missing_tables and r.has_errors


def test_bad_join_key_is_error(schema):
    md = WarehouseMetadata(
        facts=(FactMetadata(
            table="Fact_Orders", grain="g", business_event="x",
            primary_time_key="date_key", measures=("net_revenue",),
            relationships=(Relationship("Dim_Customer", "customer_key", "wrong"),)),),
        dimensions=(DimensionMetadata("Dim_Customer", "Customers", "customer_key"),))
    assert md.validate(schema).has_errors


def test_report_renders(schema):
    t = _valid().validate(schema).render()
    assert "Validation Report" in t and "shippable: True" in t


def test_grounding_order_and_no_sentinel_leak(schema):
    t = build_grounding_context(schema, _valid())
    assert t.index("PHYSICAL SCHEMA") < t.index("STRUCTURAL GUIDANCE")
    assert "net_revenue" in t and "one row per order" in t
    assert "<UNRESOLVED>" not in t
