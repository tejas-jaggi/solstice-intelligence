"""Validation rules as independent pure predicates.

Each rule is a pure function of (parsed AST, schema) -> tuple[ValidationError, ...]
(empty tuple meaning "no violation found"). gate.py composes them; none of them
execute SQL, mutate state, or talk to the database.

Security model:
  * The ALLOWLIST is the primary mechanism. Every referenced *warehouse* table
    must be one of the introspected objects. Table functions (e.g. read_csv)
    are not warehouse tables and therefore fail the allowlist independently of
    the denylist.
  * The FUNCTION DENYLIST is defense-in-depth: it gives an earlier, clearer
    refusal for known-dangerous DuckDB functions, but the allowlist is the wall.
"""

from __future__ import annotations

from sqlglot import expressions as exp

from app.validation.decision import ErrorCategory, ValidationError
from app.warehouse.schema import WarehouseSchema

# Defense-in-depth denylist of DuckDB functions/operations that read or write
# outside the database, or change engine state. NOT the primary protection.
DENYLISTED_FUNCTIONS: frozenset[str] = frozenset(
    {
        "read_csv",
        "read_csv_auto",
        "read_parquet",
        "read_json",
        "read_json_auto",
        "read_ndjson",
        "read_ndjson_auto",
        "read_text",
        "read_blob",
        "glob",
        "copy",
    }
)

# Statement node types that are unambiguously not read-only. Presence of any of
# these anywhere in the tree is a read-only violation.
_WRITE_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Merge,
    exp.Copy,
    exp.Command,  # Command covers PRAGMA/SET/ATTACH/etc.
)


def validate_non_empty(sql: str) -> tuple[ValidationError, ...]:
    """Reject empty or whitespace-only input."""
    if sql is None or sql.strip() == "":
        return (ValidationError(ErrorCategory.EMPTY_INPUT, "Query is empty."),)
    return ()


def validate_single_statement(
    statements: tuple[exp.Expression, ...],
) -> tuple[ValidationError, ...]:
    """Reject anything other than exactly one statement (stops smuggling)."""
    if len(statements) != 1:
        return (
            ValidationError(
                ErrorCategory.MULTIPLE_STATEMENTS,
                f"Expected exactly one statement, found {len(statements)}.",
            ),
        )
    return ()


def validate_statement_type(
    statement: exp.Expression,
) -> tuple[ValidationError, ...]:
    """Require the statement to be read-only (a SELECT, possibly with CTEs).

    Checks both the root type and, defensively, the whole subtree for any write
    node — so a write hidden anywhere (which would be unusual SQL, but we do not
    assume) is caught.
    """
    errors: list[ValidationError] = []

    # Root must be a SELECT or a UNION/INTERSECT/EXCEPT of SELECTs. A WITH is
    # represented as a Select carrying a `with` arg in sqlglot, so top-level
    # CTEs still present as Select here.
    root = statement
    if not isinstance(root, (exp.Select, exp.Union, exp.Intersect, exp.Except, exp.Subquery)):
        errors.append(
            ValidationError(
                ErrorCategory.NON_SELECT_STATEMENT,
                f"Only read-only SELECT queries are permitted; got {type(root).__name__}.",
            )
        )

    # Defense in depth: any write node anywhere is a violation.
    for node in statement.find_all(*_WRITE_NODES):
        errors.append(
            ValidationError(
                ErrorCategory.NON_SELECT_STATEMENT,
                f"Disallowed non-read-only operation: {type(node).__name__}.",
            )
        )
        break  # one is enough to reject; avoid duplicate noise

    return tuple(errors)


def _cte_names(statement: exp.Expression) -> set[str]:
    """Names defined by CTEs — these are query-local, not warehouse tables."""
    names: set[str] = set()
    for cte in statement.find_all(exp.CTE):
        alias = cte.alias
        if alias:
            names.add(alias.lower())
    return names


