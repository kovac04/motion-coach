from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.services.live_coach import LiveMotionService

router = APIRouter(prefix="/api/motion", tags=["motion"])


class AutoFinishRequest(BaseModel):
    enabled: bool = True


class ExerciseRequest(BaseModel):
    exercise_id: str


def _motion(request: Request) -> LiveMotionService:
    return request.app.state.motion


@router.get("/status")
def motion_status(request: Request) -> dict:
    return _motion(request).motion_status()


@router.post("/exercise")
def select_exercise(request: Request, body: ExerciseRequest) -> dict:
    return _motion(request).select_exercise(body.exercise_id)


@router.post("/set/start")
def set_start(request: Request) -> dict:
    return _motion(request).start_set()


@router.post("/set/finish")
async def set_finish(request: Request) -> dict:
    return await _motion(request).finish_set()


@router.post("/calibrate/start")
def calibrate_start(request: Request) -> dict:
    return _motion(request).start_calibration()


@router.post("/calibrate/finish")
def calibrate_finish(request: Request) -> dict:
    return _motion(request).finish_calibration()


@router.post("/auto-finish")
def auto_finish(request: Request, body: AutoFinishRequest) -> dict:
    return _motion(request).set_auto_finish(body.enabled)
