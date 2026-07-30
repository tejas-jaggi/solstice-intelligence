"""Mapping between internal Milestone 1 models and the public API contract.

STRUCTURAL TRANSFORMATION ONLY. This module may:
  * reshape objects
  * rename fields
  * translate enums to their string values
  * convert types (tuples -> lists)

It must NEVER contain business logic, SQL logic, validation logic, presentation
logic, or any interpretation of results. Every value it emits already exists,
decided, on the internal result — mapping only changes its SHAPE, never its
MEANING. This keeps the layer permanently small (see ADR-009).
"""

from __future__ import annotations

from app.api.models import AnswerTable, AskResponse, ResponseMetadata
from app.formatting.formatter import format_response
from app.llm.result import OrchestrationResult


def to_ask_response(result: OrchestrationResult, request_id: str) -> AskResponse:
    """Reshape an internal OrchestrationResult into the public AskResponse.

    The presentation content (explanation, status severity) is produced by the
    frozen M1 formatter; this function only restructures those already-decided
    values into the public shape and drops implementation details.
    """
    # Reuse the frozen formatter as the single source of truth for presentation.
    presented = format_response(result)

    execution = result.execution

    answer = None
    if presented.success and execution is not None:
        answer = AnswerTable(
            columns=list(execution.columns),
            rows=[list(row) for row in execution.rows],
        )

    metadata = ResponseMetadata(
        request_id=request_id,
        stage=result.stage.value,
        execution_time_ms=execution.execution_time_ms if execution else None,
        row_count=execution.rows_returned if execution else None,
        truncated=execution.truncated if execution else None,
        validation_passed=(result.validation.approved if result.validation is not None else None),
    )

    return AskResponse(
        status=presented.status.value,
        success=presented.success,
        answer=answer,
        explanation=presented.explanation,
        executed_sql=presented.executed_sql,
        metadata=metadata,
    )
