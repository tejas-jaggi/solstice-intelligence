"""Pure rendering components.

COMPONENT CONTRACT (binding):
  * Components ONLY render. Given contract data, they draw UI.
  * They NEVER perform HTTP.
  * They NEVER mutate session state.
  * They NEVER contain business logic.
  * They NEVER return business data (they return None; they draw).

This purity keeps all logic out of the presentation layer and makes each
component unit-testable in isolation.

Two correctness rules carried from the backend:
  * SQL is labeled "Executed" vs "Proposed (not run)" — a rejected query must
    never appear to have run (ADR-008).
  * The truncation notice READS metadata.truncated (backend truth) but COUNTS
    displayed rows (a presentation fact). The frontend never overrides backend
    truth; it may derive purely presentational facts (sharpened Rule 8).
"""
from __future__ import annotations

import streamlit as st

from frontend.models import (
    ApiError,
    ApiResult,
    ResultMetadata,
    ResultStatus,
    TransportErrorKind,
)

# Human-readable, trust-reinforcing headers per outcome.
_STATUS_HEADER = {
    ResultStatus.SUCCESS: ("✅ Answer", "success"),
    ResultStatus.VALIDATION_REJECTED: ("🛡️ Query not permitted", "warning"),
    ResultStatus.NO_QUERY: ("💬 No query produced", "info"),
    ResultStatus.EXECUTION_FAILED: ("⚠️ Query could not be completed", "error"),
    ResultStatus.API_ERROR: ("⚠️ Assistant unavailable", "error"),
}


def render_readiness(ready: bool) -> None:
    """Small, non-blocking backend-availability indicator."""
    if ready:
        st.caption("🟢 Backend ready")
    else:
        st.caption("🔴 Backend unavailable — the service may be starting or down.")


def render_version(app_version: str | None, milestone: str | None) -> None:
    """Show versioned-software identity from GET /version."""
    if app_version:
        label = f"Solstice Intelligence · v{app_version}"
        if milestone:
            label += f" · {milestone}"
        st.caption(label)


def render_result(result: ApiResult) -> None:
    """Render a full pipeline outcome (success or refusal) with transparency."""
    header, kind = _STATUS_HEADER.get(result.status, ("Result", "info"))
    st.subheader(header)

    # Explanation: the backend's template text, verbatim (never rewritten).
    if result.explanation:
        getattr(st, kind, st.info)(result.explanation)

    # Structured answer table (success only).
    if result.answer is not None:
        _render_answer(result.answer, result.metadata)

    # SQL transparency — labeled by whether it actually ran.
    if result.executed_sql:
        _render_sql(result.executed_sql, executed=(result.status is ResultStatus.SUCCESS))

    _render_metadata(result.metadata)


def _render_answer(answer, metadata: ResultMetadata) -> None:
    # Truncation notice: reads backend truth (truncated) + counts shown rows.
    if metadata.truncated:
        st.caption(f"Showing the first {len(answer.rows)} row(s); more exist.")
    st.dataframe(
        {col: [row[i] for row in answer.rows] for i, col in enumerate(answer.columns)},
        use_container_width=True,
    )


def _render_sql(sql: str, executed: bool) -> None:
    label = "Executed SQL" if executed else "Proposed SQL (not run)"
    st.markdown(f"**{label}**")
    st.code(sql, language="sql")


def _render_metadata(metadata: ResultMetadata) -> None:
    with st.expander("Details"):
        rows = {
            "Pipeline stage": metadata.stage,
            "Execution time (ms)": metadata.execution_time_ms,
            "Rows returned": metadata.row_count,
            "Truncated": metadata.truncated,
            "Validation passed": metadata.validation_passed,
            "Request ID": metadata.request_id,
        }
        for k, v in rows.items():
            if v is not None:
                st.text(f"{k}: {v}")


def render_transport_error(error: ApiError) -> None:
    """Render a transport failure — distinct from any pipeline outcome."""
    st.subheader("⚠️ Could not reach the assistant")
    friendly = {
        TransportErrorKind.NETWORK: "The analytics service could not be reached.",
        TransportErrorKind.TIMEOUT: "The request took too long. Please try again.",
        TransportErrorKind.BAD_RESPONSE: "The service returned an unexpected response.",
    }
    st.error(friendly.get(error.kind, error.message))
