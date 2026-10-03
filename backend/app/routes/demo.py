from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.demo import scenarios
from app.exercises import list_profiles
from app.models.metrics import SetMetrics

router = APIRouter(prefix="/api", tags=["demo"])


@router.get("/demo/scenarios")
def demo_scenarios() -> list[dict[str, str]]:
    return scenarios.list_scenario_summaries()


@router.get("/demo/scenarios/{scenario_id}", response_model=SetMetrics)
def demo_scenario(scenario_id: str) -> SetMetrics:
    try:
        return scenarios.build_scenario(scenario_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown scenario: {scenario_id}") from None


@router.get("/exercises")
def exercises() -> list[dict]:
    return [profile.model_dump() for profile in list_profiles()]
