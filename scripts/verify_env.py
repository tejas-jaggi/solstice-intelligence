"""Repository environment diagnostic for Solstice Intelligence.

Run after cloning to confirm the local environment is correctly set up *before*
starting the API or running the tests:

    python scripts/verify_env.py      # or: just verify

This module intentionally lives outside the application runtime.

It is a developer diagnostic tool rather than part of the production
request pipeline. Keeping it separate prevents development-only checks
from coupling to runtime code while still allowing reuse of the
repository's configuration loading and warehouse access logic.

Safety properties (by design):
  * Performs NO network operations.
  * NEVER constructs an OpenAI client and spends no API credit.
  * Touches the warehouse only with a single trivial, read-only query.
  * Is safe to run repeatedly — it mutates nothing.

It is a developer/local tool, not a CI gate: CI has neither a warehouse nor an
API key and deliberately does not run it. Exit code is 0 when the environment is
READY and 1 otherwise, so it is usable in shell pipelines and as a `just` recipe.
"""

from __future__ import annotations

import importlib.metadata
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings

# scripts/verify_env.py -> scripts -> repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"

# Allow `python scripts/verify_env.py` from anywhere: ensure the repo root is
# importable so `app.*` resolves the same way it does when the app runs.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Core runtime packages the app must import to start. The pinned requirements
# files are the full source of truth; this is a fast "can the app import its
# core dependencies?" smoke check.
REQUIRED_PACKAGES = (
    "fastapi",
    "duckdb",
    "openai",
    "sqlglot",
    "pydantic",
    "streamlit",
    "httpx",
    "uvicorn",
)

# Presence-only. Values are NEVER read or printed.
REQUIRED_ENV_VARS = ("OPENAI_API_KEY",)

_LABEL_WIDTH = 22


@dataclass(frozen=True)
class CheckResult:
    label: str
    ok: bool
    detail: str
    required: bool = True


@dataclass(frozen=True)
class Context:
    """Shared state passed to every check. Settings are loaded exactly once."""

    settings: Settings | None
    load_error: str


# --- single metadata source -------------------------------------------------


def _dist_version(dist: str) -> str | None:
    """The one place package presence/version is inspected."""
    try:
        return importlib.metadata.version(dist)
    except importlib.metadata.PackageNotFoundError:
        return None


def _required_python() -> tuple[int, int] | None:
    """Minimum Python (major, minor) parsed from pyproject requires-python."""
    try:
        import tomllib

        data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        spec = str(data["project"]["requires-python"])
    except (OSError, KeyError, ValueError):
        return None
    tokens = "".join(c if (c.isdigit() or c == ".") else " " for c in spec).split()
    for token in tokens:
        parts = token.split(".")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            return int(parts[0]), int(parts[1])
    return None


def _load_settings() -> tuple[Settings | None, str]:
    try:
        from app.config import load_settings
    except ImportError as exc:
        return None, f"cannot import app.config ({exc.__class__.__name__})"
    try:
        return load_settings(), ""
    except (ValueError, OSError) as exc:
        return None, f"load_settings failed ({exc.__class__.__name__})"


# --- checks (each takes the shared Context, returns one or more results) -----


def check_python(ctx: Context) -> list[CheckResult]:
    v = sys.version_info
    current = f"{v.major}.{v.minor}.{v.micro}"
    required = _required_python()
    if required is None:
        return [CheckResult("Python", True, f"{current} (requirement unknown)")]
    ok = (v.major, v.minor) >= required
    detail = current if ok else f"{current} (requires >= {required[0]}.{required[1]})"
    return [CheckResult("Python", ok, detail)]


def check_packages(ctx: Context) -> list[CheckResult]:
    missing = [p for p in REQUIRED_PACKAGES if _dist_version(p) is None]
    ok = not missing
    return [CheckResult("Packages", ok, "Installed" if ok else f"missing: {', '.join(missing)}")]


def check_duckdb(ctx: Context) -> list[CheckResult]:
    version = _dist_version("duckdb")
    return [CheckResult("DuckDB", version is not None, version or "not installed")]


def check_openai_sdk(ctx: Context) -> list[CheckResult]:
    version = _dist_version("openai")
    return [CheckResult("OpenAI SDK", version is not None, version or "not installed")]


