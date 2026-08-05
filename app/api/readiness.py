"""Live readiness probe for /ready (ADR-013).

A minimal, inexpensive local health check: open the warehouse read-only and run a
trivial SELECT 1. No metadata scan, no expensive query, no LLM call — safe to poll
under a health-probe cadence. Returns True/False; never raises.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("solstice.api")


def check_warehouse_reachable(warehouse_path: Path) -> bool:
    """Return True iff the warehouse opens read-only and answers SELECT 1."""
    try:
        import duckdb
    except ImportError:
        return False
    try:
        conn = duckdb.connect(str(warehouse_path), read_only=True)
        try:
            conn.execute("SELECT 1")
        finally:
            conn.close()
    except (duckdb.Error, OSError):
        # METADATA-ONLY: log the event, never the path contents or error payload.
        logger.warning("readiness probe failed", extra={"event": "readiness_failed"})
        return False
    return True
