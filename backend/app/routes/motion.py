from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.services.live_coach import LiveMotionService

router = APIRouter(prefix="/api/motion", tags=["motion"])


class CalibrateRequest(BaseModel):
    exercise_id: str = "bicep_curl"
    seconds: float = Field(default=20.0, ge=5.0, le=60.0)


def _motion(request: Request) -> LiveMotionService:
    return request.app.state.motion


@router.get("/status")
def motion_status(request: Request) -> dict:
    return _motion(request).motion_status()


@router.post("/calibrate")
async def calibrate(request: Request, body: CalibrateRequest) -> dict:
    service = _motion(request)
    service.exercise_id = body.exercise_id
    return await service.calibrate(body.seconds)
