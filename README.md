# Solstice Intelligence

> A governed natural-language analytics platform that lets business
> users query a dimensional data warehouse using plain English while
> validating every AI-generated SQL statement before execution.

![Python](https://img.shields.io/badge/Python-3.14-blue)
![DuckDB](https://img.shields.io/badge/DuckDB-Data%20Warehouse-orange)
![FastAPI](https://img.shields.io/badge/FastAPI-REST%20API-green)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-lightgrey)
[![CI](https://github.com/tejas-jaggi/solstice-intelligence/actions/workflows/ci.yml/badge.svg)](https://github.com/tejas-jaggi/solstice-intelligence/actions/workflows/ci.yml)
![Coverage](https://img.shields.io/badge/coverage-88%25-brightgreen)

------------------------------------------------------------------------

## Overview

Solstice Intelligence is a production-style analytics project that
explores how large language models can be used safely for business
intelligence.

Instead of allowing an AI model to generate and execute SQL directly,
every query passes through a governed pipeline that validates the
generated SQL before it reaches the warehouse. The goal is an analytics
assistant that is accurate, transparent, and easy to trust.

The project was developed across three milestones. Milestones 1 and 2 — the
governed backend, the versioned REST API, and the Streamlit frontend — are complete
and frozen. **Milestone 3 (production engineering) is complete:** continuous
integration and quality gates (Phase A), developer experience (Phase B), a
reproducible Docker deployment (Phase C), tag-driven release engineering with GHCR
publishing (Phase D), and operational hardening (Phase E). Milestone 3 completes at
`v1.3.0`.

------------------------------------------------------------------------

## Quick Start

Get the project running before reading how it works.

**Prerequisites:** Python 3.14+, [`just`](https://just.systems) (developer task
runner), and an OpenAI API key.

```bash
git clone https://github.com/tejas-jaggi/solstice-intelligence.git
cd solstice-intelligence

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1

# install just once (macOS: brew install just | Windows: winget install Casey.Just
# | any: cargo install just), then install runtime + dev dependencies:
just setup

cp .env.example .env               # Windows: copy .env.example .env
#   edit .env and set OPENAI_API_KEY

just verify                        # environment diagnostic — no network, no API cost
just test                          # full deterministic suite

just run-api                       # http://127.0.0.1:8000/docs   (terminal 1)
just run-ui                        # Streamlit UI                 (terminal 2)
```

Full workflow, task reference, and troubleshooting:
[Developer Guide](docs/developer/Developer_Guide.md).
To build and run the container: [Deployment Guide](docs/developer/Deployment_Guide.md).
To cut a release: [Release Guide](docs/developer/Release_Guide.md).

------------------------------------------------------------------------

## Why I Built This

Many AI-powered SQL assistants focus on generating queries quickly. This project
focuses on engineering discipline:

- How can an AI assistant answer questions without blindly trusting AI-generated SQL?
- How can a warehouse remain the source of truth?
- How can an analytics system be designed so each layer has a single responsibility?

The result is a layered architecture with clear boundaries, automated validation,
deterministic execution, and production-grade CI, deployment, release engineering,
and operational hardening.

------------------------------------------------------------------------

## Key Features

-   Natural-language analytics using the OpenAI Responses API
-   Schema-aware SQL generation
-   SQL validation using sqlglot (allowlist-first rules)
-   Read-only query execution with a row-cap backstop
-   DuckDB dimensional warehouse (certified, immutable, bundled as a deployment artifact)
-   FastAPI REST API (`/v1`) with health, readiness, and version endpoints
-   OpenAPI / Swagger documentation and request-ID tracing
-   Reproducible Docker deployment with a cost-safety guard
-   Tag-driven release engineering with GHCR publishing
-   Structured, metadata-only operational logging and a bounded LLM request timeout
-   Deterministic, zero-cost automated testing

------------------------------------------------------------------------

## High-Level Architecture

``` text
Business User
      │
      ▼
 FastAPI REST API
      │
      ▼
 AnalyticsAssistant
      │
      ▼
 Schema Grounding
      │
      ▼
 OpenAI Responses API  (request-timeout bounded)
      │
      ▼
 SQL Validation Gate
      │
      ▼
 Read-only Executor
      │
      ▼
 DuckDB Warehouse
      │
      ▼
 Structured Response
```

> **The LLM reasons. The warehouse provides truth. Validation decides trust.**

------------------------------------------------------------------------

## Repository Structure

``` text
solstice-intelligence/
├── app/
│   ├── api/            # routes, contract, mapping, DI, main, access_guard,
│   │                   # build_info, logging_config, readiness
│   ├── execution/      # read-only executor
│   ├── formatting/     # deterministic response formatting
│   ├── llm/            # LLM client (timeout-bounded), tool, orchestrator
│   ├── metadata/       # structural warehouse metadata
│   ├── models/         # reserved (empty)
│   ├── semantic/       # schema grounding
│   ├── validation/     # SQL validation gate
│   └── warehouse/      # read-only DuckDB connection + introspection
│
├── frontend/           # HTTP-only Streamlit client + tests
├── scripts/            # verify_env, check_version, dev utilities
├── data/               # certified warehouse + .sha256 sidecar + README
├── tests/
├── docs/
│   ├── adr/            # ADR-004 … ADR-013
│   ├── assets/
│   ├── developer/      # Developer_Guide, Deployment_Guide, Release_Guide
│   └── phase_completion_milestone3/   # Phase A–E completion reports
├── .github/workflows/  # ci.yml, release.yml
├── Dockerfile, .dockerignore, render.yaml
├── requirements.txt, requirements-dev.txt
├── justfile, pyproject.toml, CHANGELOG.md
├── README.md, LICENSE
```

------------------------------------------------------------------------

## Engineering Principles

-   The warehouse is the source of truth; the LLM only proposes.
-   AI output is never trusted without validation.
-   Business logic and presentation stay separate.
-   Every architectural decision is documented with an ADR.
-   Public APIs are versioned and treated as stable contracts.
-   Deployments are reproducible, self-contained artifacts; releases are verified,
    tag-driven events.
-   Operational logs are metadata-only — never prompts, SQL, results, or secrets.
-   New work should not weaken existing guarantees.

------------------------------------------------------------------------

## REST API

**Main endpoint:** `POST /v1/ask`

**Operational endpoints:** `GET /health` (liveness), `GET /ready` (live readiness —
`SELECT 1` on the warehouse, never an LLM call), `GET /version`. Swagger is served at
`/docs`. In a public deployment `POST /v1/ask` is protected by the Deployment Access
Guard (see [ADR-012](docs/adr/ADR-012-deployment-architecture.md)); the operational
endpoints stay open and cost nothing.

------------------------------------------------------------------------

## Web Interface

A thin Streamlit client provides a browser interface to the assistant. It consumes
the REST API only — it never imports backend modules (see ADR-010) — so the
presentation layer is fully decoupled and could be replaced by any other HTTP client.

**Architecture**
 
```
Browser → Streamlit (frontend/) → HTTP → FastAPI (/v1) → AnalyticsAssistant → governed backend → DuckDB
```
 
**Running it locally**

```bash
uvicorn app.api.main:app --reload                    # backend
streamlit run frontend/streamlit_app.py              # UI (second terminal)
SOLSTICE_API_URL=http://localhost:8000 streamlit run frontend/streamlit_app.py  # non-default API
```

## Interface Preview

### Homepage
![Solstice UI — homepage](docs/assets/ui_home.png)
### Successful Analytics Query
![Solstice UI — successful answer with executed SQL](docs/assets/ui_success.png)
### Live Demonstration
![Solstice UI — demo](docs/assets/ui_demo.gif)

------------------------------------------------------------------------

## Deployment

The backend is packaged as a reproducible Docker image with the certified warehouse
bundled, so the deployment is self-contained and portable. Rationale:
[ADR-012](docs/adr/ADR-012-deployment-architecture.md); operations:
[Deployment Guide](docs/developer/Deployment_Guide.md).

- Base image pinned by digest; non-root execution; runtime dependencies only.
- `OPENAI_MODEL` pinned to a dated snapshot (never a floating alias).
- The certified `solstice_apparel.duckdb` (~34.5 MB) is bundled read-only as an
  immutable artifact (produced and certified by the separate Customer Revenue
  Analytics project; provenance and SHA-256 in `data/README.md` and its `.sha256`
  sidecar).

**Cost safety.** A public `POST /v1/ask` makes a real, paid model call, so it is
protected by the **Deployment Access Guard** — a route-level dependency combining a
deterministic in-memory rate limiter and an optional Demo Access Gate token. It is
*not* authentication; it exists only to protect OpenAI spend, defaults to disabled,
and is enabled through environment variables. An OpenAI account hard budget cap is
the financial backstop.

| Mode            | Rate limiter | Demo Access Gate | OpenAI account cap | Where it runs     |
|-----------------|--------------|------------------|--------------------|-------------------|
| Development     | off          | off              | n/a                | Local             |
| Demo            | on           | off              | on                 | Public demo       |
| Restricted demo | on           | on               | on                 | Gated public demo |

**Operational hardening.** Structured metadata-only logging (JSON in deployment,
text locally), a repository-owned LLM request timeout (`OPENAI_TIMEOUT_SECONDS`,
default 60s) that fails safely, graceful shutdown, and a live readiness check. See
[ADR-013](docs/adr/ADR-013-Operational_Observability_and_Resilience.md).

**Build and run**

```bash
docker build -t solstice-intelligence .          # after pinning the base-image digest
docker run --rm -p 8000:8000 \
  -e OPENAI_API_KEY=sk-... \
  -e OPENAI_MODEL=gpt-4o-2024-08-06 \
  -e RATE_LIMIT_MAX_REQUESTS=20 \
  solstice-intelligence
# API + Swagger: http://127.0.0.1:8000/docs
```

A `render.yaml` blueprint is provided; Cloud Run and Fly.io use the same image and
variables.

------------------------------------------------------------------------

## Releases

Releases are deterministic and tag-driven. `pyproject.toml` is the single version
source; `scripts/check_version.py` verifies tag ↔ `pyproject` ↔ `/version`; the
release workflow independently re-verifies the quality gates and warehouse
provenance, builds and publishes the image to GHCR (via the built-in `GITHUB_TOKEN`),
and creates the GitHub Release from `CHANGELOG.md`. See
[Release Guide](docs/developer/Release_Guide.md).

------------------------------------------------------------------------

## Testing & Verification

### Automated
-   147 automated tests (deterministic, zero-cost)
-   Engine, API contract, and adversarial validation tests
-   Frontend client, component, and flow tests
-   Operational tests: logging formatter, the metadata-only logging invariant,
    timeout resolution/handling, live readiness, environment diagnostic, and the
    version-consistency checker
-   88% coverage (informational)

### Manual release verification
-   Startup, health/readiness/version, Swagger, a successful governed query,
    invalid-request handling, and a reproducible Docker image build.

------------------------------------------------------------------------

## Current Status

- **Milestone 1** — governed backend ✅ (frozen)
- **Milestone 2** — Phase G REST API ✅, Phase H Streamlit frontend ✅ (frozen)
- **Milestone 3 — Production Engineering ✅ (complete at `v1.3.0`)**
  - Phase A — CI & quality gates ✅ (`v1.2.1`)
  - Phase B — Developer experience & repository standards ✅ (`v1.2.2`)
  - Phase C — Deployment ✅ (`v1.2.3`)
  - Phase D — Release engineering ✅ (`v1.2.4`)
  - Phase E — Operational hardening ✅ (`v1.3.0`)

------------------------------------------------------------------------

## Technology Stack

Python · FastAPI · DuckDB · OpenAI Responses API · sqlglot · Pydantic · Pytest ·
Docker · GitHub Actions · Git

------------------------------------------------------------------------

## Roadmap

Milestone 3 is complete. Future directions (each additive, each warranting its own
design review) include an observability platform built on the structured-logging
foundation, conversation memory / multi-turn, authentication as a product feature,
and caching — all deferred by design, not omissions.

------------------------------------------------------------------------

## License

MIT License

------------------------------------------------------------------------

## Author

**Tejas Jaggi**

M.S. in Information Management

University of Illinois Urbana-Champaign
