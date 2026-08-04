# Architecture State — Solstice Intelligence

**Snapshot as of:** Milestone 3, Phase D (release engineering) — release `v1.2.4`
**Purpose:** the authoritative architecture reference. A new engineer should be
able to read this document and understand the system without reading the project's
development history. This describes *architecture*, not history.

---

## 1. Repository Purpose

Solstice Intelligence is a **governed natural-language analytics assistant**. A
user asks a business question in plain English; the system produces a validated
answer computed against a dimensional data warehouse, and returns the exact SQL
that ran alongside a plain-English explanation.

Its defining property is governance: a large language model (LLM) proposes SQL,
but that SQL is treated as untrusted and must pass a strict validation gate before
anything executes. The organizing principle throughout is:

> **The LLM reasons. The warehouse provides truth. Validation decides trust.**

The LLM never touches the database directly.

---

## 2. High-Level Architecture

```mermaid
flowchart TD
    U[User] --> FE[Streamlit frontend]
    FE -->|HTTP only| API[FastAPI service /v1]
    API --> ORC[AnalyticsAssistant orchestrator]
    ORC --> GND[Schema grounding]
    ORC --> LLM[LLM client - proposes SQL]
    LLM --> GATE[Validation gate]
    GATE -->|approved| EXEC[Read-only executor]
    GATE -->|rejected| REFUSE[Safe refusal]
    EXEC --> WH[(DuckDB warehouse)]
    EXEC --> FMT[Response formatter]
    REFUSE --> FMT
    FMT --> API
    API --> FE
```

Two processes at runtime: the **backend service** (FastAPI over the governed
engine) and the **frontend** (Streamlit). They communicate only over HTTP. In a
public deployment the paid endpoint is protected by the Deployment Access Guard
(§14); the operational endpoints stay open and never call the LLM.

---

## 3. Layered Architecture

```mermaid
flowchart LR
    subgraph Presentation
      FE[frontend/]
    end
    subgraph Transport
      API[app/api/]
    end
    subgraph Orchestration
      ORC[app/llm/orchestrator]
    end
    subgraph Governance
      GND[app/semantic + app/metadata]
      GATE[app/validation]
    end
    subgraph Execution
      EXEC[app/execution]
      WH[app/warehouse]
    end
    subgraph Presentation-of-Result
      FMT[app/formatting]
    end
    FE -->|HTTP| API --> ORC
    ORC --> GND --> GATE --> EXEC --> WH
    ORC --> FMT
```

Dependencies point in one direction: presentation depends on transport, transport
depends on the engine, the engine depends on the warehouse. Nothing lower depends
on anything higher. The frontend depends on nothing in `app/` — only on the HTTP
contract.

---

## 4. Directory Structure

