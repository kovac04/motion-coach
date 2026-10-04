"""Orchestration layer. Owns the workflow; services do not call each other.

Live-demo latency budgets: the decision (Jev) and language (Gemini) stages each get
a configurable timeout. If a real provider exceeds its budget we immediately use
the deterministic fallback instead of waiting on the network, so the spoken cue is
never blocked by API variance.
"""

from __future__ import annotations

import asyncio
import logging
import time

from pydantic import BaseModel

from app.config import Settings
from app.models.coaching import CoachingResponse
from app.models.decisions import MovementDecision
from app.models.metrics import RepMetrics, SetMetrics
from app.services.fallbacks import evaluate_decision
from app.services.gemini import get_language_service
from app.services.jev import get_decision_service

logger = logging.getLogger(__name__)


class EvaluationResult(BaseModel):
    metrics: RepMetrics | SetMetrics
    decision: MovementDecision
    coaching: CoachingResponse
    timings_ms: dict[str, float]


class CoachPipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.decision_service = get_decision_service(settings)
        self.language_service = get_language_service(settings)
        self.decision_timeout_s = settings.live_jev_timeout_s
        self.language_timeout_s = settings.live_gemini_timeout_s

    async def evaluate(
        self, metrics: RepMetrics | SetMetrics, exercise_id: str | None = None
    ) -> EvaluationResult:
        exercise = exercise_id or metrics.exercise_id

        # --- decision (Jev), with budget ---
        decision_started = time.perf_counter()
        try:
            decision = await asyncio.wait_for(
                self.decision_service.evaluate(metrics), timeout=self.decision_timeout_s
            )
        except asyncio.TimeoutError:
            logger.warning(
                "JEV TIMEOUT (%.1fs) -> FALLBACK", self.decision_timeout_s
            )
            decision = evaluate_decision(metrics).model_copy(update={"provider": "fallback"})
        decision_ms = (time.perf_counter() - decision_started) * 1000.0
        decision.latency_ms = decision_ms
        logger.info("DECISION: provider=%s latency=%.0fms", decision.provider, decision_ms)

        # --- language (Gemini), with budget ---
        language_started = time.perf_counter()
        try:
            coaching = await asyncio.wait_for(
                self.language_service.generate(decision, metrics, exercise),
                timeout=self.language_timeout_s,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "GEMINI TIMEOUT (%.1fs) -> TEMPLATE", self.language_timeout_s
            )
            coaching = self.language_service.template(decision, exercise, provider="fallback")
        coaching_ms = (time.perf_counter() - language_started) * 1000.0
        coaching.latency_ms = coaching_ms
        logger.info("LANGUAGE: provider=%s latency=%.0fms", coaching.provider, coaching_ms)

        return EvaluationResult(
            metrics=metrics,
            decision=decision,
            coaching=coaching,
            timings_ms={"decision": decision_ms, "coaching": coaching_ms},
        )
