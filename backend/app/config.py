"""Application configuration. All secrets stay server-side and are never exposed."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DecisionProvider = Literal["mock", "jev", "fallback"]
LanguageProvider = Literal["mock", "gemini", "fallback"]
VoiceProvider = Literal["elevenlabs", "browser", "disabled"]


class Settings(BaseSettings):
    # Reads backend/.env (when run from backend/) or repo-root .env; both gitignored.
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"

    decision_provider: DecisionProvider = "mock"
    language_provider: LanguageProvider = "mock"
    voice_provider: VoiceProvider = "browser"

    # TypeSafe Jev. Accepts JEV_BASE_URL or the provider's JEV_API_BASE_URL name.
    jev_api_key: str = ""
    jev_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("JEV_BASE_URL", "JEV_API_BASE_URL"),
    )
    jev_model: str = "jev-latest"
    jev_docs: str = ""

    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-lite-latest"

    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_model_id: str = "eleven_v4_turbo"
    elevenlabs_output_format: str = "mp3_44100_128"
    elevenlabs_stability: float = 0.55
    elevenlabs_similarity_boost: float = 0.80
    elevenlabs_style: float = 0.15
    elevenlabs_speaker_boost: bool = True
    elevenlabs_speed: float = 1.0

    database_url: str = ""

    # Live IMU sensor runtime (single BLE owner). Disabled by default so tests
    # and the offline demo never touch Bluetooth.
    sensor_enabled: bool = False
    sensor_device_name: str = "MotionCoach-IMU"
    sensor_buffer_seconds: float = 6.0
    sensor_retry_delay: float = 2.0

    # Persist every finalized live set to data/debug/ for offline diagnosis.
    debug_save_live_sets: bool = False

    # Timeouts (seconds) for paid providers.
    provider_connect_timeout: float = 5.0
    provider_request_timeout: float = 20.0

    # Live-demo decision/language budgets (seconds). If a real provider exceeds
    # its budget the pipeline immediately uses the deterministic fallback, so the
    # spoken cue never waits on the network.
    live_jev_timeout_s: float = 2.0
    live_gemini_timeout_s: float = 2.0

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
                "voice_id": self.elevenlabs_voice_id or None,
                "output_format": self.elevenlabs_output_format,
            },
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
