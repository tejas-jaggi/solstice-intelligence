"""LLM client boundary.

This module is the ONLY place the OpenAI SDK is imported. Everything upstream
(the orchestrator) depends on the LLMClient protocol, never on OpenAI directly —
so the provider can change (or be faked in tests) without touching orchestration.

The client's job is narrow: given a system prompt, a user question, and the
run_query tool definition, return what the model proposed — either a candidate
SQL string (the model called run_query) or a natural-language message (the model
declined / answered in prose). The client does not validate, execute, or format.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class LLMError(RuntimeError):
    """Raised by a client when the provider call fails (network, auth, etc.).

    The orchestrator catches this and turns it into a typed API_ERROR outcome;
    it never propagates as a raw provider exception.
    """


@dataclass(frozen=True)
class ProposedQuery:
    """What the model proposed in response to a question.

    Exactly one of (sql) / (message) is meaningful:
      * sql is set when the model called run_query -> a candidate query to
        validate.
      * message is set when the model did NOT call the tool (declined, asked for
        clarification, or answered in prose) -> no query to run.
    """

    sql: str | None
    message: str | None

    @property
    def has_query(self) -> bool:
        return self.sql is not None and self.sql.strip() != ""


class LLMClient(Protocol):
    """Protocol the orchestrator depends on. Implemented by OpenAIClient and
    FakeLLMClient."""

    model_name: str

    def propose_query(self, system_prompt: str, question: str) -> ProposedQuery:
        """Ask the model to propose a query via the run_query tool."""
        ...


class FakeLLMClient:
    """Deterministic, network-free client for tests.

    Scripted to return a fixed ProposedQuery (or raise LLMError), so orchestration
    tests exercise the full real pipeline (prompt -> gate -> executor) without any
    provider call.
    """

    def __init__(
        self,
        *,
        sql: str | None = None,
        message: str | None = None,
        raise_error: bool = False,
        model_name: str = "fake-model",
    ) -> None:
        self._sql = sql
        self._message = message
        self._raise = raise_error
        self.model_name = model_name

    def propose_query(self, system_prompt: str, question: str) -> ProposedQuery:
        if self._raise:
            raise LLMError("simulated provider failure")
        return ProposedQuery(sql=self._sql, message=self._message)


class OpenAIClient:
    """OpenAI Responses API implementation of LLMClient.

    Kept intentionally thin: it assembles the request, calls the Responses API
    with the run_query tool, and extracts either the tool-call SQL or a text
    message. All validation/execution/formatting happens elsewhere.

    NOTE: This is the one component that requires live verification against the
    installed OpenAI SDK version, since exact field paths on the Responses API
    response object can vary by SDK release. The extraction below targets the
    documented tool-call structure; adjust field access if your SDK differs.
    """

    def __init__(self, model_name: str, tool_schema: dict) -> None:
        # Import here so the SDK is only required when actually using OpenAI
        # (tests use FakeLLMClient and never import this path).
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise LLMError(
                "openai package is not installed; install it or use a different client."
            ) from exc
        self._client = OpenAI()  # reads OPENAI_API_KEY from environment
        self.model_name = model_name
        self._tool_schema = tool_schema

    def propose_query(self, system_prompt: str, question: str) -> ProposedQuery:
        try:
            response = self._client.responses.create(
                model=self.model_name,
                instructions=system_prompt,
                input=question,
                tools=[self._tool_schema],
            )
        except Exception as exc:  # pragma: no cover - network/provider dependent
            raise LLMError(f"OpenAI request failed: {exc}") from exc

        return self._extract(response)

    @staticmethod
    def _extract(response) -> ProposedQuery:  # pragma: no cover - shape-dependent
        """Extract a run_query tool call (or a text message) from a Responses
        API result.

        Walks the response output items looking for a function/tool call named
        'run_query'; if found, parses its arguments for 'sql'. Otherwise collects
        any text output as a message.
        """
        import json

        sql: str | None = None
        text_parts: list[str] = []

        for item in getattr(response, "output", []) or []:
            itype = getattr(item, "type", "")
            name = getattr(item, "name", "")
            if itype in ("function_call", "tool_call") and name == "run_query":
                raw_args = getattr(item, "arguments", "") or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    candidate = args.get("sql")
                    if isinstance(candidate, str):
                        sql = candidate
                except (json.JSONDecodeError, AttributeError):
                    sql = None
            elif itype == "message":
                for block in getattr(item, "content", []) or []:
                    txt = getattr(block, "text", None)
                    if txt:
                        text_parts.append(txt)

        message = " ".join(text_parts).strip() or None
        return ProposedQuery(sql=sql, message=message)
