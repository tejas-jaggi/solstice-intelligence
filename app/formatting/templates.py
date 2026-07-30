"""Centralized user-facing wording for the response layer.

All copy the user might read lives here, not scattered through formatter.py.
This keeps the formatter pure logic, makes wording changes a single-file edit,
and gives a future localization pass one place to work.

Explanations are deterministic templates — never LLM-generated. The warehouse
(and the executed SQL shown alongside) is the source of truth; the explanation
describes what the SYSTEM did, never an interpretation of what the data MEANS.
"""

from __future__ import annotations

# Headlines: short status labels for each outcome.
HEADLINE_COMPLETED = "Answer"
HEADLINE_NO_QUERY = "No query produced"
HEADLINE_VALIDATION_REJECTED = "Query not permitted"
HEADLINE_EXECUTION_FAILED = "Query could not be completed"
HEADLINE_API_ERROR = "Assistant temporarily unavailable"

# Explanation templates. Callables take the minimal facts they need and return a
# deterministic sentence. No business interpretation, only description of events.


def explain_completed(rows_returned: int, truncated: bool) -> str:
    base = (
        f"Answered by running a read-only query against the warehouse; "
        f"{rows_returned} row(s) returned."
    )
    if truncated:
        base += " Results were limited to the configured maximum; more rows exist."
    return base


def explain_no_query(model_message: str | None) -> str:
    base = "The assistant did not produce a warehouse query for this question."
    if model_message:
        return f"{base} It responded: {model_message}"
    return base


def explain_validation_rejected(reasons: tuple[str, ...]) -> str:
    base = "The proposed query was not permitted and was not run."
    if reasons:
        joined = "; ".join(reasons)
        return f"{base} Reason(s): {joined}."
    return base


def explain_execution_failed(error_message: str | None) -> str:
    base = "The query passed validation but failed during execution."
    if error_message:
        return f"{base} Details: {error_message}"
    return base


# API errors: deliberately generic to the user; provider internals stay in logs
# (metadata), never surfaced in user-facing fields.
EXPLAIN_API_ERROR = (
    "The assistant could not reach the language model service. Please try again shortly."
)
