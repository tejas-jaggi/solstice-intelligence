# ADR-010: Frontend–Backend HTTP Boundary

- **Status:** Accepted
- **Date:** Milestone 2, Phase H
- **Context area:** The presentation layer's relationship to the backend

## Problem

Phase G exposed the backend as a versioned REST API. The Streamlit frontend,
being Python in the same repository, could import and call the backend directly.
Whether it should is the defining architectural decision of Phase H.

## Decision

The frontend communicates with the backend **exclusively over HTTP through the
frozen `/v1` contract**. It never imports backend modules, shares no business
logic or orchestration, and designs against the public OpenAPI contract rather
than backend internals.

- **Ownership.** The frontend owns presentation, user interaction, rendering,
  and REST communication. The backend owns orchestration, business logic,
  validation, SQL generation, execution, and governance.
- **Typed public mirror.** The frontend defines its own small typed
  representation of the public contract (`ApiResult` / `ApiError`), never reusing
  internal backend types. `ApiResult` and `ApiError` are distinct types so the
  Phase G two-category HTTP semantics (a refusal is a 200 result; an unreachable
  API is a transport error) are enforced at the type level.
- **Client protocol.** A minimal `AnalyticsApiClient` protocol (`ask`, `ready`)
  is implemented by both `RealApiClient` and `FakeApiClient`, so tests inject a
  first-class fake rather than monkeypatching.
- **HTTP implementation is owned, not the library.** `api_client` owns the HTTP
  implementation behind the protocol; the underlying library (httpx today) can
  be replaced without touching the app or components.
- **Pure components.** Rendering components only render — never perform HTTP,
  mutate state, contain business logic, or return business data.
- **Request lifecycle.** Idle → Submitting → Waiting → Response → Idle governs
  the submit button, preventing duplicate submissions (and duplicate token
  spend).
- **Render-only transcript.** History is displayed but never resent; the backend
  receives exactly one independent question per request (conversation memory
  deferred).

## Alternatives considered

- **Direct import of `AnalyticsAssistant` in Streamlit.** Rejected: fuses
  frontend and backend into one unit, making Phase G's "replaceable frontend"
  property decorative, and re-exposes the OpenAI key path to the presentation
  layer.
- **A shared "core" library imported by both.** Rejected: the frontend needs
  none of the backend's logic, only its responses; a shared library would invent
  coupling that need not exist.

## How production systems solve this

Web architectures almost universally separate frontend and backend across an
HTTP (often REST) boundary so the two evolve and deploy independently, and so
multiple clients (web, mobile, bots) share one backend. This decision applies
that standard pattern.

## Future extensibility

Because the frontend is only an HTTP client of the frozen `/v1` contract, future
clients — a React app, a CLI, a Slack or Teams bot — can consume the same API
with **zero backend changes**. Each is simply another consumer of the same
contract:

    Streamlit → /v1 → backend
    React     → /v1 → backend
    CLI       → /v1 → backend
    Slack bot → /v1 → backend

This is the concrete payoff of the boundary and the reason ADR-010 exists.

## Consequences

The frontend is a true, replaceable client; the import graph mechanically
enforces the boundary (nothing in `frontend/` imports `app/`). Trade-off: the
frontend re-declares a small typed mirror of the public contract rather than
reusing backend types — accepted deliberately, because coupling to the public
contract is the point and coupling to internal types is what we prevent. Testing
stays fully deterministic and zero-cost via the fake client.
