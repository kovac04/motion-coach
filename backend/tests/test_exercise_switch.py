import numpy as np

from app.config import Settings
from app.motion.calibration import build_profile
from app.motion.profiles import load_profile, profile_path
from app.sensors.packet import ImuSample
from app.services.live_coach import LiveMotionService

AXIS = np.array([0.0, 0.0, 1.0])


def _rows(rep_len: int = 60):
    dt = 0.02
    t = np.arange(0, 16, dt)
    v = np.zeros_like(t)
    for k in range(5):
        s = 100 + k * (2 * rep_len + 10)
        v[s:s + rep_len] = 140.0
        v[s + rep_len:s + 2 * rep_len] = -140.0
    g = np.outer(v, AXIS) * 32.8
    return [
        {"host_timestamp": float(t[i]), "gx_raw": float(g[i, 0]),
         "gy_raw": float(g[i, 1]), "gz_raw": float(g[i, 2])}
        for i in range(len(t))
    ]


def _sample(i, t, gx, gy, gz):
    return ImuSample(sequence=i, timestamp_ms=int(t * 1000), ax=0, ay=0, az=0,
                     gx=int(round(gx)), gy=int(round(gy)), gz=int(round(gz)),
                     host_timestamp=float(t))


def _save(profile):
    profile.save(profile_path(profile.exercise_id))


def test_switch_loads_the_correct_profile(monkeypatch, tmp_path):
    monkeypatch.setattr("app.motion.profiles.PROFILE_DIR", tmp_path)
    bicep = build_profile("bicep_curl", [_rows(rep_len=60)])
    lateral = build_profile("lateral_raise", [_rows(rep_len=40)])
    _save(bicep)
    _save(lateral)

    service = LiveMotionService(Settings(decision_provider="mock", language_provider="mock"))
    # Default exercise is bicep_curl and its own profile is loaded.
    assert service.select_exercise("bicep_curl")["has_profile"] is True
    bicep_ref = service.profile.reference_duration_ms

    assert service.select_exercise("lateral_raise")["has_profile"] is True
    lateral_ref = service.profile.reference_duration_ms

    # The bicep profile must not be reused for lateral raise.
    assert lateral_ref != bicep_ref

    # Switching back restores the previous profile.
    assert service.select_exercise("bicep_curl")["has_profile"] is True
    assert service.profile.reference_duration_ms == bicep_ref


def test_switch_to_uncalibrated_is_no_profile(monkeypatch, tmp_path):
    monkeypatch.setattr("app.motion.profiles.PROFILE_DIR", tmp_path)
    service = LiveMotionService(Settings(decision_provider="mock", language_provider="mock"))
    result = service.select_exercise("triceps_extension")
    assert result["ok"] is True
    assert result["has_profile"] is False
    assert service.profile is None
    assert service.motion_status()["mode"] == "NO_PROFILE"
    # unavailable exercises are rejected
    assert service.select_exercise("bench_press")["ok"] is False


def test_cannot_switch_during_active_set_or_calibration(monkeypatch, tmp_path):
    monkeypatch.setattr("app.motion.profiles.PROFILE_DIR", tmp_path)
    _save(build_profile("bicep_curl", [_rows(60)]))
    service = LiveMotionService(Settings(decision_provider="mock", language_provider="mock"))

    service.start_set()
    assert service.select_exercise("lateral_raise")["ok"] is False
    service.detector.reset()

    service.start_calibration()
    assert service.select_exercise("lateral_raise")["ok"] is False


def test_calibration_saves_under_selected_exercise(monkeypatch, tmp_path):
    monkeypatch.setattr("app.motion.profiles.PROFILE_DIR", tmp_path)
    service = LiveMotionService(Settings(decision_provider="mock", language_provider="mock"))
    assert service.select_exercise("triceps_extension")["has_profile"] is False

    service.start_calibration()
    dt = 0.02
    idx = 0
    t = 0.0
    for _ in range(70):  # quiet baseline
        service.on_sample(_sample(idx, t, 2.0, -1.0, 3.0)); idx += 1; t += dt
    for _ in range(5):   # five reps
        for _ in range(50):
            service.on_sample(_sample(idx, t, 0.0, 0.0, 140.0 * 32.8)); idx += 1; t += dt
        for _ in range(50):
            service.on_sample(_sample(idx, t, 0.0, 0.0, -140.0 * 32.8)); idx += 1; t += dt
        for _ in range(10):
            service.on_sample(_sample(idx, t, 0.0, 0.0, 0.0)); idx += 1; t += dt
    for _ in range(60):
        service.on_sample(_sample(idx, t, 0.0, 0.0, 0.0)); idx += 1; t += dt

    assert service.calibration_result and service.calibration_result["ok"] is True
    assert profile_path("triceps_extension").exists()
    assert not profile_path("bicep_curl").exists()
    assert load_profile("triceps_extension").exercise_id == "triceps_extension"
