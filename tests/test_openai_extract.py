"""Deterministic tests for OpenAIClient._extract (Phase E client boundary).

These do NOT call the network. They feed _extract fake response objects shaped
like the real Responses API output (verified against openai SDK 2.x types:
function_call items carry .type='function_call', .name, .arguments; message items
carry .content blocks with .text). This closes the coverage gap on the one
component that otherwise requires live verification, without making any network
call.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.llm.client import OpenAIClient


def _fn_call(name, arguments):
    return SimpleNamespace(type="function_call", name=name, arguments=arguments, content=None)


def _message(text):
    block = SimpleNamespace(text=text)
    return SimpleNamespace(type="message", name="", content=[block])


def _response(output):
    return SimpleNamespace(output=output)


def test_extract_tool_call_sql():
    resp = _response([_fn_call("run_query", '{"sql": "SELECT 1 FROM Fact_Orders"}')])
    pq = OpenAIClient._extract(resp)
    assert pq.sql == "SELECT 1 FROM Fact_Orders"
    assert pq.has_query


def test_extract_message_when_no_tool_call():
    resp = _response([_message("I can't answer that from this warehouse.")])
    pq = OpenAIClient._extract(resp)
    assert pq.sql is None
    assert not pq.has_query
    assert "can't answer" in pq.message


def test_extract_ignores_non_run_query_tool():
    resp = _response([_fn_call("some_other_tool", '{"x": 1}')])
    pq = OpenAIClient._extract(resp)
    assert pq.sql is None


def test_extract_handles_malformed_arguments():
    resp = _response([_fn_call("run_query", "not valid json")])
    pq = OpenAIClient._extract(resp)
    assert pq.sql is None  # malformed -> no query, no crash


def test_extract_handles_dict_arguments():
    # Some SDK paths may present already-parsed dict arguments.
    resp = _response([_fn_call("run_query", {"sql": "SELECT 2"})])
    pq = OpenAIClient._extract(resp)
    assert pq.sql == "SELECT 2"


def test_extract_empty_output():
    pq = OpenAIClient._extract(_response([]))
    assert pq.sql is None and pq.message is None
