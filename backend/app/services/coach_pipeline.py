"""Orchestration layer. Owns the workflow; services do not call each other."""

from __future__ import annotations

import time

from pydantic import BaseModel

from app.config import Settings
from app.models.coaching import CoachingResponse
from app.models.decisions import MovementDecision
from app.models.metrics import RepMetrics, SetMetrics
from app.services.gemini import get_language_service
from app.services.jev import get_decision_service


class EvaluationResult(BaseModel):
    metrics: RepMetrics | SetMetrics
    decision: MovementDecision
    coaching: CoachingResponse
    timings_ms: dict[str, float]


class CoachPipeline:
    def __init__(self, settings: Settings) -> None:
        self.decision_service = get_decision_service(settings)
        self.language_service = get_language_service(settings)

    async def evaluate(
        self, metrics: RepMetrics | SetMetrics, exercise_id: str | None = None
    ) -> EvaluationResult:
        exercise = exercise_id or metrics.exercise_id

        decision = await self.decision_service.evaluate(metrics)
        coaching = await self.language_service.generate(decision, metrics, exercise)

        return EvaluationResult(
            metrics=metrics,
            decision=decision,
            coaching=coaching,
            timings_ms={
                "decision": decision.latency_ms or 0.0,
                "coaching": coaching.latency_ms or 0.0,
            },
        )
