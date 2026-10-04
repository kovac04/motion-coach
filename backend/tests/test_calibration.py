import numpy as np

from app.config import Settings
from app.sensors.packet import ImuSample
from app.services.live_coach import LiveMotionService


def _sample(i, t, gx, gy, gz):
    return ImuSample(sequence=i, timestamp_ms=int(t * 1000), ax=0, ay=0, az=0,
                     gx=int(round(gx)), gy=int(round(gy)), gz=int(round(gz)),
                     host_timestamp=float(t))


def _feed(svc, start_index, t):
    dt = 0.02
    # still phase: ~1.2 s of quiet gyro
    idx = start_index
    for _ in range(70):
        svc.on_sample(_sample(idx, t, 2.0, -1.0, 3.0))
        idx += 1
        t += dt
    # five reps on the z axis (~140 dps), brief rest between
    for _ in range(5):
        for _ in range(50):
            svc.on_sample(_sample(idx, t, 0.0, 0.0, 140.0 * 32.8))
            idx += 1
            t += dt
        for _ in range(50):
            svc.on_sample(_sample(idx, t, 0.0, 0.0, -140.0 * 32.8))
            idx += 1
            t += dt
        for _ in range(10):
            svc.on_sample(_sample(idx, t, 0.0, 0.0, 0.0))
            idx += 1
            t += dt
    # tail rest so the periodic counter observes the 5th rep and finishes
    for _ in range(60):
        svc.on_sample(_sample(idx, t, 0.0, 0.0, 0.0))
        idx += 1
        t += dt
    return idx, t


def test_calibration_phases_and_clean_baseline(monkeypatch, tmp_path):
    # Never touch the real data/profiles directory from tests.
    monkeypatch.setattr("app.motion.profiles.PROFILE_DIR", tmp_path)
    settings = Settings(decision_provider="mock", language_provider="mock")
    service = LiveMotionService(settings)
    service.start_calibration()
    assert service._cal_phase == "WAITING_STILL"
    _feed(service, 0, 0.0)
    result = service.calibration_result
    assert result is not None and result["ok"] is True
    assert result["reps_used"] >= 4
    # The baseline comes from the still phase, so noise stays low.
    assert result["noise_dps"] < 10.0


def test_calibration_timeout_without_still(monkeypatch, tmp_path):
    monkeypatch.setattr("app.motion.profiles.PROFILE_DIR", tmp_path)
    settings = Settings(decision_provider="mock", language_provider="mock")
    service = LiveMotionService(settings)
    service.start_calibration()
    # Force the timeout by pretending we started long ago.
    service._cal_started -= 100
    service.on_sample(_sample(0, 0.0, 2.0, -1.0, 3.0))
    assert service._calibrating is False
    assert service.calibration_result["ok"] is False
    assert "quiet baseline" in service.calibration_result["error"]
