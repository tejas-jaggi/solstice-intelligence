"""Pure presentation transformation.

format_response(OrchestrationResult) -> AssistantResponse.

A pure function: same input always yields the same output, no I/O, no LLM, no
database. It depends only on the typed result modules — the narrowest dependency
set of any component. It never validates, executes, generates, or interprets.
"""
from __future__ import annotations

from app.formatting import templates as T
from app.formatting.response import (
    AssistantResponse,
    ResponseSeverity,
    ResponseStatus,
)
from app.llm.result import OrchestrationResult, PipelineStage


def _metadata(result: OrchestrationResult) -> dict:
    """Observability fields carried through for logs/debugging (not user copy)."""
    meta: dict = {
        "stage": result.stage.value,
        "model_name": result.model_name,
        "total_time_ms": result.total_time_ms,
    }
    if result.execution is not None:
        meta["execution_time_ms"] = result.execution.execution_time_ms
        meta["rows_returned"] = result.execution.rows_returned
        meta["truncated"] = result.execution.truncated
    # API error internals live here (logs), never in user-facing fields.
    if result.stage is PipelineStage.API_ERROR and result.error_message:
        meta["api_error_detail"] = result.error_message
    return meta


def _validation_reasons(result: OrchestrationResult) -> tuple[str, ...]:
    if result.validation is None:
        return ()
    return tuple(e.message for e in result.validation.errors)


def format_response(result: OrchestrationResult) -> AssistantResponse:
    """Transform an orchestration outcome into the user-facing response."""
    meta = _metadata(result)
    stage = result.stage

    if stage is PipelineStage.COMPLETED and result.execution is not None:
        ex = result.execution
        return AssistantResponse(
            success=True,
            status=ResponseStatus.SUCCESS,
            severity=ResponseSeverity.INFO,
            headline=T.HEADLINE_COMPLETED,
            explanation=T.explain_completed(ex.rows_returned, ex.truncated),
            executed_sql=ex.executed_sql,
            columns=ex.columns,
            rows=ex.rows,
            metadata=meta,
        )

    if stage is PipelineStage.NO_QUERY_PROPOSED:
        return AssistantResponse(
            success=False,
            status=ResponseStatus.NO_QUERY,
            severity=ResponseSeverity.INFO,  # benign: often an off-topic question
            headline=T.HEADLINE_NO_QUERY,
            explanation=T.explain_no_query(result.model_message),
            metadata=meta,
        )

    if stage is PipelineStage.VALIDATION_REJECTED:
        return AssistantResponse(
            success=False,
            status=ResponseStatus.VALIDATION_REJECTED,
            severity=ResponseSeverity.WARNING,
            headline=T.HEADLINE_VALIDATION_REJECTED,
            explanation=T.explain_validation_rejected(_validation_reasons(result)),
            # The rejected query is shown for transparency but labeled as PROPOSED,
            # never as executed — it did not run.
            proposed_sql=result.candidate_sql,
            metadata=meta,
        )

    if stage is PipelineStage.EXECUTION_FAILED:
        executed = result.execution.executed_sql if result.execution else result.candidate_sql
        return AssistantResponse(
            success=False,
            status=ResponseStatus.EXECUTION_FAILED,
            severity=ResponseSeverity.ERROR,
            headline=T.HEADLINE_EXECUTION_FAILED,
            explanation=T.explain_execution_failed(result.error_message),
            executed_sql=executed,
            metadata=meta,
        )

    # PipelineStage.API_ERROR (and any unforeseen stage) -> generic error.
    return AssistantResponse(
        success=False,
        status=ResponseStatus.API_ERROR,
        severity=ResponseSeverity.ERROR,
        headline=T.HEADLINE_API_ERROR,
        explanation=T.EXPLAIN_API_ERROR,  # generic; detail is in metadata/logs
        metadata=meta,
    )
