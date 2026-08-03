"""Build/version metadata for the public /version endpoint.

Single-sources application version and milestone from pyproject.toml — the sole
version definition in the repository (there is no runtime version module). Read
once and cached; degrades to "unknown" if the file is unavailable so the
endpoint never fails.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

# app/api/build_info.py -> api -> app -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"


@lru_cache(maxsize=1)
def _pyproject() -> dict[str, Any]:
    try:
        import tomllib

        return tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def get_app_version() -> str:
    """Application version, read from pyproject `[project].version`."""
    try:
        return str(_pyproject()["project"]["version"])
    except (KeyError, TypeError):
        return "unknown"


def get_milestone() -> str:
    """Repository milestone, read from pyproject `[tool.solstice].milestone`."""
    try:
        return str(_pyproject()["tool"]["solstice"]["milestone"])
    except (KeyError, TypeError):
        return "unknown"
