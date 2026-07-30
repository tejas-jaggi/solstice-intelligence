"""Validation decision model.

A structured, deterministic result for the SQL validation gate. Rather than a
single refusal reason, a rejected query reports one or more categorized errors,
each with a human-readable message — better for debugging, testing, and
explaining behavior in an interview, while remaining fully deterministic.

The gate is a pure function from (candidate SQL, schema) to a ValidationResult.
It never executes, generates, or repairs SQL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ErrorCategory(str, Enum):
    """Categories of validation failure.

    Categories map to the threat model: parse/structural failures, read-only
    violations, schema (allowlist) violations, and safety (function) violations.
    """

    PARSE_ERROR = "parse_error"
    EMPTY_INPUT = "empty_input"
    MULTIPLE_STATEMENTS = "multiple_statements"
    NON_SELECT_STATEMENT = "non_select_statement"
    UNKNOWN_TABLE = "unknown_table"
    UNKNOWN_COLUMN = "unknown_column"
    DISALLOWED_FUNCTION = "disallowed_function"


@dataclass(frozen=True)
class ValidationError:
    """A single categorized validation failure."""

    category: ErrorCategory
    message: str

    def __str__(self) -> str:
        return f"[{self.category.value}] {self.message}"


@dataclass(frozen=True)
class ApprovedQuery:
    """A proof-of-approval artifact produced by the validation gate.

    The execution engine accepts an ApprovedQuery — not a raw SQL string and not
    a bare ValidationResult — so that the trust boundary is a single named type.
    The only sanctioned producer is the gate on a successful validation.

    This narrows accidental bypass (you cannot call the executor without holding
    one) but does not make forgery cryptographically impossible; the read-only
    connection remains the ultimate backstop. Unforgeable/signed approvals are
    documented as post-Milestone-1 hardening (see ADR-006).
    """

    safe_sql: str


@dataclass(frozen=True)
class ValidationResult:
    """The gate's verdict on a candidate query.

    Attributes:
        approved: True only if there are zero errors.
        errors: All categorized violations found (may be more than one).
        safe_sql: The validated, bounds-applied SQL to execute. Populated only
            when approved; None on rejection. This is the ONLY SQL the executor
            should ever run.
    """

    approved: bool
    errors: tuple[ValidationError, ...] = field(default_factory=tuple)
    safe_sql: str | None = None

    @property
    def categories(self) -> frozenset[ErrorCategory]:
        return frozenset(e.category for e in self.errors)

    @property
    def approved_query(self) -> ApprovedQuery | None:
        """The approval artifact for the executor, or None if rejected."""
        if self.approved and self.safe_sql is not None:
            return ApprovedQuery(safe_sql=self.safe_sql)
        return None

    def render(self) -> str:
        """Human-readable explanation of the verdict."""
        if self.approved:
            return "APPROVED"
        lines = ["REJECTED:"]
        lines.extend(f"  - {e}" for e in self.errors)
        return "\n".join(lines)

    @classmethod
    def approve(cls, safe_sql: str) -> ValidationResult:
        return cls(approved=True, errors=(), safe_sql=safe_sql)

    @classmethod
    def reject(cls, errors: tuple[ValidationError, ...]) -> ValidationResult:
        # A rejection with no errors would be a logic bug; guard against it.
        if not errors:
            raise ValueError("reject() requires at least one error")
        return cls(approved=False, errors=errors, safe_sql=None)
