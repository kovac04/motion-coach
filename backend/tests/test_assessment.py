from app.models.decisions import PrimaryIssue
from app.models.metrics import RepMetrics, build_set_metrics
from app.motion.assessment import assess, deterministic_decision


def _set(duration_ratios, rom_ratios):
    reps = [
        RepMetrics(
            exercise_id="bicep_curl", rep_number=i + 1,
            duration_ms=dr * 2000.0, reference_duration_ms=2000.0,
            rom_deg=rr * 120.0, reference_rom_deg=120.0,
        )
        for i, (dr, rr) in enumerate(zip(duration_ratios, rom_ratios))
    ]
    return build_set_metrics("bicep_curl", reps)


def test_all_normal_no_candidates_good_no_speech():
    metrics = _set([1.0, 1.02, 0.99, 1.01, 1.0], [1.0, 0.99, 1.01, 1.0, 1.0])
    assessment = assess(metrics)
    assert assessment.candidates == []
    decision = deterministic_decision(assessment, provider="deterministic")
    assert decision.primary_issue is PrimaryIssue.GOOD
    assert decision.should_speak is False
    assert decision.coaching_priority.value == "NONE"


def test_fast_set_becomes_tempo_candidate_not_rom():
    metrics = _set([0.70, 0.72, 0.68, 0.74, 0.71], [1.0, 0.99, 1.01, 1.0, 1.0])
    assessment = assess(metrics)
    assert PrimaryIssue.TOO_FAST in assessment.candidates
    assert PrimaryIssue.INSUFFICIENT_ROM not in assessment.candidates
    decision = deterministic_decision(assessment)
    assert decision.primary_issue is PrimaryIssue.TOO_FAST
    assert decision.coaching_priority.value == "TEMPO"
    assert decision.should_speak is True


def test_short_rom_set_becomes_rom_candidate():
    metrics = _set([1.0, 1.01, 0.99, 1.0, 1.0], [0.70, 0.72, 0.68, 0.71, 0.70])
    assessment = assess(metrics)
    assert PrimaryIssue.INSUFFICIENT_ROM in assessment.candidates
    assert PrimaryIssue.TOO_FAST not in assessment.candidates
    decision = deterministic_decision(assessment)
    assert decision.primary_issue is PrimaryIssue.INSUFFICIENT_ROM


def test_fast_and_short_yields_both_candidates():
    metrics = _set([0.70, 0.72, 0.68, 0.74, 0.71], [0.72, 0.75, 0.70, 0.74, 0.73])
    assessment = assess(metrics)
    assert PrimaryIssue.TOO_FAST in assessment.candidates
    assert PrimaryIssue.INSUFFICIENT_ROM in assessment.candidates


def test_one_weird_rom_rep_does_not_fail_the_set():
    metrics = _set([1.0, 1.01, 0.99, 1.0, 1.0], [1.0, 1.0, 1.0, 1.0, 0.55])
    assessment = assess(metrics)
    # median ROM ~1.0 -> NORMAL; a single short rep must not become a ROM failure.
    assert assessment.rom_state == "NORMAL"
    assert PrimaryIssue.INSUFFICIENT_ROM not in assessment.candidates


def test_one_slow_rep_does_not_hide_a_fast_set():
    metrics = _set([0.70, 0.72, 0.68, 0.74, 1.08], [1.0, 1.0, 1.0, 1.0, 1.0])
    assessment = assess(metrics)
    assert assessment.tempo_state == "TOO_FAST"
    assert PrimaryIssue.TOO_FAST in assessment.candidates


def test_fast_overshoot_does_not_become_excessive_rom():
    # Fast reps overshoot the measured excursion; only TOO_FAST should be a candidate.
    metrics = _set([0.70, 0.72, 0.68, 0.74, 0.71], [1.25, 1.30, 1.22, 1.28, 1.26])
    assessment = assess(metrics)
    assert assessment.rom_state == "EXCESSIVE_ROM"  # measured
    assert PrimaryIssue.TOO_FAST in assessment.candidates
    assert PrimaryIssue.EXCESSIVE_ROM not in assessment.candidates


def test_low_similarity_alone_does_not_create_a_candidate():
    reps = [
        RepMetrics(exercise_id="bicep_curl", rep_number=i, duration_ms=2000,
                   reference_duration_ms=2000, rom_deg=120, reference_rom_deg=120,
                   similarity_score=0.3)
        for i in range(1, 6)
    ]
    metrics = build_set_metrics("bicep_curl", reps)
    assessment = assess(metrics)
    assert assessment.similarity_state == "LOW"
    assert assessment.candidates == []
