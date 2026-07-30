"""A fake AnalyticsApiClient for deterministic, zero-cost frontend tests.

Implements the SAME protocol as RealApiClient, so it is a first-class client
injected via normal dependency passing — not a monkeypatch. Scripted to return a
fixed ApiResult or ApiError, so UI logic can be tested without any server,
network, or OpenAI call.
"""

from __future__ import annotations

from frontend.models import ApiError, ApiResult


class FakeApiClient:
    """Returns scripted outcomes; makes no network calls."""

    def __init__(
        self,
        outcome: ApiResult | ApiError | None = None,
        ready_value: bool = True,
    ) -> None:
        self._outcome = outcome
        self._ready = ready_value
        self.calls: list[str] = []  # records questions asked, for assertions

    def ask(self, question: str) -> ApiResult | ApiError:
        self.calls.append(question)
        if self._outcome is None:
            raise AssertionError("FakeApiClient was not given an outcome to return.")
        return self._outcome

    def ready(self) -> bool:
        return self._ready