```
app/
    config.py settings loading
    warehouse/     read-only DuckDB connection + schema introspection
    metadata/      structural warehouse metadata
    models/ reserved namespace for shared internal models (currently empty)
    semantic/      grounding: presenting the schema to the LLM
    validation/    SQL validation gate (parsing, rules, bounds, decision, gate)
    execution/     read-only query executor + typed results
    llm/           LLM client, tool definition, orchestrator (AnalyticsAssistant)
    formatting/    deterministic response formatting (formatter, response, templates)
    api/           init.py, access_guard.py Deployment Access Guard (rate limiter + optional demo gate), build_info.py version/milestone reader (single-sourced from pyproject), dependencies.py DI providers (get_assistant, ...), main.py app factory, lifespan, request-ID middleware, guard state, mapping.py internal result -> public contract, models.py frozen public /v1 request/response contract, routes.py HTTP handlers (/v1/ask, /health, /ready, /version)
frontend/
    config.py      presentation/client config (API URL, timeout, page)
    models.py      typed mirror of the public API contract + client Protocol
    api_client.py  the sole HTTP boundary (RealApiClient)
    fake_client.py test double implementing the same Protocol
    components.py  pure rendering functions
    streamlit_app.py  the UI entry point
    frontend/tests/    frontend tests
scripts/
    init.py developer tooling package (not part of the runtime pipeline)
    verify_env.py deterministic environment diagnostic
    check_version.py deterministic version-consistency checker (release)
    inspect_schema.py, smoke_test_openai.py developer utilities
data/
    solstice_apparel.duckdb bundled certified warehouse artifact (~34.5 MB, read-only)
    solstice_apparel.duckdb.sha256 canonical machine-readable checksum (validated at release)
    README.md provenance
tests/             backend tests
docs/    
    adr/          ADR-004 … ADR-012
    assets/ UI screenshots / demo
    developer/ Developer_Guide.md, Deployment_Guide.md, Release_Guide.md
    phase_completion_milestone3/ Phase_A/B/C/D completion reports
.github/
    workflows/ ci.yml CI: "can this merge?" (quality + image jobs), release.yml Release: "can this become an official release?" (tag-driven)
Dockerfile, .dockerignore reproducible image (digest-pinned base, non-root, runtime-only)
render.yaml deployment blueprint
requirements.txt runtime dependencies (pinned ==)
requirements-dev.txt development / tooling dependencies (pinned ==)
justfile developer task runner (convenience)
pyproject.toml     centralized tool configuration and the SOLE version definition
CHANGELOG.md Keep-a-Changelog release history
README.md, LICENSE
```

Project version metadata is maintained solely in `pyproject.toml`
(`[project].version`). There is no separate runtime version module.

---

## 5. Responsibilities of Every Major Package

- **`app/warehouse`** — opens the DuckDB warehouse read-only and introspects its
  live schema. The physical read-only guarantee originates here.
- **`app/metadata`** — a typed, structural description of the warehouse used to
  ground the LLM and validate references.
- **`app/models`** — a reserved namespace for shared internal models. Currently
  empty; models owned by a single layer live with that layer.
- **`app/semantic`** — grounding: turning metadata into the schema context shown
  to the LLM.
- **`app/validation`** — the trust boundary. Parses proposed SQL, applies rules
  (read-only only, real tables only, no dangerous constructs), enforces bounds,
  and produces an approve/reject decision.
- **`app/execution`** — runs only approved queries, read-only, with an independent
  row-cap backstop; returns typed results.
- **`app/llm`** — the LLM client (the sole place the AI SDK is used), the single
  tool the model may call, and the orchestrator.
- **`app/formatting`** — turns pipeline outcomes into a structured response and a
  template explanation; never lets the LLM interpret data.
- **`app/api`** — the FastAPI service: the frozen public `/v1` contract, request
  validation, DI, health/readiness/version endpoints, the internal→public mapping,
  the Deployment Access Guard, and version metadata (`build_info.py`).
- **`frontend`** — the Streamlit presentation layer, a pure HTTP client of the API.

---

## 6. Data Flow

1. A question arrives (frontend → API, or directly to the API).
2. The orchestrator grounds the question in the live schema.
3. The LLM proposes SQL by calling the single permitted tool.
4. The proposed SQL passes through the validation gate.
5. If approved, the read-only executor runs it; if rejected, a safe refusal is produced.
6. The formatter builds a structured response plus a plain explanation and the exact SQL.
7. The API returns the public-contract response; the frontend renders it.

---

## 7. LLM Boundaries

- The LLM is reached through exactly one module (`app/llm/client.py`).
- Its only sanctioned action is to call one tool that proposes a SQL string.
- The proposed SQL is powerless until the validation gate approves it.
- The LLM never executes SQL, never sees raw results to interpret, and never
  narrates the answer — explanations are template-based and deterministic.
- The provider/model identity is internal and never appears in the public contract.

---

## 8. Validation Pipeline

Allowlist-first, defense-in-depth, pure (`validate(sql, schema) -> result`):
parse (DuckDB dialect) → read-only statement type → every source allowlisted
against real warehouse tables (table functions and empty-named sources rejected
structurally) → column checks → function denylist → bounds (LIMIT injected/clamped)
→ approve or reject. A rejection is a legitimate, explained outcome.

