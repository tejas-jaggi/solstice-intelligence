"""Orchestration result model.

Mirrors the typed-result philosophy of the validation and execution layers: a
typed stage/status enum (not strings) plus observability metadata. The stage
field is the key debugging artifact — it tells you exactly how far the pipeline
got before it stopped.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.execution.result import ExecutionResult
from app.validation.decision import ValidationResult


class PipelineStage(str, Enum):
    """How far the pipeline progressed / where it concluded."""

    NO_QUERY_PROPOSED = "no_query_proposed"      # model declined / answered in prose
    VALIDATION_REJECTED = "validation_rejected"  # gate rejected candidate SQL
    EXECUTION_FAILED = "execution_failed"        # gate approved, executor failed
    COMPLETED = "completed"                       # full success
    API_ERROR = "api_error"                       # provider call failed


@dataclass(frozen=True)
class OrchestrationResult:
    """The outcome of coordinating one natural-language question.

    Attributes:
        stage: Typed pipeline outcome.
        question: The original natural-language question.
        model_name: The model that produced the proposal.
        candidate_sql: The SQL the model proposed (None if it proposed none).
        model_message: A natural-language message from the model, if any
            (e.g. a refusal or clarification when no query was proposed).
        validation: The gate's ValidationResult, if validation ran.
        execution: The executor's ExecutionResult, if execution ran.
        total_time_ms: End-to-end orchestration time.
        error_message: Human-readable summary when the stage is a failure.
    """

    stage: PipelineStage
    question: str
    model_name: str
    candidate_sql: str | None = None
    model_message: str | None = None
    validation: ValidationResult | None = None
    execution: ExecutionResult | None = None
    total_time_ms: float | None = None
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.stage is PipelineStage.COMPLETED

    def render(self) -> str:
        head = f"[{self.stage.value}] {self.question!r}"
        if self.ok and self.execution is not None:
            return f"{head} -> {self.execution.rows_returned} row(s)"
        if self.error_message:
            return f"{head}: {self.error_message}"
        return head
