from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.models.metrics import RepMetrics, SetMetrics
from app.services.coach_pipeline import CoachPipeline, EvaluationResult
from app.services.elevenlabs import get_voice_service

router = APIRouter(prefix="/api", tags=["coaching"])


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=400)


def _pipeline(settings: Settings) -> CoachPipeline:
    return CoachPipeline(settings)


@router.post("/evaluate/rep", response_model=EvaluationResult)
async def evaluate_rep(
    metrics: RepMetrics, settings: Settings = Depends(get_settings)
) -> EvaluationResult:
    return await _pipeline(settings).evaluate(metrics)


@router.post("/evaluate/set", response_model=EvaluationResult)
async def evaluate_set(
    metrics: SetMetrics, settings: Settings = Depends(get_settings)
) -> EvaluationResult:
    return await _pipeline(settings).evaluate(metrics)


@router.post("/tts")
async def tts(request: TTSRequest, settings: Settings = Depends(get_settings)):
    result = await get_voice_service(settings).synthesize(request.text)
    if result.audio:
        headers = {"X-TTS-Ms": f"{result.latency_ms or 0:.0f}", "X-TTS-Provider": result.provider}
        return Response(content=result.audio, media_type=result.content_type, headers=headers)
    # Fail soft: tell the frontend to use browser speechSynthesis.
    raise HTTPException(
        status_code=502,
        detail={"voice_provider": result.provider, "message": result.error or "voice unavailable"},
    )


@router.get("/providers")
def providers(settings: Settings = Depends(get_settings)) -> dict:
    return settings.provider_status()
