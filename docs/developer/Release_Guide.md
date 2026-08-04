# Release Guide

How Solstice Intelligence cuts a release. A release is a deliberate, verified,
tag-driven event: the tag is the source of truth, and the release workflow proves
the repository is releasable before it publishes anything.

## CI vs. release verification

These answer two different questions and are intentionally separate:

- **CI** (`ci.yml`, every push/PR) — *"Can this commit merge?"* Blocking gates
  plus an image build.
- **Release** (`release.yml`, on a `v*` tag) — *"Can this commit become an
  official release?"* An independent, higher-assurance verification: it re-runs
  the same quality gates **and** adds release-only checks (version consistency,
  warehouse provenance) before building, publishing, and releasing.

The re-run of Ruff/pytest/mypy in the release workflow is not redundant CI — it is
the release asserting its own, stronger guarantee independently of the merge gate.

## Versioning

`pyproject.toml` `[project].version` is the single source of truth. The public
`GET /version` endpoint reads it at runtime (via `app/api/build_info.py`), and
each release tag `vX.Y.Z` is verified to match it. `scripts/check_version.py`
enforces this; run it locally with `just check-version vX.Y.Z`.

## Cutting a release

1. Update `CHANGELOG.md`: move the relevant `Unreleased` items under a new
   `## [X.Y.Z] - ...` section.
2. Bump `[project].version` in `pyproject.toml` to `X.Y.Z`.
3. Verify locally: `just check-version vX.Y.Z`, then `just test`.
4. Commit, then tag and push:
```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
```
5. The release workflow then runs automatically and:
   - verifies version consistency and warehouse provenance,
   - re-runs the blocking quality gates,
   - builds the image and pushes `ghcr.io/<owner>/solstice-intelligence:X.Y.Z`
     and `:latest` to GHCR,
   - creates the GitHub Release with notes drawn from `CHANGELOG.md`.

### Recovery path

If a tagged run needs to be re-driven without moving the tag, use the workflow's
`workflow_dispatch` trigger (Actions → Release → Run workflow) and supply the
version (e.g. `v1.2.4`). The tag push remains the primary release mechanism.

## Warehouse provenance at release

The bundled certified warehouse has a canonical checksum in
`data/solstice_apparel.duckdb.sha256`. The release workflow recomputes the file's
SHA-256 and fails if it does not match the sidecar, so a release can never ship a
warehouse that drifted from its certified provenance. To replace the warehouse
(only from a newly certified upstream copy), update both the `.duckdb` file and
its `.sha256` sidecar.

## One-time GitHub settings (GHCR)

Publishing uses only the built-in `GITHUB_TOKEN` — no personal access token, no
added secrets. The first release requires two one-time settings:

- **Actions → General → Workflow permissions:** ensure Actions may write packages
  (the workflow already requests `packages: write` with least privilege; the
  repository setting must permit it).
- **Package visibility:** a newly published GHCR package is **private** by
  default. To make the demo image publicly pullable, open the package (under the
  repository's *Packages*) and set its visibility to public. This is a one-time
  action per package.

## Verifying a release

- The GitHub Release appears under *Releases* with the changelog notes.
- The image is pullable:
  `docker pull ghcr.io/<owner>/solstice-intelligence:X.Y.Z`.
- `GET /version` on a running instance reports `X.Y.Z`.
