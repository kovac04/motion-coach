"""Decision layer.

Supports three provider modes (env ``DECISION_PROVIDER``):
    mock     — deterministic, scenario-aware fake decisions (default; no credentials)
    jev      — real TypeSafe Jev provider (verified contract; fails soft to the rules engine)
    fallback — the deterministic rules engine in ``services/fallbacks.py``

Jev wire contract (verified from https://docs.typesafe.ai on 2026-10-03):
    POST {JEV_BASE_URL}/v1/systemone
    Authorization: Bearer <JEV_API_KEY>
    body:    {"state": <object>, "model": "jev-latest", "questions": <map>}
    returns: {"model": "...", "answers": {...}, "usage": {...}}

The public entry point is ``get_decision_service(settings)``.
"""

from __future__ import annotations

import logging
import time

import httpx

from app.config import Settings
from app.exercises import get_profile
from app.models.decisions import (
    CoachingPriority,
    MovementDecision,
    OverallQuality,
    PrimaryIssue,
    Severity,
)
from app.models.metrics import RepMetrics, SetMetrics
from app.motion.assessment import (
    Bands,
    DeviationAssessment,
    PRIORITY_FOR_ISSUE,
    assess,
    deterministic_decision,
    quality_from_severity,
)
from app.services.fallbacks import evaluate_decision, summarize

logger = logging.getLogger(__name__)

JEV_ENDPOINT = "/v1/systemone"
JEV_DEFAULT_MODEL = "jev-latest"

# Canned mock decisions per demo scenario, with illustrative probability spreads.
_MOCK_SCENARIOS: dict[str, MovementDecision] = {
    "perfect_set": MovementDecision(
        primary_issue=PrimaryIssue.GOOD,
        coaching_priority=CoachingPriority.NONE,
        severity=Severity.NONE,
        should_speak=False,
        overall_quality=OverallQuality.EXCELLENT,
        confidence=0.94,
        evidence=["duration_ratio=1.01", "rom_ratio=1.00", "consistency_score=0.97"],
        alternatives={"GOOD": 0.93, "INCONSISTENT": 0.04, "TOO_FAST": 0.03},
        provider="mock",
    ),
    "too_fast": MovementDecision(
        primary_issue=PrimaryIssue.TOO_FAST,
        coaching_priority=CoachingPriority.TEMPO,
        severity=Severity.MODERATE,
        should_speak=True,
        overall_quality=OverallQuality.FAIR,
        confidence=0.91,
        evidence=["duration_ratio=0.73", "tempo_drift=-23% (reps speeding up)"],
        alternatives={"TOO_FAST": 0.82, "GOOD": 0.11, "INCONSISTENT": 0.07},
        provider="mock",
    ),
    "too_slow": MovementDecision(
        primary_issue=PrimaryIssue.TOO_SLOW,
        coaching_priority=CoachingPriority.TEMPO,
        severity=Severity.MODERATE,
        should_speak=True,
        overall_quality=OverallQuality.FAIR,
        confidence=0.86,
        evidence=["duration_ratio=1.18", "tempo_drift=+20% (reps slowing)"],
        alternatives={"TOO_SLOW": 0.78, "GOOD": 0.14, "INCONSISTENT": 0.08},
        provider="mock",
    ),
    "low_rom": MovementDecision(
        primary_issue=PrimaryIssue.INSUFFICIENT_ROM,
        coaching_priority=CoachingPriority.ROM,
        severity=Severity.MODERATE,
        should_speak=True,
        overall_quality=OverallQuality.FAIR,
        confidence=0.90,
        evidence=["rom_ratio=0.78", "range consistently below reference"],
        alternatives={"INSUFFICIENT_ROM": 0.88, "GOOD": 0.08, "INCONSISTENT": 0.04},
        provider="mock",
    ),
    "inconsistent": MovementDecision(
        primary_issue=PrimaryIssue.INCONSISTENT,
        coaching_priority=CoachingPriority.CONSISTENCY,
        severity=Severity.MAJOR,
        should_speak=True,
        overall_quality=OverallQuality.POOR,
        confidence=0.88,
        evidence=["consistency_score=0.66", "duration varies 1700-2300ms"],
        alternatives={"INCONSISTENT": 0.79, "TOO_FAST": 0.12, "GOOD": 0.09},
        provider="mock",
    ),
    "fatigue_drift": MovementDecision(
        primary_issue=PrimaryIssue.INCONSISTENT,
        coaching_priority=CoachingPriority.CONSISTENCY,
        severity=Severity.MODERATE,
        should_speak=True,
        overall_quality=OverallQuality.FAIR,
        confidence=0.84,
        evidence=["rom_drift=-10%", "tempo_drift=+12% late in set"],
        alternatives={"INCONSISTENT": 0.61, "INSUFFICIENT_ROM": 0.24, "GOOD": 0.15},
        provider="mock",
    ),
}


