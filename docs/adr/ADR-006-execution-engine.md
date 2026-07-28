# ADR-006: Execution Engine

- **Status:** Accepted
- **Date:** Phase D, Milestone 1
- **Context area:** Executing validated SQL against the read-only warehouse

## Problem

Approved SQL must be executed against the warehouse and its results returned,
without weakening the trust boundary the validation gate establishes. The
executor is downstream of the gate and must never become a path to run
unvalidated SQL.

## Decision

A single-purpose execution engine: `execute(approved, settings) ->
ExecutionResult`. It obeys; it does not validate, format, or generate.

### Typed boundary
The executor accepts an **`ApprovedQuery`** — not a raw SQL string and not a
bare `ValidationResult`. `ApprovedQuery` is produced by the gate on successful
validation (`ValidationResult.approved_query`). This makes the trust boundary a
single named type: you cannot call the executor without holding the gate's
approval artifact. This narrows *accidental* bypass (the most likely real
failure — a future refactor passing a string).

### Layered safeguards (defense in depth)
1. **Type barrier** — signature requires `ApprovedQuery`.
2. **Approval check** — refuses None/empty approval (`NOT_APPROVED`).
3. **Read-only connection** — even a forged approval carrying a write cannot
   mutate data; DuckDB rejects it physically.
4. **Independent row cap** — the executor fetches at most `max_rows` regardless
   of whether the gate injected LIMIT correctly, and reports `truncated`
   honestly. It never assumes the gate's bounds step succeeded.

### Result model
`ExecutionResult` uses a typed `ExecutionStatus`
(`SUCCESS | NOT_APPROVED | EXECUTION_ERROR | CONNECTION_ERROR`) rather than a
boolean, consistent with Phase C's structured model, and carries observability
metadata: `execution_time_ms`, `rows_returned`, `truncated`, `executed_sql`.
Runtime SQL errors are captured as structured errors — never propagated as raw
DuckDB tracebacks.

## Alternatives considered

- **Executor takes a SQL string.** Rejected: makes the gate a convention, not a
  guarantee — the exact class of bug behind the Phase C `read_csv` exploit.
- **Executor re-runs full validation.** Rejected: couples execution to
  validation and duplicates logic. The type barrier + read-only + row cap is the
  right amount of paranoia for Milestone 1.

## Explicit non-goals / deferred hardening

- **Unforgeable / signed approvals.** A hand-forged `ApprovedQuery` is still
  constructible in Python; the read-only connection is the ultimate backstop for
  that case. Cryptographically-signed or gate-module-scoped approvals are
  documented as post-Milestone-1 hardening, not built now.
- **Query-cost governance** (cartesian joins, scan cost) remains deferred; the
  row cap bounds returned rows.

## Consequences

Clean, typed trust boundary consistent with the rest of the pipeline; four
independent safeguards each covering a distinct failure mode; honest truncation
reporting. Trade-off named above: the type barrier narrows but does not
eliminate forged approvals, mitigated by the read-only backstop.
