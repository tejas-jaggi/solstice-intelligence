"""Deterministic tests for scripts/check_version.py — no network, no runtime imports."""

from __future__ import annotations

import tomllib
from pathlib import Path

import scripts.check_version as cv

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _pyproject_version() -> str:
    data = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def test_normalize_ref_forms():
    assert cv.normalize_ref("refs/tags/v1.2.4") == "v1.2.4"
    assert cv.normalize_ref("v1.2.4") == "v1.2.4"
    assert cv.normalize_ref("  v1.2.4  ") == "v1.2.4"
    assert cv.normalize_ref("") is None
    assert cv.normalize_ref(None) is None


def test_parse_tag_version_valid_and_invalid():
    assert cv.parse_tag_version("v1.2.4")[0] == "1.2.4"
    assert cv.parse_tag_version("1.2.4")[0] is None      # missing 'v'
    assert cv.parse_tag_version("v1.2")[0] is None        # not X.Y.Z
    assert cv.parse_tag_version("vabc")[0] is None
    assert cv.parse_tag_version(None)[0] is None


def test_read_pyproject_version_matches_file():
    assert cv.read_pyproject_version() == _pyproject_version()


def test_matching_tag_is_consistent():
    ref = f"refs/tags/v{_pyproject_version()}"
    outcomes = cv.run_checks(ref)
    assert cv.is_consistent(outcomes)


def test_mismatched_tag_is_inconsistent():
    outcomes = cv.run_checks("v0.0.1")  # will not match the real pyproject version
    assert not cv.is_consistent(outcomes)
    labels = {o.label: o.ok for o in outcomes}
    assert labels["Tag <-> pyproject"] is False


def test_malformed_tag_is_inconsistent():
    outcomes = cv.run_checks("release-1.2.4")
    assert not cv.is_consistent(outcomes)
    assert any(o.label == "Release tag format" and not o.ok for o in outcomes)


def test_missing_tag_is_inconsistent():
    outcomes = cv.run_checks(None)
    assert not cv.is_consistent(outcomes)


def test_main_exit_codes(capsys):
    assert cv.main([f"v{_pyproject_version()}"]) == 0
    assert cv.main(["v0.0.1"]) == 1
    assert "Version Consistency Check" in capsys.readouterr().out
