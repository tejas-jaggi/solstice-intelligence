# ADR-012: Deployment Architecture & Cost Safety

- **Status:** Accepted
- **Date:** Milestone 3, Phase C
- **Context area:** Publishing the governed pipeline as a live, public service

## Problem

The system is a working governed pipeline but has never run outside a developer's
machine. Publishing it introduces a risk that does not exist locally: `POST /v1/ask`
makes a real, paid OpenAI call per request against a key with no access control and
no rate limit. A naive public deployment is therefore an open door to unbounded API
spend and abuse. Separately, the certified warehouse the app reads lives in a
different repository and is referenced by an absolute local path — a deployed
container cannot depend on that. Phase C must publish the pipeline reproducibly,
protect the key and the spend, and package the warehouse, all without changing the
frozen governed engine.

## Decision

### A. Deployment Access Guard (route-level, not middleware)

A guard is attached as a FastAPI dependency on `POST /v1/ask` only. It is
deliberately *not* global middleware: the concern applies to exactly one endpoint —
the one that spends money — so scoping it to that route keeps the free endpoints
(`/health`, `/ready`, `/version`, `/docs`) untouched, localizes the trust boundary,
and is unit-testable via dependency override. It runs after the existing request-ID
middleware, so refused requests still carry a correlation ID.

This is **not authentication**. Authentication as a product feature remains deferred
(see non-goals). The guard exists solely to protect OpenAI spend on a public
demonstration deployment.

The guard has two parts:

1. **Rate limiter (always evaluated).** A deterministic in-memory fixed-window
   counter, keyed per client, that returns HTTP 429 once a client exceeds N requests
   per window. It takes an injectable time source so tests advance time explicitly
   and never sleep — preserving deterministic, zero-cost testing. `N <= 0` disables
   limiting entirely, which is how local development and the test suite run with the
   guard as a pass-through. Fixed-window was chosen over sliding-window-log (heavier),
   token/leaky bucket (more state), and any external store such as Redis (rejected:
   breaks portability, zero-dependency, and deterministic testing for a
   single-instance demo). Known limitation: in-memory state is per-instance and
   resets on restart; a horizontally-scaled product would need a shared store.
   Acceptable because the deployment is single-instance and the account cap (below)
   is the real financial backstop.

2. **Demo Access Gate (optional).** When a demo token is configured via environment,
   `/ask` additionally requires it; when unset, `/ask` is open (rate-limited only).
   Enabling it later requires the trusted frontend to attach the token header — a
   backward-compatible, env-gated frontend change, deferred until needed.

### B. OpenAI account hard budget cap (financial backstop)

A hard monthly spend ceiling is set on the OpenAI account itself. It is
platform-independent, requires no code, and guarantees the bill cannot exceed the cap
even if every in-app guard were misconfigured. It is set before the service is
exposed.

### C. Certified warehouse as a bundled deployment artifact

The certified `solstice_apparel.duckdb` (~34.5 MB) is copied once into this
repository's `data/` directory and baked into the image (`COPY data/`), with
`WAREHOUSE_PATH` defaulting to the repo-relative path. The file is opened read-only
and never modified, so the frozen-warehouse guarantee is preserved: this is a copy of
a certified artifact, never a regeneration. Its SHA-256 is recorded in
`data/README.md` so the bundled copy is verifiably the certified one.

Alternatives rejected: generating the warehouse at build (reintroduces the external
repository dependency and risks drift from the certified copy); fetching from object
storage at startup (adds infrastructure, credentials, network, and a cold-start
failure mode); a git submodule to the producer repo (couples the repositories). Git
LFS was considered and set aside: for a single frozen 34.5 MB file, a plain committed
artifact is simpler and well within limits.

### Artifact Provenance

