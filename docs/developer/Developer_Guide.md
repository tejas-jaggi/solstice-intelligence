# Developer Guide

How to work on Solstice Intelligence from a clean clone. This guide documents the
*purpose* of each workflow; the exact commands live in the `justfile` and
`.github/workflows/ci.yml`, so they are defined once and cannot drift out of sync
with this document. The README Quick Start is the fast path; this is the full
reference.

---

## Prerequisites

- **Python 3.14+.** The repository targets 3.14 (`pyproject.toml`'s
  `requires-python`, the mypy `python_version`, and CI all agree).
- **[`just`](https://just.systems)** — the developer task runner. It is a
  convenience only: CI invokes the underlying tools directly and never routes
  through `just`.
- **An OpenAI API key** — needed only to *run* the application. Tests and CI
  never require it.

---

## Clean-clone workflow

A task runner cannot install itself, so the first bootstrap steps are plain
commands; `just` orchestrates everything afterward.

```bash
git clone https://github.com/tejas-jaggi/solstice-intelligence.git
cd solstice-intelligence

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1

# install just (see just.systems), then:
just setup                         # installs runtime + development dependencies
cp .env.example .env               # Windows: copy .env.example .env
#   set OPENAI_API_KEY in .env

just verify                        # confirm the environment is READY
just test                          # run the full deterministic suite
```

`.env` values other than `OPENAI_API_KEY` (`WAREHOUSE_PATH`, `OPENAI_MODEL`,
`MAX_ROWS`, `DEFAULT_LIMIT`) have safe local defaults.

---

## Task reference

Every recipe wraps the same command CI runs, so local results match CI.

| Recipe | Purpose |
|---|---|
| `just setup` | Install runtime (`requirements.txt`) and development (`requirements-dev.txt`) dependencies into the active venv. |
| `just verify` | Run the environment diagnostic (`scripts/verify_env.py`). No network, no OpenAI client, zero API cost. |
| `just test` | Full test suite with coverage (mirrors the CI test gate). |
| `just lint` | Ruff lint (mirrors the CI lint gate). |
| `just format-check` | Ruff format check (mirrors the CI format gate). |
| `just format` | Apply Ruff formatting. |
| `just typecheck` | mypy over `app` and `frontend` (mirrors the CI type gate). |
| `just run-api` | Start the FastAPI backend (Swagger at `/docs`). |
| `just run-ui` | Start the Streamlit frontend. |

---

## Environment verification

`just verify` runs `scripts/verify_env.py`, a deterministic diagnostic that
reports, in startup order: Python version (checked against the declared
requirement), core package availability, DuckDB and OpenAI SDK versions,
environment-variable **presence** (never values), warehouse accessibility, a
read-only open of the warehouse, and configuration validity. It performs no
network operation, never constructs an OpenAI client, touches the warehouse only
with a single read-only query, and is safe to run repeatedly. It exits non-zero
when the environment is not READY. It is a local tool by design and is not part
of CI, which has neither a warehouse nor a key.

---

## Testing

`just test` runs the full suite with coverage. Tests are deterministic and
zero-cost: the LLM is faked and HTTP is mocked, so no test needs the network, a
real model call, or secrets. Coverage is measured for information only and never
gates a build. The current suite is 135 tests at 88% coverage.

---

## Quality checks

`just lint`, `just format-check`, and `just typecheck` reproduce the three
blocking CI gates exactly; `just format` applies formatting. Running these before
pushing means CI holds no surprises.

---

## Running the application

`just run-api` starts the FastAPI backend; `just run-ui` starts the Streamlit
frontend, which talks to the backend over HTTP only. Swagger is at
`http://127.0.0.1:8000/docs`.

---

## Dependency philosophy

Dependencies are split by role and pinned exactly:

- `requirements.txt` — runtime dependencies, pinned `==`.
- `requirements-dev.txt` — development and tooling dependencies, pinned `==`
  (pytest, pytest-cov, Ruff, mypy, pip-audit).

Exact pins make installs reproducible and, critically, keep the blocking gates
deterministic. An unpinned formatter or type checker could reformat or re-analyze
unchanged code and turn CI red on a commit nobody touched — the exact
non-determinism ADR-011 forbids in a gate. `ruff` is held at the version recorded
in ADR-011 (its py314 formatter bug is why `target-version` is `py312`); revisit
that ADR before bumping it.

To change a dependency: edit the appropriate file, reinstall with `just setup`,
run `just verify` and `just test`, and confirm CI is green. Upgrades are
deliberate, reviewed changes, never incidental. pip-tools and similar tooling
were considered and rejected: the runtime is already hand-pinned and the split is
the simplest approach that satisfies reproducibility.

---

## Versioning

Project version metadata is maintained solely in `pyproject.toml`
(`[project].version`). There is no separate runtime version module, and none is
introduced by the developer-experience tooling. A dedicated runtime version
module may be considered in a future release if runtime version reporting becomes
a project requirement. To cut a release, bump `version` in `pyproject.toml` and
tag.

---

## How CI maps to local commands

CI runs the tools directly (not through `just`) in this order: Ruff lint → Ruff
format check → pytest with coverage → mypy over `app frontend` → pip-audit
(advisory). The `just` recipes wrap those same commands. CI installs both
requirements files on Python 3.14 and caches on both.

Gate policy (ADR-011): **blocking** — Ruff, pytest, mypy; **advisory** —
coverage, pip-audit. A red build always means a real, fixable problem.

---

## Troubleshooting

- **`just: command not found`** — the task runner is not installed. See
  just.systems; it cannot bootstrap itself, which is why the first setup steps
  are plain commands.
- **`just verify` reports NOT READY** — read the failing line. Common causes: a
  missing `.env` or unset `OPENAI_API_KEY` (presence only), or `WAREHOUSE_PATH`
  pointing at a file that does not exist. The verifier never prints secret values.
- **Warehouse read-only check fails** — the file exists but is not a valid DuckDB
  warehouse (a corrupted or partial file). Re-point `WAREHOUSE_PATH` at the
  certified warehouse.
- **Starlette deprecation warning during tests** — an upstream FastAPI/Starlette
  TestClient notice, unrelated to this repository; benign and not a regression.
- **mypy passes locally but you added a new module** — mypy checks `app` and
  `frontend`; `scripts/` and `tests/` are intentionally out of scope.

---

## Repository conventions

- **Additive-first.** Milestones 1 and 2 are frozen. New work surrounds the
  frozen core rather than modifying it.
- **Architecture decisions are ADRs.** Add a new ADR for a new architectural
  decision; do not rewrite existing ADRs (they are a historical record).
  Repository-engineering and workflow changes (like this phase) do not require an
  ADR.
- **Deterministic, zero-cost tests.** Never introduce a test that needs the
  network, a real model call, or a secret.
- **Boundaries are structural.** The frontend never imports `app/`; the LLM SDK
  lives only in `app/llm/client.py`; the public API contract is separate from
  internal types.

---

## Documentation layout

- `docs/developer/` — developer-facing guides (this file); grows with later
  milestones (deployment and release guides in Phases C and D).
- `docs/adr/` — architecture decision records.
- Root handoff documents (`Architecture_State.md`, `Milestone_Continuation.md`,
  `Project_Bible.md`, and the phase completion reports) — orientation and history.