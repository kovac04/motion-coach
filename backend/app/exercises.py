"""Small, configurable exercise-profile system.

Profiles carry coaching *context* only. They make no medical or biomechanical
claims — they describe which objective dimensions matter for the cue.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExerciseProfile(BaseModel):
    id: str
    display_name: str
    key_dimensions: list[str] = Field(default_factory=list)
    description: str = ""
    desired_behavior: str = ""
    jev_context: str = ""


_PROFILES: dict[str, ExerciseProfile] = {
    "generic_arm_motion": ExerciseProfile(
        id="generic_arm_motion",
        display_name="Generic Arm Motion",
        key_dimensions=["tempo", "rom", "consistency", "control"],
        description="Fallback profile for any arm movement without a specific profile.",
        desired_behavior="Smooth, repeatable arm motion through a comfortable range.",
        jev_context="Generic arm movement. Balance tempo, range, and consistency.",
    ),
    "bicep_curl": ExerciseProfile(
        id="bicep_curl",
        display_name="Bicep Curl",
        key_dimensions=["tempo", "rom", "control", "consistency"],
        description="Elbow flexion/extension tracked on the wrist.",
        desired_behavior="Controlled tempo with full comfortable range and stable reps.",
        jev_context="Bicep curl. Watch for rushing (fast reps), partial range, and drift.",
    ),
    "lateral_raise": ExerciseProfile(
        id="lateral_raise",
        display_name="Lateral Raise",
        key_dimensions=["tempo", "rom", "control", "consistency"],
        description="Shoulder abduction tracked on the wrist.",
        desired_behavior="Controlled raise to a consistent height without swinging.",
        jev_context="Lateral raise. Watch for momentum/swing and shrinking range late in set.",
    ),
}

_DEFAULT_PROFILE = _PROFILES["generic_arm_motion"]


def get_profile(exercise_id: str) -> ExerciseProfile:
    """Always returns a usable profile; unknown ids fall back to generic."""
    return _PROFILES.get(exercise_id, _DEFAULT_PROFILE)


def list_profiles() -> list[ExerciseProfile]:
    return list(_PROFILES.values())
