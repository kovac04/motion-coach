"""Live set detection over the continuous BLE stream.

The ESP32 never knows about reps or sets. Python owns that state. This detector
consumes individual samples, keeps a short pre-roll so rep 1 is never clipped,
detects reps with the calibrated profile, and declares a set complete after a
configurable idle timeout. It never stops BLE; it returns to WAITING for the next
set.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

import numpy as np

from app.motion.calibration import CalibrationProfile
from app.motion.pipeline import ProjectedRecording, build_reps
from app.motion.segmentation import RepSpan, detect_reps
from app.motion.signal import RestEstimate, lowpass, project
from app.models.metrics import SetMetrics, build_set_metrics


@dataclass
class CompletedSet:
    metrics: SetMetrics
    spans: list[RepSpan]
    rep_count: int
    rejected: bool
    reason: str = ""


class LiveSetDetector:
    def __init__(
        self,
        profile: CalibrationProfile,
        idle_timeout_s: float = 3.0,
        pre_roll_s: float = 1.0,
        min_reps: int = 2,
        max_set_s: float = 30.0,
        process_interval_s: float = 0.2,
        sample_rate_hz: float = 50.0,
    ) -> None:
        self.profile = profile
        self.idle_timeout_s = idle_timeout_s
        self.min_reps = min_reps
        self.max_set_s = max_set_s
        self.process_interval_s = process_interval_s
        self.sample_rate_hz = sample_rate_hz
        self.params = profile.detector_params()
        self._pre_roll_len = max(5, int(pre_roll_s * sample_rate_hz))
        self.reset()

    # --- lifecycle ---------------------------------------------------------
    def reset(self) -> None:
        self.state_name = "WAITING"
        self.rep_count = 0
        self._pre_roll: deque[list[float]] = deque(maxlen=self._pre_roll_len)
        self._active: list[list[float]] = []
        self._set_start = 0.0
        self._last_process = 0.0

    def status(self) -> dict:
        return {
            "state": self.state_name,
            "rep_count": self.rep_count,
            "exercise_id": self.profile.exercise_id,
        }

    # --- sample intake -----------------------------------------------------
    @staticmethod
    def _row(sample) -> list[float]:
        return [sample.host_timestamp or time.monotonic(),
                sample.gx, sample.gy, sample.gz]

    def _velocity(self, rows: list[list[float]]) -> tuple[np.ndarray, np.ndarray]:
        t = np.asarray([r[0] for r in rows], dtype=float)
        t = t - t[0]
        g = np.asarray([[r[1], r[2], r[3]] for r in rows], dtype=float)
        bias = np.asarray(self.profile.bias, dtype=float)
        axis = np.asarray(self.profile.axis, dtype=float)
        return t, lowpass(project(g, bias, axis), 5)

    def update(self, sample) -> CompletedSet | None:
        row = self._row(sample)
        now = row[0]

        if self.state_name == "WAITING":
            self._pre_roll.append(row)
            if len(self._pre_roll) < self._pre_roll_len:
                return None
            _, velocity = self._velocity(list(self._pre_roll))
            tail = velocity[-max(3, int(0.5 * self.sample_rate_hz)):]
            if float(np.max(np.abs(tail))) > self.params.start_dps:
                self.state_name = "ACTIVE"
                self.rep_count = 0
                self._active = list(self._pre_roll)  # ~1 s pre-roll preserves rep 1
                self._set_start = now
                self._last_process = 0.0
            return None

        if self.state_name != "ACTIVE":
            return None

        self._active.append(row)
        if now - self._last_process < self.process_interval_s:
            return None
        self._last_process = now
        return self._process(now)

    # --- segmentation ------------------------------------------------------
    def _process(self, now: float) -> CompletedSet | None:
        t, velocity = self._velocity(self._active)
        spans = detect_reps(t, velocity, self.params)
        self.rep_count = len(spans)

        window = max(3, int(self.idle_timeout_s * self.sample_rate_hz))
        tail = velocity[-window:]
        moving = bool(len(tail)) and float(np.max(np.abs(tail))) > self.params.start_dps

        if not moving and self.rep_count >= 1:
            return self._finalize(t, velocity, spans)
        if now - self._set_start > self.max_set_s:
            return self._finalize(t, velocity, spans)
        return None

    def _finalize(self, t, velocity, spans) -> CompletedSet:
        projected = ProjectedRecording(
            t=t,
            velocity_dps=velocity,
            rest=RestEstimate(bias=np.asarray(self.profile.bias, dtype=float),
                              noise_dps=self.profile.noise_dps, window_start=0, window_end=0),
            axis=np.asarray(self.profile.axis, dtype=float),
            axis_variance_fraction=self.profile.axis_variance_fraction,
        )
        reps = build_reps(projected, spans, self.profile, self.profile.exercise_id)
        metrics = build_set_metrics(self.profile.exercise_id, reps, source="live")
        rejected = len(reps) < self.min_reps
        completed = CompletedSet(
            metrics=metrics,
            spans=spans,
            rep_count=len(reps),
            rejected=rejected,
            reason="" if not rejected else f"insufficient valid reps ({len(reps)})",
        )
        self.reset()  # automatically wait for the next set
        return completed
