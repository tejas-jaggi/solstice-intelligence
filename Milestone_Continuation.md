# Milestone Continuation — Solstice Intelligence

*Authoritative handoff for a new working session (Claude or ChatGPT). Assumes
access to the repository. Detailed architecture lives in `Architecture_State.md`;
reasoning lives in `docs/adr/`. This document is the quick-orientation layer.*

---

## Repository snapshot

- **Version:** `pyproject.toml` `[project].version` — release `v1.3.0`.
  `pyproject.toml` is the sole version definition; `GET /version` derives from it.
- **Current milestone:** **Milestone 3 — Production Engineering — COMPLETE.**
- **Phase status:** Phases A, B, C, D, and E — all **complete**.
- **Working tree:** clean; CI green; release workflow green; GHCR publishing live.

---

## Architecture summary (one paragraph)

A governed natural-language analytics assistant. A plain-English question is
grounded in a live warehouse schema; an LLM proposes SQL (the call is
timeout-bounded); a validation gate approves or rejects it; approved SQL runs
read-only against a DuckDB warehouse; the result is formatted with the exact SQL and
a template explanation. A FastAPI service exposes a frozen `/v1` contract; a thin
Streamlit frontend consumes it over HTTP only. Governing rule: **the LLM reasons,
the warehouse provides truth, validation decides trust** — the LLM never executes
SQL directly.

---

## Completed phases

- **Milestone 1** — governed engine (warehouse, grounding, validation gate,
  read-only execution, formatting) — frozen.
- **Milestone 2** — Phase G (FastAPI `/v1` service) and Phase H (Streamlit
  frontend) — frozen.
- **Milestone 3, Phase A** — CI & quality gates; mypy promoted to blocking (`v1.2.1`).
- **Milestone 3, Phase B** — developer experience: `just`, runtime/dev dependency
  split, `verify_env.py`, developer docs, CI on Python 3.14 (`v1.2.2`).
- **Milestone 3, Phase C** — deployment: reproducible Docker image, bundled
  certified warehouse, Deployment Access Guard, truthful `/version`, ADR-012
  (`v1.2.3`).
- **Milestone 3, Phase D** — release engineering: version-consistency checker,
  tag-driven release workflow, GHCR publishing, CHANGELOG, Release Guide, warehouse
  SHA sidecar, CI action modernization (`v1.2.4`).
- **Milestone 3, Phase E** — operational hardening: structured metadata-only
  logging, repository-owned LLM timeout, graceful shutdown, live readiness, ADR-013
  (`v1.3.0`). **Completes Milestone 3.**

---

## Current architecture (packages)

`app/`: `api` (routes, models contract, mapping, dependencies, main, `access_guard`,
`build_info`, `logging_config`, `readiness`), `validation`, `execution`, `llm`
(timeout-bounded client), `formatting`, `metadata`, `semantic`, `warehouse`,
`models` (reserved/empty), `config`. `frontend/` (HTTP-only Streamlit). `scripts/`
(`verify_env`, `check_version`, dev utilities). `data/` (certified warehouse +
`.sha256` sidecar + README). `docs/` (`adr/` 004–013, `developer/`,
`phase_completion_milestone3/`). Two workflows (`ci.yml`, `release.yml`).

---

## Current quality status

- Tests: **147 passing**.
- Coverage: **88%** (informational — not a gate).
- Ruff lint: clean. Ruff format: compliant (77 files).
- mypy: **0 issues across 47 source files**, blocking.
- pip-audit: no known vulnerabilities (advisory).
- One upstream Starlette/httpx deprecation warning (dependency-level, benign).

---

## Current CI & release status

- **CI** (`ci.yml`, every push/PR) — quality job (blocking Ruff, pytest, mypy;
  advisory coverage, pip-audit) + image job (blocking `docker build`; advisory Trivy
  scan). Python 3.14; `checkout@v5` / `setup-python@v6`.
- **Release** (`release.yml`, on `v*` tags + `workflow_dispatch`) — independent
  release verification (version consistency + warehouse SHA + re-run of gates), then
  image build, GHCR publish, GitHub Release from `CHANGELOG.md`.
- No secrets beyond `GITHUB_TOKEN`; zero OpenAI credit spent.

---

## Testing status

Deterministic and zero-cost: the LLM is faked, HTTP is mocked. Coverage spans engine
layers, API contract/HTTP semantics, adversarial validation, frontend
client/components/flow, and tooling/operational areas (`verify_env`, access guard,
`build_info`, `check_version`, logging formatter, the metadata-only logging
invariant, timeout resolution/handling, live readiness). The assembled Streamlit UI
is verified manually.

---

## Operational configuration (Phase E)

| Variable | Purpose | Default |
|---|---|---|
| `OPENAI_TIMEOUT_SECONDS` | Repository-owned LLM request timeout | `60` |
| `LOG_LEVEL` | Log level for the `solstice` logger | `INFO` |
| `LOG_FORMAT` | `json` (deployment) or `text` (local) | `text` |

---

## Repository invariants (do not violate)

- The LLM never executes SQL directly; only gate-approved SQL reaches the executor.
- Execution is read-only, with an independent row-cap backstop.
- The frontend never imports backend modules — HTTP only.
- The public API contract excludes provider/model details; `models.py` is frozen.
- Explanations are template-based; the LLM never narrates results.
- **Operational logs are metadata-only** (ADR-013) — enforced and tested.
- The provider call is timeout-bounded; a timeout fails safely via the existing
  non-success path.
- `/health` and `/ready` never call the LLM.
- Tests remain deterministic, secret-free, and zero-cost.
- The Deployment Access Guard defaults to disabled and never affects local dev/CI.
- `pyproject.toml` is the sole version definition; releases are verified tag-driven
  events; the bundled warehouse matches its recorded provenance.
- Milestones 1 and 2, and the governed engine, are frozen.

---

## Files that define repository behavior

- `app/validation/*`, `app/execution/*` — governed engine (frozen).
- `app/llm/client.py` — sole LLM/SDK boundary (timeout-bounded).
- `app/api/models.py` — frozen public contract; `app/api/main.py`/`routes.py` —
  lifecycle, endpoints, logging/guard/readiness wiring; `access_guard.py`,
  `build_info.py`, `logging_config.py`, `readiness.py`.
- `frontend/api_client.py` — sole frontend HTTP boundary.
- `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `pyproject.toml`.
- `scripts/verify_env.py`, `scripts/check_version.py`.
- `data/solstice_apparel.duckdb` (+ `.sha256`) — certified warehouse artifact.

---

## Next recommended work (post–Milestone 3)

Milestone 3 is complete. Candidate future directions, each additive and each
warranting its own architecture-first design review before implementation:

1. **Observability platform** — build metrics/tracing/dashboards on the Phase E
   structured-logging foundation (explicitly out of Milestone 3 scope).
2. **Conversation memory / multi-turn** — a product capability deferred by design.
3. **Authentication & authorization** as real product features (distinct from the
   demo-only Deployment Access Guard).
4. **Caching / automatic query-repair / usage persistence** — deferred options.

Follow the established process for any of these: architecture review → detailed
design → independent critique → refined design → implementation → verification →
documentation → git/GitHub closeout → clean-clone validation. Do not modify the
frozen governed engine without an ADR justifying it.
