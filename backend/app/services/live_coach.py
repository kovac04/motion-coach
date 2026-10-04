"""Live motion service: detects sets from the BLE stream and runs the existing
decision -> language pipeline on completed sets.

Reuses CoachPipeline (Jev/Gemini + fallbacks) unchanged. Owns no BLE connection
itself — it subscribes to the single SensorRuntime owner.
"""

from __future__ import annotations

import asyncio
import logging

from app.config import Settings
from app.motion.calibration import build_profile
from app.motion.live import CompletedSet, LiveSetDetector
from app.motion.profiles import list_profiles, load_profile, save_profile
from app.services.coach_pipeline import CoachPipeline
from app.sensors.runtime import SensorRuntime

logger = logging.getLogger(__name__)


class LiveMotionService:
    def __init__(self, settings: Settings, exercise_id: str = "bicep_curl") -> None:
        self.settings = settings
        self.exercise_id = exercise_id
        self.profile = None
        self.detector: LiveSetDetector | None = None
        self.last_completed: CompletedSet | None = None
        self.last_evaluation: dict | None = None
        self._pipeline = CoachPipeline(settings)
        self._capture: list[dict[str, float]] | None = None
        self._load()

    # --- setup -------------------------------------------------------------
    def _load(self) -> None:
        self.profile = load_profile(self.exercise_id)
        self.detector = LiveSetDetector(self.profile) if self.profile else None

    def attach(self, runtime: SensorRuntime) -> None:
        runtime.subscribe(self.on_sample)

    def set_profile(self, profile) -> None:
        self.profile = profile
        self.exercise_id = profile.exercise_id
        self.detector = LiveSetDetector(profile)

    # --- sample fan-in -----------------------------------------------------
    def on_sample(self, sample) -> None:
        if self._capture is not None:
            self._capture.append(
                {
                    "host_timestamp": sample.host_timestamp,
                    "gx_raw": float(sample.gx),
                    "gy_raw": float(sample.gy),
                    "gz_raw": float(sample.gz),
                }
            )
        if self.detector is None:
            return
        completed = self.detector.update(sample)
        if completed is None:
            return
        self.last_completed = completed
        if completed.rejected:
            self.last_evaluation = {
                "rejected": True,
                "reason": completed.reason,
                "rep_count": completed.rep_count,
                "metrics": completed.metrics.model_dump(),
            }
            return
        asyncio.create_task(self._coach(completed))

    async def _coach(self, completed: CompletedSet) -> None:
        try:
            result = await self._pipeline.evaluate(completed.metrics)
            self.last_evaluation = {
                "rejected": False,
                "rep_count": completed.rep_count,
                "metrics": completed.metrics.model_dump(),
                "decision": result.decision.model_dump(),
                "coaching": result.coaching.model_dump(),
                "timings_ms": result.timings_ms,
            }
        except Exception as exc:  # noqa: BLE001 - never crash the stream
            logger.exception("live coaching failed")
            self.last_evaluation = {
                "rejected": True,
                "reason": str(exc),
                "rep_count": completed.rep_count,
                "metrics": completed.metrics.model_dump(),
            }

    # --- status / calibration ---------------------------------------------
    def motion_status(self) -> dict:
        base = self.detector.status() if self.detector else {
            "state": "NO_PROFILE", "rep_count": 0, "exercise_id": self.exercise_id
        }
        base["has_profile"] = self.profile is not None
        base["available_profiles"] = list_profiles()
        base["last_evaluation"] = self.last_evaluation
        return base

    async def calibrate(self, seconds: float = 20.0) -> dict:
        if self._capture is not None:
            return {"ok": False, "error": "calibration already running"}
        self._capture = []
        try:
            await asyncio.sleep(seconds)
        finally:
            rows = self._capture
            self._capture = None
        if not rows or len(rows) < 200:
            return {"ok": False, "error": f"captured only {len(rows or [])} samples; is the sensor connected?"}
        try:
            profile = build_profile(self.exercise_id, [rows], source="live calibration")
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"calibration failed: {exc}"}
        save_profile(profile)
        self.set_profile(profile)
        self.last_evaluation = None
        return {
            "ok": True,
            "exercise_id": profile.exercise_id,
            "reps_used": profile.reps_used,
            "reference_duration_ms": profile.reference_duration_ms,
            "reference_excursion_deg": profile.reference_excursion_deg,
            "noise_dps": profile.noise_dps,
        }
