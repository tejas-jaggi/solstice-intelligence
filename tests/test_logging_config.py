"""Deterministic tests for structured, metadata-only logging (ADR-013)."""

from __future__ import annotations

import json
import logging

from app.api import logging_config as lc


def _record(msg="hello", **extra):
    rec = logging.LogRecord("solstice.api", logging.INFO, __file__, 1, msg, None, None)
    for k, v in extra.items():
        setattr(rec, k, v)
    return rec


def test_structured_formatter_emits_fixed_fields():
    fmt = lc.StructuredFormatter(time_fn=lambda: "2026-01-01T00:00:00+0000")
    out = json.loads(fmt.format(_record("ask handled", request_id="rid-1", stage="success")))
    assert out["timestamp"] == "2026-01-01T00:00:00+0000"
    assert out["level"] == "INFO"
    assert out["logger"] == "solstice.api"
    assert out["message"] == "ask handled"
    assert out["request_id"] == "rid-1"
    assert out["stage"] == "success"


def test_formatter_drops_non_whitelisted_attributes():
    # A sensitive value mistakenly attached to a record must NOT be serialized.
    fmt = lc.StructuredFormatter(time_fn=lambda: "t")
    rec = _record(
        "ask handled",
        request_id="rid",
        question="TOP SECRET QUESTION",
        generated_sql="SELECT * FROM secrets",
        api_key="sk-leak",
    )
    out = json.loads(fmt.format(rec))
    serialized = json.dumps(out)
    assert "TOP SECRET QUESTION" not in serialized
    assert "SELECT * FROM secrets" not in serialized
    assert "sk-leak" not in serialized
    assert set(out) <= {
        "timestamp",
        "level",
        "logger",
        "message",
        "request_id",
        "stage",
        "status_code",
        "duration_ms",
        "event",
    }


def test_text_formatter_is_metadata_only():
    line = lc.TextFormatter().format(_record("startup", event="startup", stage="ready"))
    assert "startup" in line and "event=startup" in line and "stage=ready" in line


def test_configure_logging_is_idempotent():
    for _ in range(5):
        logger = lc.configure_logging()
    handlers = [h for h in logger.handlers if getattr(h, "name", None) == lc._HANDLER_NAME]
    assert len(handlers) == 1  # exactly one handler, however many calls


def test_configure_logging_does_not_propagate():
    logger = lc.configure_logging()
    assert logger.propagate is False
