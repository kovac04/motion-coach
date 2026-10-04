"""Load and save calibration profiles from data/profiles/<exercise>.json."""

from __future__ import annotations

from pathlib import Path

from app.motion.calibration import CalibrationProfile

REPO_ROOT = Path(__file__).resolve().parents[3]
PROFILE_DIR = REPO_ROOT / "data" / "profiles"


def profile_path(exercise_id: str) -> Path:
    return PROFILE_DIR / f"{exercise_id}.json"


def load_profile(exercise_id: str) -> CalibrationProfile | None:
    path = profile_path(exercise_id)
    if path.exists():
        try:
            return CalibrationProfile.load(path)
        except Exception:  # noqa: BLE001 - a corrupt profile should not crash startup
            return None
    return None


def save_profile(profile: CalibrationProfile) -> Path:
    path = profile_path(profile.exercise_id)
    profile.save(path)
    return path


def list_profiles() -> list[str]:
    if not PROFILE_DIR.exists():
        return []
    return sorted(p.stem for p in PROFILE_DIR.glob("*.json"))
