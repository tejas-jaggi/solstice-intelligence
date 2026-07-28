"""Authored structural metadata for the Customer Revenue Analytics warehouse.

Column names below are resolved against the certified warehouse schema
(12 tables, 110 columns) obtained via ``python -m scripts.inspect_schema``.
All content is STRUCTURAL: grain, business event, primary time key, measures
(named, not defined), and join topology with real keys. No business
definitions, formulas, or concept->SQL mappings appear here.

Grain distinctions captured deliberately:
  * Fact_Orders        -> order-header revenue (net_revenue, gross_revenue)
  * Fact_Order_Lines   -> product-line revenue (net_line_revenue) -- different grain
  * Fact_Returns       -> return-line detail
  * Fact_Customer_Monthly_Snapshot -> derived customer-month state (snapshot key)
"""
from __future__ import annotations

from app.metadata.metadata import (
    DimensionMetadata,
    FactMetadata,
    Relationship,
    WarehouseMetadata,
)


_DIMENSIONS: tuple[DimensionMetadata, ...] = (
    DimensionMetadata("Dim_Customer", "Customers and descriptive attributes", "customer_key"),
    DimensionMetadata("Dim_Product", "Products and their attributes", "product_key"),
    DimensionMetadata("Dim_Date", "Calendar date dimension for time-based analysis", "date_key"),
    DimensionMetadata("Dim_Geography", "Geographic markets", "geography_key"),
    DimensionMetadata("Dim_Marketing_Channel", "Marketing/acquisition channels", "marketing_channel_key"),
    DimensionMetadata("Dim_Sales_Channel", "Sales channels", "sales_channel_key"),
    DimensionMetadata("Dim_Campaign", "Marketing campaigns", "campaign_key"),
    DimensionMetadata("Dim_Return_Reason", "Reasons a product was returned", "return_reason_key"),
)


_FACTS: tuple[FactMetadata, ...] = (
    FactMetadata(
        table="Fact_Orders",
        grain="one row per order (order header)",
        business_event="A customer places an order; header-level revenue.",
        primary_time_key="order_date_key",
        measures=("gross_revenue", "net_revenue", "discount_amount", "shipping_revenue"),
        relationships=(
            Relationship("Dim_Customer", "customer_key", "customer_key"),
            Relationship("Dim_Date", "order_date_key", "date_key"),
            Relationship("Dim_Sales_Channel", "sales_channel_key", "sales_channel_key"),
            Relationship("Dim_Geography", "geography_key", "geography_key"),
            Relationship("Dim_Campaign", "campaign_key", "campaign_key"),
        ),
    ),
    FactMetadata(
        table="Fact_Order_Lines",
        grain="one row per product line within an order",
        business_event="A product line within an order; product-level revenue.",
        primary_time_key="order_date_key",
        measures=("quantity", "gross_line_revenue", "discount_amount", "net_line_revenue"),
        relationships=(
            Relationship("Dim_Product", "product_key", "product_key"),
            Relationship("Dim_Customer", "customer_key", "customer_key"),
            Relationship("Dim_Date", "order_date_key", "date_key"),
        ),
    ),
    FactMetadata(
        table="Fact_Returns",
        grain="one row per returned order line",
        business_event="A product return; return-level detail.",
        primary_time_key="return_date_key",
        measures=("return_quantity", "return_amount", "restocking_fee"),
        relationships=(
            Relationship("Dim_Return_Reason", "return_reason_key", "return_reason_key"),
            Relationship("Dim_Product", "product_key", "product_key"),
            Relationship("Dim_Customer", "customer_key", "customer_key"),
            Relationship("Dim_Date", "return_date_key", "date_key"),
        ),
    ),
    FactMetadata(
        table="Fact_Customer_Monthly_Snapshot",
        grain="one row per customer per month",
        business_event="Periodic snapshot of customer state by month (derived, no randomness).",
        primary_time_key="snapshot_month_date_key",
        measures=(
            "cumulative_net_revenue_to_date",
            "rolling_12mo_net_revenue",
            "orders_last_30_days",
            "orders_last_90_days",
        ),
        relationships=(
            Relationship("Dim_Customer", "customer_key", "customer_key"),
            Relationship("Dim_Date", "snapshot_month_date_key", "date_key"),
        ),
    ),
)


def build_warehouse_metadata() -> WarehouseMetadata:
    """Return the authored structural metadata for the warehouse."""
    return WarehouseMetadata(facts=_FACTS, dimensions=_DIMENSIONS)
