"""Component tests: render functions are pure and callable with contract data.

Streamlit calls are stubbed so we can invoke components headlessly and assert
they execute the right branches without a running Streamlit server.
"""
from __future__ import annotations

import sys
import types
import pytest

from frontend.models import (
    AnswerTable, ApiError, ApiResult, ResultMetadata, ResultStatus, TransportErrorKind,
)


class FakeSt:
    """Minimal Streamlit stand-in recording calls."""
    def __init__(self):
        self.calls = []
    def __getattr__(self, name):
        def rec(*a, **k):
            self.calls.append((name, a, k))
            # expander is used as a context manager
            if name == "expander":
                return _Ctx()
            return None
        return rec

class _Ctx:
    def __enter__(self): return self
    def __exit__(self, *a): return False


@pytest.fixture()
def fake_st(monkeypatch):
    fs = FakeSt()
    import frontend.components as comp
    monkeypatch.setattr(comp, "st", fs)
    return fs


def test_render_success_shows_table_and_executed_sql(fake_st):
    import frontend.components as comp
    r = ApiResult(status=ResultStatus.SUCCESS, success=True, explanation="ok",
                  answer=AnswerTable(columns=["c"], rows=[[1]]),
                  executed_sql="SELECT 1", metadata=ResultMetadata(truncated=False))
    comp.render_result(r)
    names = [c[0] for c in fake_st.calls]
    assert "dataframe" in names          # table rendered
    assert "code" in names               # SQL rendered
    # executed label, not proposed
    md_calls = [c for c in fake_st.calls if c[0] == "markdown"]
    assert any("Executed SQL" in c[1][0] for c in md_calls)


def test_render_rejection_labels_sql_not_run(fake_st):
    import frontend.components as comp
    r = ApiResult(status=ResultStatus.VALIDATION_REJECTED, success=False,
                  explanation="nope", answer=None, executed_sql="DROP TABLE x",
                  metadata=ResultMetadata(validation_passed=False))
    comp.render_result(r)
    md_calls = [c for c in fake_st.calls if c[0] == "markdown"]
    assert any("Proposed SQL (not run)" in c[1][0] for c in md_calls)
    # no table on a rejection
    assert "dataframe" not in [c[0] for c in fake_st.calls]


def test_render_transport_error(fake_st):
    import frontend.components as comp
    comp.render_transport_error(ApiError(TransportErrorKind.TIMEOUT, "slow"))
    assert any(c[0] == "error" for c in fake_st.calls)


def test_truncation_notice_uses_backend_truth(fake_st):
    import frontend.components as comp
    r = ApiResult(status=ResultStatus.SUCCESS, success=True, explanation="ok",
                  answer=AnswerTable(columns=["c"], rows=[[1],[2]]),
                  executed_sql=None, metadata=ResultMetadata(truncated=True))
    comp.render_result(r)
    caption_calls = [c for c in fake_st.calls if c[0] == "caption"]
    assert any("Showing the first" in c[1][0] for c in caption_calls)
