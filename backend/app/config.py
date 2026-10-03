"""Application configuration. All secrets stay server-side and are never exposed."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

DecisionProvider = Literal["mock", "jev", "fallback"]
LanguageProvider = Literal["mock", "gemini", "fallback"]
VoiceProvider = Literal["elevenlabs", "browser", "disabled"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"

    decision_provider: DecisionProvider = "mock"
    language_provider: LanguageProvider = "mock"
    voice_provider: VoiceProvider = "browser"

    jev_api_key: str = ""
    jev_base_url: str = ""
    jev_model: str = ""

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_model_id: str = "eleven_turbo_v2_5"

    database_url: str = ""

    # Timeouts (seconds) for paid providers.
    provider_connect_timeout: float = 5.0
    provider_request_timeout: float = 20.0

    def provider_status(self) -> dict[str, dict[str, object]]:
        """Safe, non-secret summary for /health and /api/providers."""
        return {
            "decision": {
                "mode": self.decision_provider,
                "configured": bool(self.jev_api_key and self.jev_base_url),
                "model": self.jev_model or None,
            },
            "language": {
                "mode": self.language_provider,
                "configured": bool(self.gemini_api_key),
                "model": self.gemini_model or None,
            },
            "voice": {
                "mode": self.voice_provider,
                "configured": bool(self.elevenlabs_api_key and self.elevenlabs_voice_id),
                "model": self.elevenlabs_model_id or None,
            },
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
