"""Deterministic tests for scripts/verify_env.py — no network, no OpenAI call."""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

import scripts.verify_env as verify_env
from app.config import Settings


def _make_warehouse(tmp_path: Path) -> Path:
    db = tmp_path / "wh.duckdb"
    conn = duckdb.connect(str(db))
    conn.execute("CREATE TABLE t (a INTEGER)")
    conn.close()
    return db


def _make_corrupt_warehouse(tmp_path: Path) -> Path:
    db = tmp_path / "corrupt.duckdb"
    db.write_bytes(b"not a valid duckdb database file" * 16)
    return db


def _settings(warehouse: Path, **overrides) -> Settings:
    defaults = {
        "warehouse_path": warehouse,
        "openai_model": "gpt-4o",
        "max_rows": 1000,
        "default_limit": 100,
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def _ctx(settings: Settings | None = None, load_error: str = "") -> verify_env.Context:
    return verify_env.Context(settings=settings, load_error=load_error)


def test_required_python_matches_pyproject():
    assert verify_env._required_python() == (3, 14)


def test_python_check_reflects_running_interpreter():
    required = verify_env._required_python()
    expected = (sys.version_info.major, sys.version_info.minor) >= required
    assert verify_env.check_python(_ctx())[0].ok is expected


def test_env_presence_masks_and_reports(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-not-real")
    present = verify_env.check_env(_ctx())[0]
    assert present.ok and present.detail == "Present"

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    missing = verify_env.check_env(_ctx())[0]
    assert not missing.ok and missing.detail == "Missing"


def test_packages_check_reports_installed():
    # Core packages are installed in the dev environment.
    assert verify_env.check_packages(_ctx())[0].ok


def test_warehouse_and_read_only_pass_for_real_db(tmp_path):
    ctx = _ctx(_settings(_make_warehouse(tmp_path)))
    assert verify_env.check_warehouse(ctx)[0].ok
    assert verify_env.check_read_only(ctx)[0].ok


def test_warehouse_fails_when_missing(tmp_path):
    ctx = _ctx(_settings(tmp_path / "absent.duckdb"))
    assert not verify_env.check_warehouse(ctx)[0].ok
    assert not verify_env.check_read_only(ctx)[0].ok


def test_read_only_fails_gracefully_on_corrupt_db(tmp_path):
    # Distinct from a *missing* DB: the file exists but is not a valid warehouse.
    ctx = _ctx(_settings(_make_corrupt_warehouse(tmp_path)))
    assert verify_env.check_warehouse(ctx)[0].ok  # file is present
    result = verify_env.check_read_only(ctx)[0]  # ...but opening it fails, no raise
    assert not result.ok


def test_configuration_validation(tmp_path):
    wh = _make_warehouse(tmp_path)
    assert verify_env.check_configuration(_ctx(_settings(wh)))[0].ok
    bad = _ctx(_settings(wh, default_limit=5000, max_rows=1000))
    assert not verify_env.check_configuration(bad)[0].ok


def test_configuration_reports_load_error_when_settings_missing():
    result = verify_env.check_configuration(_ctx(None, "load_settings failed (OSError)"))[0]
    assert not result.ok and "load_settings failed" in result.detail


def test_check_registry_order():
    """Diagnostic registry preserves the intended startup order."""

    assert verify_env.CHECKS == (
        verify_env.check_python,
        verify_env.check_packages,
        verify_env.check_duckdb,
        verify_env.check_openai_sdk,
        verify_env.check_env,
        verify_env.check_warehouse,
        verify_env.check_read_only,
        verify_env.check_configuration,
    )


def test_is_ready_and_main(monkeypatch, capsys):
    ok = [verify_env.CheckResult("A", True, "x")]
    bad = [verify_env.CheckResult("A", False, "x")]
    assert verify_env.is_ready(ok)
    assert not verify_env.is_ready(bad)

    monkeypatch.setattr(verify_env, "run_checks", lambda: ok)
    assert verify_env.main() == 0
    monkeypatch.setattr(verify_env, "run_checks", lambda: bad)
    assert verify_env.main() == 1
    assert "Environment Check" in capsys.readouterr().out
