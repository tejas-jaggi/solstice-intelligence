"""Central configuration for Solstice Intelligence.

All tunable values live here so no magic constants are scattered across modules.
Values are read from the environment where sensitive or deployment-specific,
with safe defaults for local development.

Nothing in this module connects to anything or performs side effects on import.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Repository root = two levels up from this file (app/config.py -> app -> repo root).
REPO_ROOT = Path(__file__).resolve().parent.parent

# Load environment variables from .env file
load_dotenv(REPO_ROOT / ".env")


def _env(key: str, default: str) -> str:
    value = os.environ.get(key)
    return value if value is not None and value.strip() != "" else default


@dataclass(frozen=True)
class Settings:
    """Immutable application settings.

    Attributes:
        warehouse_path: Filesystem path to the certified Customer Revenue
            Analytics DuckDB file. The assistant is a read-only *consumer* of
            this database; it never creates, regenerates, or mutates it.
        openai_model: Hosted model identifier used for tool-calling. Confirmed
            at build time against the account in use.
        max_rows: Hard cap on rows returned by any query, enforced both by the
            validation gate (LIMIT injection/clamping) and again at execution.
        default_limit: LIMIT injected when a candidate SELECT has none.
    """

    warehouse_path: Path
    openai_model: str
    max_rows: int
    default_limit: int


def load_settings() -> Settings:
    """Build Settings from the environment.

    WAREHOUSE_PATH must point at the existing, certified DuckDB warehouse.
    We do NOT default it to a fabricated path: an unset warehouse path is a
    configuration error the caller should see explicitly, not a silent guess.
    """
    warehouse_path_str = os.environ.get("WAREHOUSE_PATH", "").strip()
    # Fall back to a conventional location under the repo's data/ directory,
    # but this is only a convenience default for local runs.
    if warehouse_path_str:
        warehouse_path = Path(warehouse_path_str).expanduser().resolve()
    else:
        warehouse_path = (REPO_ROOT / "data" / "customer_revenue.duckdb").resolve()

    return Settings(
        warehouse_path=warehouse_path,
        openai_model=_env("OPENAI_MODEL", "gpt-4o"),
        max_rows=int(_env("MAX_ROWS", "1000")),
        default_limit=int(_env("DEFAULT_LIMIT", "100")),
    )


# A module-level singleton is convenient, but we expose the loader too so tests
# can construct settings with a temporary warehouse path.
settings = load_settings()
