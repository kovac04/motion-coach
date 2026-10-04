import pytest

from app.demo import scenarios
from app.models.decisions import CoachingPriority, MovementDecision, PrimaryIssue, Severity
from app.models.metrics import RepMetrics, build_set_metrics
from app.services.fallbacks import coaching_template, evaluate_decision


def _rep(duration_ms: float, reference: float = 2000.0, rom: float = 120.0, ref_rom: float = 120.0):
    return RepMetrics(
        exercise_id="bicep_curl",
        rep_number=1,
        duration_ms=duration_ms,
        reference_duration_ms=reference,
        rom_deg=rom,
        reference_rom_deg=ref_rom,
    )


def test_fast_rep_classified_too_fast():
    decision = evaluate_decision(_rep(1500))
    assert decision.primary_issue is PrimaryIssue.TOO_FAST
    assert decision.coaching_priority is CoachingPriority.TEMPO


def test_slow_rep_classified_too_slow():
    decision = evaluate_decision(_rep(2600))
    assert decision.primary_issue is PrimaryIssue.TOO_SLOW


def test_low_rom_classified_insufficient():
    decision = evaluate_decision(_rep(2000, rom=80))
    assert decision.primary_issue is PrimaryIssue.INSUFFICIENT_ROM


def test_within_bounds_classified_good():
    decision = evaluate_decision(_rep(2000))
    assert decision.primary_issue is PrimaryIssue.GOOD
    assert decision.severity is Severity.NONE


def test_good_set_does_not_speak():
    decision = evaluate_decision(_rep(2000))
    assert decision.should_speak is False


def test_deviations_request_speech():
    assert evaluate_decision(_rep(1500)).should_speak is True          # too fast
    assert evaluate_decision(_rep(2600)).should_speak is True          # too slow
    assert evaluate_decision(_rep(2000, rom=80)).should_speak is True  # insufficient ROM


def test_set_consistency_classification():
    reps = [_rep(d) for d in [1600, 2400, 1700, 2300, 1650]]
    metrics = build_set_metrics("bicep_curl", reps)
    decision = evaluate_decision(metrics)
    assert decision.primary_issue is PrimaryIssue.INCONSISTENT


def test_coaching_template_always_returns_text():
    decision = MovementDecision(
        primary_issue=PrimaryIssue.TOO_FAST,
        coaching_priority=CoachingPriority.TEMPO,
        severity=Severity.MODERATE,
        should_speak=True,
        overall_quality="FAIR",
    )
    text, label = coaching_template(decision, "Bicep Curl")
    assert text
    assert label
    assert len(text.split()) <= 25
