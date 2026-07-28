"""The user-facing presentation contract.

AssistantResponse is the stable, UI-agnostic object that future FastAPI and
Streamlit layers consume. FastAPI serializes it (to_dict); Streamlit reads its
fields directly. Producing a typed object rather than a formatted string means
both consumers share one contract without re-parsing.

This module defines the contract only. The pure transformation that builds it
from an OrchestrationResult lives in formatter.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ResponseStatus(str, Enum):
    """Presentation status, one per pipeline outcome."""

    SUCCESS = "success"
    NO_QUERY = "no_query"
    VALIDATION_REJECTED = "validation_rejected"
    EXECUTION_FAILED = "execution_failed"
    API_ERROR = "api_error"


class ResponseSeverity(str, Enum):
    """Lightweight severity so UIs present outcomes consistently without
    embedding presentation logic of their own."""

    INFO = "info"        # a normal answer, or a benign "no query" outcome
    WARNING = "warning"  # the user should adjust (e.g. rejected query)
    ERROR = "error"      # something failed (execution or API)


@dataclass(frozen=True)
class AssistantResponse:
    """The structured, UI-agnostic presentation of one assistant outcome.

    Attributes:
        success: True only for a completed answer.
        status: Typed presentation status.
        severity: INFO / WARNING / ERROR for consistent UI treatment.
        headline: Short status label.
        explanation: Deterministic, template-based plain-English description of
            what happened (never an LLM narration, never a data interpretation).
        executed_sql: The SQL that ran (success/execution-failure), or None.
        proposed_sql: The model's proposed SQL when it was rejected before
            running — labeled separately so it is never confused with executed.
        columns: Result column names (empty unless success).
        rows: Result rows (empty unless success).
        metadata: Observability fields (stage, model, timing, etc.) for logs and
            debugging; not necessarily displayed to the user.
    """

    success: bool
    status: ResponseStatus
    severity: ResponseSeverity
    headline: str
    explanation: str
    executed_sql: str | None = None
    proposed_sql: str | None = None
    columns: tuple[str, ...] = ()
    rows: tuple[tuple, ...] = ()
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to a plain dict (for FastAPI JSON and logging).

        Rows are converted to lists and cell values to strings so the payload is
        trivially JSON-serializable regardless of underlying DB types (e.g.
        Decimal, date).
        """
        return {
            "success": self.success,
            "status": self.status.value,
            "severity": self.severity.value,
            "headline": self.headline,
            "explanation": self.explanation,
            "executed_sql": self.executed_sql,
            "proposed_sql": self.proposed_sql,
            "columns": list(self.columns),
            "rows": [[_cell(v) for v in row] for row in self.rows],
            "metadata": self.metadata,
        }


def _cell(value) -> str | None:
    """JSON-safe cell rendering: None stays None, everything else stringified."""
    if value is None:
        return None
    return str(value)
