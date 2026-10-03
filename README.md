# Motion Coach — StormHacks 2026

A wearable intelligent movement coach: deterministic movement metrics are evaluated by a
bounded decision model (Jev), converted into one concise coaching cue by Gemini, and spoken
aloud via ElevenLabs.

> **This repository was created fresh during the StormHacks 2026 hacking period.**
> See `docs/BUILD_LOG.md` for the initial timestamps and `docs/ARCHITECTURE.md` for design.

## Status

Currently the project sits **after** the sensor/metrics boundary: it runs end-to-end on
synthetic `RepMetrics` / `SetMetrics`. The IMU → MCU → signal-processing pipeline is **not
built yet** and plugs in later by producing those same Pydantic models.

```
synthetic / future-real metrics
        ↓
   decision provider   (mock | jev | fallback)
        ↓
   MovementDecision
        ↓
   language provider   (mock | gemini | fallback)
        ↓
   CoachingResponse
        ↓
  voice provider       (elevenlabs | browser | disabled)
        ↓
   spoken feedback + React UI
```

## Quick start (no credentials required)

```bash
make install      # uv sync backend + npm install frontend
make backend      # FastAPI on http://localhost:8000
make frontend     # Vite dev server on http://localhost:5173
```

Everything defaults to mock providers, so the full demo works offline with zero API keys.

## Tests

```bash
make test         # backend pytest
```

## Provider modes

See `.env.example`. Defaults:

```
DECISION_PROVIDER=mock
LANGUAGE_PROVIDER=mock
VOICE_PROVIDER=browser
```

Enable real providers progressively (`jev`, `gemini`, `elevenlabs`) once credentials exist.
Every paid provider has a deterministic fallback so a live demo survives network failures.

## Documentation

- `docs/ARCHITECTURE.md` — layers, boundaries, metric conventions
- `docs/API.md` — HTTP endpoints
- `docs/BUILD_LOG.md` — provenance / timestamps
