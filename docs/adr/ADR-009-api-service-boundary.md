# ADR-009: API Service Boundary

- **Status:** Accepted
- **Date:** Milestone 2, Phase G
- **Context area:** Exposing the frozen Milestone 1 backend as a public service

## Problem

Milestone 1 is a library with no public interface. It must be exposed as a
production-quality HTTP service without modifying the frozen backend, and the
public contract must be stable enough to freeze while remaining independent of
implementation details.

## Decision

A FastAPI service in `app/api/` is the **sole public interface** to the backend.
It owns HTTP transport, request validation, dependency injection, response
serialization, and mapping between internal models and the public contract — and
**no** business, SQL, validation, or presentation logic. The dependency arrow
points one way: `api/` imports from the backend; the backend never imports from
`api/`.

### Construct-once / inject-per-request
The `AnalyticsAssistant` is built once in the `lifespan` context manager
(warehouse introspected once, `OpenAIClient` constructed once — no OpenAI call
at startup) and injected into each request via FastAPI dependency injection.
Rejected per-request construction as wasteful and slow. Chose `lifespan` over the
legacy `@app.on_event` startup hooks because it puts resource creation and
teardown in one place with explicit ownership.

### Fail-fast configuration
Mandatory configuration (OpenAI key, model, warehouse path) is validated at
startup; the app refuses to boot if any is missing. Rejected failing on first
request: a deployment platform should learn of misconfiguration when the
container fails to start, not when a user gets a 500.

### Versioned, frozen contract
Endpoints live under `/v1` from day one; versioning is architectural, not
retrofitted. The public models (`app/api/models.py`) are Pydantic and are the
frozen contract, deliberately separate from the internal result types so
internal refactors cannot silently change the public API.

### HTTP semantics
Pipeline outcomes (validation rejected, no query, execution failed) return
**200 OK with a `status` field** — a refusal is a successful response describing
a non-success outcome. Only genuine API/infrastructure failures use 4xx/5xx:
422 (malformed request, automatic via Pydantic), 503 (backend/warehouse
unavailable), 404 (unknown route).

### Implementation details excluded from the contract
Response metadata carries only consumer-stable facts (request ID, stage,
execution time, row count, truncation, validation outcome). Provider and model
name are internal-only — logged if needed, never returned — so the model can
change without breaking the frozen contract.

### Structured answer, no narrative (consistent with ADR-008)
The API returns structured `columns`/`rows` plus the M1 template `explanation`.
It does not add an LLM-generated answer string; interpreting the data remains the
consumer's job.

### `status` vs `metadata.stage` — two deliberate vocabularies
`status` is the **outcome category** the consumer acts on (from the formatter's
`ResponseStatus`: `success | no_query | validation_rejected | execution_failed |
api_error`). `metadata.stage` is the **pipeline diagnostic** for debugging (from
`PipelineStage`). They intentionally use different vocabularies because they
serve different audiences — application logic reads `status`; a developer
debugging reads `stage`. This is a documented decision, not an inconsistency.

### Mapping layer is structural-only
`app/api/mapping.py` performs structural transformation only — reshaping,
field renaming, enum translation, type conversion. It contains no business, SQL,
validation, presentation logic, or result interpretation, which keeps it
permanently small and prevents it from becoming a catch-all.

### Correlation ID at the edge
A request-ID middleware generates a UUID for **every** request before routing,
so requests that fail early (e.g. 422) still receive a traceable ID. The ID
appears in logs, in `metadata.request_id`, and in the `X-Request-ID` response
header.

### Logging philosophy
Logs record system behavior for debugging (request ID, endpoint, stage, outcome)
and never user prompts, returned data, or secrets — enough to diagnose a problem,
never enough to leak a user's data.

## Consequences

The backend stays frozen behind a stable, versioned, implementation-independent
contract; the presentation layer (Phase H) and any future client (React, Slack,
CLI) consume only this API. The API layer is intentionally thin — nearly all
engineering complexity remains inside the governed backend pipeline.

Trade-off: a thin mapping layer duplicates the *shape* of the internal response,
accepted deliberately so internal refactors cannot silently break the public
contract. Testing stays fully deterministic and zero-cost: every API test uses a
FakeLLMClient-backed assistant injected via dependency override, so no test
spends an OpenAI token.

Verification: Phase G was validated through automated tests, operational endpoint verification, successful governed query execution, invalid request handling, and truthful "no query" pipeline behavior before being frozen for future milestones.
