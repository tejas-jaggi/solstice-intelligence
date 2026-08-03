# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Pin the base image by DIGEST for reproducible builds. Capture the digest with:
#   docker pull python:3.14-slim
#   docker inspect --format='{{index .RepoDigests 0}}' python:3.14-slim
# then replace the placeholder below. The image will not build until a real
# digest is pinned — intentional: reproducibility over convenience.
# ---------------------------------------------------------------------------
FROM python:3.14-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Unprivileged runtime user.
RUN groupadd --system app && useradd --system --gid app --home-dir /app app

# Runtime dependencies only (dev tooling stays in requirements-dev.txt).
# Copied first so this layer caches across application code changes.
COPY requirements.txt ./
RUN python -m pip install --upgrade pip && pip install -r requirements.txt

# Version metadata (read by GET /version), application code, and the certified
# read-only warehouse artifact (see data/README.md and ADR-012 Artifact Provenance).
COPY pyproject.toml ./
COPY app ./app
COPY data ./data

USER app

# Platforms inject $PORT; default to 8000 locally. Shell form so $PORT expands.
CMD ["sh", "-c", "uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

# Liveness probe: no OpenAI, no tokens. Platforms may additionally probe /ready.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/health', timeout=4)" || exit 1
