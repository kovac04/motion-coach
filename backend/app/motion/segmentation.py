"""Deterministic rep segmentation from the projected angular-velocity signal.

No ML. A small state machine with hysteresis, minimum/maximum duration, minimum
excursion, opposing-phase requirement, debounce, and a refractory interval.

Thresholds come from the calibration profile (resting noise + reference
movement), never from hard-coded sensor axes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


@dataclass
class DetectorParams:
    start_dps: float = 25.0          # velocity magnitude to start a rep
    stop_dps: float = 10.0           # near-rest threshold to end a rep
    min_rep_ms: float = 400.0
    max_rep_ms: float = 6000.0
    min_excursion_deg: float = 30.0  # total angular range
    min_phase_deg: float = 12.0      # each direction must contribute
    start_debounce: int = 2
    stop_debounce: int = 5
    refractory_ms: float = 250.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DetectorParams":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class RepSpan:
    start: int
    turnaround: int
    end: int
    peak_index: int
    duration_ms: float
    excursion_deg: float
    peak_velocity_dps: float
    phase_a_deg: float
    phase_b_deg: float


def bootstrap_params(noise_dps: float) -> DetectorParams:
    """Derive detector thresholds from the resting noise scale."""
    start = float(np.clip(noise_dps * 6.0, 15.0, 40.0))
    return DetectorParams(
        start_dps=start,
        stop_dps=start * 0.4,
        min_excursion_deg=30.0,
        min_phase_deg=12.0,
    )


def detect_reps(t: np.ndarray, velocity_dps: np.ndarray, params: DetectorParams) -> list[RepSpan]:
    """Segment the projected signal into reps. Pure function."""
    n = len(velocity_dps)
    if n < 5:
        return []
    dt = np.diff(t, prepend=t[0])
    dt[0] = dt[1] if len(dt) > 1 else 0.0

    reps: list[RepSpan] = []
    state = 0  # 0 idle, 1 phase A, 2 phase B
    start = turnaround = peak_index = 0
    theta = theta_min = theta_max = 0.0
    peak_abs = 0.0
    base_sign = 0
    above = below = 0
    refractory_until = -1e9

    def emit(end_index: int) -> None:
        duration_ms = (float(t[end_index]) - float(t[start])) * 1000.0
        theta1 = theta_max if base_sign > 0 else theta_min
        theta2 = theta_min if base_sign > 0 else theta_max
        excursion = theta_max - theta_min
        phase_a = abs(theta1)
        phase_b = abs(theta2 - theta1)
        if (duration_ms >= params.min_rep_ms and excursion >= params.min_excursion_deg
                and min(phase_a, phase_b) >= params.min_phase_deg):
            reps.append(
                RepSpan(
                    start=start,
                    turnaround=turnaround,
                    end=end_index,
                    peak_index=peak_index,
                    duration_ms=duration_ms,
                    excursion_deg=float(excursion),
                    peak_velocity_dps=float(peak_abs),
                    phase_a_deg=float(phase_a),
                    phase_b_deg=float(phase_b),
                )
            )

    def reset(i: int) -> None:
        nonlocal state, start, turnaround, peak_index, theta, theta_min, theta_max, peak_abs, above, below
        state = 1
        start = turnaround = peak_index = i
        theta = theta_min = theta_max = 0.0
        peak_abs = abs(float(velocity_dps[i]))
        above = below = 0

    for i in range(n):
        v = float(velocity_dps[i])
        now = float(t[i])

        if state == 0:
            if now < refractory_until:
                continue
            if abs(v) > params.start_dps:
                above += 1
                if above >= params.start_debounce:
                    base_sign = 1 if v >= 0 else -1
                    reset(i)
                    continue
            else:
                above = 0
            continue

        theta += v * dt[i]
        theta_min = min(theta_min, theta)
        theta_max = max(theta_max, theta)
        if abs(v) > peak_abs:
            peak_abs = abs(v)
            peak_index = i

        # Phase A -> B on a real reversal of the initial direction.
        if state == 1 and v * base_sign < -params.start_dps:
            state = 2
            turnaround = i

        # Continuous reps: when motion returns to the initial direction, the rep
        # is complete and the next rep begins immediately.
        if state == 2 and v * base_sign > params.start_dps:
            emit(i)
            reset(i)
            continue

        if abs(v) < params.stop_dps:
            below += 1
        else:
            below = 0

        duration_ms = (now - float(t[start])) * 1000.0
        if duration_ms > params.max_rep_ms:
            state = 0
            refractory_until = now + params.refractory_ms / 1000.0
            continue

        # End of a set: return to rest after the second phase.
        if state == 2 and below >= params.stop_debounce and duration_ms >= params.min_rep_ms:
            emit(i)
            state = 0
            refractory_until = now + params.refractory_ms / 1000.0

    return reps
