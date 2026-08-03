"""Deterministic tests for the Deployment Access Guard — no network, no OpenAI."""

from __future__ import annotations

import types

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers

from app.api import access_guard as ag


def _clock():
    box = {"t": 0.0}

    def now() -> float:
        return box["t"]

    def advance(dt: float) -> None:
        box["t"] += dt

    return now, advance


def _request(headers=None, host="1.2.3.4", guard=None):
    app = types.SimpleNamespace(state=types.SimpleNamespace(cost_guard=guard))
    client = types.SimpleNamespace(host=host) if host is not None else None
    return types.SimpleNamespace(app=app, headers=Headers(headers or {}), client=client)


def test_limiter_allows_up_to_max_then_denies():
    now, _ = _clock()
    limiter = ag.FixedWindowRateLimiter(2, 60, now)
    assert limiter.allow("a")
    assert limiter.allow("a")
    assert not limiter.allow("a")
    assert limiter.allow("b")  # a separate key has its own window


def test_limiter_window_resets_with_time():
    now, advance = _clock()
    limiter = ag.FixedWindowRateLimiter(1, 60, now)
    assert limiter.allow("a")
    assert not limiter.allow("a")
    advance(60)
    assert limiter.allow("a")


def test_limiter_disabled_when_max_not_positive():
    limiter = ag.FixedWindowRateLimiter(0, 60)
    assert not limiter.enabled
    for _ in range(100):
        assert limiter.allow("a")


def test_guard_passthrough_when_disabled():
    guard = ag.DeploymentAccessGuard(ag.FixedWindowRateLimiter(0, 60))
    assert not guard.rate_limit_enabled and not guard.gate_enabled
    for _ in range(50):
        guard.check("ip", None)  # never raises


def test_guard_rate_limits():
    guard = ag.DeploymentAccessGuard(ag.FixedWindowRateLimiter(1, 60))
    guard.check("ip", None)
    with pytest.raises(HTTPException) as exc:
        guard.check("ip", None)
    assert exc.value.status_code == 429


def test_guard_requires_token_when_configured():
    guard = ag.DeploymentAccessGuard(ag.FixedWindowRateLimiter(0, 60), demo_token="s3cret")
    assert guard.gate_enabled
    with pytest.raises(HTTPException) as missing:
        guard.check("ip", None)
    assert missing.value.status_code == 401
    with pytest.raises(HTTPException):
        guard.check("ip", "wrong")
    guard.check("ip", "s3cret")  # correct token → no raise


def test_client_key_prefers_forwarded_for():
    req = _request(headers={"x-forwarded-for": "9.9.9.9, 1.1.1.1"}, host="10.0.0.1")
    assert ag.client_key(req) == "9.9.9.9"


def test_client_key_falls_back_to_peer():
    assert ag.client_key(_request(headers={}, host="10.0.0.1")) == "10.0.0.1"


def test_client_key_unknown_without_client():
    assert ag.client_key(_request(headers={}, host=None)) == "unknown"


def test_enforce_delegates_to_state_guard():
    guard = ag.DeploymentAccessGuard(ag.FixedWindowRateLimiter(1, 60))
    req = _request(headers={}, host="ip", guard=guard)
    ag.enforce_deployment_guard(req)  # first allowed
    with pytest.raises(HTTPException) as exc:
        ag.enforce_deployment_guard(req)  # second → 429
    assert exc.value.status_code == 429


def test_enforce_reads_demo_token_header():
    guard = ag.DeploymentAccessGuard(ag.FixedWindowRateLimiter(0, 60), demo_token="tok")
    ok = _request(headers={"x-demo-token": "tok"}, host="ip", guard=guard)
    ag.enforce_deployment_guard(ok)  # correct token → no raise
    bad = _request(headers={}, host="ip", guard=guard)
    with pytest.raises(HTTPException) as exc:
        ag.enforce_deployment_guard(bad)
    assert exc.value.status_code == 401


def test_build_guard_defaults_disabled(monkeypatch):
    monkeypatch.delenv("RATE_LIMIT_MAX_REQUESTS", raising=False)
    monkeypatch.delenv("SOLSTICE_DEMO_TOKEN", raising=False)
    guard = ag.build_deployment_guard()
    assert not guard.rate_limit_enabled and not guard.gate_enabled


def test_build_guard_enabled_from_env(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_MAX_REQUESTS", "5")
    monkeypatch.setenv("SOLSTICE_DEMO_TOKEN", "tok")
    guard = ag.build_deployment_guard()
    assert guard.rate_limit_enabled and guard.gate_enabled
