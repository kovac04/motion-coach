"""Objective analysis of a recorded IMU CSV.

Pure, hardware-independent functions used by `scripts/imu_analyze.py` and
`scripts/imu_plot.py`. This module reports facts about a signal only — it makes
no attempt to detect reps or classify movement.
"""

from __future__ import annotations

import csv
import math
import statistics
from pathlib import Path

ACCEL_AXES = ("ax_raw", "ay_raw", "az_raw")
GYRO_AXES = ("gx_raw", "gy_raw", "gz_raw")
ALL_AXES = ACCEL_AXES + GYRO_AXES

INT16_MIN = -32768
INT16_MAX = 32767
# Values at/near the rail indicate the chosen full-scale range clipped.
CLIP_LEVEL = 32765


def load_recording_csv(path: Path) -> list[dict[str, float]]:
    """Load an `imu-record` CSV into a list of numeric rows (host_timestamp last)."""
    rows: list[dict[str, float]] = []
    with Path(path).open(newline="") as csv_file:
        for raw in csv.DictReader(csv_file):
            try:
                row = {axis: float(raw[axis]) for axis in ALL_AXES}
            except (KeyError, TypeError, ValueError):
                continue
            host = raw.get("host_timestamp")
            row["host_timestamp"] = float(host) if host not in (None, "") else math.nan
            try:
                row["sequence"] = float(raw.get("sequence", 0) or 0)
            except (TypeError, ValueError):
                row["sequence"] = 0.0
            rows.append(row)
    return rows


def moving_average(values: list[float], window: int) -> list[float]:
    """Centered moving average for visualization only. Never mutates the input."""
    n = len(values)
    if window <= 1 or n == 0:
        return list(values)
    window = min(window, n)
    half = window // 2
    prefix = [0.0]
    for value in values:
        prefix.append(prefix[-1] + value)
    smoothed: list[float] = []
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        smoothed.append((prefix[hi] - prefix[lo]) / (hi - lo))
    return smoothed


def magnitudes(rows: list[dict[str, float]], axes: tuple[str, str, str]) -> list[float]:
    return [math.sqrt(sum(row[axis] ** 2 for axis in axes)) for row in rows]


def _axis_stats(values: list[float]) -> dict[str, float]:
    return {
        "min": min(values),
        "max": max(values),
        "range": max(values) - min(values),
        "variance": statistics.pvariance(values) if len(values) > 1 else 0.0,
    }


def _clip_percent(rows: list[dict[str, float]], axes: tuple[str, str, str]) -> float:
    if not rows:
        return 0.0
    clipped = sum(1 for row in rows if any(abs(row[axis]) >= CLIP_LEVEL for axis in axes))
    return 100.0 * clipped / len(rows)


def analyze_recording(rows: list[dict[str, float]], rest_seconds: float = 2.0) -> dict:
    """Compute objective facts. Raises ValueError on an empty recording."""
    if not rows:
        raise ValueError("recording has no samples")

    count = len(rows)
    timestamps = [row["host_timestamp"] for row in rows if not math.isnan(row["host_timestamp"])]
    duration = (timestamps[-1] - timestamps[0]) if len(timestamps) >= 2 else 0.0
    measured_hz = (count - 1) / duration if duration > 0 else 0.0

    axis_minmax = {
        axis: {"min": _axis_stats([row[axis] for row in rows])["min"],
               "max": _axis_stats([row[axis] for row in rows])["max"]}
        for axis in ALL_AXES
    }

    gyro_variance = {axis: statistics.pvariance([row[axis] for row in rows]) for axis in GYRO_AXES}
    accel_variance = {axis: statistics.pvariance([row[axis] for row in rows]) for axis in ACCEL_AXES}

    # Resting estimate from the first N seconds, if that window has enough samples.
    resting = None
    if len(timestamps) >= 2:
        t0 = timestamps[0]
        rest_rows = [r for r in rows
                     if not math.isnan(r["host_timestamp"]) and r["host_timestamp"] - t0 <= rest_seconds]
        if len(rest_rows) >= 10:
            resting = {
                "samples": len(rest_rows),
                "gyro_std": {axis: statistics.pstdev([r[axis] for r in rest_rows]) for axis in GYRO_AXES},
                "accel_std": {axis: statistics.pstdev([r[axis] for r in rest_rows]) for axis in ACCEL_AXES},
            }

    gyro_mag = magnitudes(rows, GYRO_AXES)
    accel_mag = magnitudes(rows, ACCEL_AXES)

    return {
        "sample_count": count,
        "duration_s": duration,
        "measured_hz": measured_hz,
        "axis_minmax": axis_minmax,
        "clip_percent_accel": _clip_percent(rows, ACCEL_AXES),
        "clip_percent_gyro": _clip_percent(rows, GYRO_AXES),
        "resting": resting,
        "dominant_gyro_axis": max(gyro_variance, key=gyro_variance.get),
        "dominant_accel_axis": max(accel_variance, key=accel_variance.get),
        "gyro_variance": gyro_variance,
        "accel_variance": accel_variance,
        "gyro_magnitude": {"min": min(gyro_mag), "max": max(gyro_mag), "range": max(gyro_mag) - min(gyro_mag)},
        "accel_magnitude": {"min": min(accel_mag), "max": max(accel_mag), "range": max(accel_mag) - min(accel_mag)},
    }


def format_report(analysis: dict, name: str = "") -> str:
    lines: list[str] = []
    if name:
        lines.append(f"Recording: {name}")
    lines.append(f"samples={analysis['sample_count']}  duration={analysis['duration_s']:.2f}s  "
                 f"measured={analysis['measured_hz']:.1f} Hz")
    lines.append("per-axis min/max:")
    for axis, mm in analysis["axis_minmax"].items():
        lines.append(f"  {axis:7s} {mm['min']:9.0f} .. {mm['max']:9.0f}")
    lines.append(f"clip (near int16 rail): accel={analysis['clip_percent_accel']:.2f}%  "
                 f"gyro={analysis['clip_percent_gyro']:.2f}%")
    resting = analysis["resting"]
    if resting:
        g = ", ".join(f"{k}={v:.1f}" for k, v in resting["gyro_std"].items())
        a = ", ".join(f"{k}={v:.1f}" for k, v in resting["accel_std"].items())
        lines.append(f"resting noise (first {resting['samples']} samples): gyro_std[{g}]  accel_std[{a}]")
    else:
        lines.append("resting noise: not identifiable (need ~2 s of still data at the start)")
    lines.append(f"dominant gyro axis (variance): {analysis['dominant_gyro_axis']}   "
                 f"dominant accel axis: {analysis['dominant_accel_axis']}")
    gm, am = analysis["gyro_magnitude"], analysis["accel_magnitude"]
    lines.append(f"gyro |mag| range: {gm['min']:.0f} .. {gm['max']:.0f}   "
                 f"accel |mag| range: {am['min']:.0f} .. {am['max']:.0f}")
    return "\n".join(lines)
