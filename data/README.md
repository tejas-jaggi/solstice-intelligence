# data/

This directory holds the **certified Customer Revenue Analytics warehouse**,
bundled as an immutable deployment artifact.

- **File:** `solstice_apparel.duckdb` (~34.5 MB)
- **SHA-256:** `187538285A2DC3BB0F87F06B459D67D4A6A9F6403AB6DE9B96601BEF498BE3BB`
- **Producer (authoritative source):** the separate Customer Revenue Analytics
  repository, which creates, validates, certifies, and freezes the warehouse.
- **Consumer:** Solstice Intelligence opens it strictly read-only and never
  creates, regenerates, or modifies it.

The database is intentionally **copied**, never regenerated during deployment.
Updating it means recertifying the upstream warehouse and replacing this file —
not rebuilding it here. See ADR-012 (Artifact Provenance).
