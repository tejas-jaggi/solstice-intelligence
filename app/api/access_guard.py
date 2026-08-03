"""Deployment Access Guard for the public POST /v1/ask endpoint.

This guard exists ONLY to protect OpenAI spend on a public demonstration
deployment. It is NOT authentication — authentication as a product feature is
deferred (see ADR-012). It is attached as a route-level dependency on
POST /v1/ask so the free operational endpoints (/health, /ready, /version,
/docs) are never affected.

Two in-process, dependency-free layers:
  * a deterministic fixed-window rate limiter (injectable clock), and
  * an optional Demo Access Gate (a shared token; disabled unless configured).

Defaults leave the guard as a pass-through (limiter disabled, no token), which
is how local development and the test suite run. A deployment enables it purely
through environment variables. The real financial backstop is the OpenAI account
hard budget cap, set outside the application (ADR-012): these layers bound abuse;
the cap bounds the bill.
"""

from __future__ import annotations

import os
import secrets
import time
from collections.abc import Callable

from fastapi import HTTPException, Request, status


class FixedWindowRateLimiter:
    """A deterministic per-key fixed-window rate limiter.

    `max_requests <= 0` disables limiting entirely (always allow). The clock is
    injectable so tests advance time explicitly and never sleep.
    """

    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._now = time_fn
        self._state: dict[str, tuple[float, int]] = {}

    @property
    def enabled(self) -> bool:
        return self._max > 0

    def allow(self, key: str) -> bool:
        if self._max <= 0:
            return True
        now = self._now()
        entry = self._state.get(key)
        if entry is None or (now - entry[0]) >= self._window:
            self._state[key] = (now, 1)
            return True
        window_start, count = entry
        if count >= self._max:
            return False
        self._state[key] = (window_start, count + 1)
        return True


class DeploymentAccessGuard:
    """Combines the rate limiter and the optional Demo Access Gate.

    `check` raises HTTPException(401) when a configured demo token is missing or
    wrong, and HTTPException(429) when rate-limited. Neither path ever reaches
    OpenAI. When no token is configured the gate is disabled; when the limiter is
    disabled it is a pass-through.
    """

    def __init__(
        self,
        limiter: FixedWindowRateLimiter,
        demo_token: str | None = None,
    ) -> None:
        self._limiter = limiter
        self._demo_token = demo_token or None  # empty string => disabled

    @property
    def rate_limit_enabled(self) -> bool:
        return self._limiter.enabled

    @property
    def gate_enabled(self) -> bool:
        return self._demo_token is not None

    def check(self, client_key: str, provided_token: str | None) -> None:
        # Token first: reject unauthorized callers without consuming a limiter
        # slot. Constant-time comparison avoids leaking the token via timing.
        if self._demo_token is not None:
            if not provided_token or not secrets.compare_digest(provided_token, self._demo_token):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="A demo access token is required for this deployment.",
                )
        if not self._limiter.allow(client_key):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded for the demo deployment. Please retry shortly.",
            )


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def build_deployment_guard() -> DeploymentAccessGuard:
    """Construct the guard from the environment.

    Defaults (RATE_LIMIT_MAX_REQUESTS=0, no SOLSTICE_DEMO_TOKEN) leave the guard
    as a pass-through — the Development mode. A deployment enables it by setting
    RATE_LIMIT_MAX_REQUESTS (and optionally SOLSTICE_DEMO_TOKEN).
    """
    limiter = FixedWindowRateLimiter(
        max_requests=_int_env("RATE_LIMIT_MAX_REQUESTS", 0),
        window_seconds=_float_env("RATE_LIMIT_WINDOW_SECONDS", 60.0),
    )
    demo_token = os.environ.get("SOLSTICE_DEMO_TOKEN") or None
    return DeploymentAccessGuard(limiter, demo_token)


def client_key(request: Request) -> str:
    """Best-effort client identity for rate limiting.

    Behind a platform proxy the real client is the first hop of X-Forwarded-For;
    otherwise the direct peer. Spoofable in principle, which is acceptable because
    the OpenAI account cap — not this key — is the financial backstop.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client is not None:
        return request.client.host
    return "unknown"


def enforce_deployment_guard(request: Request) -> None:
    """FastAPI dependency — applied ONLY to POST /v1/ask."""
    guard: DeploymentAccessGuard = request.app.state.cost_guard
    guard.check(client_key(request), request.headers.get("x-demo-token"))
