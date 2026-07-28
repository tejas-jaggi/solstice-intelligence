# ADR-008: Response Formatting

- **Status:** Accepted
- **Date:** Phase F, Milestone 1
- **Context area:** Presentation boundary between backend and UI

## Problem

The typed OrchestrationResult must be turned into something a UI can present,
without the presentation layer acquiring logic (validation, execution, business
interpretation) or becoming non-deterministic.

## Decision

A pure presentation layer in `app/formatting/`:
- `templates.py` — all user-facing wording (centralized, single-edit copy).
- `response.py` — `AssistantResponse` (the contract) + `ResponseStatus` and
  `ResponseSeverity` enums + `to_dict()`.
- `formatter.py` — pure `format_response(OrchestrationResult) -> AssistantResponse`.

### Deterministic, template-based explanations
Explanations are generated from typed result fields via templates — never by a
second LLM call. This was a deliberate rejection (see below). Explanations
describe what the SYSTEM did (which query ran, how many rows, why a refusal
occurred), never an interpretation of what the DATA means; interpretation is the
user's, and the executed SQL is shown so they can trust the numbers.

### AssistantResponse as the backend presentation contract
A typed, UI-agnostic object — not a formatted string — so future FastAPI (via
`to_dict()`) and Streamlit (via field access) consumers share one contract
without re-parsing. `to_dict()` stringifies cells (Decimal, date) for
trivial JSON-safety.

### Severity for consistent UI treatment
`ResponseSeverity` (INFO / WARNING / ERROR) lets UIs present outcomes
consistently without embedding presentation logic. Success and benign
"no query" are INFO; a rejected query is WARNING; execution/API failures are
ERROR.

### Presentation-security details
- API-error internals (which may carry auth/config detail) are kept OUT of
  user-facing fields and preserved only in `metadata` for logs.
- Rejected SQL is surfaced as `proposed_sql`, explicitly separate from
  `executed_sql`, so an un-run query is never presented as having executed.

## Why LLM-generated explanations were rejected

An LLM narrating results would: (1) add a second API call per question, against
the project's minimal-cost constraint; (2) make the layer non-deterministic and
un-hermetically-testable, breaking the pattern every other subsystem follows;
and (3) reintroduce the exact trust problem the architecture exists to solve — a
model narrating data can misstate it. After five phases keeping the LLM off the
truth path, putting it back on the output would undermine "the warehouse
provides truth." Templates preserve trust, determinism, zero added cost, and
hermetic testing. Narrated insights remain a possible future feature with its
own cost/trust review — not smuggled into the formatter.

## Separation between structured presentation and UI rendering

The formatter produces structured data; it does not render strings for any
specific UI. FastAPI serializes the object; Streamlit reads its fields. String
or widget rendering is each UI's concern, keeping one presentation contract for
many consumers.

## Consequences

The purest, most deterministic layer in the repo (no warehouse/LLM/network in
tests), with the narrowest dependency set (only the typed result modules).
Trade-off: template explanations are less fluent than LLM prose — accepted as
the right choice for a trust-focused tool, and arguably better for it.
