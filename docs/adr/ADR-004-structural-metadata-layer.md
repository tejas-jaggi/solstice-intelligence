# ADR-004: Structural Metadata Layer (not a Semantic Glossary)

- **Status:** Accepted
- **Date:** Phase B, Milestone 1
- **Context area:** Warehouse grounding for LLM SQL generation

## Problem

The certified warehouse contains multiple fact tables at different grains that
all relate to overlapping business language. Both `Fact_Orders` (order-header
grain) and `Fact_Order_Lines` (product-line grain) represent "revenue" at
different grains; returns, snapshots, and campaign questions resolve to
different objects. Physical schema grounding alone (names and types) is
insufficient: the LLM can know every table and still choose the wrong grain,
producing a query that executes but answers the wrong question. Wrong-but-valid
answers are the most dangerous failure mode for a trustworthiness-first system.

## Alternatives considered

### A — Semantic glossary (concept → object mapping). Rejected.
Entries like "Revenue by Product → Fact_Order_Lines" are structural, but
"CLV → net_revenue" and "Campaign Performance → Fact_Orders" are business
definitions and modeling opinions. Encoding those turns a "lightweight
glossary" into a metrics layer / ontology — a second source of truth that can
silently drift from the warehouse, contradicting "the warehouse provides
truth," and moving reasoning out of the LLM into a hand-maintained map.

### B — Fold grain hints into schema introspection. Rejected.
Introspected content is discovered and cannot drift; grain descriptions are
authored and can. Mixing them hides that asymmetry and makes drift harder to
test.

### C — Structural metadata layer. Selected.
A separate, strongly-typed, authored layer describing only structure: grain,
business event, primary time key, measures (named, not defined), and join
relationships. Rendered to natural language only at prompt time, and validated
against the introspected schema.

## Decision

`app/metadata/` holds the typed models (`FactMetadata`, `DimensionMetadata`,
`Relationship`, `WarehouseMetadata`) and the authored warehouse metadata.
`app/semantic/grounding.py` assembles schema + metadata into prompt context.
The physical schema remains the single source of truth; the metadata is an
annotation validated against it.

Two engineering properties:

1. **Structured validation report.** `WarehouseMetadata.validate(schema)`
   returns a `ValidationReport` summarizing, per object: existence, missing
   columns, unresolved fields, and join issues — a governance artifact usable
   in logs, CI, and interviews. `raise_if_invalid(schema)` gates the build on
   `report.is_shippable`.

2. **Explicit unresolved sentinel.** Fields needing a real column that is not
   yet confirmed hold the typed `UNRESOLVED` sentinel — never placeholder
   prose. Unresolved state is first-class, reported, blocks shipping, and never
   leaks into rendered prompts.

## Explicit non-goals

Not, and never to become: a metrics engine or KPI store; a business ontology or
semantic model; concept→SQL or concept→object mappings; a home for metric
formulas; or speculative future-feature abstraction. Structure only; meaning is
left to the LLM reasoning against real columns.

## Consequences

**Positive:** grain ambiguity reduced with governed, drift-checked structural
context; discovered vs. authored content cleanly separated; the validation
report is a strong governance and interview artifact; typed models are testable.

**Trade-off:** slightly less deterministic than a hardcoded concept→object map —
the LLM reasons from grain descriptions rather than being handed the answer.
Accepted deliberately. If later empirical testing shows grain mis-selection
despite good descriptions, the correct escalation is to improve descriptions
first, and only then a minimal, explicitly-labeled set of structural grain
hints — never a metrics layer.
