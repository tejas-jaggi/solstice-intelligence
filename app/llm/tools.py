"""The single tool exposed to the model: run_query.

Minimal by design — one tool, one string argument. The model's only sanctioned
action is to propose a SQL query; that proposal is powerless until the gate
approves it. Kept as a plain dict so client.py can hand it to the provider SDK
without coupling the tool definition to any SDK types.
"""

from __future__ import annotations

RUN_QUERY_TOOL: dict = {
    "type": "function",
    "name": "run_query",
    "description": (
        "Run a single read-only SQL SELECT query against the analytics "
        "warehouse to answer the user's question. Only reference tables and "
        "columns shown in the provided schema. Do not attempt writes or "
        "non-SELECT statements."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "A single read-only SQL SELECT statement.",
            }
        },
        "required": ["sql"],
        "additionalProperties": False,
    },
}
