"""Deterministic tests for /version metadata sourcing (no network, no OpenAI)."""

from __future__ import annotations

import tomllib
from pathlib import Path

from app.api import build_info

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _pyproject() -> dict:
    return tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_version_matches_pyproject_and_is_known():
    version = build_info.get_app_version()
    assert version != "unknown"
    assert version == str(_pyproject()["project"]["version"])


def test_milestone_matches_pyproject_and_is_known():
    milestone = build_info.get_milestone()
    assert milestone != "unknown"
    assert milestone == str(_pyproject()["tool"]["solstice"]["milestone"])
