"""Live schema introspection and the structured schema model.

The warehouse provides truth, and that includes the *shape* of the truth. The
schema is read directly from the live DuckDB database at runtime rather than
hand-maintained, so it can never drift from the certified warehouse.

The resulting WarehouseSchema is the single source used for:
  - grounding the LLM (what tables/columns exist), and
  - the validation gate's allowlist (what tables/columns are permitted).

Because both uses share one introspected object, the model the LLM is told
about and the allowlist the gate enforces are guaranteed identical.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import duckdb


@dataclass(frozen=True)
class ColumnInfo:
    """A single column's name and DuckDB type."""

    name: str
    data_type: str


@dataclass(frozen=True)
class TableInfo:
    """A table (or view) and its ordered columns."""

    name: str
    columns: tuple[ColumnInfo, ...]

    @property
    def column_names(self) -> frozenset[str]:
        return frozenset(c.name for c in self.columns)


@dataclass(frozen=True)
class WarehouseSchema:
    """The full introspected schema of the warehouse.

    Provides fast membership checks for the validation allowlist and a compact
    textual rendering for LLM grounding.
    """

    tables: tuple[TableInfo, ...]
    _by_name: dict[str, TableInfo] = field(default_factory=dict, compare=False, repr=False)

    def __post_init__(self) -> None:
        # Build a case-insensitive lookup. DuckDB identifiers are effectively
        # case-insensitive unless quoted; normalising to lower-case gives us a
        # predictable allowlist without surprising the caller.
        object.__setattr__(
            self, "_by_name", {t.name.lower(): t for t in self.tables}
        )

    # -- allowlist helpers used by the validation gate ------------------------

    @property
    def table_names(self) -> frozenset[str]:
        return frozenset(t.name.lower() for t in self.tables)

    def has_table(self, name: str) -> bool:
        return name.lower() in self._by_name

    def has_column(self, table: str, column: str) -> bool:
        t = self._by_name.get(table.lower())
        if t is None:
            return False
        return column.lower() in {c.lower() for c in t.column_names}

    def all_column_names(self) -> frozenset[str]:
        """Every column name across all tables (for unqualified-column checks)."""
        cols: set[str] = set()
        for t in self.tables:
            cols.update(c.lower() for c in t.column_names)
        return frozenset(cols)

    # -- LLM grounding --------------------------------------------------------

    def to_prompt_text(self) -> str:
        """Compact schema description suitable for the system prompt.

        Deliberately terse: one line per table listing columns with types, so
        the model gets the full structure without bloating the context.
        """
        lines: list[str] = []
        for t in self.tables:
            cols = ", ".join(f"{c.name} {c.data_type}" for c in t.columns)
            lines.append(f"{t.name}({cols})")
        return "\n".join(lines)


def introspect(conn: duckdb.DuckDBPyConnection) -> WarehouseSchema:
    """Read the live schema from an open read-only connection.

    Uses information_schema so the logic is standard SQL rather than
    DuckDB-internal pragmas, and restricts to the 'main' schema to avoid
    surfacing system objects into the allowlist.

    Args:
        conn: An open (read-only) DuckDB connection.

    Returns:
        A WarehouseSchema reflecting the current database contents.
    """
    # Tables and views in the user schema. Exclude system/internal schemas.
    table_rows = conn.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'main'
        ORDER BY table_name
        """
    ).fetchall()

    tables: list[TableInfo] = []
    for (table_name,) in table_rows:
        col_rows = conn.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'main' AND table_name = ?
            ORDER BY ordinal_position
            """,
            [table_name],
        ).fetchall()
        columns = tuple(ColumnInfo(name=c[0], data_type=c[1]) for c in col_rows)
        tables.append(TableInfo(name=table_name, columns=columns))

    return WarehouseSchema(tables=tuple(tables))
