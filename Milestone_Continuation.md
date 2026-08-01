# Milestone Continuation — Solstice Intelligence

*Handoff for a new working session. Assumes access to the repository. Detailed
architecture lives in `Architecture_State.md`; reasoning lives in `Project_Bible.md`
and `docs/adr/`. This document is the quick-orientation layer only.*

---

## Repository snapshot

- **Version:** `pyproject.toml` `[project].version = 1.2.1` (Phase B complete;
  release `v1.2.2` planned).
- **Current milestone:** Milestone 3 — Production Engineering
- **Current phase status:** Phase A and Phase B — **complete**. Phases C–E not yet
  started.
- **Working tree:** clean; blocking gates green on Python 3.14.

---

## Architecture summary (one paragraph)

A governed natural-language analytics assistant. A user's plain-English question is
grounded in a live warehouse schema; an LLM proposes SQL; a validation gate approves
or rejects it; approved SQL runs read-only against a DuckDB warehouse; the result is
formatted with the exact SQL and a template explanation. A FastAPI service exposes a
frozen `/v1` contract; a thin Streamlit frontend consumes that contract over HTTP
only. Governing rule: **the LLM reasons, the warehouse provides truth, validation
decides trust** — the LLM never executes SQL directly.

---

## Important ADRs

- **ADR-005** — SQL validation gate (the security-critical trust boundary).
- **ADR-008** — deterministic response formatting (no LLM narration of results).
- **ADR-009** — API service boundary (frozen `/v1` contract, HTTP semantics,
  construct-once lifecycle).
- **ADR-010** — frontend–backend HTTP-only boundary.
- **ADR-011** — CI & quality-gate policy (blocking vs advisory; mypy promotion).

(ADR-004, 006, 007 cover metadata, execution, and orchestration respectively.)

---

## Current quality status

- Tests: **112 passing**.
- Coverage: **84%** (informational — not a gate).
- Ruff lint: clean. Ruff format: compliant.
- mypy: **0 issues across 43 source files**, a **blocking** gate.
- pip-audit: no known vulnerabilities (advisory).

---

## CI status

- GitHub Actions runs on every push and pull request on **Python 3.14**.
- Installs both `requirements.txt` and `requirements-dev.txt`; caches on both.
- **Blocking:** tests, Ruff (lint + format), mypy.
- **Advisory/informational:** coverage, pip-audit.
- CI uses **no secrets** and spends **$0** on the AI provider (deterministic suite).
- CI executes the tool commands directly; the `justfile` is developer convenience
  only and is not in the CI path.

---

## Testing status

- Deterministic and zero-cost: the LLM is faked, HTTP is mocked.
- Backend layers, API contract/HTTP semantics, and adversarial validation cases are
  covered. Frontend client, pure components, and flow are covered. The environment
  diagnostic (`scripts/verify_env.py`) is covered with deterministic fixtures.
- The assembled Streamlit UI is verified manually (by design).

---

## Current repository invariants (do not violate)

- The LLM never executes SQL directly; only gate-approved SQL reaches the executor.
- Execution is read-only, with an independent row-cap backstop.
- The frontend never imports backend modules — HTTP only.
- The public API contract excludes provider/model details.
- Explanations are template-based; the LLM never narrates results.
- Tests remain deterministic, secret-free, and zero-cost.
- Milestones 1 and 2 are frozen.

---

## Files that define repository behavior

- `app/validation/*` — the validation gate (security-critical).
- `app/execution/*` — read-only execution guarantees.
- `app/llm/client.py` — the sole LLM/SDK boundary.
- `app/api/models.py` — the frozen public contract.
- `app/api/main.py` / `routes.py` — service lifecycle and endpoints.
- `frontend/api_client.py` — the sole frontend HTTP boundary.
- `.github/workflows/ci.yml` + `pyproject.toml` — CI and quality-gate configuration.
- `pyproject.toml` — project metadata and the sole version definition
  (`[project].version`).
- `requirements.txt` / `requirements-dev.txt` — runtime and development dependencies.
- `justfile` — developer task runner (convenience; not in the CI path).
- `scripts/verify_env.py` — deterministic environment diagnostic.

---

## Already completed

- Milestone 1 (governed engine) — frozen.
- Milestone 2 (FastAPI `/v1` service; Streamlit frontend) — frozen.
- Milestone 3 Phase A (CI, quality gates, mypy promoted to blocking) — done,
  released as `v1.2.1`.
- Milestone 3 Phase B (developer experience: `just`, runtime/dev dependency split,
  `scripts/verify_env.py`, developer docs, CI aligned to Python 3.14) — done;
  release `v1.2.2` planned.

---

## Intentionally deferred

Conversation memory / multi-turn; authentication / access control; automatic
query-repair loops; caching; usage/observability persistence; observability
*platforms*. Each is a deliberate future option, not an omission.

---

## Recommended starting point for the next work

**Milestone 3, Phase C — Deployment.** Objective: deploy the API and frontend and
host them, producing the first live release. The defining concern is an explicit
guard against unintended AI cost on any public endpoint (no authentication or rate
limiting exists yet, and a live `POST /v1/ask` spends real API credit per call);
ADR-012 is expected to own that decision. Keep the deployment additive — no runtime
change to frozen layers. Follow the established process: architecture review →
design approval → implementation → automated verification → manual verification →
documentation → release.

Later phases: D — Release Engineering; E — Operational Hardening (structured
logging and diagnostics, not an observability platform). Milestone 3 completes at
**v1.3.0**.