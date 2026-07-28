"""sqlglot parsing wrapper.

Isolates the single place the sqlglot API is used, so a library upgrade or a
dialect change touches one file. Parses with the DuckDB dialect specifically,
because the warehouse is DuckDB and parsing as generic ANSI could mis-handle
DuckDB-specific syntax (wrongly rejecting valid queries or mis-parsing others).
"""
from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import expressions as exp

DIALECT = "duckdb"


@dataclass(frozen=True)
class ParseOutcome:
    """Result of attempting to parse candidate SQL.

    Exactly one of (statements) / (error) is meaningful:
      * On success, ``statements`` holds the parsed expression(s). The gate then
        enforces single-statement separately, so this may contain more than one.
      * On failure, ``error`` holds a human-readable parse error and
        ``statements`` is empty.
    """

    statements: tuple[exp.Expression, ...]
    error: str | None

    @property
    def ok(self) -> bool:
        return self.error is None


def parse_sql(sql: str) -> ParseOutcome:
    """Parse candidate SQL into AST statements using the DuckDB dialect.

    Never raises: a parse failure is returned as an outcome, because malformed
    SQL is an expected input to a validation gate, not an exceptional one.
    """
    try:
        # parse() returns a list of statements; None entries can appear for
        # empty segments (e.g. trailing semicolons) and are filtered out.
        raw = sqlglot.parse(sql, read=DIALECT)
    except Exception as exc:  # sqlglot raises ParseError and subclasses
        return ParseOutcome(statements=(), error=str(exc))

    statements = tuple(s for s in raw if s is not None)
    return ParseOutcome(statements=statements, error=None)