def mock_decision(metrics: RepMetrics | SetMetrics) -> MovementDecision:
    """Return a rich canned decision for a known scenario, else classify the metrics."""
    scenario = metrics.metadata.get("scenario") if isinstance(metrics, SetMetrics) else None
    if scenario and scenario in _MOCK_SCENARIOS:
        return _MOCK_SCENARIOS[scenario].model_copy()
    decision = evaluate_decision(metrics)
    return decision.model_copy(update={"provider": "mock"})


class JevError(RuntimeError):
    """Any failure talking to the TypeSafe Jev provider."""


# --- Jev question definitions (Choice / Score / Noul) -----------------------

# Order matters: Choice `criteria` option names map 1:1 to our PrimaryIssue enum.
_ISSUE_CRITERIA = {
    "good": "Every rep is close to the reference and the set is consistent.",
    "too_fast": "Reps are clearly faster (shorter duration) than the reference.",
    "too_slow": "Reps are clearly slower (longer duration) than the reference.",
    "insufficient_rom": "Range of motion is smaller than the reference range.",
    "excessive_rom": "Range of motion is larger than the reference range.",
    "inconsistent": "Tempo or range varies noticeably between reps or drifts across the set.",
    "unstable": "The motion is jerky or the wrist is unstable.",
}

_PRIORITY_CRITERIA = {
    "tempo": "Rep speed / duration.",
    "rom": "Range of motion.",
    "control": "Smoothness and stability.",
    "consistency": "Repeatability across reps.",
    "none": "No correction is needed.",
}

_ISSUE_LEVELS = ["none", "mild", "moderate", "major"]
_QUALITY_LEVELS = ["poor", "fair", "good", "excellent"]

JEV_QUESTIONS: dict[str, dict] = {
    "primary_issue": {
        "type": "choice",
        "instructions": "What is the single primary issue with this set?",
        "criteria": _ISSUE_CRITERIA,
    },
    "severity": {
        "type": "score",
        "instructions": "How severe is the primary issue?",
        "criteria": [
            "No issue; movement matches the reference.",
            "Mild; a small deviation that is barely worth mentioning.",
            "Moderate; a clear deviation worth coaching.",
            "Major; a large or repeated deviation that needs correcting.",
        ],
    },
    "coaching_priority": {
        "type": "choice",
        "instructions": "Which dimension should the coach speak about first?",
        "criteria": _PRIORITY_CRITERIA,
    },
    "should_speak": {
        "type": "noul",
        "instructions": (
            "Is there a meaningful, actionable deviation that is worth interrupting the "
            "athlete with spoken coaching after this set?"
        ),
        "criteria": {
            "true": "There is a clear deviation the athlete should correct next set.",
            "false": (
                "The set is good or excellent, or any deviation is too small to warrant "
                "spoken feedback. Do not speak just to give positive reinforcement."
            ),
        },
    },
    "overall_quality": {
        "type": "score",
        "instructions": "Overall, how good was this set?",
        "criteria": [
            "Poor; the movement needs rework.",
            "Fair; usable but clearly off.",
            "Good; close to the reference with minor deviations.",
            "Excellent; consistent and close to the reference.",
        ],
    },
}


