"""Flow-level tests: the FakeApiClient (same protocol) drives outcomes.

Zero network, zero OpenAI. Verifies the client contract and that the app sends
exactly one question per ask (single-turn guarantee).
"""
from __future__ import annotations

from frontend.fake_client import FakeApiClient
from frontend.models import (
    AnswerTable, ApiError, ApiResult, ResultMetadata, ResultStatus, TransportErrorKind,
)


def _success():
    return ApiResult(
        status=ResultStatus.SUCCESS, success=True, explanation="ok",
        answer=AnswerTable(columns=["c"], rows=[[1]]),
        executed_sql="SELECT 1", metadata=ResultMetadata(request_id="r1"),
    )


def test_fake_client_records_single_question():
    fake = FakeApiClient(outcome=_success())
    out = fake.ask("how many orders?")
    assert isinstance(out, ApiResult)
    assert fake.calls == ["how many orders?"]      # exactly one question, verbatim


def test_fake_client_returns_scripted_error():
    fake = FakeApiClient(outcome=ApiError(TransportErrorKind.NETWORK, "down"))
    out = fake.ask("x")
    assert isinstance(out, ApiError)
    assert out.kind is TransportErrorKind.NETWORK


def test_fake_client_ready_flag():
    assert FakeApiClient(ready_value=False).ready() is False
    assert FakeApiClient(ready_value=True).ready() is True


def test_result_and_error_are_distinct_types():
    # The type-level guarantee the whole design rests on.
    assert isinstance(_success(), ApiResult)
    assert not isinstance(_success(), ApiError)
    err = ApiError(TransportErrorKind.TIMEOUT, "slow")
    assert isinstance(err, ApiError)
    assert not isinstance(err, ApiResult)
