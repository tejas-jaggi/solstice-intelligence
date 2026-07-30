#!/usr/bin/env python
"""Live OpenAI smoke test — the one component that requires a real API call.

Run this MANUALLY on a machine with OPENAI_API_KEY configured. It makes exactly
ONE Responses API call and runs it through the full pipeline (gate -> executor ->
formatter), printing every stage so any mismatch is immediately visible.

Cost control: a single request, no retries, no loops. Expect a few cents at most.

Usage (from repo root, venv active, .env populated):
    python -m scripts.smoke_test_openai
    python -m scripts.smoke_test_openai "which customers generate the most revenue?"

Exit codes:
    0  full pipeline completed (COMPLETED stage)
    1  pipeline ran but did not complete (inspect the printed stage/reason)
    2  setup/config error (no key, warehouse missing, SDK issue)
"""

from __future__ import annotations

import sys

# Load .env if python-dotenv is available (matches app config behavior).
try:
    from dotenv import load_dotenv

    from app.config import REPO_ROOT

    load_dotenv(REPO_ROOT / ".env")
except Exception:
    pass

import os

from app.config import load_settings
from app.formatting.formatter import format_response
from app.llm.client import LLMError, OpenAIClient
from app.llm.orchestrator import AnalyticsAssistant
from app.llm.tools import RUN_QUERY_TOOL
from app.metadata.warehouse_metadata import build_warehouse_metadata
from app.warehouse.connection import WarehouseUnavailableError, open_readonly
from app.warehouse.schema import introspect

RULE = "-" * 72


def main() -> int:
    question = sys.argv[1] if len(sys.argv) > 1 else "How many orders are in the warehouse?"

    print(RULE)
    print("Solstice Intelligence — Live OpenAI Smoke Test")
    print(RULE)

    # 1. Config + key present
    settings = load_settings()
    if not os.environ.get("OPENAI_API_KEY"):
        print("SETUP ERROR: OPENAI_API_KEY is not set (check .env).")
        return 2
    print(f"Model:          {settings.openai_model}")
    print(f"Warehouse:      {settings.warehouse_path}")
    print(f"Question:       {question!r}")
    print(RULE)

    # 2. Warehouse + schema
    try:
        conn = open_readonly(settings.warehouse_path)
    except WarehouseUnavailableError as exc:
        print(f"SETUP ERROR: {exc}")
        return 2
    schema = introspect(conn)
    conn.close()
    metadata = build_warehouse_metadata()

    # Confirm metadata is shippable against the real schema before spending a call.
    report = metadata.validate(schema)
    if not report.is_shippable:
        print("SETUP ERROR: warehouse metadata not shippable against schema:")
        print(report.render())
        return 2
    print(f"Schema:         {len(schema.tables)} tables introspected; metadata shippable")

    # 3. One real API call through the full pipeline
    try:
        client = OpenAIClient(model_name=settings.openai_model, tool_schema=RUN_QUERY_TOOL)
    except LLMError as exc:
        print(f"SETUP ERROR: {exc}")
        return 2

    assistant = AnalyticsAssistant(schema, metadata, client, settings)
    result = assistant.ask(question)

    # 4. Show every stage
    print(RULE)
    print(f"Pipeline stage: {result.stage.value}")
    print(f"Model:          {result.model_name}")
    if result.candidate_sql:
        print(f"Candidate SQL:  {result.candidate_sql}")
    if result.validation is not None:
        print(f"Validation:     {'APPROVED' if result.validation.approved else 'REJECTED'}")
        if not result.validation.approved:
            for e in result.validation.errors:
                print(f"                - {e}")
    if result.execution is not None:
        print(f"Execution:      {result.execution.render()}")

    # 5. Final user-facing response
    print(RULE)
    print("AssistantResponse:")
    resp = format_response(result)
    print(f"  headline:    {resp.headline}")
    print(f"  severity:    {resp.severity.value}")
    print(f"  explanation: {resp.explanation}")
    if resp.executed_sql:
        print(f"  executed_sql: {resp.executed_sql}")
    if resp.rows:
        print(f"  columns:     {resp.columns}")
        for row in resp.rows[:5]:
            print(f"    {row}")
    print(RULE)

    from app.llm.result import PipelineStage

    if result.stage is PipelineStage.COMPLETED:
        print("RESULT: ✅ full pipeline completed end-to-end.")
        return 0
    print(f"RESULT: pipeline ran but concluded at '{result.stage.value}'. See above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