---

## 9. Execution Pipeline

Accepts only gate-approved SQL (a typed trust boundary), executes read-only against
DuckDB, applies an independent row-cap backstop, and returns typed results
(columns, rows, count, truncation flag, timing). Runtime SQL errors are captured as
structured errors, never raw tracebacks.

---

## 10. Frontend Architecture

A thin Streamlit client whose only backend contact is HTTP to the `/v1` API. One
module (`api_client.py`) owns the HTTP implementation behind a small `Protocol`;
rendering components are pure. Each request sends exactly one question (single-turn
by design); a render-only transcript provides conversational feel.

---

## 11. Testing Architecture

- **Deterministic and zero-cost.** The LLM is substituted with a fake client and
  HTTP is mocked; no test needs the network, a real AI call, or secrets.
- Backend tests cover each engine layer, the API contract and HTTP semantics, and
  adversarial validation cases.
- Frontend tests cover the API client, pure components, and the interaction flow.
- Tooling tests cover the environment diagnostic (`verify_env.py`), the Deployment
  Access Guard, version metadata (`build_info.py`), and the version-consistency
  checker (`check_version.py`).
- The assembled Streamlit UI is verified manually (honest scoping).

Current suite: **135 tests passing**,
**88% coverage**

---

## 12. Dependency Philosophy

One-way dependency flow, no cycles. Each external system is isolated behind a single
module (AI SDK behind the LLM client; HTTP behind the API client) for minimal blast
radius. The frontend couples to the public contract, never to internal types.
Runtime and development dependencies are separated (`requirements.txt` /
`requirements-dev.txt`) and pinned exactly, so installs are reproducible and the
blocking gates are deterministic.

---

## 13. CI/CD Architecture

Two workflows with different guarantees:

```mermaid
flowchart LR
    push[Push / PR] --> ci[CI: can this merge?]
    ci --> q[quality job: ruff + pytest + mypy]
    ci --> img[image job: docker build + advisory scan]

    tag[Tag v*] --> rel[Release: can this become a release?]
    rel --> ver[verify: version-consistency + warehouse SHA + re-run gates]
    ver --> pub[publish: build + GHCR push + advisory scan]
    pub --> gh[release: GitHub Release from CHANGELOG]
```

- **CI** (`ci.yml`) runs on every push/PR: a **quality** job (blocking Ruff, pytest,
  mypy; advisory coverage and pip-audit) and an **image** job (blocking `docker
  build`; advisory Trivy scan).
- **Release** (`release.yml`) runs on `v*` tags (and manual `workflow_dispatch`):
  an independent, higher-assurance verification — version consistency, warehouse
  provenance (SHA-256 sidecar), and a re-run of the blocking gates — then image
  build, GHCR publish (built-in `GITHUB_TOKEN`, least privilege), and GitHub Release
  creation from `CHANGELOG.md`.

Both use no secrets beyond `GITHUB_TOKEN` and spend no OpenAI credit. CI and the
release workflow answer intentionally different questions ("can this merge?" vs
"can this become an official release?"), so the release workflow's re-run of the
gates is independent verification, not duplication.

---

## 14. Deployment Architecture

- Packaged as a reproducible Docker image: base pinned by digest, non-root
  execution, runtime dependencies only, cache-friendly layer order.
- `OPENAI_MODEL` is pinned to a dated snapshot (never a floating alias).
- The certified warehouse is bundled read-only as an immutable artifact with a
  machine-readable SHA-256 sidecar validated at release time.
- **Deployment Access Guard** (ADR-012): a route-level dependency on `POST /v1/ask`
  combining a deterministic in-memory fixed-window rate limiter (injectable clock)
  and an optional Demo Access Gate token. It exists solely to protect OpenAI spend —
  not authentication. It defaults to disabled (pass-through), so local development
  and CI are unaffected; a deployment enables it via environment variables. An
  OpenAI account hard budget cap is the platform-independent financial backstop.
