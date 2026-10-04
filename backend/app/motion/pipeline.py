"""Offline/online orchestration: samples -> projected signal -> reps -> metrics.

Ties together signal processing, calibration, and segmentation. Used by the
offline CLI tools and by the live set detector.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.motion.calibration import (
    FILTER_WINDOW,
    CalibrationProfile,
    rep_waveform,
    waveform_similarity,
)
from app.motion.segmentation import RepSpan, bootstrap_params, detect_reps
from app.motion.signal import RestEstimate, as_matrix, estimate_rest, lowpass, pca_axis, project
from app.models.metrics import RepMetrics, SetMetrics, build_set_metrics


@dataclass
class ProjectedRecording:
    t: np.ndarray
    velocity_dps: np.ndarray  # filtered projected angular velocity
    rest: RestEstimate
    axis: np.ndarray
    axis_variance_fraction: float


def project_samples(samples: list[dict[str, float]], profile: CalibrationProfile | None = None,
                    self_calibrate: bool = True) -> ProjectedRecording:
    """Project gyro samples to one signed angular-velocity signal.

    With ``self_calibrate`` the axis/bias come from this recording (robust to
    different mounts). Otherwise they come from the calibration profile (live use).
    """
    t, g = as_matrix(samples)
    if self_calibrate or profile is None:
        rest = estimate_rest(t, g)
        axis, frac = pca_axis(g, rest.bias, rest.noise_dps)
    else:
        rest = RestEstimate(
            bias=np.asarray(profile.bias, dtype=float),
            noise_dps=profile.noise_dps,
            window_start=0,
            window_end=0,
        )
        axis = np.asarray(profile.axis, dtype=float)
        axis, frac = axis / (np.linalg.norm(axis) + 1e-12), profile.axis_variance_fraction
    velocity = lowpass(project(g, rest.bias, axis), FILTER_WINDOW)
    return ProjectedRecording(t=t, velocity_dps=velocity, rest=rest, axis=axis,
                              axis_variance_fraction=frac)


def detect(projected: ProjectedRecording, profile: CalibrationProfile | None) -> list[RepSpan]:
    params = profile.detector_params() if profile else bootstrap_params(projected.rest.noise_dps)
    return detect_reps(projected.t, projected.velocity_dps, params)


def build_reps(projected: ProjectedRecording, spans: list[RepSpan],
               profile: CalibrationProfile | None, exercise_id: str) -> list[RepMetrics]:
    reference = np.asarray(profile.reference_waveform) if profile else None
    reps: list[RepMetrics] = []
    for number, span in enumerate(spans, start=1):
        similarity = None
        if reference is not None and len(reference):
            similarity = waveform_similarity(rep_waveform(projected.t, projected.velocity_dps, span),
                                             reference)
        reps.append(
            RepMetrics(
                exercise_id=exercise_id,
                rep_number=number,
                duration_ms=span.duration_ms,
                reference_duration_ms=profile.reference_duration_ms if profile else None,
                rom_deg=span.excursion_deg,
                reference_rom_deg=profile.reference_excursion_deg if profile else None,
                peak_angular_velocity_dps=span.peak_velocity_dps,
                reference_peak_velocity_dps=profile.reference_peak_dps if profile else None,
                similarity_score=similarity,
            )
        )
    return reps


def build_set(samples: list[dict[str, float]], profile: CalibrationProfile | None,
              exercise_id: str = "bicep_curl", self_calibrate: bool = True,
              **metadata) -> tuple[ProjectedRecording, list[RepSpan], SetMetrics]:
    projected = project_samples(samples, profile, self_calibrate=self_calibrate)
    spans = detect(projected, profile)
    reps = build_reps(projected, spans, profile, exercise_id)
    metrics = build_set_metrics(exercise_id, reps, **metadata)
    return projected, spans, metrics
