import numpy as np
import pytest

from app.motion.calibration import CalibrationProfile, build_profile, rep_waveform, waveform_similarity
from app.motion.pipeline import build_set
from app.motion.segmentation import DetectorParams, bootstrap_params, detect_reps
from app.motion.signal import (
    as_matrix,
    canonical_sign,
    canonicalize_waveform,
    estimate_rest,
    integrate_angle,
    lowpass,
    pca_axis,
    project,
    resample,
)


def _rows_from_gyro(t, g):
    return [
        {
            "host_timestamp": float(t[i]),
            "gx_raw": float(g[i, 0]),
            "gy_raw": float(g[i, 1]),
            "gz_raw": float(g[i, 2]),
            "ax_raw": 0.0, "ay_raw": 0.0, "az_raw": 0.0,
            "sequence": float(i),
        }
        for i in range(len(t))
    ]


def test_estimate_rest_picks_the_quiet_window():
    dt = 0.02
    t = np.arange(0, 6, dt)
    rng = np.random.default_rng(0)
    g = rng.normal(0, 2.0, size=(len(t), 3))
    # Big motion in the middle, still at the start and end.
    moving = (t > 2) & (t < 4)
    g[moving] += np.array([300.0, -200.0, 100.0])
    rest = estimate_rest(t, g, window_s=1.0)
    assert rest.noise_dps < 10.0  # quiet window found, not the moving one
    assert t[rest.window_start] < 1.0 or t[rest.window_start] > 4.0


def test_pca_recovers_known_axis_up_to_sign():
    rng = np.random.default_rng(1)
    n = 500
    axis_true = np.array([0.0, 0.0, 1.0])
    signal = rng.normal(0, 500, n)
    g = np.outer(signal, axis_true) + rng.normal(0, 5, (n, 3))
    axis, frac = pca_axis(g, bias=np.zeros(3), noise_dps=0.2)
    assert abs(abs(axis[2]) - 1.0) < 0.05
    assert frac > 0.9


def test_pca_sign_is_canonical_and_projection_is_sign_stable():
    n = 300
    g = np.zeros((n, 3))
    g[:, 2] = 200.0
    axis_a, _ = pca_axis(g, np.zeros(3), 0.2)
    axis_b, _ = pca_axis(-g, np.zeros(3), 0.2)  # flipping input must not flip canonical sign
    assert np.allclose(axis_a, axis_b)
    assert canonical_sign(np.array([0.0, 0.0, -1.0]))[2] > 0


def test_project_and_integrate_angle():
    g = np.zeros((100, 3))
    g[:, 1] = 32.8 * 100.0  # 100 dps on y
    axis = np.array([0.0, 1.0, 0.0])
    v = project(g, np.zeros(3), axis)
    assert np.allclose(v, 100.0)
    t = np.arange(100) * 0.02
    angle = integrate_angle(v, t)
    assert angle[-1] == pytest.approx(100.0 * t[-1], rel=0.05)


def test_lowpass_does_not_mutate_and_shrinks_noise():
    v = np.array([0.0, 10.0, 0.0, 10.0, 0.0])
    out = lowpass(v, 3)
    assert np.array_equal(v, np.array([0.0, 10.0, 0.0, 10.0, 0.0]))
    assert np.std(out) < np.std(v)


def test_resample_length_and_endpoints():
    out = resample(np.array([0.0, 1.0, 0.0]), 100)
    assert len(out) == 100
    assert out[0] == pytest.approx(0.0)
    assert out[-1] == pytest.approx(0.0)


def test_canonicalize_waveform_makes_peak_positive():
    wave = np.array([0.0, -3.0, 0.0])
    out = canonicalize_waveform(wave)
    assert out[1] > 0


def test_waveform_similarity_identical_is_one():
    ref = canonicalize_waveform(np.sin(np.linspace(0, 6.28, 100)))
    assert waveform_similarity(ref, ref) == pytest.approx(1.0)
    assert waveform_similarity(ref, -ref) == pytest.approx(1.0)  # sign canonicalized
    assert waveform_similarity(ref, np.roll(ref, 50)) < 0.6


def test_detect_reps_counts_cycles():
    dt = 0.02
    t = np.arange(0, 14, dt)
    v = np.zeros_like(t)
    for k in range(5):  # five up/down reps, 2.2 s apart, brief rest between
        s = 100 + k * 110
        v[s:s + 50] = 150.0
        v[s + 50:s + 100] = -150.0
    params = DetectorParams(start_dps=25, stop_dps=10, min_excursion_deg=20, min_phase_deg=8)
    spans = detect_reps(t, v, params)
    assert len(spans) == 5


def test_detect_reps_does_not_split_on_rebound():
    # One physical rep whose return phase contains a brief rebound that flips the
    # velocity sign back to the starting direction. A naive "returned to initial
    # direction" rule splits this into multiple reps; the position + debounce +
    # min-turn-gap guards must keep it as one.
    dt = 0.02
    t = np.arange(0, 5, dt)
    v = np.zeros_like(t)
    v[50:75] = 150.0     # outbound
    v[75:83] = -150.0    # return begins
    v[83:86] = 80.0      # rebound blip (sign flips back, above start threshold)
    v[86:112] = -150.0   # return continues
    v[112:135] = 150.0   # next lift brings angle back to start -> close
    params = DetectorParams(start_dps=25, stop_dps=10, min_excursion_deg=20, min_phase_deg=8)
    spans = detect_reps(t, v, params)
    assert len(spans) == 1


def test_detect_reps_rejects_tiny_excursion():
    dt = 0.02
    t = np.arange(0, 4, dt)
    v = 5.0 * np.sin(2 * np.pi * 1.0 * t)  # below threshold entirely
    spans = detect_reps(t, v, bootstrap_params(2.0))
    assert spans == []


def test_build_profile_and_set_metrics_from_synthetic():
    dt = 0.02
    t = np.arange(0, 14, dt)
    axis = np.array([0.0, 0.0, 1.0])
    v = np.zeros_like(t)
    for k in range(5):  # five reps, brief rest between
        s = 100 + k * 110
        v[s:s + 50] = 140.0
        v[s + 50:s + 100] = -140.0
    g = np.outer(v, axis) * 32.8
    rows = _rows_from_gyro(t, g)
    profile = build_profile("bicep_curl", [rows])
    projected, spans, metrics = build_set(rows, profile, self_calibrate=True)
    assert len(spans) >= 4
    assert metrics.rep_count == len(spans)
    assert metrics.average_duration_ms and metrics.average_duration_ms > 0
    assert metrics.consistency_score is not None
    assert all(r.similarity_score is not None for r in metrics.reps)
    # Round-trip the profile.
    data = profile.to_dict()
    restored = CalibrationProfile(**data)
    assert restored.exercise_id == "bicep_curl"
