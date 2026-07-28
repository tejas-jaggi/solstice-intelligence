"""LLM orchestration — the single public service.

Coordinates the full pipeline for one natural-language question:

    question -> system prompt (Phase B grounding)
             -> LLM client proposes a query (tool call)
             -> validation gate (Phase C)
             -> execution engine (Phase D)
             -> typed OrchestrationResult

The orchestrator is a conductor. It does not validate SQL, execute SQL, author
schema, or import the OpenAI SDK. It depends only on the LLMClient protocol and
the existing gate/executor, so it is fully testable with a FakeLLMClient and no
network.
"""
from __future__ import annotations

import time

from app.config import Settings, load_settings
from app.execution.executor import execute
from app.llm.client import LLMClient, LLMError
from app.llm.prompts import build_system_prompt
from app.llm.result import OrchestrationResult, PipelineStage
from app.metadata.metadata import WarehouseMetadata
from app.validation.gate import validate
from app.warehouse.schema import WarehouseSchema


class AnalyticsAssistant:
    """The single public orchestration service.

    Constructed with the schema, metadata, and an LLM client; exposes one
    method, ``ask``, which runs the whole pipeline for a question.
    """

    def __init__(
        self,
        schema: WarehouseSchema,
        metadata: WarehouseMetadata,
        client: LLMClient,
        settings: Settings | None = None,
    ) -> None:
        self._schema = schema
        self._metadata = metadata
        self._client = client
        self._settings = settings or load_settings()
        # Assemble the system prompt once — schema/metadata are fixed per session.
        self._system_prompt = build_system_prompt(schema, metadata)

    def ask(self, question: str) -> OrchestrationResult:
        """Coordinate the full pipeline for one natural-language question."""
        start = time.perf_counter()
        model = getattr(self._client, "model_name", "unknown")

        def elapsed() -> float:
            return (time.perf_counter() - start) * 1000.0

        # 1. Ask the model to propose a query (behind the client protocol).
        try:
            proposed = self._client.propose_query(self._system_prompt, question)
        except LLMError as exc:
            return OrchestrationResult(
                stage=PipelineStage.API_ERROR,
                question=question,
                model_name=model,
                total_time_ms=elapsed(),
                error_message=str(exc),
            )

        # 2. No tool call -> the model declined or answered in prose.
        if not proposed.has_query:
            return OrchestrationResult(
                stage=PipelineStage.NO_QUERY_PROPOSED,
                question=question,
                model_name=model,
                model_message=proposed.message,
                total_time_ms=elapsed(),
                error_message=(
                    "The assistant did not produce a query for this question."
                ),
            )

        candidate_sql = proposed.sql

        # 3. Validation gate (Phase C). The orchestrator never inspects SQL itself.
        vresult = validate(candidate_sql, self._schema, self._settings)
        if not vresult.approved:
            return OrchestrationResult(
                stage=PipelineStage.VALIDATION_REJECTED,
                question=question,
                model_name=model,
                candidate_sql=candidate_sql,
                validation=vresult,
                total_time_ms=elapsed(),
                error_message="Proposed query failed validation.",
            )

        # 4. Execution engine (Phase D). Only the approved artifact is passed.
        eresult = execute(vresult.approved_query, self._settings)
        if not eresult.ok:
            return OrchestrationResult(
                stage=PipelineStage.EXECUTION_FAILED,
                question=question,
                model_name=model,
                candidate_sql=candidate_sql,
                validation=vresult,
                execution=eresult,
                total_time_ms=elapsed(),
                error_message=eresult.error_message,
            )

        # 5. Success.
        return OrchestrationResult(
            stage=PipelineStage.COMPLETED,
            question=question,
            model_name=model,
            candidate_sql=candidate_sql,
            validation=vresult,
            execution=eresult,
            total_time_ms=elapsed(),
        )
