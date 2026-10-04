import pytest

from app.config import Settings
from app.demo import scenarios
from app.models.metrics import RepMetrics, build_set_metrics
from app.services.coach_pipeline import CoachPipeline


def _fast_set():
    reps = [
        RepMetrics(exercise_id="bicep_curl", rep_number=i, duration_ms=1400,
                   reference_duration_ms=2000, rom_deg=120, reference_rom_deg=120)
        for i in range(1, 6)
    ]
    return build_set_metrics("bicep_curl", reps)


@pytest.mark.asyncio
async def test_mock_pipeline_end_to_end():
    settings = Settings(decision_provider="mock", language_provider="mock")
    metrics = scenarios.build_scenario("too_fast")
    result = await CoachPipeline(settings).evaluate(metrics)
    assert result.decision.primary_issue.value == "TOO_FAST"
    assert result.coaching.text
    assert result.timings_ms["decision"] >= 0
    assert result.timings_ms["coaching"] >= 0


@pytest.mark.asyncio
async def test_fallback_decision_provider():
    settings = Settings(decision_provider="fallback", language_provider="fallback")
    result = await CoachPipeline(settings).evaluate(_fast_set())
    assert result.decision.provider == "fallback"
    assert result.decision.primary_issue.value == "TOO_FAST"
    assert result.coaching.provider == "fallback"


@pytest.mark.asyncio
async def test_jev_failure_falls_back_to_rules_engine():
    settings = Settings(
        decision_provider="jev",
        jev_base_url="https://example.invalid",
        jev_api_key="dummy",
        language_provider="mock",
    )
    metrics = scenarios.build_scenario("low_rom")
    result = await CoachPipeline(settings).evaluate(metrics)
    # Jev contract is intentionally not implemented; must fail soft, not crash.
    assert result.decision.provider == "fallback"
    assert result.decision.primary_issue.value == "INSUFFICIENT_ROM"


@pytest.mark.asyncio
async def test_rep_evaluation_missing_optionals():
    settings = Settings(decision_provider="fallback", language_provider="fallback")
    rep = RepMetrics(exercise_id="generic_arm_motion", rep_number=1, duration_ms=1900)
    result = await CoachPipeline(settings).evaluate(rep)
    assert result.coaching.text
