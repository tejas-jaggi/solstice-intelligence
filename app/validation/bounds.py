"""Bounds enforcement: LIMIT injection and clamping.

Separated from rules.py because this step *rewrites* the query (produces the
safe, bounded SQL) rather than merely inspecting it. Enforced here at the gate,
and again independently at execution time as a backstop.
"""

from __future__ import annotations

from sqlglot import expressions as exp

from app.validation.parsing import DIALECT


def apply_limit(statement: exp.Query, max_rows: int, default_limit: int) -> str:
    """Return bounded SQL: inject a LIMIT if absent, clamp it if it exceeds max.

    Args:
        statement: The parsed (and already-validated) statement.
        max_rows: Hard maximum row cap.
        default_limit: LIMIT to inject when the query has none.

    Returns:
        The final SQL string to execute, rendered in the DuckDB dialect.
    """
    # Work on a copy so we never mutate the caller's AST.
    node = statement.copy()

    existing = node.args.get("limit")
    if existing is None:
        node = node.limit(default_limit)
    else:
        # Clamp an existing numeric LIMIT that exceeds the cap.
        try:
            current = int(existing.expression.this)
        except (AttributeError, TypeError, ValueError):
            # Non-numeric / unusual LIMIT expression: replace with the cap to be safe.
            node = node.limit(max_rows)
        else:
            if current > max_rows:
                node = node.limit(max_rows)

    return node.sql(dialect=DIALECT)
