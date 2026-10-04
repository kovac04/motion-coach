import numpy as np
import pytest

from app.motion.calibration import build_profile
from app.motion.live import LiveSetDetector
from app.sensors.packet import ImuSample

AXIS = np.array([0.0, 0.0, 1.0])


def _synthetic_rows(reps: int = 5):
    dt = 0.02
    t = np.arange(0, 14, dt)
    v = np.zeros_like(t)
    for k in range(reps):
        s = 100 + k * 110
        v[s:s + 50] = 140.0
        v[s + 50:s + 100] = -140.0
    g = np.outer(v, AXIS) * 32.8
    rows = [
        {"host_timestamp": float(t[i]), "gx_raw": float(g[i, 0]),
         "gy_raw": float(g[i, 1]), "gz_raw": float(g[i, 2])}
        for i in range(len(t))
    ]
    return t, g, rows


def _sample(i, t, g):
    return ImuSample(
        sequence=i, timestamp_ms=int(t[i] * 1000),
        ax=0, ay=0, az=0,
        gx=int(round(g[i, 0])), gy=int(round(g[i, 1])), gz=int(round(g[i, 2])),
        host_timestamp=float(t[i]),
    )


def _profile():
    _, _, rows = _synthetic_rows()
    return build_profile("bicep_curl", [rows])


def test_live_detector_completes_a_set():
    profile = _profile()
    detector = LiveSetDetector(profile, idle_timeout_s=1.0, pre_roll_s=1.0, min_reps=2)
    t, g, _ = _synthetic_rows()
    completed = None
    for i in range(len(t)):
        result = detector.update(_sample(i, t, g))
        if result is not None:
            completed = result
            break
    assert completed is not None
    assert completed.rejected is False
    assert completed.rep_count >= 4
    assert completed.metrics.exercise_id == "bicep_curl"
    assert completed.metrics.reps
    # Detector returns to waiting for the next set.
    assert detector.status()["state"] == "WAITING"


def test_live_detector_rejects_single_rep():
    profile = _profile()
    detector = LiveSetDetector(profile, idle_timeout_s=1.0, min_reps=2)
    t, g, _ = _synthetic_rows(reps=1)
    completed = None
    for i in range(len(t)):
        result = detector.update(_sample(i, t, g))
        if result is not None:
            completed = result
            break
    assert completed is not None
    assert completed.rejected is True
    assert "insufficient" in completed.reason
