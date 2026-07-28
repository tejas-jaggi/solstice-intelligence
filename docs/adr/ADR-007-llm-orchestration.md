# ADR-007: LLM Orchestration & Tool-Calling

- **Status:** Accepted
- **Date:** Phase E, Milestone 1
- **Context area:** Connecting the LLM to the validated execution pipeline

## Problem

A natural-language question must become a validated, executed query without the
orchestration layer bypassing validation/execution or absorbing business logic,
and without making the pipeline untestable due to an external API dependency.

## Decision

A single public service, `AnalyticsAssistant.ask(question) ->
OrchestrationResult`, coordinating: prompt assembly (Phase B grounding) -> LLM
client proposes a query via tool-calling -> validation gate (Phase C) ->
execution engine (Phase D) -> typed result.

### One public service, one internal seam
There is a single linear workflow (one entry: a question; one exit: a result),
so one orchestration service is the right scope — multiple services are
justified only by multiple distinct workflows, which do not exist yet.
Internally, the OpenAI client is isolated behind an `LLMClient` protocol so the
orchestrator is testable with a `FakeLLMClient` and zero network calls. This
seam is what keeps the whole layer deterministic-testable.

### Provider: OpenAI Responses API
Implemented against the Responses API, isolated entirely within `client.py`.
The orchestrator, prompts, tools, and every test depend only on the protocol, so
the provider choice is a one-file concern.

### One tool
The model's only sanctioned action is `run_query(sql)`. A refusal tool is
unnecessary (no tool call = no query); a schema-retrieval tool is unnecessary at
12 tables (whole schema fits in context) and is deferred. Minimal tool surface =
minimal attack surface.

### Prompt is quality, not security
The system prompt (role + rules + Phase B grounding) encourages safe, correct
SQL; the gate GUARANTEES it. Even if the model ignores every instruction, the
gate rejects unsafe SQL. The prompt authors no schema — it consumes
build_grounding_context, preserving single-source-of-truth.

### Typed result + pipeline stage
`OrchestrationResult` carries a `PipelineStage` enum
(NO_QUERY_PROPOSED | VALIDATION_REJECTED | EXECUTION_FAILED | COMPLETED |
API_ERROR) plus observability metadata: candidate SQL, validation outcome,
execution outcome, model name, timing. The stage field is the primary debugging
artifact — it says exactly where the pipeline concluded.

## Failure handling

Handled now: no tool call (prose/refusal), malformed/empty tool args, unsafe or
hallucinated SQL (caught by the gate, surfaced), execution errors (surfaced),
and API failures (typed API_ERROR, never a raw provider exception).

Deferred (documented): retry/backoff, automatic gate-rejection repair loops,
schema-retrieval tools, and prompt-overflow mitigation — all post-Milestone-1.

## Consequences

Clean coordinator preserving the A-D layering; provider swappable in one file;
fully deterministic tests via FakeLLMClient. Honest limitation: the real
`OpenAIClient` talks to a live API and is not covered by deterministic tests —
mitigated by keeping it thin (minimal untested surface) and marking it for live
verification. Exact Responses-API response field paths may need adjustment to
the installed SDK version; this is contained to `client.py._extract`.
