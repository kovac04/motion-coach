"""Deterministic deviation assessment.

Layer A (this module) decides WHICH deviations objectively exist, using robust
(median) statistics and a majority rule so a single odd rep cannot classify a set.
Layer B (Jev) may then choose WHICH valid deviation deserves coaching priority,
but it can never invent an issue the facts did not establish.

`rom_ratio` here is *movement excursion relative to the personal reference*, not
true anatomical joint range — decision logic treats it as a relative proxy.
Similarity is supporting evidence only and never creates a candidate.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from app.models.decisions import (
    CoachingPriority,
    MovementDecision,
    OverallQuality,
    PrimaryIssue,
    Severity,
)
from app.models.metrics import RepMetrics, SetMetrics

PRIORITY_FOR_ISSUE = {
    PrimaryIssue.TOO_FAST: CoachingPriority.TEMPO,
    PrimaryIssue.TOO_SLOW: CoachingPriority.TEMPO,
    PrimaryIssue.INSUFFICIENT_ROM: CoachingPriority.ROM,
    PrimaryIssue.EXCESSIVE_ROM: CoachingPriority.ROM,
    PrimaryIssue.INCONSISTENT: CoachingPriority.CONSISTENCY,
    PrimaryIssue.UNSTABLE: CoachingPriority.CONTROL,
    PrimaryIssue.GOOD: CoachingPriority.NONE,
    PrimaryIssue.OTHER: CoachingPriority.CONTROL,
}


@dataclass
class Bands:
    tempo_fast: float = 0.85
    tempo_slow: float = 1.15
    rom_low: float = 0.90
    rom_high: float = 1.15
    consistency_low: float = 0.85
    min_affected_fraction: float = 0.5


@dataclass
class DeviationAssessment:
    rep_count: int
    median_duration_ratio: float | None
    tempo_state: str
    tempo_affected: int
    tempo_affected_fraction: float
    median_rom_ratio: float | None
    rom_state: str
    rom_affected: int
    rom_affected_fraction: float
    consistency_state: str
    consistency_score: float | None
    similarity_state: str
    median_similarity: float | None
    candidates: list[PrimaryIssue] = field(default_factory=list)

    def magnitude(self, issue: PrimaryIssue) -> float:
        if issue is PrimaryIssue.TOO_FAST and self.median_duration_ratio is not None:
            return max(0.0, 1.0 - self.median_duration_ratio)
        if issue is PrimaryIssue.TOO_SLOW and self.median_duration_ratio is not None:
            return max(0.0, self.median_duration_ratio - 1.0)
        if issue is PrimaryIssue.INSUFFICIENT_ROM and self.median_rom_ratio is not None:
            return max(0.0, 1.0 - self.median_rom_ratio)
        if issue is PrimaryIssue.EXCESSIVE_ROM and self.median_rom_ratio is not None:
            return max(0.0, self.median_rom_ratio - 1.0)
        if issue is PrimaryIssue.INCONSISTENT and self.consistency_score is not None:
            return max(0.0, 1.0 - self.consistency_score)
        return 0.0

    def evidence(self) -> list[str]:
        items: list[str] = []
        if self.median_duration_ratio is not None:
            items.append(f"median_duration_ratio={self.median_duration_ratio:.2f} "
                         f"({self.tempo_state.lower()}, {self.tempo_affected}/{self.rep_count} reps)")
        if self.median_rom_ratio is not None:
            items.append(f"median_rom_ratio={self.median_rom_ratio:.2f} "
                         f"({self.rom_state.lower()}, {self.rom_affected}/{self.rep_count} reps)")
        if self.consistency_score is not None:
            items.append(f"consistency={self.consistency_score:.2f} ({self.consistency_state.lower()})")
        if self.median_similarity is not None:
            items.append(f"similarity={self.median_similarity:.2f} ({self.similarity_state.lower()})")
        return items

    def to_dict(self) -> dict:
        return {
            "rep_count": self.rep_count,
            "median_duration_ratio": self.median_duration_ratio,
            "tempo_state": self.tempo_state,
            "tempo_affected": self.tempo_affected,
            "tempo_affected_fraction": round(self.tempo_affected_fraction, 2),
            "median_rom_ratio": self.median_rom_ratio,
            "rom_state": self.rom_state,
            "rom_affected": self.rom_affected,
            "rom_affected_fraction": round(self.rom_affected_fraction, 2),
            "consistency_state": self.consistency_state,
            "consistency_score": self.consistency_score,
            "similarity_state": self.similarity_state,
            "median_similarity": self.median_similarity,
            "candidates": [c.value for c in self.candidates],
        }


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def assess(metrics: RepMetrics | SetMetrics, bands: Bands | None = None) -> DeviationAssessment:
    """Derive robust, deterministic deviation candidates for a rep or set."""
    bands = bands or Bands()
    if isinstance(metrics, RepMetrics):
        duration_ratios = [metrics.duration_ratio] if metrics.duration_ratio is not None else []
        rom_ratios = [metrics.rom_ratio] if metrics.rom_ratio is not None else []
        consistency = None
        similarities = [metrics.similarity_score] if metrics.similarity_score is not None else []
        rep_count = 1
    else:
        duration_ratios = [r.duration_ratio for r in metrics.reps if r.duration_ratio is not None]
        rom_ratios = [r.rom_ratio for r in metrics.reps if r.rom_ratio is not None]
        consistency = metrics.consistency_score
        similarities = [r.similarity_score for r in metrics.reps if r.similarity_score is not None]
        rep_count = metrics.rep_count

    median_duration = _median(duration_ratios)
    median_rom = _median(rom_ratios)
    median_similarity = _median(similarities)

    def affected(values: list[float], predicate) -> int:
        return sum(1 for v in values if predicate(v))

    # Tempo
    tempo_affected = 0
    if median_duration is None:
        tempo_state = "NORMAL"
    elif median_duration < bands.tempo_fast:
        tempo_state = "TOO_FAST"
        tempo_affected = affected(duration_ratios, lambda v: v < bands.tempo_fast)
    elif median_duration > bands.tempo_slow:
        tempo_state = "TOO_SLOW"
        tempo_affected = affected(duration_ratios, lambda v: v > bands.tempo_slow)
    else:
        tempo_state = "NORMAL"
    tempo_fraction = tempo_affected / len(duration_ratios) if duration_ratios else 0.0

    # Excursion (ROM proxy)
    rom_affected = 0
    if median_rom is None:
        rom_state = "NORMAL"
    elif median_rom < bands.rom_low:
        rom_state = "INSUFFICIENT_ROM"
        rom_affected = affected(rom_ratios, lambda v: v < bands.rom_low)
    elif median_rom > bands.rom_high:
        rom_state = "EXCESSIVE_ROM"
        rom_affected = affected(rom_ratios, lambda v: v > bands.rom_high)
    else:
        rom_state = "NORMAL"
    rom_fraction = rom_affected / len(rom_ratios) if rom_ratios else 0.0

    consistency_state = "INCONSISTENT" if (consistency is not None
                                           and consistency < bands.consistency_low) else "NORMAL"
    similarity_state = "LOW" if (median_similarity is not None
                                 and median_similarity < 0.6) else "NORMAL"

    # A deviation only becomes a candidate if the robust median is outside the band
    # AND a majority of reps agree (or it is a single-rep assessment).
    candidates: list[PrimaryIssue] = []

    if tempo_state == "TOO_FAST" and (rep_count <= 1 or tempo_fraction >= bands.min_affected_fraction):
        candidates.append(PrimaryIssue.TOO_FAST)
    elif tempo_state == "TOO_SLOW" and (rep_count <= 1 or tempo_fraction >= bands.min_affected_fraction):
        candidates.append(PrimaryIssue.TOO_SLOW)

    if rom_state == "INSUFFICIENT_ROM" and (rep_count <= 1 or rom_fraction >= bands.min_affected_fraction):
        candidates.append(PrimaryIssue.INSUFFICIENT_ROM)
    elif rom_state == "EXCESSIVE_ROM" and (rep_count <= 1 or rom_fraction >= bands.min_affected_fraction):
        candidates.append(PrimaryIssue.EXCESSIVE_ROM)

    if consistency_state == "INCONSISTENT":
        candidates.append(PrimaryIssue.INCONSISTENT)

    # Fast motion overshoots the integrated excursion, so an elevated rom_ratio
    # during a clearly-fast set is a probable measurement artifact rather than a
    # form fault. Do not emit EXCESSIVE_ROM on its own in that case.
    if PrimaryIssue.TOO_FAST in candidates and PrimaryIssue.EXCESSIVE_ROM in candidates:
        candidates.remove(PrimaryIssue.EXCESSIVE_ROM)

    return DeviationAssessment(
        rep_count=rep_count,
        median_duration_ratio=median_duration,
        tempo_state=tempo_state,
        tempo_affected=tempo_affected,
        tempo_affected_fraction=tempo_fraction,
        median_rom_ratio=median_rom,
        rom_state=rom_state,
        rom_affected=rom_affected,
        rom_affected_fraction=rom_fraction,
        consistency_state=consistency_state,
        consistency_score=consistency,
        similarity_state=similarity_state,
        median_similarity=median_similarity,
        candidates=candidates,
    )


def severity_from_magnitude(magnitude: float) -> Severity:
    if magnitude < 0.10:
        return Severity.MILD
    if magnitude < 0.25:
        return Severity.MODERATE
    return Severity.MAJOR


def quality_from_severity(severity: Severity) -> OverallQuality:
    return {
        Severity.NONE: OverallQuality.EXCELLENT,
        Severity.MILD: OverallQuality.GOOD,
        Severity.MODERATE: OverallQuality.FAIR,
        Severity.MAJOR: OverallQuality.POOR,
    }[severity]


def _severity_for(assessment: DeviationAssessment, issue: PrimaryIssue) -> Severity:
    return severity_from_magnitude(assessment.magnitude(issue))


def deterministic_decision(assessment: DeviationAssessment,
                           provider: str = "fallback") -> MovementDecision:
    """Build a decision purely from the deterministic assessment."""
    if not assessment.candidates:
        return MovementDecision(
            primary_issue=PrimaryIssue.GOOD,
            coaching_priority=CoachingPriority.NONE,
            severity=Severity.NONE,
            should_speak=False,
            overall_quality=OverallQuality.EXCELLENT,
            confidence=0.9,
            evidence=assessment.evidence() or ["close to reference"],
            provider=provider,
        )

    # Highest-magnitude candidate wins.
    primary = max(assessment.candidates, key=assessment.magnitude)
    severity = _severity_for(assessment, primary)
    return MovementDecision(
        primary_issue=primary,
        coaching_priority=PRIORITY_FOR_ISSUE.get(primary, CoachingPriority.CONTROL),
        severity=severity,
        should_speak=True,
        overall_quality=quality_from_severity(severity),
        confidence=min(0.6 + 0.1 * assessment.magnitude(primary), 0.95),
        evidence=assessment.evidence(),
        provider=provider,
    )
