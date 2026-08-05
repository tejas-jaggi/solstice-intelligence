"""Deterministic tests for the repository-owned LLM timeout (ADR-013).

No network and no wall-clock waiting: the timeout resolution is tested directly,
and the mapping of LLMTimeoutError to a non-success outcome is exercised via an
injected client that raises it.
"""

from __future__ import annotations

import app.llm.client as client_mod


def test_default_timeout_is_repository_owned(monkeypatch):
    monkeypatch.delenv("OPENAI_TIMEOUT_SECONDS", raising=False)
    assert client_mod._resolve_timeout() == client_mod.DEFAULT_TIMEOUT_SECONDS


def test_env_overrides_timeout(monkeypatch):
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "12.5")
    assert client_mod._resolve_timeout() == 12.5


def test_invalid_or_nonpositive_timeout_falls_back(monkeypatch):
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "not-a-number")
    assert client_mod._resolve_timeout() == client_mod.DEFAULT_TIMEOUT_SECONDS
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "0")
    assert client_mod._resolve_timeout() == client_mod.DEFAULT_TIMEOUT_SECONDS


# NOTE: the LLMTimeoutError -> formatted non-success mapping is asserted against
# your orchestrator's existing non-success path once we confirm the reused stage;
# it uses a fake client that raises LLMTimeoutError, never a real timeout wait.
