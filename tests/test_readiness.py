"""Deterministic tests for the live readiness probe (ADR-013) — no LLM, no network."""

from __future__ import annotations

from pathlib import Path

import duckdb

from app.api import readiness


def _make_warehouse(tmp_path: Path) -> Path:
    db = tmp_path / "w.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE t (a INTEGER)")
    con.close()
    return db


def test_reachable_for_real_warehouse(tmp_path):
    assert readiness.check_warehouse_reachable(_make_warehouse(tmp_path)) is True


def test_unreachable_when_missing(tmp_path):
    assert readiness.check_warehouse_reachable(tmp_path / "absent.duckdb") is False


def test_unreachable_for_corrupt_file(tmp_path):
    bad = tmp_path / "corrupt.duckdb"
    bad.write_bytes(b"not a duckdb file" * 8)
    assert readiness.check_warehouse_reachable(bad) is False
