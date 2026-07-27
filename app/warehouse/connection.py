"""Read-only connection factory for the certified warehouse.

This is the first line of the trust model. The assistant is a *consumer* of a
frozen, certified analytical database. We therefore open every connection in
read-only mode at the driver level, so that even a total failure of the
validation gate upstream cannot mutate warehouse contents.

Defense in depth: read-only here is not a substitute for the validation gate,
it is a backstop beneath it.
"""
from __future__ import annotations

from pathlib import Path

import duckdb


class WarehouseUnavailableError(RuntimeError):
    """Raised when the warehouse file cannot be found or opened.

    We fail loudly rather than silently creating an empty database. DuckDB will
    happily create a new file if pointed at a non-existent path in read/write
    mode; opening read-only against a missing file must instead surface a clear
    configuration error, because a silently-empty warehouse would let the
    assistant "work" while answering from nothing.
    """


def open_readonly(warehouse_path: Path) -> duckdb.DuckDBPyConnection:
    """Open a strictly read-only connection to the existing warehouse.

    Args:
        warehouse_path: Path to the certified DuckDB file.

    Returns:
        A DuckDB connection opened with read_only=True.

    Raises:
        WarehouseUnavailableError: If the file does not exist or cannot be
            opened read-only.
    """
    path = Path(warehouse_path)
    if not path.exists():
        raise WarehouseUnavailableError(
            f"Warehouse file not found at '{path}'. The assistant does not "
            f"create or regenerate the warehouse; it consumes the existing "
            f"certified database. Set WAREHOUSE_PATH to the correct location."
        )

    try:
        # read_only=True is the enforcement: DuckDB refuses writes on this handle.
        return duckdb.connect(database=str(path), read_only=True)
    except duckdb.Error as exc:  # pragma: no cover - environment dependent
        raise WarehouseUnavailableError(
            f"Failed to open warehouse read-only at '{path}': {exc}"
        ) from exc
