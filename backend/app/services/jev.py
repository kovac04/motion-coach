"""Decision layer.

Supports three provider modes (env ``DECISION_PROVIDER``):
    mock     — deterministic, scenario-aware fake decisions (default; no credentials)
    jev      — real Jev/System-One style provider (implemented only after provider
               documentation is verified; fails soft to the rules engine)
    fallback — the deterministic rules engine in ``services/fallbacks.py``

The public entry point is ``get_decision_service(settings)``.
"""

from __future__ import annotations

import logging
import time

from app.config import Settings
from app.models.decisions import (
    CoachingPriority,
    MovementDecision,
    OverallQuality,
    PrimaryIssue,
    Severity,
)
from app.models.metrics import RepMetrics, SetMetrics
from app.services.fallbacks import evaluate_decision

logger = logging.getLogger(__name__)

# Canned mock decisions per demo scenario, with illustrative probability spreads.
_MOCK_SCENARIOS: dict[str, MovementDecision] = {
    "perfect_set": MovementDecision(
        primary_issue=PrimaryIssue.GOOD,
        coaching_priority=CoachingPriority.NONE,
        severity=Severity.NONE,
        should_speak=True,
        overall_quality=OverallQuality.EXCELLENT,
        confidence=0.94,
        evidence=["duration_ratio=1.01", "rom_ratio=1.00", "consistency_score=0.97"],
        alternatives={"GOOD": 0.93, "INCONSISTENT": 0.04, "TOO_FAST": 0.03},
        provider="mock",
    ),
    "too_fast": MovementDecision(
        primary_issue=PrimaryIssue.TOO_FAST,
        coaching_priority=CoachingPriority.TEMPO,
        severity=Severity.MODERATE,
        should_speak=True,
        overall_quality=OverallQuality.FAIR,
        confidence=0.91,
        evidence=["duration_ratio=0.73", "tempo_drift=-23% (reps speeding up)"],
        alternatives={"TOO_FAST": 0.82, "GOOD": 0.11, "INCONSISTENT": 0.07},
        provider="mock",
    ),
    "too_slow": MovementDecision(
        primary_issue=PrimaryIssue.TOO_SLOW,
        coaching_priority=CoachingPriority.TEMPO,
        severity=Severity.MODERATE,
        should_speak=True,
        overall_quality=OverallQuality.FAIR,
        confidence=0.86,
        evidence=["duration_ratio=1.18", "tempo_drift=+20% (reps slowing)"],
        alternatives={"TOO_SLOW": 0.78, "GOOD": 0.14, "INCONSISTENT": 0.08},
        provider="mock",
    ),
    "low_rom": MovementDecision(
        primary_issue=PrimaryIssue.INSUFFICIENT_ROM,
        coaching_priority=CoachingPriority.ROM,
        severity=Severity.MODERATE,
        should_speak=True,
        overall_quality=OverallQuality.FAIR,
        confidence=0.90,
        evidence=["rom_ratio=0.78", "range consistently below reference"],
        alternatives={"INSUFFICIENT_ROM": 0.88, "GOOD": 0.08, "INCONSISTENT": 0.04},
        provider="mock",
    ),
    "inconsistent": MovementDecision(
        primary_issue=PrimaryIssue.INCONSISTENT,
        coaching_priority=CoachingPriority.CONSISTENCY,
        severity=Severity.MAJOR,
        should_speak=True,
        overall_quality=OverallQuality.POOR,
        confidence=0.88,
        evidence=["consistency_score=0.66", "duration varies 1700-2300ms"],
        alternatives={"INCONSISTENT": 0.79, "TOO_FAST": 0.12, "GOOD": 0.09},
        provider="mock",
    ),
    "fatigue_drift": MovementDecision(
        primary_issue=PrimaryIssue.INCONSISTENT,
        coaching_priority=CoachingPriority.CONSISTENCY,
        severity=Severity.MODERATE,
        should_speak=True,
        overall_quality=OverallQuality.FAIR,
        confidence=0.84,
        evidence=["rom_drift=-10%", "tempo_drift=+12% late in set"],
        alternatives={"INCONSISTENT": 0.61, "INSUFFICIENT_ROM": 0.24, "GOOD": 0.15},
        provider="mock",
    ),
}


def mock_decision(metrics: RepMetrics | SetMetrics) -> MovementDecision:
    """Return a rich canned decision for a known scenario, else classify the metrics."""
    scenario = metrics.metadata.get("scenario") if isinstance(metrics, SetMetrics) else None
    if scenario and scenario in _MOCK_SCENARIOS:
        return _MOCK_SCENARIOS[scenario].model_copy()
    decision = evaluate_decision(metrics)
    return decision.model_copy(update={"provider": "mock"})


class JevNotVerifiedError(RuntimeError):
    """Raised until the real provider contract has been verified from its own docs."""


class DecisionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.mode = settings.decision_provider

    async def evaluate(self, metrics: RepMetrics | SetMetrics) -> MovementDecision:
        started = time.perf_counter()

        if self.mode == "jev":
            try:
                decision = await self._evaluate_jev(metrics)
            except Exception as exc:  # noqa: BLE001 - fail soft by design
                logger.warning("Jev decision failed (%s); using fallback evaluator", exc)
                decision = evaluate_decision(metrics)
                decision = decision.model_copy(update={"provider": "fallback"})
        elif self.mode == "fallback":
            decision = evaluate_decision(metrics)
        else:
            decision = mock_decision(metrics)

        decision.latency_ms = (time.perf_counter() - started) * 1000.0
        return decision

    async def _evaluate_jev(self, metrics: RepMetrics | SetMetrics) -> MovementDecision:
        """Real provider call.

        Intentionally unimplemented until the provider contract for the specific Jev
        account is verified from that provider's current documentation. Guessing the
        endpoint/schema would violate the project rules, so we fail soft instead.
        """
        if not (self.settings.jev_api_key and self.settings.jev_base_url):
            raise JevNotVerifiedError("JEV_BASE_URL / JEV_API_KEY not configured")
        raise JevNotVerifiedError(
            "Jev provider contract not verified yet; see docs/JEV_PROVIDER.md"
        )


def get_decision_service(settings: Settings) -> DecisionService:
    return DecisionService(settings)
