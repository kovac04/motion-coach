"""Internal decision contract.

This is OUR stable application model. It is deliberately independent of whatever
wire format the real Jev provider uses — the Jev adapter translates into this.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class PrimaryIssue(str, Enum):
    GOOD = "GOOD"
    TOO_FAST = "TOO_FAST"
    TOO_SLOW = "TOO_SLOW"
    INSUFFICIENT_ROM = "INSUFFICIENT_ROM"
    EXCESSIVE_ROM = "EXCESSIVE_ROM"
    INCONSISTENT = "INCONSISTENT"
    UNSTABLE = "UNSTABLE"
    OTHER = "OTHER"


class CoachingPriority(str, Enum):
    TEMPO = "TEMPO"
    ROM = "ROM"
    CONTROL = "CONTROL"
    CONSISTENCY = "CONSISTENCY"
    NONE = "NONE"


class Severity(str, Enum):
    NONE = "NONE"
    MILD = "MILD"
    MODERATE = "MODERATE"
    MAJOR = "MAJOR"


class OverallQuality(str, Enum):
    POOR = "POOR"
    FAIR = "FAIR"
    GOOD = "GOOD"
    EXCELLENT = "EXCELLENT"


class MovementDecision(BaseModel):
    """Bounded decision produced by the decision layer (Jev / mock / fallback)."""

    primary_issue: PrimaryIssue
    coaching_priority: CoachingPriority
    severity: Severity
    should_speak: bool
    overall_quality: OverallQuality

    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)

    # Optional probability distribution over candidate issues (for the UI's
    # "decision details" panel). Keys are PrimaryIssue values.
    alternatives: dict[str, float] = Field(default_factory=dict)

    provider: str = "unknown"
    model_version: str | None = None
    latency_ms: float | None = None
