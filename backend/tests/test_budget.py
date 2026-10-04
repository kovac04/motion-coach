import asyncio

import pytest

from app.config import Settings
from app.demo import scenarios
from app.models.coaching import CoachingResponse, Tone
from app.models.decisions import (
    CoachingPriority,
    MovementDecision,
    OverallQuality,
    PrimaryIssue,
    Severity,
)
from app.services.coach_pipeline import CoachPipeline


def _decision() -> MovementDecision:
    return MovementDecision(
        primary_issue=PrimaryIssue.TOO_FAST,
        coaching_priority=CoachingPriority.TEMPO,
        severity=Severity.MODERATE,
        should_speak=True,
        overall_quality=OverallQuality.FAIR,
    )


@pytest.mark.asyncio
async def test_decision_timeout_falls_back(monkeypatch):
    settings = Settings(decision_provider="jev", language_provider="mock",
                        live_jev_timeout_s=0.001, jev_api_key="x", jev_base_url="http://x")
    pipeline = CoachPipeline(settings)

    async def slow_evaluate(_metrics):
        await asyncio.sleep(0.2)
        return _decision()

    monkeypatch.setattr(pipeline.decision_service, "evaluate", slow_evaluate)
    result = await pipeline.evaluate(scenarios.too_fast())
    assert result.decision.provider == "fallback"
    assert result.timings_ms["decision"] < 200


@pytest.mark.asyncio
async def test_language_timeout_uses_template(monkeypatch):
    settings = Settings(decision_provider="mock", language_provider="gemini",
                        live_gemini_timeout_s=0.001, gemini_api_key="x")
    pipeline = CoachPipeline(settings)

    async def slow_generate(_decision, _metrics, _exercise):
        await asyncio.sleep(0.2)
        return CoachingResponse(text="should not be used", short_label="x", tone=Tone.NEUTRAL)

    monkeypatch.setattr(pipeline.language_service, "generate", slow_generate)
    result = await pipeline.evaluate(scenarios.too_fast())
    assert result.coaching.provider == "fallback"
    assert len(result.coaching.text.split()) <= 12
    assert result.timings_ms["coaching"] < 200


def test_fallback_templates_within_word_budget():
    # Guard: the deterministic templates stay within the 12-word budget.
    from app.services.fallbacks import coaching_template

    for issue in PrimaryIssue:
        for severity in Severity:
            decision = MovementDecision(
                primary_issue=issue, coaching_priority=CoachingPriority.TEMPO,
                severity=severity, should_speak=True, overall_quality=OverallQuality.FAIR,
            )
            text, _ = coaching_template(decision, "Bicep Curl")
            assert len(text.split()) <= 12, f"{issue}/{severity}: {text!r}"
