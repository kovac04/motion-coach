"""Synthetic demo scenarios.

These produce realistic ``SetMetrics`` so the whole product can be exercised before
the IMU pipeline exists. When real hardware arrives it simply produces the same
models — nothing downstream changes.
"""

from __future__ import annotations

from app.models.metrics import RepMetrics, SetMetrics, build_set_metrics

EXERCISE_ID = "bicep_curl"
REFERENCE_DURATION_MS = 2000.0
REFERENCE_ROM_DEG = 120.0
REFERENCE_PEAK_VELOCITY_DPS = 210.0


def _rep(
    number: int,
    duration_ms: float,
    rom_deg: float,
    peak_velocity_dps: float,
    similarity: float,
    smoothness: float,
    confidence: float = 0.9,
) -> RepMetrics:
    return RepMetrics(
        exercise_id=EXERCISE_ID,
        rep_number=number,
        duration_ms=duration_ms,
        reference_duration_ms=REFERENCE_DURATION_MS,
        rom_deg=rom_deg,
        reference_rom_deg=REFERENCE_ROM_DEG,
        peak_angular_velocity_dps=peak_velocity_dps,
        reference_peak_velocity_dps=REFERENCE_PEAK_VELOCITY_DPS,
        smoothness_score=smoothness,
        similarity_score=similarity,
        confidence=confidence,
    )


def _set(scenario: str, label: str, reps: list[RepMetrics]) -> SetMetrics:
    return build_set_metrics(EXERCISE_ID, reps, scenario=scenario, scenario_label=label)


def perfect_set() -> SetMetrics:
    durations = [2050, 1980, 2010, 1990, 2020]
    roms = [120, 119, 121, 120, 119]
    reps = [
        _rep(i + 1, durations[i], float(roms[i]), 205 + i, 0.95 + i * 0.005, 0.92 + i * 0.005)
        for i in range(5)
    ]
    return _set("perfect_set", "Perfect Set", reps)


def too_fast() -> SetMetrics:
    durations = [1950, 1850, 1710, 1600, 1510]
    roms = [118, 117, 118, 116, 117]
    reps = [
        _rep(i + 1, durations[i], float(roms[i]), 250 + i * 12, 0.83 - i * 0.02, 0.85 - i * 0.01)
        for i in range(5)
    ]
    return _set("too_fast", "Too Fast", reps)


def too_slow() -> SetMetrics:
    durations = [2100, 2250, 2380, 2450, 2520]
    roms = [119, 120, 118, 119, 120]
    reps = [
        _rep(i + 1, durations[i], float(roms[i]), 175 - i * 6, 0.90 - i * 0.01, 0.90)
        for i in range(5)
    ]
    return _set("too_slow", "Too Slow", reps)


def low_rom() -> SetMetrics:
    durations = [2000, 2010, 1985, 2020, 1995]
    roms = [96, 94, 95, 92, 93]
    reps = [
        _rep(i + 1, durations[i], float(roms[i]), 210, 0.80 - i * 0.01, 0.88)
        for i in range(5)
    ]
    return _set("low_rom", "Low Range of Motion", reps)


def inconsistent() -> SetMetrics:
    durations = [1700, 2200, 1850, 2300, 1750]
    roms = [110, 125, 105, 128, 112]
    reps = [
        _rep(i + 1, durations[i], float(roms[i]), 230, 0.72 - i * 0.01, 0.78)
        for i in range(5)
    ]
    return _set("inconsistent", "Inconsistent Reps", reps)


def fatigue_drift() -> SetMetrics:
    durations = [2000, 2040, 2090, 2160, 2250]
    roms = [120, 117, 114, 111, 108]
    reps = [
        _rep(i + 1, durations[i], float(roms[i]), 210 - i * 8, 0.93 - i * 0.03, 0.90 - i * 0.02)
        for i in range(5)
    ]
    return _set("fatigue_drift", "Fatigue Drift", reps)


_BUILDERS = {
    "perfect_set": perfect_set,
    "too_fast": too_fast,
    "too_slow": too_slow,
    "low_rom": low_rom,
    "inconsistent": inconsistent,
    "fatigue_drift": fatigue_drift,
}


def custom_set(
    exercise_id: str = EXERCISE_ID,
    duration_ratio: float = 1.0,
    rom_ratio: float = 1.0,
    similarity: float = 0.9,
    smoothness: float = 0.9,
    variability: float = 0.05,
    rep_count: int = 5,
) -> SetMetrics:
    """Build a set from high-level controls (used by the frontend dev panel).

    ``variability`` is the fractional rep-to-rep spread and drives the derived
    consistency score.
    """
    ref_duration = 2000.0
    ref_rom = 120.0
    ref_velocity = 210.0

    reps: list[RepMetrics] = []
    for i in range(rep_count):
        offset = (i - (rep_count - 1) / 2) / max(rep_count - 1, 1)  # -0.5 .. +0.5
        spread = offset * 2 * variability
        duration = ref_duration * duration_ratio * (1 + spread)
        rom = ref_rom * rom_ratio * (1 + spread)
        velocity = ref_velocity / max(duration_ratio, 0.1) * (1 - spread)
        reps.append(
            RepMetrics(
                exercise_id=exercise_id,
                rep_number=i + 1,
                duration_ms=duration,
                reference_duration_ms=ref_duration,
                rom_deg=rom,
                reference_rom_deg=ref_rom,
                peak_angular_velocity_dps=velocity,
                reference_peak_velocity_dps=ref_velocity,
                smoothness_score=max(0.0, min(1.0, smoothness)),
                similarity_score=max(0.0, min(1.0, similarity - abs(spread))),
                confidence=0.9,
            )
        )
    return build_set_metrics(exercise_id, reps, scenario="custom", scenario_label="Custom")


def list_scenario_summaries() -> list[dict[str, str]]:
    return [
        {"id": "perfect_set", "label": "Perfect Set", "description": "Consistent tempo and full range."},
        {"id": "too_fast", "label": "Too Fast", "description": "Reps speed up across the set."},
        {"id": "too_slow", "label": "Too Slow", "description": "Reps get slower than reference."},
        {"id": "low_rom", "label": "Low Range of Motion", "description": "Range stays under reference."},
        {"id": "inconsistent", "label": "Inconsistent Reps", "description": "Tempo and range vary rep to rep."},
        {"id": "fatigue_drift", "label": "Fatigue Drift", "description": "Range shrinks and tempo slows late."},
    ]


def build_scenario(scenario_id: str) -> SetMetrics:
    builder = _BUILDERS.get(scenario_id)
    if builder is None:
        raise KeyError(scenario_id)
    return builder()
