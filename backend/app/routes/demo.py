from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.demo import scenarios
from app.exercises import list_profiles
from app.models.metrics import SetMetrics

router = APIRouter(prefix="/api", tags=["demo"])


class CustomSetRequest(BaseModel):
    exercise_id: str = scenarios.EXERCISE_ID
    duration_ratio: float = Field(default=1.0, gt=0.2, lt=3.0)
    rom_ratio: float = Field(default=1.0, gt=0.1, lt=2.0)
    similarity: float = Field(default=0.9, ge=0.0, le=1.0)
    smoothness: float = Field(default=0.9, ge=0.0, le=1.0)
    variability: float = Field(default=0.05, ge=0.0, le=0.5)
    rep_count: int = Field(default=5, ge=1, le=20)


@router.get("/demo/scenarios")
def demo_scenarios() -> list[dict[str, str]]:
    return scenarios.list_scenario_summaries()


@router.get("/demo/scenarios/{scenario_id}", response_model=SetMetrics)
def demo_scenario(scenario_id: str) -> SetMetrics:
    try:
        return scenarios.build_scenario(scenario_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown scenario: {scenario_id}") from None


@router.post("/demo/custom", response_model=SetMetrics)
def demo_custom(request: CustomSetRequest) -> SetMetrics:
    return scenarios.custom_set(**request.model_dump())


@router.get("/exercises")
def exercises() -> list[dict]:
    return [profile.model_dump() for profile in list_profiles()]
