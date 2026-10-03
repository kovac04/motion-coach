"""Coaching-language contract (output of the language layer)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Tone(str, Enum):
    ENCOURAGING = "ENCOURAGING"
    NEUTRAL = "NEUTRAL"
    CORRECTIVE = "CORRECTIVE"


class CoachingResponse(BaseModel):
    """One concise, actionable coaching cue plus a short label."""

    text: str = Field(min_length=1)
    short_label: str = Field(min_length=1)
    tone: Tone = Tone.NEUTRAL

    provider: str = "unknown"
    model_version: str | None = None
    latency_ms: float | None = None
