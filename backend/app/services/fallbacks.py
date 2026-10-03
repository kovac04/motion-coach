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

# Centralized thresholds — tune here, nowhere else.
DURATION_RATIO_FAST = 0.85
DURATION_RATIO_SLOW = 1.15
ROM_RATIO_LOW = 0.90
ROM_RATIO_HIGH = 1.15
CONSISTENCY_LOW = 0.85


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


def _severity_from_magnitude(magnitude: float) -> Severity:
    if magnitude < 0.10:
        return Severity.MILD
    if magnitude < 0.25:
        return Severity.MODERATE
    return Severity.MAJOR


def _quality_from_severity(severity: Severity) -> OverallQuality:
    return {
        Severity.NONE: OverallQuality.EXCELLENT,
        Severity.MILD: OverallQuality.GOOD,
        Severity.MODERATE: OverallQuality.FAIR,
        Severity.MAJOR: OverallQuality.POOR,
    }[severity]


def evaluate_decision(metrics: RepMetrics | SetMetrics) -> MovementDecision:
    """Rules-based classification of a rep or set into our internal contract."""
    s = summarize(metrics)
    evidence: list[str] = []

    issue = PrimaryIssue.GOOD
    severity = Severity.NONE
    priority = CoachingPriority.NONE

    if s.duration_ratio is not None and s.duration_ratio < DURATION_RATIO_FAST:
        issue = PrimaryIssue.TOO_FAST
        priority = CoachingPriority.TEMPO
        severity = _severity_from_magnitude(1.0 - s.duration_ratio)
        evidence.append(f"duration_ratio={s.duration_ratio:.2f} (faster than reference)")
    elif s.duration_ratio is not None and s.duration_ratio > DURATION_RATIO_SLOW:
        issue = PrimaryIssue.TOO_SLOW
        priority = CoachingPriority.TEMPO
        severity = _severity_from_magnitude(s.duration_ratio - 1.0)
        evidence.append(f"duration_ratio={s.duration_ratio:.2f} (slower than reference)")
    elif s.rom_ratio is not None and s.rom_ratio < ROM_RATIO_LOW:
        issue = PrimaryIssue.INSUFFICIENT_ROM
        priority = CoachingPriority.ROM
        severity = _severity_from_magnitude(1.0 - s.rom_ratio)
        evidence.append(f"rom_ratio={s.rom_ratio:.2f} (below reference range)")
    elif s.rom_ratio is not None and s.rom_ratio > ROM_RATIO_HIGH:
        issue = PrimaryIssue.EXCESSIVE_ROM
        priority = CoachingPriority.ROM
        severity = _severity_from_magnitude(s.rom_ratio - 1.0)
        evidence.append(f"rom_ratio={s.rom_ratio:.2f} (above reference range)")
    elif s.consistency_score is not None and s.consistency_score < CONSISTENCY_LOW:
        issue = PrimaryIssue.INCONSISTENT
        priority = CoachingPriority.CONSISTENCY
        severity = _severity_from_magnitude(1.0 - s.consistency_score)
        evidence.append(f"consistency_score={s.consistency_score:.2f} (variable reps)")

    if issue is PrimaryIssue.GOOD:
        evidence.append("tempo and range within expected bounds")

    if s.tempo_drift_pct is not None and abs(s.tempo_drift_pct) >= 10:
        evidence.append(f"tempo_drift={s.tempo_drift_pct:+.0f}% across set")

    confidence = 0.55 + 0.05 * len(evidence)
    return MovementDecision(
        primary_issue=issue,
        coaching_priority=priority,
        severity=severity,
        should_speak=True,
        overall_quality=_quality_from_severity(severity),
        confidence=min(confidence, 0.95),
        evidence=evidence,
        provider="fallback",
    )


# --- Language templates -----------------------------------------------------

_COACHING: dict[PrimaryIssue, dict[Severity, str]] = {
    PrimaryIssue.GOOD: {
        Severity.NONE: "Good set. Keep that same rhythm and range.",
        Severity.MILD: "Nice work. Stay relaxed and keep the same rhythm.",
        Severity.MODERATE: "Solid set. Keep each rep smooth and repeatable.",
        Severity.MAJOR: "Good effort. Keep the movement controlled and steady.",
    },
    PrimaryIssue.TOO_FAST: {
        Severity.MILD: "Ease off the speed just slightly and stay smooth.",
        Severity.MODERATE: "Slow down slightly and keep the movement controlled.",
        Severity.MAJOR: "Slow the next set down and control every part of the rep.",
    },
    PrimaryIssue.TOO_SLOW: {
        Severity.MILD: "Keep the tempo, but add a touch more smoothness.",
        Severity.MODERATE: "Pick up the pace slightly while staying controlled.",
        Severity.MAJOR: "Move a little faster, but keep the motion smooth and deliberate.",
    },
    PrimaryIssue.INSUFFICIENT_ROM: {
        Severity.MILD: "Reach just a little further at the end of each rep.",
        Severity.MODERATE: "Focus on completing the full movement range.",
        Severity.MAJOR: "Finish the full range before reversing on the next rep.",
    },
    PrimaryIssue.EXCESSIVE_ROM: {
        Severity.MILD: "Keep the range a touch tighter on the next rep.",
        Severity.MODERATE: "Stay within the same range you used in your reference reps.",
        Severity.MAJOR: "Reduce the range and stay controlled through the whole rep.",
    },
    PrimaryIssue.INCONSISTENT: {
        Severity.MILD: "Keep each rep close to the same rhythm.",
        Severity.MODERATE: "Keep each rep closer to the same tempo and range.",
        Severity.MAJOR: "Reset and make every rep match — same tempo, same range.",
    },
    PrimaryIssue.UNSTABLE: {
        Severity.MILD: "Stay steady and smooth through the whole rep.",
        Severity.MODERATE: "Slow down and keep the motion stable.",
        Severity.MAJOR: "Control the movement — reduce speed and steady each rep.",
    },
    PrimaryIssue.OTHER: {
        Severity.MILD: "Keep the movement smooth and repeatable.",
        Severity.MODERATE: "Focus on clean, controlled reps.",
        Severity.MAJOR: "Slow down and focus on controlled reps.",
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
