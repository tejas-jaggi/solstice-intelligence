# Changelog

All notable changes to Solstice Intelligence are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The version in `pyproject.toml` is the single source of truth; each release tag
`vX.Y.Z` is verified to match it (see `scripts/check_version.py`).

## [Unreleased]

## [1.2.4] - Milestone 3, Phase D — Release Engineering
### Added
- Deterministic version-consistency checker (`scripts/check_version.py`) enforcing
  git tag ↔ `pyproject.toml` (and transitively the `/version` endpoint), with
  deterministic unit tests.
- Tag-driven release workflow (`.github/workflows/release.yml`) performing
  independent release verification, image build, GHCR publish, and GitHub Release
  creation; includes a `workflow_dispatch` recovery path.
- GHCR image publishing using only the built-in `GITHUB_TOKEN` (least privilege).
- Machine-readable warehouse checksum sidecar (`data/solstice_apparel.duckdb.sha256`)
  validated at release time.
- `CHANGELOG.md` and `docs/developer/Release_Guide.md`.
- `just check-version` recipe.

### Changed
- Modernized CI actions (`actions/checkout` v5, `actions/setup-python` v6) to clear
  the deprecated-Node-20 warning.
- Reconciled authoritative documentation (`Architecture_State.md`,
  `Milestone_Continuation.md`) to the current repository state; repaired markdown
  rendering in `Phase_B_Completion.md`.

### Unchanged
- The governed engine (validation, execution, llm, formatting, warehouse, SQL
  generation) is untouched. Phase D is additive: release engineering, workflow
  automation, and documentation only.

## [1.2.3] - Milestone 3, Phase C — Deployment
### Added
- Reproducible Docker image (digest-pinned base, non-root, runtime-only deps).
- Certified warehouse bundled as an immutable deployment artifact with recorded
  provenance.
- Deployment Access Guard on `POST /v1/ask` (deterministic rate limiter + optional
  demo access gate); defaults disabled.
- Truthful `/version`, single-sourced from `pyproject.toml` via `build_info.py`.
- Advisory container image scan in CI; `render.yaml`; ADR-012; Deployment Guide.

## [1.2.2] - Milestone 3, Phase B — Developer Experience & Repository Standards
### Added
- `just` task runner, runtime/development dependency split (all dev tools pinned
  `==`), `scripts/verify_env.py` environment diagnostic, and the Developer Guide.
### Changed
- CI aligned to Python 3.14.

## [1.2.1] - Milestone 3, Phase A — CI & Quality Gates
### Added
- GitHub Actions CI with blocking gates (Ruff, pytest, mypy) and advisory checks
  (coverage, pip-audit); ADR-011; status badges.
### Changed
- mypy promoted to a blocking gate after reaching a zero-finding baseline.
