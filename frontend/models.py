"""Frontend-side typed representations of the PUBLIC REST contract.

These mirror the frozen /v1 OpenAPI contract — NOT the backend's internal models
(OrchestrationResult, AssistantResponse). The frontend couples to the public
contract on purpose and to internal types never.

Two distinct result types encode the Phase G two-category distinction at the
type level:
  * ApiResult — the API was reached and returned a valid pipeline outcome
    (HTTP 200), which INCLUDES refusals (validation_rejected, no_query, ...).
    A refusal is a successful response describing a non-success outcome.
  * ApiError — the API could not be reached or did not return a valid contract
    response (network failure, timeout, malformed body). A transport failure.

Because they are different types, the UI cannot accidentally treat "the backend
refused" the same as "I couldn't reach the backend."
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol


class ResultStatus(str, Enum):
    """Public status values from the REST contract (mirror of the API's status)."""

    SUCCESS = "success"
    NO_QUERY = "no_query"
    VALIDATION_REJECTED = "validation_rejected"
    EXECUTION_FAILED = "execution_failed"
    API_ERROR = "api_error"


class TransportErrorKind(str, Enum):
    """Category of a transport-level failure (never a pipeline outcome)."""

    NETWORK = "network"        # could not connect / connection refused
    TIMEOUT = "timeout"        # request exceeded the configured timeout
    BAD_RESPONSE = "bad_response"  # non-200 or unparseable contract body


@dataclass(frozen=True)
class AnswerTable:
    """Structured tabular answer (present only on success)."""

    columns: list[str]
    rows: list[list]


@dataclass(frozen=True)
class ResultMetadata:
    """Consumer-stable metadata from the contract. No provider/model details."""

    request_id: str | None = None
    stage: str | None = None
    execution_time_ms: float | None = None
    row_count: int | None = None
    truncated: bool | None = None
    validation_passed: bool | None = None


@dataclass(frozen=True)
class ApiResult:
    """A reached-and-answered response (HTTP 200), including refusals."""

    status: ResultStatus
    success: bool
    explanation: str
    answer: AnswerTable | None = None
    executed_sql: str | None = None
    metadata: ResultMetadata = field(default_factory=ResultMetadata)


@dataclass(frozen=True)
class ApiError:
    """A transport failure — the API could not be reached or answered validly."""

    kind: TransportErrorKind
    message: str


# The outcome of any ask(): either a pipeline result or a transport error.
AskOutcome = "ApiResult | ApiError"


class AnalyticsApiClient(Protocol):
    """Minimal interface both the real and fake clients implement.

    Deliberately tiny — two methods, no abstraction hierarchy. Having a shared
    Protocol means the fake test client is a first-class implementation (not a
    monkeypatch), which makes dependency injection clean and proves the fake has
    the same shape as the real client.
    """

    def ask(self, question: str) -> "ApiResult | ApiError":
        """Send one question to the backend and return a typed outcome."""
        ...

    def ready(self) -> bool:
        """Return True if the backend reports ready (informational, non-blocking)."""
        ...
