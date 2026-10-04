"""Live motion service: explicit set control + phased calibration, feeding the
existing decision -> language pipeline on completed sets.

Reuses CoachPipeline (Jev/Gemini + fallbacks) unchanged. Owns no BLE connection
itself — it subscribes to the single SensorRuntime owner.

Set lifecycle (driven by the UI):
    NO_PROFILE -> READY -> SET_ACTIVE -> ANALYZING -> COACHING -> READY

Calibration lifecycle:
    COUNTDOWN (client) -> WAITING_STILL -> REPS -> COMPLETE
The still phase captures a clean resting baseline (gyro variance, not a blind
timer) before any reference reps are collected.
"""

from __future__ import annotations

import logging
import time

import numpy as np

from app.config import Settings
from app.exercises import LIVE_EXERCISE_IDS, get_profile, list_live_profiles
from app.motion.calibration import CalibrationProfile, build_profile
from app.motion.debug import save_live_set
from app.motion.live import CompletedSet, LiveSetDetector
from app.motion.pipeline import project_samples
from app.motion.profiles import list_profiles, load_profile, profile_path, save_profile
from app.motion.segmentation import bootstrap_params, detect_reps
from app.motion.signal import RestEstimate, as_matrix, lowpass, pca_axis, project
from app.services.coach_pipeline import CoachPipeline
from app.sensors.packet import GYRO_LSB_PER_DPS
from app.sensors.runtime import SensorRuntime

logger = logging.getLogger(__name__)

