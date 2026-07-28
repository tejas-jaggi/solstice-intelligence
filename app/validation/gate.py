"""The SQL validation gate — thin orchestration over pure predicate rules.

Public entry point: ``validate(sql, schema)`` returns a ValidationResult.

Pipeline (fail-closed):
    1. non-empty
    2. parse (DuckDB dialect)          -> parse error is terminal
    3. single statement
    4. read-only (SELECT only)
    5. allowlist (PRIMARY: tables must be warehouse objects)
    6. columns (qualified columns must exist)
    7. functions (defense-in-depth denylist)
    8. bounds (LIMIT injection/clamping) -> produces safe_sql

Steps 3-7 all run when parsing succeeds, so a rejected query reports *every*
categorized violation, not just the first. Bounds is applied only if no errors
were found, since we only bound queries we are going to approve.

The gate is pure: it never executes, generates, or repairs SQL.
"""
from __future__ import annotations

from app.config import Settings, load_settings
from app.validation import rules
from app.validation.bounds import apply_limit
from app.validation.decision import ValidationResult
from app.validation.parsing import parse_sql
from app.warehouse.schema import WarehouseSchema


def validate(
    sql: str,
    schema: WarehouseSchema,
    settings: Settings | None = None,
) -> ValidationResult:
    """Validate candidate SQL against the warehouse schema.

    Args:
        sql: Candidate SQL produced by the LLM.
        schema: The introspected warehouse schema (allowlist source of truth).
        settings: Optional settings override (for bounds caps); defaults to the
            application settings.

    Returns:
        A ValidationResult. If approved, ``safe_sql`` holds the bounded query to
        execute; otherwise ``errors`` lists every categorized violation.
    """
    cfg = settings or load_settings()

    # 1. non-empty (before parsing)
    empty = rules.validate_non_empty(sql)
    if empty:
        return ValidationResult.reject(empty)

    # 2. parse — a parse error is terminal (cannot inspect an AST we do not have)
    outcome = parse_sql(sql)
    if not outcome.ok:
        from app.validation.decision import ErrorCategory, ValidationError
        return ValidationResult.reject(
            (ValidationError(ErrorCategory.PARSE_ERROR, f"Could not parse SQL: {outcome.error}"),)
        )

    # 3. single statement
    single = rules.validate_single_statement(outcome.statements)
    if single:
        # Cannot meaningfully run per-statement AST checks on multiple/zero stmts.
        return ValidationResult.reject(single)

    statement = outcome.statements[0]

    # 4-7. collect ALL structural/safety violations
    errors = (
        rules.validate_statement_type(statement)
        + rules.validate_allowlist(statement, schema)
        + rules.validate_columns(statement, schema)
        + rules.validate_functions(statement)
    )
    if errors:
        return ValidationResult.reject(errors)

    # 8. bounds — only applied to a query we will approve
    safe_sql = apply_limit(statement, cfg.max_rows, cfg.default_limit)
    return ValidationResult.approve(safe_sql)
