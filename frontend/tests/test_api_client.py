"""Tests for RealApiClient using httpx MockTransport — no real network."""

from __future__ import annotations

import httpx

from frontend.api_client import RealApiClient
from frontend.models import ApiError, ApiResult, ResultStatus, TransportErrorKind


def client_with(handler) -> RealApiClient:
    transport = httpx.MockTransport(handler)
    c = RealApiClient(base_url="http://test", timeout=5)

    # Inject the mock transport by monkeypatching httpx.post/get to use it.
    def post(url, json=None, timeout=None):
        req = httpx.Request("POST", url, json=json)
        return transport.handle_request(req)

    def get(url, timeout=None):
        req = httpx.Request("GET", url)
        return transport.handle_request(req)

    import frontend.api_client as mod

    mod.httpx.post = post  # type: ignore
    mod.httpx.get = get  # type: ignore
    return c


SUCCESS_BODY = {
    "status": "success",
    "success": True,
    "answer": {"columns": ["order_count"], "rows": [[26299]]},
    "explanation": "Answered by running a read-only query; 1 row(s) returned.",
    "executed_sql": "SELECT COUNT(*) AS order_count FROM Fact_Orders LIMIT 100",
    "metadata": {
        "request_id": "abc",
        "stage": "completed",
        "execution_time_ms": 1.2,
        "row_count": 1,
        "truncated": False,
        "validation_passed": True,
    },
}


def test_success_parsed_to_apiresult():
    c = client_with(lambda req: httpx.Response(200, json=SUCCESS_BODY))
    out = c.ask("how many orders?")
    assert isinstance(out, ApiResult)
    assert out.status is ResultStatus.SUCCESS
    assert out.answer.columns == ["order_count"]
    assert out.answer.rows == [[26299]]
    assert out.metadata.request_id == "abc"


def test_rejection_is_apiresult_not_error():
    body = {
        "status": "validation_rejected",
        "success": False,
        "answer": None,
        "explanation": "not permitted",
        "executed_sql": None,
        "metadata": {"stage": "validation_rejected", "validation_passed": False},
    }
    c = client_with(lambda req: httpx.Response(200, json=body))
    out = c.ask("drop table")
    assert isinstance(out, ApiResult)  # a refusal is NOT a transport error
    assert out.status is ResultStatus.VALIDATION_REJECTED
    assert out.answer is None


def test_non_200_is_bad_response_error():
    c = client_with(lambda req: httpx.Response(500, json={"detail": "boom"}))
    out = c.ask("x")
    assert isinstance(out, ApiError)
    assert out.kind is TransportErrorKind.BAD_RESPONSE


def test_timeout_is_timeout_error():
    def handler(req):
        raise httpx.TimeoutException("slow")

    c = client_with(handler)
    out = c.ask("x")
    assert isinstance(out, ApiError)
    assert out.kind is TransportErrorKind.TIMEOUT


def test_connection_error_is_network_error():
    def handler(req):
        raise httpx.ConnectError("refused")

    c = client_with(handler)
    out = c.ask("x")
    assert isinstance(out, ApiError)
    assert out.kind is TransportErrorKind.NETWORK


def test_malformed_body_is_bad_response():
    c = client_with(lambda req: httpx.Response(200, text="not json"))
    out = c.ask("x")
    assert isinstance(out, ApiError)
    assert out.kind is TransportErrorKind.BAD_RESPONSE


def test_ready_true_and_false():
    c = client_with(lambda req: httpx.Response(200, json={"ready": True}))
    assert c.ready() is True
    c2 = client_with(lambda req: httpx.Response(503, json={"ready": False}))
    assert c2.ready() is False
