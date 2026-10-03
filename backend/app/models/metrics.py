"""Pydantic boundary models for movement metrics.

These models are the contract between the (future) sensor/signal-processing pipeline
and everything downstream. The hardware team only needs to produce valid
``RepMetrics`` / ``SetMetrics`` — no changes to the rest of the app are required.

Conventions (see docs/ARCHITECTURE.md):
    duration_ratio  < 1  -> faster than reference, > 1 -> slower
    rom_ratio       < 1  -> smaller range than reference
    *_score / confidence are normalized to 0..1
    *_variability  is a coefficient of variation (stdev / mean) as a 0..1 fraction
    *_drift_pct    is a signed percentage change from first to last rep
"""

from __future__ import annotations

from statistics import mean, pstdev
from typing import Any

from pydantic import BaseModel, Field, model_validator

Normalized = Field(default=None, ge=0.0, le=1.0)


class RepMetrics(BaseModel):
    """Objective facts measured for a single repetition."""

    exercise_id: str
    rep_number: int = Field(ge=1)

    duration_ms: float = Field(gt=0)
    reference_duration_ms: float | None = Field(default=None, gt=0)
    duration_ratio: float | None = Field(default=None, gt=0)

    rom_deg: float | None = Field(default=None, ge=0)
    reference_rom_deg: float | None = Field(default=None, ge=0)
    rom_ratio: float | None = Field(default=None, ge=0)

    peak_angular_velocity_dps: float | None = Field(default=None, ge=0)
    reference_peak_velocity_dps: float | None = Field(default=None, ge=0)
    peak_velocity_ratio: float | None = Field(default=None, ge=0)

    smoothness_score: float | None = Normalized
    similarity_score: float | None = Normalized
    confidence: float | None = Normalized

    @model_validator(mode="after")
    def _fill_ratios(self) -> "RepMetrics":
        """Compute ratios from reference values when only raw values were supplied."""
        if self.duration_ratio is None and self.reference_duration_ms:
            self.duration_ratio = self.duration_ms / self.reference_duration_ms
        if self.rom_ratio is None and self.reference_rom_deg:
            self.rom_ratio = self.rom_deg / self.reference_rom_deg
        if self.peak_velocity_ratio is None and self.reference_peak_velocity_dps:
            self.peak_velocity_ratio = (
                self.peak_angular_velocity_dps / self.reference_peak_velocity_dps
            )
        return self


class SetMetrics(BaseModel):
    """Aggregated facts across a completed set of reps."""

    exercise_id: str
    rep_count: int = Field(ge=0)
    reps: list[RepMetrics] = Field(default_factory=list)

    average_duration_ms: float | None = Field(default=None, ge=0)
    duration_variability: float | None = Field(default=None, ge=0)
    average_rom_deg: float | None = Field(default=None, ge=0)
    rom_variability: float | None = Field(default=None, ge=0)
    tempo_drift_pct: float | None = None
    rom_drift_pct: float | None = None
    consistency_score: float | None = Normalized
    reference_similarity_mean: float | None = Normalized

    reference_duration_ms: float | None = Field(default=None, gt=0)
    reference_rom_deg: float | None = Field(default=None, ge=0)
    reference_peak_velocity_dps: float | None = Field(default=None, ge=0)

    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_rep_count(self) -> "SetMetrics":
        if self.rep_count != len(self.reps):
            raise ValueError(
                f"rep_count ({self.rep_count}) does not match len(reps) ({len(self.reps)})"
            )
        return self


def _coefficient_of_variation(values: list[float]) -> float | None:
    if len(values) < 2:
        return 0.0 if values else None
    m = mean(values)
    if m == 0:
        return None
    return pstdev(values) / m


def _drift_pct(values: list[float]) -> float | None:
    if len(values) < 2 or values[0] == 0:
        return None
    return (values[-1] - values[0]) / values[0] * 100.0


def build_set_metrics(exercise_id: str, reps: list[RepMetrics], **metadata: Any) -> SetMetrics:
    """Derive set-level aggregates from per-rep metrics. Pure function."""
    durations = [r.duration_ms for r in reps]
    roms = [r.rom_deg for r in reps if r.rom_deg is not None]
    similarities = [r.similarity_score for r in reps if r.similarity_score is not None]

    duration_cv = _coefficient_of_variation(durations)
    rom_cv = _coefficient_of_variation(roms) if roms else None

    consistency: float | None = None
    if duration_cv is not None:
        combined = duration_cv + (rom_cv or 0.0)
        consistency = max(0.0, min(1.0, 1.0 - combined))

    reference_duration = next((r.reference_duration_ms for r in reps if r.reference_duration_ms), None)
    reference_rom = next((r.reference_rom_deg for r in reps if r.reference_rom_deg), None)

    return SetMetrics(
        exercise_id=exercise_id,
        rep_count=len(reps),
        reps=reps,
        average_duration_ms=mean(durations) if durations else None,
        duration_variability=duration_cv,
        average_rom_deg=mean(roms) if roms else None,
        rom_variability=rom_cv,
        tempo_drift_pct=_drift_pct(durations),
        rom_drift_pct=_drift_pct(roms) if roms else None,
        consistency_score=consistency,
        reference_similarity_mean=mean(similarities) if similarities else None,
        reference_duration_ms=reference_duration,
        reference_rom_deg=reference_rom,
        metadata=metadata,
    )