CALIBRATION_TARGET_REPS = 5
STILL_WINDOW_S = 0.75          # minimum genuinely-quiet baseline window
STILL_TIMEOUT_S = 15.0         # give up if no quiet baseline in this time
QUIET_RMS_DPS = 10.0           # residual gyro RMS below this counts as still
PROCESS_INTERVAL_S = 0.2
SAMPLE_RATE_HZ = 50.0


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
        # calibration state
        self._calibrating = False
        self._cal_phase = "IDLE"  # IDLE | WAITING_STILL | REPS
        self._cal_still: list[list[float]] = []
        self._cal_rows: list[dict[str, float]] = []
        self._cal_reps = 0
        self._cal_last_process = 0.0
        self._cal_started = 0.0
        self._cal_baseline: RestEstimate | None = None
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

    def select_exercise(self, exercise_id: str) -> dict:
        """Switch the active exercise and load its own saved calibration profile."""
        if exercise_id not in LIVE_EXERCISE_IDS:
            return {"ok": False, "error": f"unsupported exercise: {exercise_id}"}
        if self._calibrating:
            return {"ok": False, "error": "cannot switch exercise during calibration"}
        if self.detector is not None and self.detector.state_name == "ACTIVE":
            return {"ok": False, "error": "cannot switch exercise during an active set"}

        self.exercise_id = exercise_id
        self.last_evaluation = None
        self.last_timings_ms = None
        self.last_completed = None
        self.calibration_result = None
        self.profile = load_profile(exercise_id)
        self.detector = LiveSetDetector(self.profile) if self.profile else None
        logger.info("EXERCISE: selected %s (profile=%s)", exercise_id, self.profile is not None)
        return {
            "ok": True,
            "exercise_id": exercise_id,
            "has_profile": self.profile is not None,
            "mode": self._mode(),
        }

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

    # --- phased calibration -----------------------------------------------
    def start_calibration(self) -> dict:
        self.calibration_result = None
        self._calibrating = True
        self._cal_phase = "WAITING_STILL"
        self._cal_still = []
        self._cal_rows = []
        self._cal_reps = 0
        self._cal_last_process = 0.0
        self._cal_started = time.monotonic()
        self._cal_baseline = None
        logger.info("CALIBRATION: waiting for quiet baseline")
        return {"ok": True, "target_reps": CALIBRATION_TARGET_REPS, "phase": self._cal_phase}

    def finish_calibration(self) -> dict:
        self._calibrating = False
        self._cal_phase = "IDLE"
        if self._cal_baseline is None:
            self.calibration_result = {"ok": False, "error": "no quiet baseline captured"}
            return self.calibration_result
        if len(self._cal_rows) < 150:
            self.calibration_result = {"ok": False, "error": f"only {len(self._cal_rows)} rep samples"}
            return self.calibration_result
        try:
            profile = build_profile(
                self.exercise_id, [self._cal_rows],
                source="live calibration", rest_override=self._cal_baseline,
            )
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
            "axis_variance_fraction": profile.axis_variance_fraction,
        }
        logger.info("CALIBRATION: complete %s", self.calibration_result)
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
        if self._cal_phase == "WAITING_STILL":
            stamp = sample.host_timestamp if sample.host_timestamp is not None else time.monotonic()
            self._cal_still.append([stamp, sample.gx, sample.gy, sample.gz])
            if len(self._cal_still) > int(2.0 * SAMPLE_RATE_HZ):
                self._cal_still.pop(0)
            rms = self._still_rms()
            if rms is not None and rms <= QUIET_RMS_DPS:
                window = np.asarray(self._cal_still[-int(STILL_WINDOW_S * SAMPLE_RATE_HZ):], dtype=float)[:, 1:]
                self._cal_baseline = RestEstimate(
                    bias=window.mean(axis=0),
                    noise_dps=max(float(rms), 0.5),
                    window_start=0, window_end=len(window),
                )
                self._cal_phase = "REPS"
                self._cal_rows = []  # clear: no pre-rep data in reference capture
                self._cal_last_process = 0.0
                logger.info("CALIBRATION: baseline captured (noise %.2f dps) -> REPS", rms)
            elif time.monotonic() - self._cal_started > STILL_TIMEOUT_S:
                logger.warning("CALIBRATION: no quiet baseline within %.0fs", STILL_TIMEOUT_S)
                self._calibrating = False
                self._cal_phase = "IDLE"
                self.calibration_result = {"ok": False, "error": "could not get a quiet baseline; hold still and retry"}
            return

        if self._cal_phase == "REPS":
            self._cal_rows.append({
                "host_timestamp": sample.host_timestamp,
                "gx_raw": float(sample.gx), "gy_raw": float(sample.gy), "gz_raw": float(sample.gz),
            })
            now = sample.host_timestamp if sample.host_timestamp is not None else time.monotonic()
            if now - self._cal_last_process < PROCESS_INTERVAL_S:
                return
            self._cal_last_process = now
            self._cal_reps = self._count_reps(self._cal_rows)
            if self._cal_reps >= CALIBRATION_TARGET_REPS:
                self.finish_calibration()

    def _still_rms(self) -> float | None:
        needed = int(STILL_WINDOW_S * SAMPLE_RATE_HZ)
        if len(self._cal_still) < needed:
            return None
        window = np.asarray(self._cal_still[-needed:], dtype=float)[:, 1:]
        center = window.mean(axis=0)
        residual = np.linalg.norm(window - center, axis=1)
        return float(np.sqrt(np.mean(residual ** 2)) / GYRO_LSB_PER_DPS)

    def _count_reps(self, rows: list[dict[str, float]]) -> int:
        if len(rows) < 100 or self._cal_baseline is None:
            return 0
        t, g = as_matrix(rows)
        try:
            axis, _ = pca_axis(g, self._cal_baseline.bias, self._cal_baseline.noise_dps)
            velocity = lowpass(project(g, self._cal_baseline.bias, axis), 5)
            return len(detect_reps(t, velocity, bootstrap_params(self._cal_baseline.noise_dps)))
        except Exception:  # noqa: BLE001
            return 0

    def _maybe_save_debug(self, completed: CompletedSet) -> None:
        if not self.settings.debug_save_live_sets or self.profile is None:
            return
        try:
            paths = save_live_set(completed, self.profile,
                                  tag="rejected" if completed.rejected else "set")
            logger.info("DEBUG: saved live set trace -> %s", paths["csv"])
        except Exception:  # noqa: BLE001 - debug must never break the pipeline
            logger.exception("debug save failed")

    def _schedule_completed(self, completed: CompletedSet) -> None:
        import asyncio

        self.last_completed = completed
        if completed.rejected:
            self._maybe_save_debug(completed)
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
        self._maybe_save_debug(completed)
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

        total_ms = (time.perf_counter() - started) * 1000.0
        decision_ms = result.timings_ms.get("decision", 0.0)
        gemini_ms = result.timings_ms.get("coaching", 0.0)
        timings = {
            "metrics": round(max(total_ms - decision_ms - gemini_ms, 0.0), 1),
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
            "providers": {
                "decision": result.decision.provider,
                "language": result.coaching.provider,
            },
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

    def _profile_info(self) -> dict | None:
        if self.profile is None:
            return None
        return {
            "reference_duration_ms": self.profile.reference_duration_ms,
            "reference_excursion_deg": self.profile.reference_excursion_deg,
            "reference_peak_dps": self.profile.reference_peak_dps,
            "axis_variance_fraction": self.profile.axis_variance_fraction,
            "noise_dps": self.profile.noise_dps,
            "axis": [round(x, 3) for x in self.profile.axis],
        }

    def available_exercises(self) -> list[dict]:
        return [
            {
                "id": profile.id,
                "display_name": profile.display_name,
                "calibrated": profile_path(profile.id).exists(),
            }
            for profile in list_live_profiles()
        ]

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
            "available_exercises": self.available_exercises(),
            "profile_info": self._profile_info(),
            "calibration": {
                "active": self._calibrating,
                "phase": self._cal_phase,
                "reps": self._cal_reps,
                "target": CALIBRATION_TARGET_REPS,
                "baseline_noise_dps": round(self._cal_baseline.noise_dps, 2) if self._cal_baseline else None,
                "result": self.calibration_result,
            },
            "last_evaluation": self.last_evaluation,
            "latency_ms": self.last_timings_ms,
        }
