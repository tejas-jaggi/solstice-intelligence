# data/

This directory holds the **certified Customer Revenue Analytics warehouse**,
bundled as an immutable deployment artifact.

- **File:** `solstice_apparel.duckdb` (~34.5 MB)
- **Checksum (canonical, machine-readable):** `solstice_apparel.duckdb.sha256`
  — this sidecar file is the source of truth for the artifact's SHA-256 and is
  validated by the release workflow. Verify locally with:
  `sha256sum -c solstice_apparel.duckdb.sha256`
- **Producer (authoritative source):** the separate Customer Revenue Analytics
  repository, which creates, validates, certifies, and freezes the warehouse.
- **Consumer:** Solstice Intelligence opens it strictly read-only and never
  creates, regenerates, or modifies it.

The database is intentionally **copied**, never regenerated during deployment.
Updating it means recertifying the upstream warehouse and replacing this file
together with its `.sha256` sidecar — not rebuilding it here. See ADR-012
(Artifact Provenance).