def check_env(ctx: Context) -> list[CheckResult]:
    results: list[CheckResult] = []
    for var in REQUIRED_ENV_VARS:
        present = bool(os.environ.get(var, "").strip())
        results.append(CheckResult(var, present, "Present" if present else "Missing"))
    return results


def check_warehouse(ctx: Context) -> list[CheckResult]:
    if ctx.settings is None:
        return [CheckResult("Warehouse", False, "configuration unavailable")]
    path = ctx.settings.warehouse_path
    ok = path.is_file()
    return [CheckResult("Warehouse", ok, "Found" if ok else f"not found: {path}")]


def check_read_only(ctx: Context) -> list[CheckResult]:
    if ctx.settings is None:
        return [CheckResult("Read-only", False, "configuration unavailable")]
    path = ctx.settings.warehouse_path
    if not path.is_file():
        return [CheckResult("Read-only", False, "warehouse not found")]
    try:
        import duckdb
    except ImportError:
        return [CheckResult("Read-only", False, "duckdb not installed")]
    try:
        conn = duckdb.connect(str(path), read_only=True)
        try:
            conn.execute("SELECT 1")
        finally:
            conn.close()
    except (duckdb.Error, OSError) as exc:
        return [CheckResult("Read-only", False, f"open failed ({exc.__class__.__name__})")]
    return [CheckResult("Read-only", True, "Verified (read-only open)")]


def check_configuration(ctx: Context) -> list[CheckResult]:
    if ctx.settings is None:
        return [CheckResult("Configuration", False, ctx.load_error or "unavailable")]
    s = ctx.settings
    problems: list[str] = []
    if s.max_rows <= 0:
        problems.append("MAX_ROWS must be > 0")
    if s.default_limit <= 0:
        problems.append("DEFAULT_LIMIT must be > 0")
    if s.default_limit > s.max_rows:
        problems.append("DEFAULT_LIMIT must be <= MAX_ROWS")
    if not s.openai_model.strip():
        problems.append("OPENAI_MODEL must be set")
    ok = not problems
    return [CheckResult("Configuration", ok, "Valid" if ok else "; ".join(problems))]


# Ordered diagnostic registry.
#
# The sequence intentionally mirrors the developer startup workflow:
#
#   1. Python runtime
#   2. Required package imports
#   3. Core dependency versions
#   4. Environment variables
#   5. Warehouse availability
#   6. Read-only connectivity
#   7. Configuration validation
#
# run_checks() iterates this registry directly, so adding a new diagnostic
# requires only implementing a new check function and registering it here.
CHECKS: tuple[Callable[[Context], list[CheckResult]], ...] = (
    check_python,
    check_packages,
    check_duckdb,
    check_openai_sdk,
    check_env,
    check_warehouse,
    check_read_only,
    check_configuration,
)


# --- orchestration & rendering ----------------------------------------------


def _build_context() -> Context:
    settings, load_error = _load_settings()
    return Context(settings=settings, load_error=load_error)


def run_checks() -> list[CheckResult]:
    ctx = _build_context()
    results: list[CheckResult] = []
    for check in CHECKS:
        results.extend(check(ctx))
    return results


def is_ready(results: list[CheckResult]) -> bool:
    return all(r.ok for r in results if r.required)


def render_check(result: CheckResult) -> str:
    mark = "\u2713" if result.ok else "\u2717"  # ✓ / ✗
    dotted = (result.label + " ").ljust(_LABEL_WIDTH, ".")
    return f"{dotted} {mark} {result.detail}"


def render(results: list[CheckResult]) -> str:
    lines = ["Solstice Intelligence Environment Check", ""]
    lines.extend(render_check(r) for r in results)
    lines.append("")
    status = "READY" if is_ready(results) else "NOT READY"
    lines.append(("Overall Status ").ljust(_LABEL_WIDTH, ".") + f" {status}")
    return "\n".join(lines)


def _print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:  # legacy Windows consoles
        print(text.encode("ascii", "replace").decode("ascii"))


def main() -> int:
    results = run_checks()
    _print(render(results))
    return 0 if is_ready(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
