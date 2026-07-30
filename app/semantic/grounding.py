"""Prompt grounding: assembling LLM context from schema + structural metadata.

Phase B flow:

    Introspected Schema  (truth: real tables/columns/types)
            +
    Structural Metadata  (authored: grain, events, joins)
            |
            v
       Prompt Context

The physical schema is rendered first as the authoritative list of what exists;
the structural metadata is rendered second as grain/relationship guidance. This
module owns assembly only — not policy (the validation gate) and not the LLM
call (the llm package).
"""

from __future__ import annotations

from app.metadata.metadata import WarehouseMetadata
from app.warehouse.schema import WarehouseSchema


def build_grounding_context(schema: WarehouseSchema, metadata: WarehouseMetadata) -> str:
    """Assemble the grounding block injected into the system prompt."""
    parts: list[str] = []
    parts.append(
        "You may query ONLY the following warehouse. The physical schema below "
        "is the source of truth for which tables and columns exist."
    )
    parts.append("PHYSICAL SCHEMA (authoritative):")
    parts.append(schema.to_prompt_text())

    metadata_text = metadata.to_prompt_text()
    if metadata_text:
        parts.append(
            "STRUCTURAL GUIDANCE (use this to choose the correct table grain; "
            "it does not add or change columns):"
        )
        parts.append(metadata_text)

    return "\n\n".join(parts)
