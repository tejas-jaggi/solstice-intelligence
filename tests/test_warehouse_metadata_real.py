"""Guard test: the authored warehouse metadata must be shippable against a
schema that matches the certified warehouse's real column structure.

This reconstructs the real warehouse's DDL (structure only, no data) so the test
is hermetic and does not depend on the production database file, while still
validating the authored metadata against the *actual* column names. If a schema
change or a metadata edit breaks alignment, this test fails immediately.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from app.warehouse.connection import open_readonly
from app.warehouse.schema import introspect
from app.metadata.warehouse_metadata import build_warehouse_metadata


REAL_DDL = [
    "CREATE TABLE Dim_Campaign(campaign_key INTEGER, campaign_name VARCHAR, campaign_type VARCHAR, start_date DATE, end_date DATE, discount_depth VARCHAR, season VARCHAR, target_audience VARCHAR, is_active_flag BOOLEAN)",
    "CREATE TABLE Dim_Customer(customer_key INTEGER, customer_id VARCHAR, first_name VARCHAR, last_name VARCHAR, email VARCHAR, signup_date DATE, birth_year INTEGER, acquisition_channel_key INTEGER, home_geography_key INTEGER)",
    "CREATE TABLE Dim_Date(date_key INTEGER, full_date DATE, year INTEGER, quarter INTEGER, month INTEGER, month_name VARCHAR, week_of_year INTEGER, day_of_week INTEGER, day_name VARCHAR, is_weekend BOOLEAN, holiday_flag BOOLEAN, fiscal_quarter INTEGER, fiscal_year INTEGER, season VARCHAR, campaign_period_flag BOOLEAN)",
    "CREATE TABLE Dim_Geography(geography_key INTEGER, city VARCHAR, state VARCHAR, region VARCHAR, country VARCHAR, postal_code VARCHAR)",
    "CREATE TABLE Dim_Marketing_Channel(marketing_channel_key INTEGER, channel_name VARCHAR, channel_category VARCHAR)",
    "CREATE TABLE Dim_Product(product_key INTEGER, product_id VARCHAR, product_name VARCHAR, category VARCHAR, subcategory VARCHAR, gender VARCHAR, size VARCHAR, color VARCHAR, collection_season VARCHAR, list_price DECIMAL(10,2), unit_cost DECIMAL(10,2), is_active BOOLEAN)",
    "CREATE TABLE Dim_Return_Reason(return_reason_key INTEGER, reason_code VARCHAR, reason_description VARCHAR, is_controllable BOOLEAN)",
    "CREATE TABLE Dim_Sales_Channel(sales_channel_key INTEGER, channel_name VARCHAR, channel_type VARCHAR)",
    "CREATE TABLE Fact_Customer_Monthly_Snapshot(snapshot_key INTEGER, customer_key INTEGER, snapshot_month_date_key INTEGER, customer_age_days INTEGER, months_since_first_purchase INTEGER, recency_days INTEGER, orders_last_30_days INTEGER, orders_last_90_days INTEGER, cumulative_orders_to_date INTEGER, cumulative_net_revenue_to_date DECIMAL(14,2), rolling_12mo_net_revenue DECIMAL(14,2), is_active_flag BOOLEAN, is_repeat_customer_flag BOOLEAN, churn_risk_flag BOOLEAN)",
    "CREATE TABLE Fact_Order_Lines(order_line_key INTEGER, order_key INTEGER, customer_key INTEGER, product_key INTEGER, order_date_key INTEGER, quantity INTEGER, unit_price DECIMAL(10,2), gross_line_revenue DECIMAL(12,2), discount_amount DECIMAL(10,2), net_line_revenue DECIMAL(12,2), unit_cost DECIMAL(10,2))",
    "CREATE TABLE Fact_Orders(order_key INTEGER, order_id VARCHAR, customer_key INTEGER, order_date_key INTEGER, sales_channel_key INTEGER, geography_key INTEGER, campaign_key INTEGER, acquisition_channel_key INTEGER, gross_revenue DECIMAL(12,2), discount_amount DECIMAL(12,2), net_revenue DECIMAL(12,2), shipping_revenue DECIMAL(10,2), is_first_order BOOLEAN)",
    "CREATE TABLE Fact_Returns(return_key INTEGER, order_key INTEGER, order_line_key INTEGER, customer_key INTEGER, product_key INTEGER, return_date_key INTEGER, return_reason_key INTEGER, return_quantity INTEGER, return_amount DECIMAL(12,2), restocking_fee DECIMAL(10,2), refund_completed_flag BOOLEAN)",
]


@pytest.fixture()
def real_schema(tmp_path: Path):
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


def test_authored_metadata_is_shippable(real_schema):
    report = build_warehouse_metadata().validate(real_schema)
    assert report.is_shippable, report.render()


def test_all_twelve_tables_present(real_schema):
    assert len(real_schema.tables) == 12