def validate_allowlist(
    statement: exp.Expression, schema: WarehouseSchema
) -> tuple[ValidationError, ...]:
    """Primary mechanism: every referenced base table must be a warehouse table.

    Recursively inspects the AST. A table reference that is neither a known
    warehouse table nor a CTE-defined name is rejected (this is what stops
    hallucinated tables, system tables, and table functions like read_csv,
    since none of those are in the introspected schema).
    """
    errors: list[ValidationError] = []
    cte_names = _cte_names(statement)

    for table in statement.find_all(exp.Table):
        name = table.name  # base table name, unquoted
        # A Table node with no plain name is a table FUNCTION source
        # (e.g. read_csv(...), read_parquet(...)). These are never warehouse
        # tables. Because the allowlist is the primary mechanism, we reject any
        # source that does not resolve to a known warehouse table — including
        # these — independently of the function denylist.
        if not name:
            fn = _table_function_name(table)
            errors.append(
                ValidationError(
                    ErrorCategory.UNKNOWN_TABLE,
                    f"Query source '{fn}' is not a known warehouse table.",
                )
            )
            continue
        lname = name.lower()
        # CTE self-references are legal and not warehouse tables.
        if lname in cte_names:
            continue
        if not schema.has_table(lname):
            errors.append(
                ValidationError(
                    ErrorCategory.UNKNOWN_TABLE,
                    f"Table '{name}' is not a known warehouse table.",
                )
            )

    return tuple(errors)


def _table_function_name(table: exp.Table) -> str:
    """Best-effort human-readable name for a table-function source."""
    inner = table.this
    if inner is not None:
        return type(inner).__name__.lower()
    return "<table function>"


def validate_columns(
    statement: exp.Expression, schema: WarehouseSchema
) -> tuple[ValidationError, ...]:
    """Reject columns that are qualified to a warehouse table but do not exist.

    Only qualified columns (table.column) are checked against that specific
    table, because unqualified columns cannot be attributed to a table by the
    gate without full name resolution (deferred; see design notes). This is a
    deliberately conservative check: it catches confident hallucinations like
    Fact_Orders.nonexistent_column without risking false positives on
    legitimate unqualified references.
    """
    errors: list[ValidationError] = []
    # Map alias -> real table where a table alias is used, so alias.col resolves.
    alias_to_table: dict[str, str] = {}
    for table in statement.find_all(exp.Table):
        if table.alias:
            alias_to_table[table.alias.lower()] = table.name.lower()

    for col in statement.find_all(exp.Column):
        tbl = col.table  # qualifier, may be a real table or an alias
        if not tbl:
            continue  # unqualified: not checked here (conservative)
        real = alias_to_table.get(tbl.lower(), tbl.lower())
        if not schema.has_table(real):
            # The table itself is unknown; validate_allowlist reports that.
            continue
        if not schema.has_column(real, col.name):
            errors.append(
                ValidationError(
                    ErrorCategory.UNKNOWN_COLUMN,
                    f"Column '{col.name}' does not exist on table '{real}'.",
                )
            )

    return tuple(errors)


def validate_functions(
    statement: exp.Expression,
) -> tuple[ValidationError, ...]:
    """Defense-in-depth: reject known dangerous DuckDB functions by name."""
    errors: list[ValidationError] = []
    seen: set[str] = set()

    # (a) Named functions (parsed or anonymous) matching the denylist.
    for func in statement.find_all(exp.Func, exp.Anonymous):
        fname = (func.name or "").lower()
        if fname in DENYLISTED_FUNCTIONS and fname not in seen:
            seen.add(fname)
            errors.append(
                ValidationError(
                    ErrorCategory.DISALLOWED_FUNCTION,
                    f"Function '{fname}' is not permitted.",
                )
            )

    # (b) DuckDB parses some file-reading table functions into dedicated node
    #     types (e.g. read_csv -> exp.ReadCSV) rather than Func/Anonymous. Catch
    #     those by node type as defense-in-depth (the allowlist already rejects
    #     them as non-warehouse sources; this adds a clearer reason).
    for node_type_name in ("ReadCSV",):
        node_type = getattr(exp, node_type_name, None)
        if node_type is None:
            continue
        for _ in statement.find_all(node_type):
            key = node_type_name.lower()
            if key not in seen:
                seen.add(key)
                errors.append(
                    ValidationError(
                        ErrorCategory.DISALLOWED_FUNCTION,
                        f"File-reading table function '{key}' is not permitted.",
                    )
                )
            break

    return tuple(errors)
