"""Live motion service: explicit set control + calibration, feeding the existing
decision -> language pipeline on completed sets.

Reuses CoachPipeline (Jev/Gemini + fallbacks) unchanged. Owns no BLE connection
itself — it subscribes to the single SensorRuntime owner.

Lifecycle (driven by the UI):
    NO_PROFILE -> CALIBRATING -> READY -> SET_ACTIVE -> ANALYZING -> COACHING -> READY
"""

from __future__ import annotations

import logging
import time

from app.config import Settings
from app.motion.calibration import CalibrationProfile, build_profile
from app.motion.live import CompletedSet, LiveSetDetector
from app.motion.pipeline import project_samples
from app.motion.profiles import list_profiles, load_profile, save_profile
from app.motion.segmentation import bootstrap_params, detect_reps
from app.services.coach_pipeline import CoachPipeline
from app.sensors.runtime import SensorRuntime

logger = logging.getLogger(__name__)

CALIBRATION_TARGET_REPS = 5


class LiveMotionService:
    def __init__(self, settings: Settings, exercise_id: str = "bicep_curl") -> None:
        self.settings = settings
        self.exercise_id = exercise_id
        self.profile: CalibrationProfile | None = None
        self.detector: LiveSetDetector | None = None
        self.last_completed: CompletedSet | None = None
        self.last_evaluation: dict | None = None
        self.last_timings_ms: dict | None = None
        self.calibration_result: dict | None = None
        self._pipeline = CoachPipeline(settings)
        self._analyzing = False
        # calibration capture
        self._calibrating = False
        self._cal_rows: list[dict[str, float]] = []
        self._cal_reps = 0
        self._cal_last_process = 0.0
        self._load()

    # --- setup -------------------------------------------------------------
    def _load(self) -> None:
        self.profile = load_profile(self.exercise_id)
        self.detector = LiveSetDetector(self.profile) if self.profile else None

    def attach(self, runtime: SensorRuntime) -> None:
        runtime.subscribe(self.on_sample)

    def set_profile(self, profile: CalibrationProfile) -> None:
        self.profile = profile
        self.exercise_id = profile.exercise_id
        self.detector = LiveSetDetector(profile)

    # --- explicit set control ---------------------------------------------
    def start_set(self) -> dict:
        if self.detector is None:
            return {"ok": False, "error": "no calibration profile; calibrate first"}
        self.last_evaluation = None
        self.last_timings_ms = None
        self._analyzing = False
        self.detector.start_set()
        logger.info("LIVE SET: started (exercise=%s)", self.exercise_id)
        return {"ok": True}

    def set_auto_finish(self, enabled: bool) -> dict:
        if self.detector is None:
            return {"ok": False, "error": "no calibration profile"}
        self.detector.set_auto_finish(enabled)
        return {"ok": True, "auto_finish": enabled}

    async def finish_set(self) -> dict:
        if self.detector is None:
            return {"ok": False, "error": "no calibration profile"}
        completed = self.detector.finish_set()
        if completed is None:
            return {"ok": False, "error": "no active set"}
        return await self._handle_completed(completed)

    # --- calibration -------------------------------------------------------
    def start_calibration(self) -> dict:
        self.calibration_result = None
        self._cal_rows = []
        self._cal_reps = 0
        self._cal_last_process = 0.0
        self._calibrating = True
        logger.info("CALIBRATION: started (target %d reps)", CALIBRATION_TARGET_REPS)
        return {"ok": True, "target_reps": CALIBRATION_TARGET_REPS}

    def finish_calibration(self) -> dict:
        rows = self._cal_rows
        self._calibrating = False
        if len(rows) < 150:
            self.calibration_result = {"ok": False, "error": f"only {len(rows)} samples captured"}
            return self.calibration_result
        try:
            profile = build_profile(self.exercise_id, [rows], source="live calibration")
        except Exception as exc:  # noqa: BLE001
            self.calibration_result = {"ok": False, "error": str(exc)}
            return self.calibration_result
        save_profile(profile)
        self.set_profile(profile)
        self.last_evaluation = None
        self.calibration_result = {
            "ok": True,
            "exercise_id": profile.exercise_id,
            "reps_used": profile.reps_used,
            "reference_duration_ms": profile.reference_duration_ms,
            "reference_excursion_deg": profile.reference_excursion_deg,
            "reference_peak_dps": profile.reference_peak_dps,
            "noise_dps": profile.noise_dps,
        }
        logger.info("CALIBRATION: complete (%s)", self.calibration_result)
        return self.calibration_result

    # --- sample fan-in -----------------------------------------------------
    def on_sample(self, sample) -> None:
        if self._calibrating:
            self._capture_calibration(sample)
        if self.detector is not None:
            completed = self.detector.update(sample)
            if completed is not None:
                self._schedule_completed(completed)

    def _capture_calibration(self, sample) -> None:
        self._cal_rows.append(
            {
                "host_timestamp": sample.host_timestamp,
                "gx_raw": float(sample.gx),
                "gy_raw": float(sample.gy),
                "gz_raw": float(sample.gz),
            }
        )
        now = sample.host_timestamp or time.monotonic()
        if now - self._cal_last_process < 0.2:
            return
        self._cal_last_process = now
        self._cal_reps = self._count_reps(self._cal_rows)
        if self._cal_reps >= CALIBRATION_TARGET_REPS:
            self.finish_calibration()

    @staticmethod
    def _count_reps(rows: list[dict[str, float]]) -> int:
        if len(rows) < 100:
            return 0
        try:
            projected = project_samples(rows, None, self_calibrate=True)
            return len(detect_reps(projected.t, projected.velocity_dps,
                                   bootstrap_params(projected.rest.noise_dps)))
        except Exception:  # noqa: BLE001
            return 0

    def _schedule_completed(self, completed: CompletedSet) -> None:
        import asyncio

        self.last_completed = completed
        if completed.rejected:
            self.last_evaluation = {
                "rejected": True, "reason": completed.reason,
                "rep_count": completed.rep_count, "metrics": completed.metrics.model_dump(),
                "source": "live",
            }
            logger.info("LIVE SET: rejected (%s)", completed.reason)
            return
        asyncio.create_task(self._handle_completed(completed))

    # --- pipeline ----------------------------------------------------------
    async def _handle_completed(self, completed: CompletedSet) -> dict:
        metrics = completed.metrics
        logger.info(
            "LIVE SET: source=live rep_count=%d durations=%s duration_ratios=%s "
            "rom_ratios=%s similarities=%s consistency=%s",
            completed.rep_count,
            [round(r.duration_ms) for r in metrics.reps],
            [round(r.duration_ratio, 2) if r.duration_ratio else None for r in metrics.reps],
            [round(r.rom_ratio, 2) if r.rom_ratio else None for r in metrics.reps],
            [round(r.similarity_score, 2) if r.similarity_score is not None else None for r in metrics.reps],
            round(metrics.consistency_score, 2) if metrics.consistency_score is not None else None,
        )
        logger.info("JEV INPUT: source=live SetMetrics exercise=%s reps=%d avg_dur=%.0fms avg_rom=%.1fdeg",
                    metrics.exercise_id, metrics.rep_count,
                    metrics.average_duration_ms or 0, metrics.average_rom_deg or 0)

        self._analyzing = True
        started = time.perf_counter()
        try:
            result = await self._pipeline.evaluate(metrics)
        except Exception as exc:  # noqa: BLE001
            self._analyzing = False
            logger.exception("live coaching failed")
            self.last_evaluation = {
                "rejected": True, "reason": str(exc), "rep_count": completed.rep_count,
                "metrics": metrics.model_dump(), "source": "live",
            }
            return self.last_evaluation
        finally:
            self._analyzing = False

        metrics_ms = (time.perf_counter() - started) * 1000.0
        decision_ms = result.timings_ms.get("decision", 0.0)
        gemini_ms = result.timings_ms.get("coaching", 0.0)
        timings = {
            "metrics": round(metrics_ms - decision_ms - gemini_ms, 1),
            "jev": round(decision_ms, 1),
            "gemini": round(gemini_ms, 1),
        }
        self.last_timings_ms = timings
        self.last_evaluation = {
            "rejected": False,
            "source": "live",
            "rep_count": completed.rep_count,
            "metrics": metrics.model_dump(),
            "decision": result.decision.model_dump(),
            "coaching": result.coaching.model_dump(),
            "timings_ms": timings,
        }
        return self.last_evaluation

    # --- status ------------------------------------------------------------
    def _mode(self) -> str:
        if self._calibrating:
            return "CALIBRATING"
        if self.profile is None:
            return "NO_PROFILE"
        if self.detector is not None and self.detector.state_name == "ACTIVE":
            return "SET_ACTIVE"
        if self._analyzing:
            return "ANALYZING"
        if self.last_evaluation and not self.last_evaluation.get("rejected"):
            return "COACHING"
        return "READY"

    def motion_status(self) -> dict:
        detector = self.detector.status() if self.detector else {
            "state": "READY", "rep_count": 0, "auto_finish": True,
            "idle_timeout_s": 3.0, "exercise_id": self.exercise_id,
        }
        return {
            "mode": self._mode(),
            "state": detector["state"],
            "rep_count": detector["rep_count"],
            "auto_finish": detector.get("auto_finish", True),
            "idle_timeout_s": detector.get("idle_timeout_s", 3.0),
            "exercise_id": self.exercise_id,
            "has_profile": self.profile is not None,
            "available_profiles": list_profiles(),
            "calibration": {
                "active": self._calibrating,
                "reps": self._cal_reps,
                "target": CALIBRATION_TARGET_REPS,
                "result": self.calibration_result,
            },
            "last_evaluation": self.last_evaluation,
            "latency_ms": self.last_timings_ms,
        }
