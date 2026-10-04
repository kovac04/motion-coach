"""Live set detection over the continuous BLE stream.

The ESP32 never knows about reps or sets. Python owns that state.

For the demo the set lifecycle is *explicit*: the UI calls ``start_set`` then
``finish_set`` (with an optional idle auto-finish as a backup). Movement before
``start_set`` is never part of a set. The detector returns to READY after each
set and never stops BLE.
"""

from __future__ import annotations

import time
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
    # Debug signal (for persisting / offline replay)
    t: np.ndarray | None = None
    gyro_raw: np.ndarray | None = None
    velocity_raw_dps: np.ndarray | None = None
    velocity_filtered_dps: np.ndarray | None = None


class LiveSetDetector:
    def __init__(
        self,
        profile: CalibrationProfile,
        idle_timeout_s: float = 3.0,
        min_reps: int = 2,
        max_set_s: float = 30.0,
        process_interval_s: float = 0.2,
        auto_finish: bool = True,
        sample_rate_hz: float = 50.0,
    ) -> None:
        self.profile = profile
        self.idle_timeout_s = idle_timeout_s
        self.min_reps = min_reps
        self.max_set_s = max_set_s
        self.process_interval_s = process_interval_s
        self.auto_finish = auto_finish
        self.sample_rate_hz = sample_rate_hz
        self.params = profile.detector_params()
        self._active: list[list[float]] = []
        self.reset()

    # --- lifecycle ---------------------------------------------------------
    def reset(self) -> None:
        self.state_name = "READY"
        self.rep_count = 0
        self._active = []
        self._set_start = 0.0
        self._last_process = 0.0

    def set_auto_finish(self, enabled: bool) -> None:
        self.auto_finish = enabled

    def start_set(self) -> None:
        """Begin a new set. Clears any prior samples (no pre-start data)."""
        self._active = []
        self.rep_count = 0
        self._set_start = time.monotonic()
        self._last_process = 0.0
        self.state_name = "ACTIVE"

    def status(self) -> dict:
        return {
            "state": self.state_name,
            "rep_count": self.rep_count,
            "auto_finish": self.auto_finish,
            "idle_timeout_s": self.idle_timeout_s,
            "exercise_id": self.profile.exercise_id,
        }

    # --- sample intake -----------------------------------------------------
    @staticmethod
    def _row(sample) -> list[float]:
        stamp = sample.host_timestamp
        return [stamp if stamp is not None else time.monotonic(),
                sample.gx, sample.gy, sample.gz]

    def _project(self, rows: list[list[float]]):
        t = np.asarray([r[0] for r in rows], dtype=float)
        t = t - t[0]
        g = np.asarray([[r[1], r[2], r[3]] for r in rows], dtype=float)
        bias = np.asarray(self.profile.bias, dtype=float)
        axis = np.asarray(self.profile.axis, dtype=float)
        raw = project(g, bias, axis)
        return t, g, raw, lowpass(raw, 5)

    def _velocity(self, rows: list[list[float]]) -> tuple[np.ndarray, np.ndarray]:
        t, _, _, filtered = self._project(rows)
        return t, filtered

    def update(self, sample) -> CompletedSet | None:
        """Feed one sample. Returns a CompletedSet only when a set auto-finishes."""
        if self.state_name != "ACTIVE":
            return None
        row = self._row(sample)
        self._active.append(row)
        now = row[0]
        if now - self._last_process < self.process_interval_s:
            return None
        self._last_process = now
        return self._process(now)

    def _process(self, now: float) -> CompletedSet | None:
        t, velocity = self._velocity(self._active)
        spans = detect_reps(t, velocity, self.params)
        self.rep_count = len(spans)

        if not self.auto_finish:
            return None
        window = max(3, int(self.idle_timeout_s * self.sample_rate_hz))
        tail = velocity[-window:]
        moving = bool(len(tail)) and float(np.max(np.abs(tail))) > self.params.start_dps
        if not moving and self.rep_count >= 1:
            return self._finalize(spans)
        if now - self._set_start > self.max_set_s:
            return self._finalize(spans)
        return None

    def finish_set(self) -> CompletedSet | None:
        """Finalize the current set immediately (manual FINISH SET)."""
        if self.state_name != "ACTIVE" or not self._active:
            self.reset()
            return None
        t, velocity = self._velocity(self._active)
        spans = detect_reps(t, velocity, self.params)
        self.rep_count = len(spans)
        return self._finalize(spans)

    def _finalize(self, spans) -> CompletedSet:
        t, g, raw, velocity = self._project(self._active)
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
            metrics=metrics, spans=spans, rep_count=len(reps),
            rejected=rejected,
            reason="" if not rejected else f"insufficient valid reps ({len(reps)})",
            t=t, gyro_raw=g, velocity_raw_dps=raw, velocity_filtered_dps=velocity,
        )
        self.reset()
        return completed
