# Milestone Continuation — Solstice Intelligence

*Authoritative handoff for a new working session (Claude or ChatGPT). Assumes
access to the repository. Detailed architecture lives in `Architecture_State.md`;
reasoning lives in `Project_Bible.md` and `docs/adr/`. This document is the
quick-orientation layer.*

---

## Repository snapshot

- **Version:** `pyproject.toml` `[project].version` — release `v1.2.4` (Phase D).
  `pyproject.toml` is the sole version definition; `GET /version` derives from it.
- **Current milestone:** Milestone 3 — Production Engineering.
- **Phase status:** Phases A, B, C, and D — **complete**. Phase E not yet started.
- **Working tree:** clean; CI green; the tag-driven release workflow is in place.

---

## Architecture summary (one paragraph)

A governed natural-language analytics assistant. A plain-English question is
grounded in a live warehouse schema; an LLM proposes SQL; a validation gate
approves or rejects it; approved SQL runs read-only against a DuckDB warehouse;
the result is formatted with the exact SQL and a template explanation. A FastAPI
service exposes a frozen `/v1` contract; a thin Streamlit frontend consumes it over
HTTP only. Governing rule: **the LLM reasons, the warehouse provides truth,
validation decides trust** — the LLM never executes SQL directly.

---

## Completed phases

- **Milestone 1** — governed engine (warehouse, grounding, validation gate,
  read-only execution, formatting) — frozen.
- **Milestone 2** — Phase G (FastAPI `/v1` service) and Phase H (Streamlit
  frontend) — frozen.
- **Milestone 3, Phase A** — CI & quality gates; mypy promoted to blocking
  (`v1.2.1`).
- **Milestone 3, Phase B** — developer experience: `just`, runtime/dev dependency
  split, `verify_env.py`, developer docs, CI on Python 3.14 (`v1.2.2`).
- **Milestone 3, Phase C** — deployment: reproducible Docker image, bundled
  certified warehouse, Deployment Access Guard, truthful `/version`, ADR-012
  (`v1.2.3`).
- **Milestone 3, Phase D** — release engineering: version-consistency checker,
  tag-driven release workflow, GHCR publishing, CHANGELOG, Release Guide, warehouse
  SHA sidecar, CI action modernization (`v1.2.4`).

---

## Current architecture (packages)

`app/`: `api` (routes, models contract, mapping, dependencies, main, `access_guard`,
`build_info`), `validation`, `execution`, `llm`, `formatting`, `metadata`,
`semantic`, `warehouse`, `models` (reserved/empty), `config`. `frontend/`
(HTTP-only Streamlit). `scripts/` (`verify_env`, `check_version`, dev utilities).
`data/` (certified warehouse + `.sha256` sidecar + README). `docs/` (`adr/`,
`developer/`, `phase_completion_milestone3/`). Two workflows (`ci.yml`,
`release.yml`).

---

## Current quality status

- Tests: **135 passing**
- Coverage: **88%** (informational — not a gate).
- Ruff lint: clean. Ruff format: compliant.
- mypy: **0 issues across the app + frontend source set**, blocking.
- pip-audit: no known vulnerabilities (advisory).

---

## Current CI status

- **CI** (`ci.yml`, every push/PR) — quality job (blocking Ruff, pytest, mypy;
  advisory coverage, pip-audit) + image job (blocking `docker build`; advisory
  Trivy scan). Python 3.14. Actions on `checkout@v5` / `setup-python@v6`.
- **Release** (`release.yml`, on `v*` tags + `workflow_dispatch`) — independent
  release verification (version consistency + warehouse SHA + re-run of the gates),
  then image build, GHCR publish, GitHub Release from `CHANGELOG.md`.
- No secrets beyond `GITHUB_TOKEN`; zero OpenAI credit spent.

---

## Testing status

Deterministic and zero-cost: the LLM is faked, HTTP is mocked. Engine layers, API
contract/HTTP semantics, adversarial validation, frontend client/components/flow,
and tooling (`verify_env`, access guard, `build_info`, `check_version`) are covered.
The assembled Streamlit UI is verified manually.

---

## Release engineering status

`pyproject.toml` is the single version source; `check_version.py` enforces tag ↔
pyproject (transitively `/version`) at release; releases are tag-driven and verified
before publish; images publish to GHCR via `GITHUB_TOKEN`; GitHub Releases are
generated from `CHANGELOG.md`; the bundled warehouse is validated against its
`.sha256` sidecar. See `docs/developer/Release_Guide.md`.

---

## Repository invariants (do not violate)

- The LLM never executes SQL directly; only gate-approved SQL reaches the executor.
- Execution is read-only, with an independent row-cap backstop.
- The frontend never imports backend modules — HTTP only.
- The public API contract excludes provider/model details.
- Explanations are template-based; the LLM never narrates results.
- Tests remain deterministic, secret-free, and zero-cost.
- The Deployment Access Guard defaults to disabled and never affects local dev/CI.
- `pyproject.toml` is the sole version definition; releases are verified tag-driven
  events; the bundled warehouse matches its recorded provenance.
- Milestones 1 and 2, and the governed engine, are frozen.

---

## Files that define repository behavior

- `app/validation/*`, `app/execution/*` — governed engine (frozen).
- `app/llm/client.py` — sole LLM/SDK boundary.
- `app/api/models.py` — frozen public contract; `app/api/main.py`/`routes.py` —
  lifecycle, endpoints, guard wiring; `app/api/access_guard.py` — Deployment Access
  Guard; `app/api/build_info.py` — version metadata.
- `frontend/api_client.py` — sole frontend HTTP boundary.
- `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `pyproject.toml` —
  CI/release and the sole version definition.
- `scripts/verify_env.py`, `scripts/check_version.py` — deterministic diagnostics.
- `data/solstice_apparel.duckdb` (+ `.sha256`) — certified warehouse artifact.

---

## Next recommended work: Phase E — Operational Hardening

Objective: operational robustness for the deployed service, additive and without
redesigning the governed engine. Candidate scope (to be designed, not assumed):
structured logging (respecting ADR-009's no-prompts/no-data/no-secrets rule),
graceful shutdown, request timeouts, startup diagnostics, and readiness/health
refinements. Follow the established process: architecture review → detailed design
→ independent critique → refined design → implementation → verification →
documentation → git/GitHub closeout. Milestone 3 completes at **v1.3.0** after
Phase E.
