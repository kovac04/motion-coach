"""Voice layer: text -> spoken audio.

Modes (env ``VOICE_PROVIDER``):
    elevenlabs — real ElevenLabs SDK, returns MP3 bytes
    browser    — backend declines; frontend uses speechSynthesis
    disabled   — no audio

The frontend always has the browser ``speechSynthesis`` fallback, so a voice outage
never kills the demo.
"""

from __future__ import annotations

import asyncio
import logging
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


class VoiceService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.mode = settings.voice_provider

    async def synthesize(self, text: str) -> AudioResult:
        if self.mode != "elevenlabs":
            return AudioResult(provider=self.mode, error="voice provider not set to elevenlabs")
        if not (self.settings.elevenlabs_api_key and self.settings.elevenlabs_voice_id):
            return AudioResult(provider="browser", error="ElevenLabs not configured")
        try:
            audio = await asyncio.to_thread(self._synthesize_elevenlabs, text)
            return AudioResult(provider="elevenlabs", audio=audio, content_type=CONTENT_TYPE)
        except Exception as exc:  # noqa: BLE001 - fail soft to browser voice
            logger.warning("ElevenLabs synthesis failed (%s); frontend should use browser voice", exc)
            return AudioResult(provider="browser", error=str(exc))

    def _synthesize_elevenlabs(self, text: str) -> bytes:
        from elevenlabs.client import ElevenLabs

        client = ElevenLabs(api_key=self.settings.elevenlabs_api_key)
        chunks = client.text_to_speech.convert(
            text=text,
            voice_id=self.settings.elevenlabs_voice_id,
            model_id=self.settings.elevenlabs_model_id,
        )
        return b"".join(chunks)


def get_voice_service(settings: Settings) -> VoiceService:
    return VoiceService(settings)
