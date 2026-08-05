# Developer Guide

How to work on Solstice Intelligence from a clean clone. This guide documents the
*purpose* of each workflow; the exact commands live in the `justfile` and the CI/
release workflows, so they are defined once and cannot drift out of sync. The README
Quick Start is the fast path; this is the full reference.

---

## Prerequisites

- **Python 3.14+.** The repository targets 3.14 (`pyproject.toml`, mypy, and CI
  agree).
- **[`just`](https://just.systems)** — the developer task runner (convenience only;
  CI and the release workflow invoke the underlying tools directly).
- **An OpenAI API key** — needed only to *run* the application. Tests and CI never
  require it.

---

## Clean-clone workflow

```bash
git clone https://github.com/tejas-jaggi/solstice-intelligence.git
cd solstice-intelligence
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
just setup                         # runtime + development dependencies
cp .env.example .env               # Windows: copy .env.example .env — set OPENAI_API_KEY
just verify                        # environment diagnostic
just test                          # full deterministic suite
```

---

## Task reference

| Recipe | Purpose |
|---|---|
| `just setup` | Install runtime + development dependencies. |
| `just verify` | Environment diagnostic (`scripts/verify_env.py`). No network, no OpenAI call. |
| `just test` | Full test suite with coverage (mirrors CI). |
| `just lint` | Ruff lint (mirrors the CI blocking gate). |
| `just format-check` | Ruff format check (mirrors the CI blocking gate). |
| `just format` | Apply Ruff formatting. |
| `just typecheck` | mypy over `app` and `frontend` (mirrors the CI blocking gate). |
| `just check-version vX.Y.Z` | Verify tag ↔ pyproject ↔ /version consistency (release). |
| `just run-api` | Start the FastAPI backend (Swagger at `/docs`). |
| `just run-ui` | Start the Streamlit frontend. |

---

## Environment verification

`just verify` runs `scripts/verify_env.py`: Python version, required packages, DuckDB
and OpenAI SDK versions, environment-variable **presence** (never values), warehouse
accessibility, a read-only warehouse open, and configuration validity. No network,
no OpenAI client, safe to run repeatedly; not part of CI.

---

## Testing

`just test` runs the full suite with coverage. Tests are deterministic and
zero-cost: the LLM is faked and HTTP is mocked. Coverage is informational and never
gates. The current suite is 147 tests at 88% coverage.

New operational tests to be aware of: the logging formatter, the **metadata-only
logging invariant** (a full request is driven and the captured logs are asserted to
contain operational metadata and never the question, SQL, results, model response,
or secrets), timeout resolution/handling, and the live readiness probe.

---

## Quality checks

`just lint`, `just format-check`, and `just typecheck` reproduce the three blocking
CI gates; `just format` applies formatting. Running these before pushing means CI
holds no surprises.

---

## Running the application

`just run-api` starts the FastAPI backend; `just run-ui` starts the Streamlit
frontend, which talks to the backend over HTTP only. Swagger is at
`http://127.0.0.1:8000/docs`.

### Operational configuration (Phase E)

These are read from the environment; all are optional with safe defaults.

| Variable | Purpose | Default |
|---|---|---|
| `OPENAI_TIMEOUT_SECONDS` | Repository-owned LLM request timeout (seconds). A timeout fails safely as a non-success response, never a hang. | `60` |
| `LOG_LEVEL` | Level for the `solstice` logger (`DEBUG`/`INFO`/`WARNING`/…). | `INFO` |
| `LOG_FORMAT` | `text` for human-readable local logs, `json` for structured deployment logs. | `text` |

Logs are **metadata-only** by design and by test: request IDs, lifecycle events,
timing, status, and diagnostics — never prompts, generated SQL, warehouse results,
model responses, user data, or secrets. Reading logs locally, leave `LOG_FORMAT`
unset (text); in deployment set `LOG_FORMAT=json` for queryable structured output.

---

## Dependency management

Runtime dependencies are pinned in `requirements.txt`; development/tooling
dependencies are pinned in `requirements-dev.txt` (both `==`). Exact pins make
installs reproducible and keep the blocking gates deterministic. To change a
dependency: edit the file, `just setup`, `just verify`, `just test`, confirm CI is
green. `ruff` is held at the ADR-011 version; revisit that ADR before bumping it.

---

## Releasing

`pyproject.toml` is the single version source. To cut a release: update
`CHANGELOG.md`, bump `pyproject.toml`, run `just check-version vX.Y.Z` and
`just test`, then tag and push. The release workflow then verifies, builds,
publishes to GHCR, and creates the GitHub Release. Full procedure and one-time GHCR
settings: [Release Guide](Release_Guide.md).

---

## How CI maps to local commands

CI runs the tools directly (not through `just`): Ruff lint → Ruff format check →
pytest with coverage → mypy over `app frontend` → pip-audit (advisory), plus a
`docker build` and an advisory image scan. The release workflow adds version-
consistency and warehouse-provenance checks. The `just` recipes wrap the same
commands, so local results match CI.

---

## Repository conventions

- **Additive-first.** The governed engine and Milestones 1–2 are frozen; new work
  surrounds the frozen core.
- **Architecture decisions are ADRs** (`docs/adr/`); add a new ADR rather than
  rewriting old ones. Workflow/repository-engineering changes don't require an ADR.
- **Deterministic, zero-cost tests.** Never introduce a test that needs the network,
  a real model call, or a secret.
- **Boundaries are structural.** The frontend never imports `app/`; the LLM SDK lives
  only in `app/llm/client.py`; the public contract is separate from internal types.
- **Logs are metadata-only** — a tested invariant (ADR-013).

---

## Documentation layout

- `docs/developer/` — developer-facing guides (this file, Deployment, Release).
- `docs/adr/` — architecture decision records (ADR-004 … ADR-013).
- `docs/phase_completion_milestone3/` — phase completion reports.
- Root: `Architecture_State.md` (authoritative architecture), `Milestone_Continuation.md`
  (handoff), `CHANGELOG.md`.
