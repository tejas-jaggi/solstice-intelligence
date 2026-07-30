"""Execution engine.

Single responsibility: execute an already-approved query against the read-only
warehouse and return a structured result. It does not validate, format, or
generate.

Layered safeguards (defense in depth), each catching a distinct failure mode:
    1. Type barrier   — accepts an ApprovedQuery, never a raw SQL string, so the
                        executor cannot be called without going through the gate.
    2. Approval check — refuses a missing/empty approval.
    3. Read-only conn — even a forged approval cannot mutate data (physical).
    4. Row-cap backstop — independent fetch cap; never assumes the gate injected
                        LIMIT correctly.
"""

from __future__ import annotations

import time

import duckdb

from app.config import Settings, load_settings
from app.execution.result import ExecutionResult, ExecutionStatus
from app.validation.decision import ApprovedQuery
from app.warehouse.connection import WarehouseUnavailableError, open_readonly


def execute(
    approved: ApprovedQuery | None,
    settings: Settings | None = None,
) -> ExecutionResult:
    """Execute an approved query and return a structured result.

    Args:
        approved: The gate's proof-of-approval. None or missing SQL is refused.
        settings: Optional settings override (warehouse path, row cap).

    Returns:
        An ExecutionResult with a typed status and observability metadata.
    """
    cfg = settings or load_settings()

    # 2. Approval check (the type barrier is enforced by the signature).
    if approved is None or not getattr(approved, "safe_sql", None):
        return ExecutionResult(
            status=ExecutionStatus.NOT_APPROVED,
            error_message="No approved query supplied; refusing to execute.",
        )

    sql = approved.safe_sql

    # 3. Open read-only connection (physical write backstop).
    try:
        conn = open_readonly(cfg.warehouse_path)
    except WarehouseUnavailableError as exc:
        return ExecutionResult(
            status=ExecutionStatus.CONNECTION_ERROR,
            executed_sql=sql,
            error_message=str(exc),
        )

    start = time.perf_counter()
    try:
        cursor = conn.execute(sql)
        columns = tuple(d[0] for d in (cursor.description or []))
        # 4. Row-cap backstop: fetch at most max_rows + 1 to detect truncation
        #    without materializing an unbounded result set.
        fetched = cursor.fetchmany(cfg.max_rows + 1)
        truncated = len(fetched) > cfg.max_rows
        rows = tuple(tuple(r) for r in fetched[: cfg.max_rows])
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            executed_sql=sql,
            columns=columns,
            rows=rows,
            rows_returned=len(rows),
            truncated=truncated,
            execution_time_ms=elapsed_ms,
        )
    except duckdb.Error as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        # Structured error; never propagate a raw DuckDB traceback to the user.
        return ExecutionResult(
            status=ExecutionStatus.EXECUTION_ERROR,
            executed_sql=sql,
            execution_time_ms=elapsed_ms,
            error_message=f"Query execution failed: {exc}",
        )
    finally:
        # Resource cleanup always, even on error.
        conn.close()
