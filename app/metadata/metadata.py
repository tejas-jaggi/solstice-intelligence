"""Structural metadata models and drift-validation reporting.

Purpose (and only purpose): reduce warehouse ambiguity for the LLM by supplying
authored STRUCTURAL facts the introspected physical schema cannot express —
chiefly the grain of each fact table and how tables relate.

Boundaries (by design):
  * Structure only. Grain, business event, joins, time key, measures-by-name.
  * Never business definitions, metric formulas, concept->SQL, or ontology.
  * Authored, therefore kept separate from the introspected schema and
    validated against it so it can never silently drift.

Two refinements over the initial design:
  1. Validation produces a structured REPORT (an engineering artifact), not
     only an exception. A convenience raiser sits on top for build gating.
  2. Fields that need a real column but are not yet resolved use an explicit
     UNRESOLVED sentinel rather than placeholder prose, so unresolved state is
     first-class and cannot ship unnoticed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.warehouse.schema import WarehouseSchema


class Unresolved(Enum):
    """Explicit sentinel for a structural field whose real column is unconfirmed.

    Using a distinct type (not None, not a string) means unresolved state is
    unambiguous, type-checkable, and impossible to confuse with a real column
    name. Any field holding UNRESOLVED is reported and blocks the build gate.
    """

    TOKEN = "UNRESOLVED"

    def __str__(self) -> str:  # renders clearly in reports
        return "<UNRESOLVED>"


UNRESOLVED = Unresolved.TOKEN

# A column reference is either a real name (str) or the UNRESOLVED sentinel.
ColumnRef = "str | Unresolved"


@dataclass(frozen=True)
class Relationship:
    """A join relationship from a fact to a dimension."""

    dimension_table: str
    fact_key: str | Unresolved
    dimension_key: str | Unresolved


@dataclass(frozen=True)
class FactMetadata:
    """Authored structural facts about a single fact table.

    ``grain`` and ``business_event`` are structural prose (stable without live
    columns). Column-level fields may be UNRESOLVED until confirmed from the
    live schema.
    """

    table: str
    grain: str
    business_event: str
    primary_time_key: str | Unresolved
    measures: tuple[str | Unresolved, ...]
    relationships: tuple[Relationship, ...]


@dataclass(frozen=True)
class DimensionMetadata:
    """Authored structural facts about a dimension table."""

    table: str
    describes: str
    key_column: str | Unresolved


# --------------------------------------------------------------------------- #
# Validation report
# --------------------------------------------------------------------------- #


class Severity(str, Enum):
    OK = "ok"
    UNRESOLVED = "unresolved"
    MISSING = "missing"


@dataclass(frozen=True)
class ObjectReport:
    """Validation outcome for one metadata object (fact or dimension)."""

    table: str
    exists: bool
    missing_columns: tuple[str, ...]
    unresolved_fields: tuple[str, ...]
    join_issues: tuple[str, ...]

    @property
    def status(self) -> Severity:
        if not self.exists or self.missing_columns or self.join_issues:
            return Severity.MISSING
        if self.unresolved_fields:
            return Severity.UNRESOLVED
        return Severity.OK


@dataclass(frozen=True)
class ValidationReport:
    """Structured governance artifact summarizing metadata validity."""

    objects: tuple[ObjectReport, ...]

    @property
    def tables_validated(self) -> tuple[str, ...]:
        return tuple(o.table for o in self.objects if o.status is Severity.OK)

    @property
    def missing_tables(self) -> tuple[str, ...]:
        return tuple(o.table for o in self.objects if not o.exists)

    @property
    def has_unresolved(self) -> bool:
        return any(o.status is Severity.UNRESOLVED for o in self.objects)

    @property
    def has_errors(self) -> bool:
        return any(o.status is Severity.MISSING for o in self.objects)

    @property
    def is_shippable(self) -> bool:
        """True only if nothing is missing AND nothing is unresolved."""
        return not self.has_errors and not self.has_unresolved

    def render(self) -> str:
        """Human-readable report for logs / CI / interview demonstration."""
        lines = ["Structural Metadata Validation Report", "=" * 38]
        for o in self.objects:
            lines.append(f"[{o.status.value.upper():10}] {o.table}")
            if not o.exists:
                lines.append("             table not present in warehouse schema")
            for c in o.missing_columns:
                lines.append(f"             missing column: {c}")
            for u in o.unresolved_fields:
                lines.append(f"             unresolved: {u}")
            for j in o.join_issues:
                lines.append(f"             join issue: {j}")
        lines.append("-" * 38)
        lines.append(
            f"validated: {len(self.tables_validated)}  "
            f"unresolved: {sum(o.status is Severity.UNRESOLVED for o in self.objects)}  "
            f"errors: {sum(o.status is Severity.MISSING for o in self.objects)}"
        )
        lines.append(f"shippable: {self.is_shippable}")
        return "\n".join(lines)


class MetadataDriftError(ValueError):
    """Raised by the build gate when metadata is not shippable."""


@dataclass(frozen=True)
class WarehouseMetadata:
    """The complete authored structural metadata for the warehouse."""

    facts: tuple[FactMetadata, ...]
    dimensions: tuple[DimensionMetadata, ...] = field(default_factory=tuple)

    # -- validation -----------------------------------------------------------

    def validate(self, schema: WarehouseSchema) -> ValidationReport:
        """Validate every authored reference against the live schema.

        Returns a structured report rather than raising, so callers can inspect
        the full picture. Use ``raise_if_invalid`` for build-gate behavior.
        """
        reports: list[ObjectReport] = []

        def check_col(
            table: str, col: str | Unresolved, missing: list[str], unresolved: list[str], label: str
        ) -> None:
            if isinstance(col, Unresolved):
                unresolved.append(label)
            elif not schema.has_column(table, col):
                missing.append(f"{label}={col}")

        for f in self.facts:
            missing: list[str] = []
            unresolved: list[str] = []
            joins: list[str] = []
            exists = schema.has_table(f.table)
            if exists:
                check_col(f.table, f.primary_time_key, missing, unresolved, "primary_time_key")
                for i, m in enumerate(f.measures):
                    check_col(f.table, m, missing, unresolved, f"measure[{i}]")
                for r in f.relationships:
                    if not schema.has_table(r.dimension_table):
                        joins.append(f"dimension '{r.dimension_table}' missing")
                        continue
                    check_col(
                        f.table,
                        r.fact_key,
                        missing,
                        unresolved,
                        f"join->{r.dimension_table}.fact_key",
                    )
                    check_col(
                        r.dimension_table,
                        r.dimension_key,
                        missing,
                        unresolved,
                        f"join->{r.dimension_table}.dimension_key",
                    )
            reports.append(
                ObjectReport(
                    table=f.table,
                    exists=exists,
                    missing_columns=tuple(missing),
                    unresolved_fields=tuple(unresolved),
                    join_issues=tuple(joins),
                )
            )

        for d in self.dimensions:
            missing = []
            unresolved = []
            exists = schema.has_table(d.table)
            if exists:
                check_col(d.table, d.key_column, missing, unresolved, "key_column")
            reports.append(
                ObjectReport(
                    table=d.table,
                    exists=exists,
                    missing_columns=tuple(missing),
                    unresolved_fields=tuple(unresolved),
                    join_issues=(),
                )
            )

        return ValidationReport(objects=tuple(reports))

    def raise_if_invalid(self, schema: WarehouseSchema) -> ValidationReport:
        """Build gate: validate and raise if the metadata is not shippable.

        Returns the report on success so callers can still log it.
        """
        report = self.validate(schema)
        if not report.is_shippable:
            raise MetadataDriftError("\n" + report.render())
        return report

    # -- LLM grounding rendering ---------------------------------------------

    def to_prompt_text(self) -> str:
        """Render structural metadata as natural language for the prompt.

        Only resolved fields are rendered; unresolved fields are omitted so the
        prompt never contains sentinel tokens. (Callers should gate on a
        shippable report before using this in production.)
        """

        def col(x: str | Unresolved) -> str | None:
            return None if isinstance(x, Unresolved) else x

        lines: list[str] = []
        if self.facts:
            lines.append("FACT TABLES (grain matters — choose the correct one):")
            for f in self.facts:
                lines.append(f"- {f.table}: {f.grain}. {f.business_event}")
                measures = [m for m in (col(x) for x in f.measures) if m]
                if measures:
                    lines.append(f"    measures: {', '.join(measures)}")
                tk = col(f.primary_time_key)
                if tk:
                    lines.append(f"    time key: {tk}")
                joins = []
                for r in f.relationships:
                    fk, dk = col(r.fact_key), col(r.dimension_key)
                    if fk and dk:
                        joins.append(
                            f"{r.dimension_table} (on {f.table}.{fk} = {r.dimension_table}.{dk})"
                        )
                    else:
                        joins.append(r.dimension_table)
                if joins:
                    lines.append(f"    joins: {', '.join(joins)}")
        if self.dimensions:
            lines.append("DIMENSION TABLES:")
            for d in self.dimensions:
                key = col(d.key_column)
                suffix = f" (key: {key})" if key else ""
                lines.append(f"- {d.table}: {d.describes}{suffix}")
        return "\n".join(lines)
