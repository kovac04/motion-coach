"""Language layer: turns a MovementDecision into ONE concise coaching cue.

Modes (env ``LANGUAGE_PROVIDER``):
    mock     — deterministic template, no credentials (default)
    gemini   — real Google GenAI SDK with structured output
    fallback — deterministic template
"""

from __future__ import annotations

import asyncio
import logging
import time

from pydantic import BaseModel

from app.config import Settings
from app.exercises import get_profile
from app.models.coaching import CoachingResponse, Tone
from app.models.decisions import MovementDecision, PrimaryIssue, Severity
from app.models.metrics import RepMetrics, SetMetrics
from app.services.fallbacks import coaching_template, summarize

logger = logging.getLogger(__name__)


class _GeminiCoaching(BaseModel):
    """Minimal structured-output schema; tone/provider metadata is added by us."""

    text: str
    short_label: str


_SYSTEM_INSTRUCTION = (
    "You are a concise movement coach. You receive a structured decision and a few "
    "objective metrics. Produce ONE short coaching instruction: 4-9 words, hard maximum "
    "12 words. Choose only the single highest-priority correction from the decision. "
    "Speak directly to the athlete. No percentages, no numbers, no explanations, no "
    "'based on', no multiple corrections, no motivational filler."
)


def _prompt(decision: MovementDecision, metrics: RepMetrics | SetMetrics, exercise_id: str) -> str:
    profile = get_profile(exercise_id)
    s = summarize(metrics)
    return (
        f"Exercise: {profile.display_name}\n"
        f"Context: {profile.jev_context}\n"
        f"Decision: primary_issue={decision.primary_issue.value}, "
        f"priority={decision.coaching_priority.value}, severity={decision.severity.value}, "
        f"overall_quality={decision.overall_quality.value}\n"
        f"Evidence: {', '.join(decision.evidence) or 'none'}\n"
        f"Observed: duration_ratio={s.duration_ratio}, rom_ratio={s.rom_ratio}, "
        f"consistency={s.consistency_score}, similarity={s.similarity_score}\n"
        "Write the athlete-facing coaching cue now."
    )


def _tone_for(decision: MovementDecision) -> Tone:
    if decision.primary_issue is PrimaryIssue.GOOD:
        return Tone.ENCOURAGING
    if decision.severity in (Severity.MODERATE, Severity.MAJOR):
        return Tone.CORRECTIVE
    return Tone.NEUTRAL


class LanguageService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.mode = settings.language_provider

    async def generate(
        self,
        decision: MovementDecision,
        metrics: RepMetrics | SetMetrics,
        exercise_id: str,
    ) -> CoachingResponse:
        started = time.perf_counter()

        if self.mode == "gemini" and self.settings.gemini_api_key:
            try:
                response = await asyncio.to_thread(
                    self._generate_gemini, decision, metrics, exercise_id
                )
            except Exception as exc:  # noqa: BLE001 - fail soft by design
                logger.warning("Gemini generation failed (%s); using template", exc)
                response = self._template(decision, exercise_id, provider="fallback")
        else:
            response = self._template(
                decision, exercise_id, provider="mock" if self.mode == "mock" else "fallback"
            )

        response.latency_ms = (time.perf_counter() - started) * 1000.0
        return response

    def _template(self, decision: MovementDecision, exercise_id: str, provider: str) -> CoachingResponse:
        profile = get_profile(exercise_id)
        text, label = coaching_template(decision, profile.display_name)
        return CoachingResponse(
            text=text,
            short_label=label,
            tone=_tone_for(decision),
            provider=provider,
        )

    def _generate_gemini(
        self, decision: MovementDecision, metrics: RepMetrics | SetMetrics, exercise_id: str
    ) -> CoachingResponse:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.settings.gemini_api_key)
        prompt = _prompt(decision, metrics, exercise_id)

        base_config: dict = {
            "system_instruction": _SYSTEM_INSTRUCTION,
            "response_mime_type": "application/json",
            "response_schema": _GeminiCoaching,
            "temperature": 0.4,
            "max_output_tokens": 400,
        }

        # Some Gemini flash models "think" and exhaust the small output budget; some
        # lite models reject a thinking config outright. Try thinking-disabled first,
        # then fall back to a plain call. This keeps the model configurable.
        configs: list[dict] = []
        if hasattr(types, "ThinkingConfig"):
            configs.append({**base_config, "thinking_config": types.ThinkingConfig(thinking_budget=0)})
        configs.append(base_config)

        parsed = None
        last_error: Exception | None = None
        for config_kwargs in configs:
            try:
                result = client.models.generate_content(
                    model=self.settings.gemini_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config_kwargs),
                )
            except Exception as exc:  # noqa: BLE001 - try the next config shape
                last_error = exc
                continue
            if result.parsed is not None:
                parsed = result.parsed
                break

        if parsed is None:
            raise ValueError(f"Gemini returned no structured output ({last_error})")
        return CoachingResponse(
            text=parsed.text,
            short_label=parsed.short_label,
            tone=_tone_for(decision),
            provider="gemini",
            model_version=self.settings.gemini_model,
        )


def get_language_service(settings: Settings) -> LanguageService:
    return LanguageService(settings)
