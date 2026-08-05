"""Structured, metadata-only logging configuration (ADR-013).

Configured ONCE, deterministically and idempotently, from create_app(): calling
create_app() any number of times attaches exactly one handler to the 'solstice'
logger — no duplicates.

INVARIANT (ADR-013): operational logs are metadata-only. Records may carry request
IDs, lifecycle events, timing, status codes, and operational diagnostics, and must
NEVER carry prompts, generated SQL, warehouse query results, model responses, user
data, API keys, or secrets. The formatter emits a fixed field set plus explicitly
whitelisted operational extras — it never serializes arbitrary record attributes,
so sensitive values cannot leak in even if mistakenly attached to a record.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable

_ROOT_LOGGER_NAME = "solstice"
_HANDLER_NAME = "solstice-structured"

# The ONLY record attributes ever emitted. Anything not in this set is dropped by
# construction — the enforcement mechanism for the metadata-only invariant.
_OPERATIONAL_EXTRAS = ("request_id", "stage", "status_code", "duration_ms", "event")


class StructuredFormatter(logging.Formatter):
    """Emit a fixed, metadata-only field set as JSON.

    Deterministic given its inputs: an injectable time source lets tests assert on
    a stable timestamp. Only whitelisted operational extras are included; arbitrary
    record attributes are never serialized.
    """

    def __init__(self, time_fn: Callable[[], str] | None = None) -> None:
        super().__init__()
        self._time_fn = time_fn

    def _timestamp(self, record: logging.LogRecord) -> str:
        if self._time_fn is not None:
            return self._time_fn()
        return self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S%z")

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": self._timestamp(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in _OPERATIONAL_EXTRAS:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


class TextFormatter(logging.Formatter):
    """Human-readable local formatter — same metadata-only fields, dev-friendly."""

    def format(self, record: logging.LogRecord) -> str:
        parts = [f"{record.levelname:<7}", record.name, record.getMessage()]
        for key in _OPERATIONAL_EXTRAS:
            value = getattr(record, key, None)
            if value is not None:
                parts.append(f"{key}={value}")
        return "  ".join(str(p) for p in parts)


def _make_formatter() -> logging.Formatter:
    # Deployment defaults to JSON; local dev defaults to text for readability.
    fmt = os.environ.get("LOG_FORMAT", "text").strip().lower()
    return StructuredFormatter() if fmt == "json" else TextFormatter()


def _level() -> int:
    name = os.environ.get("LOG_LEVEL", "INFO").strip().upper()
    return getattr(logging, name, logging.INFO)


def configure_logging() -> logging.Logger:
    """Idempotently configure the 'solstice' logger. Safe to call repeatedly.

    Removes any prior handler we installed before attaching a fresh one, so N calls
    to create_app() yield exactly one handler — deterministic and duplicate-free.
    """
    logger = logging.getLogger(_ROOT_LOGGER_NAME)
    logger.setLevel(_level())
    logger.propagate = False  # don't double-emit through the root logger

    # Idempotency: drop a handler we previously attached, if any.
    for handler in list(logger.handlers):
        if getattr(handler, "name", None) == _HANDLER_NAME:
            logger.removeHandler(handler)

    handler = logging.StreamHandler()
    handler.name = _HANDLER_NAME
    handler.setFormatter(_make_formatter())
    logger.addHandler(handler)
    return logger