def _round(value: float | None, digits: int = 3) -> float | None:
    return None if value is None else round(value, digits)


def _compact_state(metrics: RepMetrics | SetMetrics, exercise_id: str,
                   assessment: DeviationAssessment | None = None) -> dict:
    """Build the Jev `state`. Never raw sensor arrays — only derived facts."""
    profile = get_profile(exercise_id)
    s = summarize(metrics)

    if isinstance(metrics, RepMetrics):
        state: dict = {
            "exercise": exercise_id,
            "exercise_context": profile.jev_context,
            "reference": {
                "duration_ms": _round(metrics.reference_duration_ms),
                "rom_deg": _round(metrics.reference_rom_deg),
                "peak_velocity_dps": _round(metrics.reference_peak_velocity_dps),
            },
            "current": {
                "rep_number": metrics.rep_number,
                "duration_ms": _round(metrics.duration_ms),
                "duration_ratio": _round(metrics.duration_ratio),
                "rom_deg": _round(metrics.rom_deg),
                "rom_ratio": _round(metrics.rom_ratio),
                "peak_velocity_ratio": _round(metrics.peak_velocity_ratio),
                "smoothness_score": _round(metrics.smoothness_score),
                "similarity_score": _round(metrics.similarity_score),
            },
        }
    else:
        state = {
            "exercise": exercise_id,
            "exercise_context": profile.jev_context,
            "reference": {
                "duration_ms": _round(metrics.reference_duration_ms),
                "rom_deg": _round(metrics.reference_rom_deg),
                "peak_velocity_dps": _round(metrics.reference_peak_velocity_dps),
            },
            "current": {
                "rep_count": metrics.rep_count,
                "average_duration_ms": _round(metrics.average_duration_ms),
                "average_rom_deg": _round(metrics.average_rom_deg),
                "avg_duration_ratio": _round(s.duration_ratio),
                "avg_rom_ratio": _round(s.rom_ratio),
                "duration_variability": _round(metrics.duration_variability),
                "rom_variability": _round(metrics.rom_variability),
                "reference_similarity_mean": _round(metrics.reference_similarity_mean),
            },
            "set_context": {
                "tempo_drift_pct": _round(metrics.tempo_drift_pct, 1),
                "rom_drift_pct": _round(metrics.rom_drift_pct, 1),
                "consistency_score": _round(metrics.consistency_score),
            },
        }

    # Drop null fields so Jev sees a tight state.
    for section in list(state.values()):
        if isinstance(section, dict):
            for key in [k for k, v in section.items() if v is None]:
                del section[key]

    if assessment is not None:
        # Deterministic facts first; Jev may only choose among these candidates.
        state["detected_deviations"] = assessment.to_dict()
        state["candidate_issues"] = [c.value for c in assessment.candidates]
    return state


def _evidence(metrics: RepMetrics | SetMetrics) -> list[str]:
    """Deterministic facts, generated by our code (Jev is not asked for prose)."""
    s = summarize(metrics)
    evidence: list[str] = []
    if s.duration_ratio is not None:
        evidence.append(f"duration_ratio={s.duration_ratio:.2f}")
    if s.rom_ratio is not None:
        evidence.append(f"rom_ratio={s.rom_ratio:.2f}")
    if s.peak_velocity_ratio is not None:
        evidence.append(f"peak_velocity_ratio={s.peak_velocity_ratio:.2f}")
    if s.similarity_score is not None:
        evidence.append(f"similarity={s.similarity_score:.2f}")
    if s.consistency_score is not None:
        evidence.append(f"consistency={s.consistency_score:.2f}")
    if s.tempo_drift_pct is not None:
        evidence.append(f"tempo_drift={s.tempo_drift_pct:+.0f}%")
    if s.rom_drift_pct is not None:
        evidence.append(f"rom_drift={s.rom_drift_pct:+.0f}%")
    return evidence


