"""Deterministic tests for the response layer (Phase F).

The purest tests in the repo: no warehouse, no LLM, no network, no fixtures.
Each test hand-builds an OrchestrationResult for one PipelineStage and asserts on
the resulting AssistantResponse.
"""

from __future__ import annotations

from app.execution.result import ExecutionResult, ExecutionStatus
from app.formatting.formatter import format_response
from app.formatting.response import ResponseSeverity, ResponseStatus
from app.llm.result import OrchestrationResult, PipelineStage
from app.validation.decision import (
    ErrorCategory,
    ValidationError,
    ValidationResult,
)


def _base(stage, **kw):
    return OrchestrationResult(
        stage=stage,
        question="q",
        model_name="fake-model",
        total_time_ms=12.3,
        **kw,
    )


def test_completed():
    ex = ExecutionResult(
        status=ExecutionStatus.SUCCESS,
        executed_sql="SELECT 1 LIMIT 100",
        columns=("a",),
        rows=((1,),),
        rows_returned=1,
        truncated=False,
        execution_time_ms=2.0,
    )
    r = format_response(_base(PipelineStage.COMPLETED, candidate_sql="SELECT 1", execution=ex))
    assert r.success
    assert r.status is ResponseStatus.SUCCESS
    assert r.severity is ResponseSeverity.INFO
    assert r.executed_sql == "SELECT 1 LIMIT 100"
    assert r.columns == ("a",) and r.rows == ((1,),)
    assert "1 row" in r.explanation
    assert r.metadata["model_name"] == "fake-model"


def test_completed_truncated_mentions_limit():
    ex = ExecutionResult(
        status=ExecutionStatus.SUCCESS,
        executed_sql="SELECT 1",
        columns=("a",),
        rows=tuple((i,) for i in range(5)),
        rows_returned=5,
        truncated=True,
        execution_time_ms=1.0,
    )
    r = format_response(_base(PipelineStage.COMPLETED, execution=ex))
    assert "more rows exist" in r.explanation.lower()


def test_no_query():
    r = format_response(
        _base(PipelineStage.NO_QUERY_PROPOSED, model_message="I can't answer that.")
    )
    assert not r.success
    assert r.status is ResponseStatus.NO_QUERY
    assert r.severity is ResponseSeverity.INFO
    assert r.executed_sql is None and r.proposed_sql is None
    assert "I can't answer that." in r.explanation


def test_validation_rejected():
    vr = ValidationResult.reject(
        (ValidationError(ErrorCategory.UNKNOWN_TABLE, "Table 'X' is not a known warehouse table."),)
    )
    r = format_response(
        _base(PipelineStage.VALIDATION_REJECTED, candidate_sql="SELECT * FROM X", validation=vr)
    )
    assert not r.success
    assert r.status is ResponseStatus.VALIDATION_REJECTED
    assert r.severity is ResponseSeverity.WARNING
    # rejected SQL is shown as PROPOSED, never executed
    assert r.proposed_sql == "SELECT * FROM X"
    assert r.executed_sql is None
    assert "not a known warehouse table" in r.explanation


def test_execution_failed():
    ex = ExecutionResult(
        status=ExecutionStatus.EXECUTION_ERROR,
        executed_sql="SELECT bad FROM Fact_Orders",
        execution_time_ms=1.0,
        error_message="Query execution failed: no column bad",
    )
    vr = ValidationResult.approve("SELECT bad FROM Fact_Orders LIMIT 100")
    r = format_response(
        _base(
            PipelineStage.EXECUTION_FAILED,
            candidate_sql="SELECT bad FROM Fact_Orders",
            validation=vr,
            execution=ex,
            error_message="Query execution failed: no column bad",
        )
    )
    assert not r.success
    assert r.status is ResponseStatus.EXECUTION_FAILED
    assert r.severity is ResponseSeverity.ERROR
    assert r.executed_sql == "SELECT bad FROM Fact_Orders"
    assert "failed during execution" in r.explanation


def test_api_error_does_not_leak_internals():
    r = format_response(
        _base(PipelineStage.API_ERROR, error_message="401 Unauthorized: bad key sk-secret")
    )
    assert not r.success
    assert r.status is ResponseStatus.API_ERROR
    assert r.severity is ResponseSeverity.ERROR
    # provider internals must NOT appear in user-facing fields
    assert "sk-secret" not in r.explanation
    assert "401" not in r.explanation
    # but they ARE preserved in metadata for logs
    assert "api_error_detail" in r.metadata


def test_purity_same_input_same_output():
    ex = ExecutionResult(
        status=ExecutionStatus.SUCCESS,
        executed_sql="SELECT 1",
        columns=("a",),
        rows=((1,),),
        rows_returned=1,
        truncated=False,
        execution_time_ms=1.0,
    )
    result = _base(PipelineStage.COMPLETED, execution=ex)
    assert format_response(result).to_dict() == format_response(result).to_dict()


def test_to_dict_is_json_safe():
    import json
    from decimal import Decimal

    ex = ExecutionResult(
        status=ExecutionStatus.SUCCESS,
        executed_sql="SELECT 1",
        columns=("rev",),
        rows=((Decimal("250.00"),),),
        rows_returned=1,
        truncated=False,
        execution_time_ms=1.0,
    )
    d = format_response(_base(PipelineStage.COMPLETED, execution=ex)).to_dict()
    json.dumps(d)  # must not raise (Decimal stringified)
    assert d["rows"] == [["250.00"]]
