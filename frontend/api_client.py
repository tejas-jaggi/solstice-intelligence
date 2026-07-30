"""The sole HTTP boundary between the frontend and the backend.

This module owns the HTTP IMPLEMENTATION, not a specific library. The rest of the
frontend depends only on the AnalyticsApiClient protocol (models.py), so the
underlying library (httpx today, could be aiohttp later) can change here without
touching streamlit_app.py or the components.

Responsibility: turn a question into an HTTP call and turn EVERY possible
transport failure (timeout, connection refused, non-200, malformed body) into a
typed ApiError. No exception ever escapes to the UI — mirroring the backend
executor, which returns structured errors rather than raising.

Nothing in this module (or anywhere in frontend/) imports backend modules. The
only contact with the backend is over HTTP against the frozen /v1 contract.
"""

from __future__ import annotations

import httpx

from frontend import config
from frontend.models import (
    AnswerTable,
    ApiError,
    ApiResult,
    ResultMetadata,
    ResultStatus,
    TransportErrorKind,
)


class RealApiClient:
    """AnalyticsApiClient backed by an HTTP call to the FastAPI backend."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._base_url = (base_url or config.API_BASE_URL).rstrip("/")
        self._timeout = timeout if timeout is not None else config.REQUEST_TIMEOUT_SECONDS

    # -- public interface (AnalyticsApiClient) -------------------------------

    def ask(self, question: str) -> ApiResult | ApiError:
        """POST one question to /v1/ask; return a typed outcome."""
        try:
            response = httpx.post(
                f"{self._base_url}/v1/ask",
                json={"question": question},
                timeout=self._timeout,
            )
        except httpx.TimeoutException:
            return ApiError(TransportErrorKind.TIMEOUT, "The request timed out.")
        except httpx.HTTPError:
            return ApiError(TransportErrorKind.NETWORK, "Could not reach the analytics service.")

        if response.status_code != 200:
            return ApiError(
                TransportErrorKind.BAD_RESPONSE,
                f"Service returned an unexpected status ({response.status_code}).",
            )

        try:
            return self._parse(response.json())
        except (ValueError, KeyError, TypeError):
            return ApiError(
                TransportErrorKind.BAD_RESPONSE, "Service returned an unreadable response."
            )

    def ready(self) -> bool:
        """Best-effort readiness probe. Never raises; False on any failure."""
        try:
            r = httpx.get(f"{self._base_url}/ready", timeout=self._timeout)
        except httpx.HTTPError:
            return False
        return r.status_code == 200 and bool(r.json().get("ready"))

    # -- private: contract parsing -------------------------------------------

    @staticmethod
    def _parse(body: dict) -> ApiResult:
        """Map a public /v1/ask JSON body into a typed ApiResult."""
        answer = None
        if body.get("answer") is not None:
            answer = AnswerTable(
                columns=list(body["answer"]["columns"]),
                rows=[list(r) for r in body["answer"]["rows"]],
            )
        meta = body.get("metadata") or {}
        return ApiResult(
            status=ResultStatus(body["status"]),
            success=bool(body["success"]),
            explanation=body.get("explanation", ""),
            answer=answer,
            executed_sql=body.get("executed_sql"),
            metadata=ResultMetadata(
                request_id=meta.get("request_id"),
                stage=meta.get("stage"),
                execution_time_ms=meta.get("execution_time_ms"),
                row_count=meta.get("row_count"),
                truncated=meta.get("truncated"),
                validation_passed=meta.get("validation_passed"),
            ),
        )
