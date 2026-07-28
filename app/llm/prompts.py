"""System prompt assembly.

Wraps the Phase B grounding context (schema-as-truth + structural guidance) with
the role and hard rules. Authors NO schema itself — it consumes
build_grounding_context, preserving single-source-of-truth for schema and the
"warehouse is truth" philosophy.

The prompt is for output QUALITY, not security. It encourages safe, correct SQL;
the validation gate GUARANTEES it. Nothing here is a trust boundary.
"""
from __future__ import annotations

from app.metadata.metadata import WarehouseMetadata
from app.semantic.grounding import build_grounding_context
from app.warehouse.schema import WarehouseSchema


_ROLE_AND_RULES = """\
You are an analytics assistant for a data warehouse. Your job is to translate \
the user's business question into a single read-only SQL SELECT query for DuckDB, \
by calling the run_query tool.

Rules:
- Call run_query with exactly one SELECT statement. Never write, update, delete, \
or alter anything.
- Reference ONLY the tables and columns shown in the schema below. Do not invent \
tables or columns.
- Use the structural guidance to choose the correct table grain (for example, \
order-header revenue vs. product-line revenue).
- If the question cannot be answered from this warehouse, say so plainly instead \
of guessing or inventing data. Do not call run_query in that case.
"""


def build_system_prompt(
    schema: WarehouseSchema, metadata: WarehouseMetadata
) -> str:
    """Assemble the full system prompt from role/rules + Phase B grounding."""
    grounding = build_grounding_context(schema, metadata)
    return f"{_ROLE_AND_RULES}\n\n{grounding}"
