"""Voice layer: text -> spoken audio.

Modes (env ``VOICE_PROVIDER``):
    elevenlabs — real ElevenLabs SDK, returns MP3 bytes
    browser    — backend declines; frontend uses speechSynthesis
    disabled   — no audio

The frontend always has the browser ``speechSynthesis`` fallback, so a voice outage
never kills the demo. The provider actually used is reported so the UI can label
"VOICE: ELEVENLABS" vs "VOICE: BROWSER FALLBACK" unambiguously.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from app.config import Settings

logger = logging.getLogger(__name__)

CONTENT_TYPE = "audio/mpeg"


@dataclass
class AudioResult:
    provider: str
    audio: bytes | None = None
    content_type: str | None = None
    error: str | None = None
    latency_ms: float | None = None
    voice_id: str | None = None
    model_id: str | None = None
    output_format: str | None = None
    byte_count: int | None = None


class VoiceService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.mode = settings.voice_provider

    async def synthesize(self, text: str) -> AudioResult:
        if self.mode != "elevenlabs":
            return AudioResult(provider=self.mode, error="voice provider not set to elevenlabs")
        if not (self.settings.elevenlabs_api_key and self.settings.elevenlabs_voice_id):
            return AudioResult(provider="browser", error="ElevenLabs not configured")
        started = time.perf_counter()
        try:
            audio = await asyncio.to_thread(self._synthesize_elevenlabs, text)
            latency_ms = (time.perf_counter() - started) * 1000.0
            logger.info(
                "ELEVENLABS: voice=%s model=%s format=%s bytes=%d latency=%.0fms",
                self.settings.elevenlabs_voice_id, self.settings.elevenlabs_model_id,
                self.settings.elevenlabs_output_format, len(audio), latency_ms,
            )
            return AudioResult(
                provider="elevenlabs", audio=audio, content_type=CONTENT_TYPE,
                latency_ms=latency_ms, voice_id=self.settings.elevenlabs_voice_id,
                model_id=self.settings.elevenlabs_model_id,
                output_format=self.settings.elevenlabs_output_format,
                byte_count=len(audio),
            )
        except Exception as exc:  # noqa: BLE001 - fail soft to browser voice
            logger.warning("ElevenLabs synthesis failed (%s); frontend should use browser voice", exc)
            return AudioResult(provider="browser", error=str(exc),
                               latency_ms=(time.perf_counter() - started) * 1000.0)

    def _synthesize_elevenlabs(self, text: str) -> bytes:
        from elevenlabs import VoiceSettings
        from elevenlabs.client import ElevenLabs

        client = ElevenLabs(api_key=self.settings.elevenlabs_api_key)
        voice_settings = VoiceSettings(
            stability=self.settings.elevenlabs_stability,
            similarity_boost=self.settings.elevenlabs_similarity_boost,
            style=self.settings.elevenlabs_style,
            use_speaker_boost=self.settings.elevenlabs_speaker_boost,
            speed=self.settings.elevenlabs_speed,
        )
        chunks = client.text_to_speech.convert(
            text=text,
            voice_id=self.settings.elevenlabs_voice_id,
            model_id=self.settings.elevenlabs_model_id,
            output_format=self.settings.elevenlabs_output_format,
            voice_settings=voice_settings,
        )
        return b"".join(chunks)


def get_voice_service(settings: Settings) -> VoiceService:
    return VoiceService(settings)
