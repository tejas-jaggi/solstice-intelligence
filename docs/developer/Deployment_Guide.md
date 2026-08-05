# Deployment Guide

How Solstice Intelligence is published as a live, public service. Design rationale
lives in ADR-012; this guide is the operational reference.

## What gets deployed

Two processes that communicate only over HTTP:

- the **FastAPI backend** — packaged as a reproducible Docker image (see
  `Dockerfile`), with the certified read-only warehouse bundled in;
- the **Streamlit frontend** — deployed separately (e.g. Streamlit Community
  Cloud) and pointed at the backend via `SOLSTICE_API_URL`.

The backend image is the deployment artifact. The frontend needs no image: it is
a pure HTTP client of the `/v1` contract.

## Deployment modes

The Deployment Access Guard (ADR-012) exists only to protect OpenAI spend. Its
behavior is entirely environment-driven, giving three modes:

| Mode            | Rate limiter | Demo Access Gate | OpenAI account cap | Where it runs     |
|-----------------|--------------|------------------|--------------------|-------------------|
| Development     | off          | off              | n/a                | Local             |
| Demo            | on           | off              | on                 | Public demo       |
| Restricted demo | on           | on               | on                 | Gated public demo |

- **Development** — `RATE_LIMIT_MAX_REQUESTS=0` (unset), no token. The guard is a
  pass-through; this is how local runs and the test suite behave.
- **Demo** — `RATE_LIMIT_MAX_REQUESTS>0`, no token, **plus** an OpenAI account
  hard budget cap. Frictionless for reviewers; runaway spend is impossible.
- **Restricted demo** — as Demo, plus `SOLSTICE_DEMO_TOKEN`. `/v1/ask` then
  requires the token; the frontend must send it (`X-Demo-Token`), a small
  env-gated change deferred until needed.

The **OpenAI account hard budget cap** (set in the OpenAI dashboard) is the
financial backstop and must be set before any public exposure. The guards bound
abuse; the cap bounds the bill.

## Environment variables

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | Secret. Injected by the platform; never committed or logged. |
| `OPENAI_MODEL` | A **pinned dated model snapshot** (e.g. `gpt-4o-2024-08-06`), never a floating alias — otherwise deployment behavior is not reproducible. |
| `WAREHOUSE_PATH` | Repo-relative path to the bundled warehouse (`data/solstice_apparel.duckdb`). |
| `MAX_ROWS`, `DEFAULT_LIMIT` | Safety caps enforced by the validation gate and executor. |
| `RATE_LIMIT_MAX_REQUESTS` | `0` disables the limiter (Development); `>0` enables it. |
| `RATE_LIMIT_WINDOW_SECONDS` | Rate-limit window length. |
| `SOLSTICE_DEMO_TOKEN` | Optional. When set, `/v1/ask` requires this shared token. |
| `SOLSTICE_API_URL` | Frontend only: the deployed backend URL. |

## Health and readiness

- `GET /health` — liveness: process up, no I/O, no OpenAI. Used to restart a hung
  process.
- `GET /ready` — readiness: assistant constructed and warehouse reachable, no
  OpenAI. Used to gate traffic; the platform readiness probe targets this.

Neither ever calls OpenAI, so both are free to poll.

## The warehouse artifact

The certified `solstice_apparel.duckdb` (~34.5 MB) is committed under `data/` and
copied into the image. It is a copy of a certified artifact produced by the
Customer Revenue Analytics repository, opened strictly read-only and never
modified. Provenance and checksum are recorded in `data/README.md`. Updating it
means replacing the file from a newly certified upstream warehouse — never
regenerating it here.

## Build and run

```bash
# Build (after pinning the base-image digest in the Dockerfile)
docker build -t solstice-intelligence .

# Run locally (Demo mode)
docker run --rm -p 8000:8000 \
  -e OPENAI_API_KEY=sk-... \
  -e OPENAI_MODEL=gpt-4o-2024-08-06 \
  -e RATE_LIMIT_MAX_REQUESTS=20 \
  solstice-intelligence
# API + Swagger: http://127.0.0.1:8000/docs
```

Platform deployment (Render) is described by `render.yaml`; Cloud Run and Fly.io
use the same image and the same environment variables.

## Reproducibility checklist

- Base image pinned by digest (not a moving tag).
- Runtime dependencies only in the image; dev tooling excluded.
- `OPENAI_MODEL` pinned to a dated snapshot.
- Warehouse checksum recorded and verified.
- Non-root container execution.

## Operational configuration (ADR-013)

| Variable | Purpose | Default |
|---|---|---|
| `OPENAI_TIMEOUT_SECONDS` | Repository-owned LLM request timeout (seconds). On timeout the request returns a non-success response rather than hanging. Deterministic across SDK upgrades. | `60` |
| `LOG_LEVEL` | Level for the `solstice` logger. | `INFO` |
| `LOG_FORMAT` | `json` for structured deployment logs, `text` for local readability. | `text` |

**Logging in deployment.** Set `LOG_FORMAT=json` so logs are structured and
queryable. Logs are metadata-only by design and by test — request IDs, lifecycle
events, timing, status codes, and operational diagnostics — and never contain
prompts, generated SQL, warehouse query results, model responses, user data, API
keys, or secrets. No log aggregation backend is bundled; JSON lines can be shipped by
the platform's own log pipeline if desired.

**Readiness under load.** `GET /ready` performs a live `SELECT 1` on the read-only
warehouse and never calls the LLM, so a platform may poll it at zero cost. `GET
/health` is pure liveness. Configure the platform's readiness probe against `/ready`
and its liveness probe against `/health`.

**Graceful shutdown.** The service drains in-flight requests on shutdown; ensure the
platform's stop-grace period allows in-flight governed requests (bounded by
`OPENAI_TIMEOUT_SECONDS`) to complete.
