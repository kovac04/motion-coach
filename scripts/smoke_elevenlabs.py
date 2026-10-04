"""One-shot ElevenLabs diagnostic. Run intentionally: `make smoke-elevenlabs`.

Generates a fixed sentence with the configured model/voice/format/voice_settings and
saves the raw MP3 so you can play it directly (outside the browser) to separate a
voice/model problem from a browser-playback problem.

    python scripts/smoke_elevenlabs.py                 # configured model
    python scripts/smoke_elevenlabs.py --model eleven_v4_turbo
    python scripts/smoke_elevenlabs.py --voice <voice_id>

Never prints keys.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import Settings  # noqa: E402

SENTENCE = ("Your tempo increased toward the end of the set. "
            "Slow down and keep every rep controlled.")
OUT_PATH = Path("/tmp/motion-coach-elevenlabs-test.mp3")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=None, help="override ELEVENLABS_MODEL_ID")
    parser.add_argument("--voice", default=None, help="override ELEVENLABS_VOICE_ID")
    parser.add_argument("--output", type=Path, default=OUT_PATH)
    args = parser.parse_args()

    settings = Settings()
    if args.model:
        settings.elevenlabs_model_id = args.model
    if args.voice:
        settings.elevenlabs_voice_id = args.voice
    if not settings.elevenlabs_api_key or not settings.elevenlabs_voice_id:
        print("ELEVENLABS_API_KEY and/or ELEVENLABS_VOICE_ID not set.")
        return 2

    from elevenlabs import VoiceSettings
    from elevenlabs.client import ElevenLabs

    print(f"voice={settings.elevenlabs_voice_id} model={settings.elevenlabs_model_id} "
          f"format={settings.elevenlabs_output_format}")
    print(f"voice_settings: stability={settings.elevenlabs_stability} "
          f"similarity={settings.elevenlabs_similarity_boost} style={settings.elevenlabs_style} "
          f"speaker_boost={settings.elevenlabs_speaker_boost} speed={settings.elevenlabs_speed}")

    client = ElevenLabs(api_key=settings.elevenlabs_api_key)
    started = time.perf_counter()
    chunks = client.text_to_speech.convert(
        text=SENTENCE,
        voice_id=settings.elevenlabs_voice_id,
        model_id=settings.elevenlabs_model_id,
        output_format=settings.elevenlabs_output_format,
        voice_settings=VoiceSettings(
            stability=settings.elevenlabs_stability,
            similarity_boost=settings.elevenlabs_similarity_boost,
            style=settings.elevenlabs_style,
            use_speaker_boost=settings.elevenlabs_speaker_boost,
            speed=settings.elevenlabs_speed,
        ),
    )
    audio = b"".join(chunks)
    latency_ms = (time.perf_counter() - started) * 1000.0
    args.output.write_bytes(audio)
    print(f"OK: {len(audio)} bytes in {latency_ms:.0f} ms -> {args.output}")
    print("Play it directly to judge the voice, e.g.:  afplay " + str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
