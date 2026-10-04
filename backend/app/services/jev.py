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


def _compact_state(metrics: RepMetrics | SetMetrics, exercise_id: str) -> dict:
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


def parse_jev_response(data: dict, metrics: RepMetrics | SetMetrics, model: str) -> MovementDecision:
    """Translate a verified Jev response into our internal MovementDecision."""
    try:
        answers = data["answers"]
        issue_answer = answers["primary_issue"]
        severity_answer = answers["severity"]
        priority_answer = answers["coaching_priority"]
        speak_answer = answers["should_speak"]
        quality_answer = answers["overall_quality"]
    except (KeyError, TypeError) as exc:
        raise JevError(f"malformed Jev response: missing {exc}") from exc

    issue_key = str(issue_answer.get("choice", "")).lower()
    priority_key = str(priority_answer.get("choice", "")).lower()

    try:
        severity = Severity(_ISSUE_LEVELS[round(float(severity_answer["score"]))].upper())
        quality = OverallQuality(_QUALITY_LEVELS[round(float(quality_answer["score"]))].upper())
    except (KeyError, ValueError, IndexError) as exc:
        raise JevError(f"malformed Jev score in response: {exc}") from exc

    alternatives = {
        str(name).upper(): float(prob)
        for name, prob in (issue_answer.get("probabilities") or {}).items()
    }

    return MovementDecision(
        primary_issue=PrimaryIssue(issue_key.upper()) if issue_key else PrimaryIssue.OTHER,
        coaching_priority=(
            CoachingPriority(priority_key.upper()) if priority_key else CoachingPriority.NONE
        ),
        severity=severity,
        should_speak=float(speak_answer.get("noul", 0.0)) >= 0.5,
        overall_quality=quality,
        confidence=issue_answer.get("confidence"),
        evidence=_evidence(metrics),
        alternatives=alternatives,
        provider="jev",
        model_version=data.get("model") or model,
    )


class DecisionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.mode = settings.decision_provider

    async def evaluate(self, metrics: RepMetrics | SetMetrics) -> MovementDecision:
        started = time.perf_counter()

        if self.mode == "jev":
            try:
                decision = await self._evaluate_jev(metrics)
            except Exception as exc:  # noqa: BLE001 - fail soft by design
                logger.warning("Jev decision failed (%s); using fallback evaluator", exc)
                decision = evaluate_decision(metrics)
                decision = decision.model_copy(update={"provider": "fallback"})
        elif self.mode == "fallback":
            decision = evaluate_decision(metrics)
        else:
            decision = mock_decision(metrics)

        decision.latency_ms = (time.perf_counter() - started) * 1000.0
        return decision

    async def _evaluate_jev(self, metrics: RepMetrics | SetMetrics) -> MovementDecision:
        """Call the verified TypeSafe Jev endpoint and translate the answer."""
        if not self.settings.jev_api_key:
            raise JevError("JEV_API_KEY is not set")
        if not self.settings.jev_base_url:
            raise JevError("JEV_API_BASE_URL / JEV_BASE_URL is not set")

        model = self.settings.jev_model or JEV_DEFAULT_MODEL
        payload = {
            "state": _compact_state(metrics, metrics.exercise_id),
            "model": model,
            "questions": JEV_QUESTIONS,
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
        return parse_jev_response(data, metrics, model)

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
