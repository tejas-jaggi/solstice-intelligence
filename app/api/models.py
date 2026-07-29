"""Public API contract models.

These Pydantic models ARE the frozen public contract. They are deliberately
separate from the internal Milestone 1 result types (OrchestrationResult /
AssistantResponse) so that internal refactors cannot silently change the public
API. The mapping layer (mapping.py) is the only thing that converts between the
two — see ADR-009.

Design rules encoded here:
  * No implementation details (provider name, model name) appear in the public
    contract. Only consumer-stable facts are exposed.
  * The answer is STRUCTURED (columns + rows), never an LLM-narrated string
    (consistent with ADR-008: the system reports what it did, it does not
    interpret the data).
  * Representative examples are attached so they render in the OpenAPI docs.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    """A natural-language analytics question."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="A natural-language question about the warehouse.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"question": "How many orders are in the warehouse?"}
            ]
        }
    }


class AnswerTable(BaseModel):
    """Structured tabular result. Present only on a successful answer."""

    columns: list[str] = Field(description="Column names, in order.")
    rows: list[list] = Field(description="Result rows, aligned to columns.")


class ResponseMetadata(BaseModel):
    """Consumer-stable observability metadata.

    Deliberately excludes implementation details (LLM provider/model). Those are
    logged internally if needed, never returned, so the model can change without
    breaking this frozen contract.
    """

    request_id: str = Field(description="Correlation ID for this request.")
    stage: str = Field(description="Where the pipeline concluded.")
    execution_time_ms: float | None = Field(
        default=None, description="Query execution time, if a query ran."
    )
    row_count: int | None = Field(
        default=None, description="Number of rows returned, if a query ran."
    )
    truncated: bool | None = Field(
        default=None, description="True if the row cap limited the result."
    )
    validation_passed: bool | None = Field(
        default=None, description="Whether the proposed SQL passed validation."
    )


class AskResponse(BaseModel):
    """The response to POST /v1/ask.

    Pipeline outcomes (including refusals) are returned here with HTTP 200 and a
    ``status`` field — a refusal is a successful response describing a non-success
    outcome, not an HTTP error. Only genuine API/infrastructure failures use
    4xx/5xx.
    """

    status: str = Field(description="Pipeline outcome (e.g. success, validation_rejected).")
    success: bool = Field(description="True only for a completed answer.")
    answer: AnswerTable | None = Field(
        default=None, description="Structured result; null unless success."
    )
    explanation: str = Field(
        description="Plain-English description of what the system did (never an "
        "interpretation of the data)."
    )
    executed_sql: str | None = Field(
        default=None, description="The SQL that ran, for transparency; null if none ran."
    )
    metadata: ResponseMetadata

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "success",
                    "success": True,
                    "answer": {"columns": ["order_count"], "rows": [[26299]]},
                    "explanation": "Answered by running a read-only query against the warehouse; 1 row(s) returned.",
                    "executed_sql": "SELECT COUNT(*) AS order_count FROM Fact_Orders LIMIT 100",
                    "metadata": {
                        "request_id": "b3f1c2a4-...",
                        "stage": "completed",
                        "execution_time_ms": 1.2,
                        "row_count": 1,
                        "truncated": False,
                        "validation_passed": True,
                    },
                },
                {
                    "status": "validation_rejected",
                    "success": False,
                    "answer": None,
                    "explanation": "The proposed query was not permitted and was not run. Reason(s): Table 'X' is not a known warehouse table.",
                    "executed_sql": None,
                    "metadata": {
                        "request_id": "c4a2d3b5-...",
                        "stage": "validation_rejected",
                        "execution_time_ms": None,
                        "row_count": None,
                        "truncated": None,
                        "validation_passed": False,
                    },
                },
            ]
        }
    }


class HealthResponse(BaseModel):
    status: str = Field(description="'alive' when the process is running.")


class ReadyResponse(BaseModel):
    ready: bool = Field(description="True when the assistant and warehouse are usable.")
    detail: str = Field(description="Human-readable readiness detail.")


class VersionResponse(BaseModel):
    app_version: str
    milestone: str
