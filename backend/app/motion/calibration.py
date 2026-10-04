"""Exercise calibration profiles and rep waveform extraction.

A profile captures everything exercise-specific so the live pipeline contains no
hard-coded sensor axes or magic numbers: the PCA rotation axis, resting baseline,
reference rep statistics, a reference waveform, and detector parameters derived
from the data.

The axis sign from PCA is arbitrary. Waveforms are canonicalized (largest sample
positive) and amplitude-normalized before comparison, so signed direction never
matters.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from app.motion.segmentation import DetectorParams, RepSpan, bootstrap_params, detect_reps
from app.motion.signal import (
    canonicalize_waveform,
    estimate_rest,
    lowpass,
    pca_axis,
    project,
    resample,
)

WAVEFORM_POINTS = 100
FILTER_WINDOW = 5  # ~0.1 s centered moving average; light, preserves transitions


@dataclass
class CalibrationProfile:
    exercise_id: str
    axis: list[float]
    bias: list[float]
    noise_dps: float
    params: dict
    reference_duration_ms: float
    duration_spread_ms: float
    reference_excursion_deg: float
    excursion_spread_deg: float
    reference_peak_dps: float
    peak_spread_dps: float
    reference_waveform: list[float]
    reps_used: int
    source: str = ""
    axis_variance_fraction: float = 0.0
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path: Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: Path) -> "CalibrationProfile":
        return cls(**json.loads(Path(path).read_text()))

    def detector_params(self) -> DetectorParams:
        return DetectorParams.from_dict(self.params)


def rep_waveform(t: np.ndarray, velocity_dps: np.ndarray, span: RepSpan,
                 points: int = WAVEFORM_POINTS) -> np.ndarray:
    """Canonicalized, amplitude-normalized waveform for one rep."""
    segment = velocity_dps[span.start: span.end + 1]
    wave = canonicalize_waveform(resample(segment, points))
    peak = float(np.max(np.abs(wave))) if len(wave) else 0.0
    return wave / peak if peak > 0 else wave


def waveform_similarity(wave: np.ndarray, reference: np.ndarray) -> float:
    """Pearson correlation of two zero-mean waveforms, clamped to 0..1.

    Both inputs are sign-canonicalized first, so the arbitrary PCA axis sign
    never affects the score.
    """
    if len(wave) != len(reference) or len(wave) == 0:
        return 0.0
    wave = canonicalize_waveform(np.asarray(wave, dtype=float))
    reference = canonicalize_waveform(np.asarray(reference, dtype=float))
    a = wave - wave.mean()
    b = reference - reference.mean()
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.clip(float(a @ b) / denom, 0.0, 1.0))


def _project(samples: list[dict[str, float]], rest, axis: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    from app.motion.signal import as_matrix

    t, g = as_matrix(samples)
    velocity = lowpass(project(g, rest.bias, axis), FILTER_WINDOW)
    return t, velocity


def build_profile(exercise_id: str, recordings: list[list[dict[str, float]]],
                  source: str = "") -> CalibrationProfile:
    """Build a profile from one or more recordings (usually the GOOD ones).

    Each recording is self-calibrated for its own PCA axis so different mounts do
    not corrupt the reference statistics. The first recording's axis/bias/noise
    become the profile's live defaults.
    """
    if not recordings:
        raise ValueError("no recordings supplied")

    durations: list[float] = []
    excursions: list[float] = []
    peaks: list[float] = []
    waveforms: list[np.ndarray] = []
    live_axis = None
    live_bias = None
    live_noise = None
    live_frac = 0.0

    for index, samples in enumerate(recordings):
        t, g = _as_matrix(samples)
        # Short window: recordings (especially live calibration) may only pause
        # briefly, so a 1 s window can miss the true rest and inflate noise.
        rest = estimate_rest(t, g, window_s=0.5, step_s=0.1)
        axis, frac = pca_axis(g, rest.bias, rest.noise_dps)
        t, velocity = _project(samples, rest, axis)
        params = bootstrap_params(rest.noise_dps)
        spans = detect_reps(t, velocity, params)
        if index == 0:
            live_axis, live_bias, live_noise, live_frac = axis, rest.bias, rest.noise_dps, frac
        for span in spans:
            durations.append(span.duration_ms)
            excursions.append(span.excursion_deg)
            peaks.append(span.peak_velocity_dps)
            waveforms.append(rep_waveform(t, velocity, span))

    if not durations:
        raise ValueError("calibration found no reps; recordings may be too noisy or short")

    reference_duration = float(np.median(durations))
    reference_excursion = float(np.median(excursions))
    reference_peak = float(np.median(peaks))
    reference_waveform = np.mean(np.vstack(waveforms), axis=0)

    params = bootstrap_params(live_noise if live_noise else 2.0)
    params.min_excursion_deg = max(20.0, 0.35 * reference_excursion)
    params.min_phase_deg = max(8.0, 0.25 * reference_excursion)

    return CalibrationProfile(
        exercise_id=exercise_id,
        axis=[float(x) for x in (live_axis if live_axis is not None else [0, 0, 1])],
        bias=[float(x) for x in (live_bias if live_bias is not None else [0, 0, 0])],
        noise_dps=float(live_noise if live_noise else 2.0),
        params=params.to_dict(),
        reference_duration_ms=reference_duration,
        duration_spread_ms=float(np.sqrt(np.mean((np.array(durations) - reference_duration) ** 2))),
        reference_excursion_deg=reference_excursion,
        excursion_spread_deg=float(np.sqrt(np.mean((np.array(excursions) - reference_excursion) ** 2))),
        reference_peak_dps=reference_peak,
        peak_spread_dps=float(np.sqrt(np.mean((np.array(peaks) - reference_peak) ** 2))),
        reference_waveform=[float(x) for x in reference_waveform],
        reps_used=len(durations),
        source=source,
        axis_variance_fraction=live_frac,
        extra={"n_recordings": len(recordings)},
    )


def _as_matrix(samples: list[dict[str, float]]):
    from app.motion.signal import as_matrix

    return as_matrix(samples)
