# ADR-005: SQL Validation Gate

- **Status:** Accepted
- **Date:** Phase C, Milestone 1
- **Context area:** Trust boundary between LLM-generated SQL and execution

## Problem

The LLM proposes SQL; that SQL must not be trusted to execute against the
warehouse without validation. The gate is the highest-risk component: it decides
whether candidate SQL is safe and legal before any execution.

## Decision

A pure validation gate: `validate(sql, schema) -> ValidationResult`. No side
effects, no data access, no SQL generation or repair. It parses with the DuckDB
dialect (`read="duckdb"`) and runs independent pure-predicate rules, aggregating
all categorized violations.

### Security model
- **Allowlist is primary.** Every query source must resolve to one of the
  introspected warehouse tables (or a CTE-local name). Hallucinated tables,
  system tables (`information_schema`, `duckdb_*`), and table functions
  (`read_csv`, `read_parquet`, ...) all fail because none are warehouse tables.
- **Function denylist is defense-in-depth.** Known dangerous DuckDB functions
  get an earlier, clearer refusal, but the allowlist is the wall.
- **Read-only** enforced by AST statement type (SELECT/CTE/set-ops only) and a
  write-node sweep, with the read-only DuckDB connection as a further backstop.
- **Bounds** injected/clamped at the gate and again at execution.

### Pipeline
non-empty -> parse (terminal on failure) -> single statement -> read-only ->
allowlist -> columns -> functions -> bounds (produces safe_sql).

Steps after parsing aggregate ALL violations, so a rejected query reports every
categorized error, not just the first.

## Key finding during implementation

Adversarial tests caught a real hole: `SELECT * FROM read_csv('/etc/passwd')`
was initially APPROVED. DuckDB parses `read_csv` in FROM as a dedicated
`ReadCSV` node wrapped in an empty-named `Table`, which the naive allowlist walk
skipped. Fix: an empty-named table source is treated as a non-warehouse source
and rejected by the allowlist, and dedicated read-function node types are also
caught by the denylist. This validated the "allowlist is primary" decision —
the allowlist now rejects file-reading functions structurally, independent of
whether the denylist enumerates them.

## Alternatives considered

- **Regex/string validation.** Rejected in the Phase C design review:
  defeatable by comments, string literals, and obfuscation; fails the
  "defensible in an interview" bar.
- **Denylist-primary.** Rejected: denylists are inherently incomplete (a future
  DuckDB function could be missed). The allowlist is a positive guarantee.

## Explicit non-goals

- Not semantic/analytical correctness. A query can be structurally valid and
  still answer the wrong business question; catching that is not the gate's job
  (the response layer surfaces executed SQL so a human can verify meaning).
- No SQL repair/regeneration (that would be guessing).
- No full query-cost governance or cartesian-join detection for Milestone 1;
  the row cap bounds returned damage. Deferred to a later phase.

## Consequences

Strong separation of concerns and interview defensibility; the allowlist-primary
model is robust to denylist gaps; multi-error reporting aids debugging and
testing. Trade-off: the column check is conservative (only qualified columns are
validated) to avoid false positives without full name resolution — acceptable
for Milestone 1, improvable later.
