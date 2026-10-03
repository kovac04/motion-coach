"""One short real ElevenLabs request. Run intentionally: `make smoke-elevenlabs`.

Never prints keys. Writes audio to a temp file (not in the repo).
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import Settings  # noqa: E402
from app.services.elevenlabs import VoiceService  # noqa: E402

SENTENCE = "Slow down slightly and keep the movement controlled."


def main() -> int:
    settings = Settings(voice_provider="elevenlabs")
    if not settings.elevenlabs_api_key or not settings.elevenlabs_voice_id:
        print("ELEVENLABS_API_KEY and/or ELEVENLABS_VOICE_ID not set.")
        return 2

    print(f"provider: elevenlabs  voice: {settings.elevenlabs_voice_id}  model: {settings.elevenlabs_model_id}")
    result = asyncio.run(VoiceService(settings).synthesize(SENTENCE))
    print(f"provider returned: {result.provider}")

    if not result.audio:
        print(f"FAIL: no audio returned ({result.error})")
        return 1

    out = Path(tempfile.gettempdir()) / "motion_coach_smoke.mp3"
    out.write_bytes(result.audio)
    print(f"OK: {len(result.audio)} bytes -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
