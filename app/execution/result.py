"""Execution result model.

Structured, typed outcome of executing an approved query — consistent with the
Phase C validation model (typed status rather than a boolean, categorized
errors). Carries observability metadata (timing, row counts, truncation, the
exact executed SQL) for transparency and debugging.

The executor obeys; it does not validate, format, or generate.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ExecutionStatus(str, Enum):
    """Outcome category of an execution attempt."""

    SUCCESS = "success"
    NOT_APPROVED = "not_approved"  # caller passed a non-approval
    EXECUTION_ERROR = "execution_error"  # SQL errored at runtime
    CONNECTION_ERROR = "connection_error"  # warehouse could not be opened


@dataclass(frozen=True)
class ExecutionResult:
    """Result of executing an approved query.

    Attributes:
        status: Typed outcome.
        columns: Column names, in order (empty on failure).
        rows: Result rows as tuples (empty on failure or empty result set).
        rows_returned: Number of rows actually returned (after the cap).
        truncated: True if the independent row cap limited the result — the
            underlying query had more rows available. Kept honest so the
            response layer can say "showing first N" rather than hiding data.
        executed_sql: The exact SQL executed (after validation-layer rewriting).
        execution_time_ms: Wall-clock execution time in milliseconds.
        error_message: Human-readable error (None on success).
    """

    status: ExecutionStatus
    executed_sql: str | None = None
    columns: tuple[str, ...] = ()
    rows: tuple[tuple, ...] = ()
    rows_returned: int = 0
    truncated: bool = False
    execution_time_ms: float | None = None
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.status is ExecutionStatus.SUCCESS

    def render(self) -> str:
        if self.ok:
            trunc = " (truncated)" if self.truncated else ""
            return f"SUCCESS: {self.rows_returned} row(s){trunc} in {self.execution_time_ms:.1f} ms"
        return f"{self.status.value.upper()}: {self.error_message}"
