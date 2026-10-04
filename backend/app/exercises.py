"""Small, configurable exercise-profile system.

Profiles carry coaching *context* only. They make no medical or biomechanical
claims — they describe which objective dimensions matter for the cue.

Only exercises that produce clear cyclical rotational wrist motion are marked
live-selectable. Each learns its own calibration profile independently.
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
        key_dimensions=["tempo", "excursion", "consistency", "control"],
        description="Elbow flexion/extension tracked on the wrist.",
        desired_behavior="Controlled tempo with full comfortable range and stable reps.",
        jev_context="Bicep curl. Watch for rushing (fast reps), partial range, and drift.",
    ),
    "lateral_raise": ExerciseProfile(
        id="lateral_raise",
        display_name="Lateral Raise",
        key_dimensions=["tempo", "excursion", "consistency", "swing/control"],
        description="Shoulder abduction tracked on the wrist.",
        desired_behavior="Controlled raise to a consistent height without swinging.",
        jev_context="Lateral raise. Watch for momentum/swing and shrinking range late in set.",
    ),
    "triceps_extension": ExerciseProfile(
        id="triceps_extension",
        display_name="Triceps Extension",
        key_dimensions=["tempo", "excursion", "consistency", "control"],
        description="Elbow extension/flexion tracked on the wrist.",
        desired_behavior="Controlled extension through a consistent range.",
        jev_context="Triceps extension. Watch for rushed reps and incomplete range.",
    ),
    "front_raise": ExerciseProfile(
        id="front_raise",
        display_name="Front Raise",
        key_dimensions=["tempo", "excursion", "consistency", "control"],
        description="Shoulder flexion tracked on the wrist.",
        desired_behavior="Controlled lift to a consistent height without using momentum.",
        jev_context="Front raise. Watch for momentum at the bottom and dropping range.",
    ),
}

_DEFAULT_PROFILE = _PROFILES["generic_arm_motion"]

# Exercises exposed in LIVE mode. These all produce clear cyclical rotational
# wrist motion. (Bench press is intentionally excluded: significant translation
# with little orientation change makes gyro-derived excursion untrustworthy.)
LIVE_EXERCISE_IDS = ["bicep_curl", "lateral_raise", "triceps_extension", "front_raise"]


def get_profile(exercise_id: str) -> ExerciseProfile:
    """Always returns a usable profile; unknown ids fall back to generic."""
    return _PROFILES.get(exercise_id, _DEFAULT_PROFILE)


def list_profiles() -> list[ExerciseProfile]:
    return list(_PROFILES.values())


def list_live_profiles() -> list[ExerciseProfile]:
    return [_PROFILES[exercise_id] for exercise_id in LIVE_EXERCISE_IDS]