The bundled warehouse is intentionally treated as an **immutable deployment artifact**
rather than repository-owned source data. The authoritative source remains the
separate Customer Revenue Analytics repository, which creates, validates, certifies,
and freezes the warehouse. Solstice Intelligence is a read-only consumer that packages
the certified artifact solely for reproducible deployment. The bundled database is
intentionally copied, never regenerated or modified. Updating the bundled artifact
requires recertifying the upstream warehouse and replacing the file — not rebuilding
or regenerating it during deployment. This is why a database file is committed to the
repository: it is a versioned, certified artifact of a separate producer, not mutable
application state.

### D. Reproducible container

- **Base image pinned by digest** (`python:3.14-slim-bookworm@sha256:…`), not merely by
  tag, so the build is reproducible even if a tag is re-pushed.
- **Non-root execution**: the image creates and runs as an unprivileged user; the app
  needs only read access to the warehouse and a high port.
- **Runtime-only dependencies**: the image installs `requirements.txt` only, never
  `requirements-dev.txt` — a direct payoff of the Phase B split.
- **Explicit, pinned model**: `OPENAI_MODEL` is an explicit deployment variable set to
  a dated model snapshot (e.g. `gpt-4o-2024-08-06`), never a floating alias such as
  `gpt-4o` or "latest". A floating model would make deployment behavior non-reproducible
  as the alias moves.
- **Secret injection**: `OPENAI_API_KEY` is provided at runtime via the platform's
  secret mechanism; it never appears in an image layer, the repository, or a log line
  (logging already excludes secrets and user data). `.dockerignore` excludes `.env`,
  VCS, caches, and dev files.
- **Deterministic build**: pinned base by digest + pinned deps + pinned warehouse +
  cache-friendly layer order (dependencies before code and data).

### E. Health and readiness as the deployment contract

`/health` is liveness (process up; no I/O, no OpenAI) and drives process restart.
`/ready` is readiness (assistant constructed, warehouse reachable; no OpenAI) and
gates traffic. Neither ever triggers a model call, so a platform may poll them
freely at zero cost. The existing handlers already satisfy this; they are unchanged.

### F. Truthful public version metadata

The public `/version` endpoint is single-sourced from `pyproject.toml`
(`[project].version` and `[tool.solstice].milestone`), replacing previously-hardcoded
constants that had drifted. `pyproject.toml` remains the sole version definition; no
runtime version module is introduced.

### G. CI extension (consistent with ADR-011)

CI additionally **builds** the image — deterministic, so a build failure blocks — and
runs an **advisory image vulnerability scan** that never gates, because its CVE
database changes over time and would otherwise make the same commit pass or fail
depending on when CI ran. This is the exact blocking-vs-advisory principle ADR-011
established, extended to the container layer. The build requires no secret and makes
no model call, preserving zero-cost, deterministic CI.

## Scope of change to frozen layers

Phase C is not purely additive. The governed engine (validation, execution, llm,
formatting, warehouse) is unchanged. The only edits to frozen files are: attaching the
guard dependency to `POST /v1/ask`, and single-sourcing `/version` — both in
`app/api/routes.py`/`app/api/main.py`, edge concerns that add no business, SQL,
validation, or presentation logic and do not alter the pipeline's behavior for an
allowed request. These controlled touches are the reason this ADR exists.

## Explicit non-goals

Not authentication, user accounts, sessions, or authorization as product features; not
multi-tenancy; not autoscaling or a shared-state rate limiter; not an observability
platform; not any change to what a permitted query does.

## Consequences

The pipeline becomes publicly demonstrable from a reproducible, self-contained,
non-root image with the warehouse bundled and the key protected, and unbounded spend
is made structurally impossible by layered guards with an account-level financial
backstop. The demo runs frictionless with the gate off. Trade-offs, accepted: the
rate limiter is per-instance; the guard adds one edit to a frozen edge file; enabling
the optional token later requires a small frontend change; and the runtime image
carries the frontend libraries it does not run (a consequence of the runtime/dev split
being role-based, not process-based) — a minor, acceptable inefficiency. CI stays
deterministic, secret-free, and zero-cost; the one live end-to-end check remains a
manual post-deploy step.
