#!/usr/bin/env python
"""Developer utility: verify and print the live warehouse schema.

A thin orchestration script over the warehouse package. It contains no
introspection logic of its own — it wires together the existing, tested
components so a developer can confirm, at any time, that:

  * configuration resolves to the intended warehouse file,
  * the warehouse opens read-only, and
  * the introspected schema matches expectations.

The printed schema (via ``WarehouseSchema.to_prompt_text()``) is the
authoritative ground truth for the semantic layer, LLM schema grounding, and
the validation allowlist. This script is the sanctioned way to regenerate that
ground truth.

Exit codes:
    0  schema inspected and printed successfully
    2  warehouse could not be opened (missing file, permissions, corruption)
    3  connected, but introspection failed unexpectedly

Usage:
    python -m scripts.inspect_schema
    # or
    python scripts/inspect_schema.py
"""
from __future__ import annotations

import sys

from app.config import load_settings
from app.warehouse.connection import open_readonly, WarehouseUnavailableError
from app.warehouse.schema import introspect


# Exit codes are named so intent is explicit at the call sites below.
EXIT_OK = 0
EXIT_WAREHOUSE_UNAVAILABLE = 2
EXIT_INTROSPECTION_FAILED = 3

_RULE = "-" * 72


def _print_header(title: str) -> None:
    print(_RULE)
    print(title)
    print(_RULE)


def main() -> int:
    """Run the inspection and return a process exit code."""
    settings = load_settings()

    _print_header("Solstice Intelligence — Warehouse Schema Inspection")
    print(f"Warehouse path: {settings.warehouse_path}")

    # --- open the warehouse (read-only) --------------------------------------
    try:
        conn = open_readonly(settings.warehouse_path)
    except WarehouseUnavailableError as exc:
        # Expected, actionable failure: report cleanly, no traceback.
        print("Connection: FAILED")
        print(f"Reason: {exc}")
        return EXIT_WAREHOUSE_UNAVAILABLE

    print("Connection: OK (read-only)")

    # --- introspect ----------------------------------------------------------
    try:
        schema = introspect(conn)
    except Exception as exc:  # noqa: BLE001 - report any introspection failure clearly
        print("Introspection: FAILED")
        print(f"Reason: {type(exc).__name__}: {exc}")
        return EXIT_INTROSPECTION_FAILED
    finally:
        conn.close()

    # --- summary -------------------------------------------------------------
    table_count = len(schema.tables)
    column_count = sum(len(t.columns) for t in schema.tables)
    print(f"Tables discovered: {table_count}")
    print(f"Columns discovered: {column_count}")

    _print_header("Full schema (authoritative ground truth)")
    print(schema.to_prompt_text())

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