def _build_questions(assessment: DeviationAssessment) -> dict:
    """Ask Jev only what the deterministic layer leaves open.

    * 1 candidate  -> Jev is asked only for severity (primary issue is fixed).
    * >1 candidate -> Jev chooses the priority among the detected candidates only.
    """
    questions: dict[str, dict] = {"severity": JEV_QUESTIONS["severity"]}
    if len(assessment.candidates) > 1:
        criteria = {
            candidate.value.lower(): _ISSUE_CRITERIA[candidate.value.lower()]
            for candidate in assessment.candidates
        }
        questions["primary_issue"] = {
            "type": "choice",
            "instructions": (
                "Of the objectively detected deviations listed in the state, which one "
                "deserves the coaching priority?"
            ),
            "criteria": criteria,
        }
    return questions


def parse_jev_response(data: dict, metrics: RepMetrics | SetMetrics, model: str,
                       assessment: DeviationAssessment | None = None,
                       asked_primary: bool = True) -> MovementDecision:
    """Translate a verified Jev response, constrained to the deterministic candidates."""
    try:
        answers = data["answers"]
        severity_answer = answers["severity"]
    except (KeyError, TypeError) as exc:
        raise JevError(f"malformed Jev response: missing {exc}") from exc

    try:
        severity = Severity(_ISSUE_LEVELS[round(float(severity_answer["score"]))].upper())
    except (KeyError, ValueError, IndexError) as exc:
        raise JevError(f"malformed Jev score in response: {exc}") from exc

    candidates = assessment.candidates if assessment else []
    alternatives: dict[str, float] = {}
    confidence: float | None = None

    if asked_primary and "primary_issue" in answers:
        issue_answer = answers["primary_issue"]
        key = str(issue_answer.get("choice", "")).upper()
        chosen: PrimaryIssue | None = None
        try:
            chosen = PrimaryIssue(key)
        except ValueError:
            chosen = None
        # Jev must never win with an issue we did not establish.
        if chosen not in candidates:
            chosen = max(candidates, key=assessment.magnitude) if candidates else PrimaryIssue.OTHER
        confidence = issue_answer.get("confidence")
        alternatives = {
            str(name).upper(): float(prob)
            for name, prob in (issue_answer.get("probabilities") or {}).items()
        }
    else:
        # Single candidate (or no primary_issue question): decision is fixed.
        chosen = candidates[0] if candidates else PrimaryIssue.GOOD
        confidence = severity_answer.get("confidence")

    return MovementDecision(
        primary_issue=chosen,
        coaching_priority=PRIORITY_FOR_ISSUE.get(chosen, CoachingPriority.NONE),
        severity=severity,
        should_speak=bool(candidates),
        overall_quality=quality_from_severity(severity),
        confidence=confidence,
        evidence=assessment.evidence() if assessment else _evidence(metrics),
        alternatives=alternatives,
        provider="jev",
        model_version=data.get("model") or model,
    )


class DecisionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.mode = settings.decision_provider

    def _bands(self) -> Bands:
        return Bands(
            tempo_fast=self.settings.band_tempo_fast,
            tempo_slow=self.settings.band_tempo_slow,
            rom_low=self.settings.band_rom_low,
            rom_high=self.settings.band_rom_high,
            consistency_low=self.settings.band_consistency_low,
            min_affected_fraction=self.settings.min_affected_fraction,
        )

    @staticmethod
    def _log_assessment(assessment: DeviationAssessment) -> None:
        ratio = lambda v: "None" if v is None else f"{v:.2f}"
        logger.info(
            "DEVIATION ASSESSMENT: reps=%d | median_duration_ratio=%s tempo=%s affected=%d/%d | "
            "median_rom_ratio=%s rom=%s affected=%d/%d | consistency=%s | similarity=%s | candidates=%s",
            assessment.rep_count, ratio(assessment.median_duration_ratio), assessment.tempo_state,
            assessment.tempo_affected, assessment.rep_count, ratio(assessment.median_rom_ratio),
            assessment.rom_state, assessment.rom_affected, assessment.rep_count,
            assessment.consistency_state, assessment.similarity_state,
            [c.value for c in assessment.candidates],
        )

    @staticmethod
    def _log_decision(decision: MovementDecision, assessment: DeviationAssessment) -> None:
        logger.info("FINAL DECISION: primary_issue=%s should_speak=%s provider=%s candidates=%s",
                    decision.primary_issue.value, decision.should_speak, decision.provider,
                    [c.value for c in assessment.candidates])

    async def evaluate(self, metrics: RepMetrics | SetMetrics) -> MovementDecision:
        started = time.perf_counter()
        assessment = assess(metrics, self._bands())
        self._log_assessment(assessment)

        if self.mode == "mock":
            decision = mock_decision(metrics)
        elif not assessment.candidates:
            # Clearly normal set: deterministic GOOD, Jev is never consulted.
            decision = deterministic_decision(assessment, provider="deterministic")
        elif self.mode == "fallback":
            decision = deterministic_decision(assessment, provider="fallback")
        elif self.mode == "jev":
            try:
                decision = await self._evaluate_jev(metrics, assessment)
            except Exception as exc:  # noqa: BLE001 - fail soft by design
                logger.warning("Jev decision failed (%s); using fallback evaluator", exc)
                decision = deterministic_decision(assessment, provider="fallback")
        else:
            decision = deterministic_decision(assessment, provider="fallback")

        decision.latency_ms = (time.perf_counter() - started) * 1000.0
        self._log_decision(decision, assessment)
        return decision

    async def _evaluate_jev(self, metrics: RepMetrics | SetMetrics,
                            assessment: DeviationAssessment) -> MovementDecision:
        """Call the verified TypeSafe Jev endpoint and translate the answer."""
        if not self.settings.jev_api_key:
            raise JevError("JEV_API_KEY is not set")
        if not self.settings.jev_base_url:
            raise JevError("JEV_API_BASE_URL / JEV_BASE_URL is not set")

        model = self.settings.jev_model or JEV_DEFAULT_MODEL
        questions = _build_questions(assessment)
        asked_primary = "primary_issue" in questions
        payload = {
            "state": _compact_state(metrics, metrics.exercise_id, assessment),
            "model": model,
            "questions": questions,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.jev_api_key}",
            "Content-Type": "application/json",
        }
        url = self.settings.jev_base_url.rstrip("/") + JEV_ENDPOINT
        timeout = httpx.Timeout(
            self.settings.provider_request_timeout,
            connect=self.settings.provider_connect_timeout,
        )

        data = await self._post_with_retry(url, payload, headers, timeout)
        return parse_jev_response(data, metrics, model, assessment, asked_primary)

    async def _post_with_retry(
        self, url: str, payload: dict, headers: dict, timeout: httpx.Timeout
    ) -> dict:
        """POST with one retry on rate limit / server error / network failure."""
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(url, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                last_error = JevError(f"network error: {exc}")
                logger.warning("Jev network error (attempt %d): %s", attempt + 1, exc)
                continue

            if response.status_code in (401, 403):
                raise JevError(f"Jev auth failed ({response.status_code})")
            if response.status_code == 429:
                last_error = JevError("Jev rate limited (429)")
                logger.warning("Jev rate limited (attempt %d)", attempt + 1)
                continue
            if response.status_code >= 500:
                last_error = JevError(f"Jev server error ({response.status_code})")
                logger.warning("Jev 5xx %s (attempt %d)", response.status_code, attempt + 1)
                continue
            if response.status_code >= 400:
                raise JevError(f"Jev request rejected ({response.status_code}): {response.text[:200]}")

            try:
                return response.json()
            except ValueError as exc:
                raise JevError(f"Jev returned non-JSON: {exc}") from exc

        raise last_error or JevError("Jev request failed")


def get_decision_service(settings: Settings) -> DecisionService:
    return DecisionService(settings)
