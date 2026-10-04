"""Deterministic signal processing for wrist IMU motion.

Turns raw 3-axis gyro samples into a single signed angular-velocity signal using
PCA, plus robust resting/noise estimation. Nothing here is exercise-specific and
nothing hard-codes a sensor axis.

Units: raw int16 -> degrees/second via the configured gyro sensitivity
(`packet.GYRO_LSB_PER_DPS`).

This is Layer A (facts). It does not detect reps or classify movement.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.sensors.packet import GYRO_LSB_PER_DPS


@dataclass
class RestEstimate:
    """Robust resting baseline found from the quietest window in a recording."""

    bias: np.ndarray  # raw units, per gyro axis
    noise_dps: float  # RMS of the residual in the quietest window, deg/s
    window_start: int
    window_end: int


@dataclass
class Projection:
    """PCA rotation axis and the resulting signed angular-velocity signal."""

    axis: np.ndarray  # unit vector, sign is arbitrary
    variance_fraction: float  # PC1 variance explained, 0..1
    velocity_dps: np.ndarray  # signed angular velocity, deg/s


def as_matrix(samples: list[dict[str, float]]) -> tuple[np.ndarray, np.ndarray]:
    """Return (time_seconds, gyro_raw[N,3]) from recording rows."""
    t = np.asarray([row["host_timestamp"] for row in samples], dtype=float)
    if len(t) >= 1:
        t = t - t[0]
    g = np.asarray(
        [[row["gx_raw"], row["gy_raw"], row["gz_raw"]] for row in samples], dtype=float
    )
    return t, g


def sample_period(t: np.ndarray) -> float:
    """Median sample period in seconds (fallback 0.02 s = 50 Hz)."""
    if len(t) >= 2:
        d = np.diff(t)
        d = d[d > 0]
        if len(d):
            return float(np.median(d))
    return 0.02


def estimate_rest(t: np.ndarray, g_raw: np.ndarray, window_s: float = 1.0,
                  step_s: float = 0.25, min_noise_dps: float = 0.5) -> RestEstimate:
    """Find a quiet window by minimizing residual gyro RMS.

    Robust to recordings that start moving: we slide a window over the whole
    recording and pick the calmest one, instead of assuming the first seconds
    are still.
    """
    n = len(g_raw)
    dt = sample_period(t)
    win = max(3, int(round(window_s / dt)))
    step = max(1, int(round(step_s / dt)))
    if n <= win:
        segments = [(0, n)]
    else:
        segments = [(s, s + win) for s in range(0, n - win + 1, step)]

    best = None
    for start, end in segments:
        segment = g_raw[start:end]
        center = segment.mean(axis=0)
        residual = np.linalg.norm(segment - center, axis=1)
        rms_dps = float(np.sqrt(np.mean(residual ** 2)) / GYRO_LSB_PER_DPS)
        if best is None or rms_dps < best[0]:
            best = (rms_dps, center, start, end)

    rms_dps, center, start, end = best  # type: ignore[misc]
    return RestEstimate(
        bias=center,
        noise_dps=max(rms_dps, min_noise_dps),
        window_start=start,
        window_end=end,
    )


def pca_axis(g_raw: np.ndarray, bias: np.ndarray, noise_dps: float,
             movement_k: float = 8.0) -> tuple[np.ndarray, float]:
    """Dominant rotation axis from PCA over clearly-moving samples.

    Returns (unit_axis, variance_fraction). The sign is canonicalized so the
    largest-magnitude component is positive; callers must not assume a fixed
    sign direction.
    """
    residual = g_raw - bias
    magnitude = np.linalg.norm(residual, axis=1)
    threshold = max(movement_k * noise_dps * GYRO_LSB_PER_DPS, 1.0)
    mask = magnitude > threshold
    if int(mask.sum()) < 10:
        cutoff = np.percentile(magnitude, 70)
        mask = magnitude >= cutoff
    moving = residual[mask]
    if len(moving) < 3:
        return np.array([0.0, 0.0, 1.0]), 0.0

    cov = np.cov(moving.T)
    eigvals, eigvecs = np.linalg.eigh(cov)  # ascending
    axis = eigvecs[:, -1]
    order = np.sort(eigvals)[::-1]
    fraction = float(order[0] / order.sum()) if order.sum() > 0 else 0.0
    axis = canonical_sign(axis)
    return axis, fraction


def canonical_sign(axis: np.ndarray) -> np.ndarray:
    """Make the dominant component positive so the sign convention is stable."""
    axis = axis / (np.linalg.norm(axis) + 1e-12)
    idx = int(np.argmax(np.abs(axis)))
    if axis[idx] < 0:
        axis = -axis
    return axis


def project(g_raw: np.ndarray, bias: np.ndarray, axis: np.ndarray) -> np.ndarray:
    """Signed angular velocity (deg/s) onto the rotation axis."""
    return ((g_raw - bias) @ axis) / GYRO_LSB_PER_DPS


def lowpass(signal: np.ndarray, window: int) -> np.ndarray:
    """Centered moving average. Small windows only; keeps rep transitions."""
    if window <= 1 or len(signal) == 0:
        return np.array(signal, dtype=float)
    window = min(window, len(signal))
    kernel = np.ones(window) / window
    pad = window // 2
    padded = np.pad(signal, pad, mode="edge")
    smoothed = np.convolve(padded, kernel, mode="valid")
    return smoothed[: len(signal)]


def integrate_angle(velocity_dps: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Cumulative angular excursion in degrees (trapezoidal, zero at start)."""
    if len(velocity_dps) < 2:
        return np.zeros_like(velocity_dps)
    dt = np.diff(t, prepend=t[0])
    dt[0] = dt[1] if len(dt) > 1 else 0.0
    return np.cumsum(velocity_dps * dt)


def resample(values: np.ndarray, length: int = 100) -> np.ndarray:
    """Linear-resample a waveform to a fixed number of points."""
    if len(values) == 0:
        return np.zeros(length)
    if len(values) == 1:
        return np.full(length, values[0])
    src = np.linspace(0.0, 1.0, len(values))
    dst = np.linspace(0.0, 1.0, length)
    return np.interp(dst, src, values)


def canonicalize_waveform(values: np.ndarray) -> np.ndarray:
    """Flip a waveform so its largest-magnitude sample is positive.

    The PCA axis sign is arbitrary; this removes that ambiguity before comparing
    reps to a reference.
    """
    if len(values) == 0:
        return values
    idx = int(np.argmax(np.abs(values)))
    return values if values[idx] >= 0 else -values
