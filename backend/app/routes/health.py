from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "status": "ok",
        "app_env": settings.app_env,
        "providers": settings.provider_status(),
    }
