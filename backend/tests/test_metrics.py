import pytest
from pydantic import ValidationError

from app.models.metrics import RepMetrics, SetMetrics, build_set_metrics


def test_reference_ratios_are_derived():
    rep = RepMetrics(
        exercise_id="bicep_curl",
        rep_number=1,
        duration_ms=1600,
        reference_duration_ms=2000,
        rom_deg=110,
        reference_rom_deg=120,
        peak_angular_velocity_dps=280,
        reference_peak_velocity_dps=210,
    )
    assert rep.duration_ratio == pytest.approx(0.8)
    assert rep.rom_ratio == pytest.approx(110 / 120)
    assert rep.peak_velocity_ratio == pytest.approx(280 / 210)


def test_optional_fields_can_be_missing():
    rep = RepMetrics(exercise_id="generic_arm_motion", rep_number=1, duration_ms=1800)
    assert rep.rom_deg is None
    assert rep.similarity_score is None


def test_normalized_scores_are_bounded():
    with pytest.raises(ValidationError):
        RepMetrics(
            exercise_id="x",
            rep_number=1,
            duration_ms=1000,
            smoothness_score=1.5,
        )


def test_rep_count_must_match_reps():
    rep = RepMetrics(exercise_id="x", rep_number=1, duration_ms=1000)
    with pytest.raises(ValidationError):
        SetMetrics(exercise_id="x", rep_count=3, reps=[rep])


def test_build_set_metrics_aggregates():
    reps = [
        RepMetrics(
            exercise_id="bicep_curl",
            rep_number=i,
            duration_ms=d,
            reference_duration_ms=2000,
            rom_deg=120,
            reference_rom_deg=120,
        )
        for i, d in enumerate([2000, 2000, 2000], start=1)
    ]
    metrics = build_set_metrics("bicep_curl", reps, scenario="test")
    assert metrics.rep_count == 3
    assert metrics.average_duration_ms == pytest.approx(2000)
    assert metrics.duration_variability == pytest.approx(0.0)
    assert metrics.tempo_drift_pct == pytest.approx(0.0)
    assert metrics.metadata["scenario"] == "test"
