"""Deterministic fallback intelligence.

Two responsibilities:
    * ``evaluate_decision`` — simple, centralized rules-based decision engine used when
      the real decision provider is unavailable (and as the base classifier for mock).
    * ``coaching_template`` — deterministic language templates used when the language
      provider is unavailable.

This module is intentionally simple. It exists so a live demo never dies.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.decisions import (
    CoachingPriority,
    MovementDecision,
    OverallQuality,
    PrimaryIssue,
    Severity,
)
from app.models.metrics import RepMetrics, SetMetrics
from app.motion.assessment import deterministic_decision


@dataclass
class _Summary:
    duration_ratio: float | None
    rom_ratio: float | None
    peak_velocity_ratio: float | None
    consistency_score: float | None
    similarity_score: float | None
    tempo_drift_pct: float | None
    rom_drift_pct: float | None


def summarize(metrics: RepMetrics | SetMetrics) -> _Summary:
    """Extract representative ratio values from either a rep or a set."""
    if isinstance(metrics, RepMetrics):
        return _Summary(
            duration_ratio=metrics.duration_ratio,
            rom_ratio=metrics.rom_ratio,
            peak_velocity_ratio=metrics.peak_velocity_ratio,
            consistency_score=None,
            similarity_score=metrics.similarity_score,
            tempo_drift_pct=None,
            rom_drift_pct=None,
        )

    reps = metrics.reps
    duration_ratios = [r.duration_ratio for r in reps if r.duration_ratio is not None]
    rom_ratios = [r.rom_ratio for r in reps if r.rom_ratio is not None]
    return _Summary(
        duration_ratio=sum(duration_ratios) / len(duration_ratios) if duration_ratios else None,
        rom_ratio=sum(rom_ratios) / len(rom_ratios) if rom_ratios else None,
        peak_velocity_ratio=None,
        consistency_score=metrics.consistency_score,
        similarity_score=metrics.reference_similarity_mean,
        tempo_drift_pct=metrics.tempo_drift_pct,
        rom_drift_pct=metrics.rom_drift_pct,
    )


def evaluate_decision(metrics: RepMetrics | SetMetrics) -> MovementDecision:
    """Rules-based fallback, delegated to the deterministic deviation assessment."""
    from app.motion.assessment import assess

    return deterministic_decision(assess(metrics), provider="fallback")


# --- Language templates -----------------------------------------------------

# End-of-set coaching: 15-25 words preferred, hard max 32, at most 2 sentences.
# Sentence 1 says what happened; sentence 2 says what to do next.
_COACHING: dict[PrimaryIssue, dict[Severity, str]] = {
    PrimaryIssue.GOOD: {
        Severity.NONE: "Your tempo and range stayed consistent across the set. Keep that same rhythm on the next set.",
        Severity.MILD: "Your tempo and range stayed consistent across the set. Keep that same rhythm on the next set.",
        Severity.MODERATE: "Your movement held together well overall. Keep that same rhythm and range on the next set.",
        Severity.MAJOR: "Your movement held together well overall. Keep that same rhythm and range on the next set.",
    },
    PrimaryIssue.TOO_FAST: {
        Severity.MILD: "Your reps were slightly quicker than your baseline. Ease off the pace and keep each rep controlled.",
        Severity.MODERATE: "Your reps sped up noticeably through the set. Slow the next set down and keep each rep controlled through the full range.",
        Severity.MAJOR: "Your reps sped up noticeably through the set. Slow the next set down and keep each rep controlled through the full range.",
    },
    PrimaryIssue.TOO_SLOW: {
        Severity.MILD: "Your reps were a little slower than your baseline. Pick up the pace slightly while staying smooth.",
        Severity.MODERATE: "Your reps slowed down through the set. Increase the pace slightly and keep each rep smooth and controlled.",
        Severity.MAJOR: "Your reps slowed down through the set. Increase the pace slightly and keep each rep smooth and controlled.",
    },
    PrimaryIssue.INSUFFICIENT_ROM: {
        Severity.MILD: "Your range was slightly shorter than your baseline. Reach a little further on each rep.",
        Severity.MODERATE: "Your range shortened as the set progressed. Focus on finishing each rep before reversing the movement.",
        Severity.MAJOR: "Your range shortened as the set progressed. Focus on finishing each rep before reversing the movement.",
    },
    PrimaryIssue.EXCESSIVE_ROM: {
        Severity.MILD: "Your range ran a bit longer than your baseline. Keep the range a little tighter.",
        Severity.MODERATE: "Your range ran longer than your baseline. Keep the range consistent and stay controlled through each rep.",
        Severity.MAJOR: "Your range ran longer than your baseline. Keep the range consistent and stay controlled through each rep.",
    },
    PrimaryIssue.INCONSISTENT: {
        Severity.MILD: "Your reps varied slightly in tempo or range. Try to keep each rep close to the same rhythm.",
        Severity.MODERATE: "Your tempo became less consistent across the set. Try to keep every rep closer to the same rhythm.",
        Severity.MAJOR: "Your tempo became less consistent across the set. Try to keep every rep closer to the same rhythm.",
    },
    PrimaryIssue.UNSTABLE: {
        Severity.MILD: "The movement was a little unsteady in places. Stay smooth and controlled through each rep.",
        Severity.MODERATE: "The movement became less steady through the set. Slow down and keep each rep smooth and controlled.",
        Severity.MAJOR: "The movement became less steady through the set. Slow down and keep each rep smooth and controlled.",
    },
    PrimaryIssue.OTHER: {
        Severity.MILD: "The set was mostly solid with a small deviation. Keep the movement smooth and repeatable.",
        Severity.MODERATE: "The movement drifted from your baseline. Slow down and match the same rhythm and range on the next set.",
        Severity.MAJOR: "The movement drifted from your baseline. Slow down and match the same rhythm and range on the next set.",
    },
}


def coaching_template(
    decision: MovementDecision, exercise_display_name: str = ""
) -> tuple[str, str]:
    """Return (text, short_label) for a decision using deterministic templates."""
    issue_map = _COACHING[decision.primary_issue]
    text = issue_map.get(decision.severity, issue_map[Severity.MODERATE])
    short_label = {
        CoachingPriority.TEMPO: "Control your tempo",
        CoachingPriority.ROM: "Own the full range",
        CoachingPriority.CONTROL: "Stay in control",
        CoachingPriority.CONSISTENCY: "Match every rep",
        CoachingPriority.NONE: "Keep it up",
    }[decision.coaching_priority]
    return text, short_label