- `OPENAI_API_KEY` is injected as a platform secret; it never appears in an image
  layer, the repository, or a log line.
- `/health` (liveness) and `/ready` (readiness) never call the LLM, so they are free
  to poll. Deployment blueprint: `render.yaml` (Cloud Run / Fly.io equivalent).

---

## 15. Release Engineering

`pyproject.toml` is the single version source; `GET /version` derives from it via
`build_info.py`; `scripts/check_version.py` enforces tag ↔ `pyproject` at release
time (transitively guaranteeing tag ↔ `/version`). Releases are tag-driven and
verified before anything is published; images are published to GHCR; GitHub Releases
are generated from `CHANGELOG.md`. See `docs/developer/Release_Guide.md`.

---

## 16. ADR Summary

| ADR | Subject |
|---|---|
| ADR-004 | Structural metadata layer |
| ADR-005 | SQL validation gate |
| ADR-006 | Execution engine |
| ADR-007 | LLM orchestration |
| ADR-008 | Response formatting (deterministic, no LLM narration) |
| ADR-009 | API service boundary (frozen `/v1` contract, HTTP semantics, lifecycle) |
| ADR-010 | Frontend–backend HTTP boundary |
| ADR-011 | CI & quality-gate policy (blocking vs advisory; mypy promotion) |
| ADR-012 | Deployment architecture & cost safety (guard, bundled warehouse, image) |

Release engineering (Phase D) introduced no new architectural decision and no ADR:
it is workflow automation and repository infrastructure, consistent with the
"every tool must justify its cost / ADRs record architecture, not workflow"
principle.

---

## 17. Important Invariants

- The LLM is never trusted to execute SQL directly; only gate-approved SQL reaches
  the executor.
- Execution is read-only, with an independent row-cap backstop.
- The frontend never imports backend modules — HTTP only.
- The public API contract excludes implementation details (provider/model).
- Explanations are template-based; the LLM never narrates results.
- CI and the release workflow require no secrets beyond `GITHUB_TOKEN` and spend no
  API credit.
- The Deployment Access Guard defaults to disabled and never affects local dev/CI.
- `pyproject.toml` is the sole version definition; releases are verified tag-driven
  events; the bundled warehouse is validated against its recorded provenance.

---

## 18. Files That Should Rarely Change

- The validation gate (`app/validation/*`) — the security-critical trust boundary.
- The execution engine (`app/execution/*`) — the read-only guarantees.
- The public API models (`app/api/models.py`) — the frozen contract.
- The LLM client boundary (`app/llm/client.py`) — the single SDK contact point.
- The ADRs — historical decisions; add new ones rather than rewriting old ones.

---

## 19. Extension Points

- **New clients** (React, CLI, chat bots) — build against the frozen `/v1` contract.
- **New analytics capability** — extend the engine behind the API without altering
  the contract.
- **New quality checks** — add advisory CI steps; promote to blocking once clean.
- **Operational hardening** (Phase E) — structured logging, graceful shutdown,
  timeouts, startup diagnostics — additive, not a redesign.

---

## 20. Technical Debt

- Minor, cosmetic: raw floating-point execution-time values are not rounded for
  display; to be folded into a future UI/operational touch. No structural or
  security debt is outstanding; the type checker is at zero findings.

---

## 21. Future Evolution Considerations

- Remaining Milestone 3 phase: **E — Operational Hardening** (structured logging,
  graceful shutdown, timeouts, startup diagnostics — operational, not architectural
  redesign). Milestone 3 completes at **v1.3.0**.
- Deferred by design: conversation memory / multi-turn, authentication as a product
  feature, caching, automatic query-repair loops, usage persistence, shared-state
  rate limiting. Each is a deliberate future option, not an accidental omission.
- Any future change to a frozen layer should be justified by an ADR.
