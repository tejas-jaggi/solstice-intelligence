# ADR-013: Operational Observability & Resilience

- **Status:** Accepted
- **Date:** Milestone 3, Phase E
- **Context area:** Operating the deployed service safely and legibly

## Problem

The service is built, deployed, and released reproducibly, but was not yet hardened
for operation. Three gaps remained: (1) logging was ad-hoc and unstructured, so
operational behaviour was not queryable; (2) the LLM call had no request-level
timeout, so a slow upstream could hang a request indefinitely; (3) readiness
reflected a startup flag rather than current serve-ability, and there was no
structured account of startup. Phase E hardens the running service without changing
what the governed pipeline computes and without touching the frozen engine.

## Decision

### A. Structured, metadata-only logging (formal invariant)

Logging is configured once, deterministically and idempotently, in the application
factory via `app/api/logging_config.py`. Records are structured — JSON in
deployment (`StructuredFormatter`), human-readable text locally (`TextFormatter`) —
and carry a fixed field set: `timestamp`, `level`, `logger`, `message`, and
whitelisted operational extras (`request_id`, `stage`, `status_code`,
`duration_ms`, `event`). Only whitelisted keys are serialized, so arbitrary record
attributes cannot leak. The existing request-correlation ID (stamped by the
request-ID middleware) is reused. Setup is idempotent: repeated `create_app()`
calls attach exactly one handler.

This promotes ADR-009's logging discipline to a **formal, enforced repository
invariant**:

> **Operational logs are metadata-only.** They may contain request IDs, lifecycle
> events, timing, status codes, and operational diagnostics. They must **never**
> contain prompts, generated SQL, warehouse query results, model responses, user
> data, API keys, or secrets.

The invariant is enforced structurally (log call sites accept only fixed scalar
operational fields; the formatter serializes only whitelisted keys) and verified by
a deterministic end-to-end test that drives a full request and asserts the forbidden
values are absent from the captured logs.

### B. Repository-owned request timeout at the isolated LLM-client seam

The single isolated LLM boundary (`app/llm/client.py`) enforces a request-level
timeout. The value is repository-owned: a default of **60 seconds**, overridable via
`OPENAI_TIMEOUT_SECONDS`. A repository default (rather than the SDK's default) keeps
behaviour deterministic even if the SDK changes its default in a future release. On
timeout the client raises `LLMTimeoutError`, a **subclass of the existing
`LLMError`**, so the orchestrator's existing provider-failure handling maps it to
the same non-success (API_ERROR) outcome through the existing formatter — no new
public response shape, no orchestrator change, no `models.py` change. The timeout
lives at the client seam (how we call the SDK), never in orchestration, validation,
or execution logic.

### C. Graceful shutdown

The application lifespan drains in-flight requests within a bounded grace period
before tearing down resources, and emits structured startup and shutdown lifecycle
events. This extends the existing lifespan teardown seam; it does not redesign it.

### D. Live, inexpensive readiness; no-LLM diagnostics

`GET /ready` performs a minimal *live* local check — a trivial `SELECT 1` on the
read-only warehouse connection (`app/api/readiness.py`) — answering "can I serve a
request now?" rather than "did I once start?" It performs no metadata scan, no
expensive query, and **never** an LLM call, so it remains free to poll. Startup
emits metadata-only diagnostics (no secret values, no model call). `GET /health`
remains pure liveness.

## Rationale for preserving the frozen governed analytics engine

Operational hardening is an edge concern, not a pipeline concern. Structured logging
belongs where requests enter and leave (the API layer, which already owns the
correlation ID and lifecycle); a request timeout belongs where the process talks to
the provider (the single isolated SDK seam); readiness belongs at the transport
edge. Placing every change there keeps validation, execution, llm orchestration,
formatting, warehouse, and SQL generation byte-for-byte unchanged, so the security
and correctness guarantees those layers provide are unaffected. `LLMTimeoutError`
subclassing `LLMError` is the mechanism that let a new failure mode reuse the
existing non-success path rather than force an orchestrator or contract change.

## Explicit non-goals

Not an observability platform: no metrics endpoint, no tracing vendor, no dashboards,
no log aggregation backend. Not multi-turn, auth, caching, or any change to what a
permitted query computes. These are deferred beyond Milestone 3.

## Scope of change to frozen layers

None. The governed engine (validation, execution, llm orchestration, formatting,
warehouse, SQL generation) and the public API contract (`app/api/models.py`) are
unchanged. Edits are confined to the edge (logging configuration, lifecycle, and the
readiness handler in `app/api/`) and the isolated SDK seam (a timeout in
`app/llm/client.py`).

## Consequences

The running service is legible (structured, metadata-only logs keyed by the existing
correlation ID), resilient (a bounded, repository-owned LLM timeout that fails
safely; graceful shutdown), and truthful about readiness (a live cheap check). The
metadata-only logging rule is now a regression-guarded invariant. Accepted
trade-offs: logging setup mutates process-wide logging state (made idempotent and
tested via the formatter in isolation); local logs default to text for readability;
and the timeout mapping is tested via an injected condition rather than wall-clock
waiting. CI stays deterministic, secret-free, and zero-cost.
