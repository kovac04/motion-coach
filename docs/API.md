# API

Base URL during dev: `http://localhost:8000` (the Vite dev server proxies `/api` and `/health`).

## GET /health

Returns backend status and the *non-secret* provider summary.

```json
{
  "status": "ok",
  "app_env": "development",
  "providers": {
    "decision": { "mode": "mock", "configured": false, "model": null },
    "language": { "mode": "mock", "configured": false, "model": "gemini-2.0-flash" },
    "voice":    { "mode": "browser", "configured": false, "model": "eleven_turbo_v2_5" }
  }
}
```

## GET /api/demo/scenarios

List synthetic scenarios.

## GET /api/demo/scenarios/{scenario_id}

Return a fully built `SetMetrics` for a scenario. IDs: `perfect_set`, `too_fast`,
`too_slow`, `low_rom`, `inconsistent`, `fatigue_drift`.

## POST /api/demo/custom

Build a `SetMetrics` from high-level controls (used by the developer panel).

```json
{
  "exercise_id": "bicep_curl",
  "duration_ratio": 0.8,
  "rom_ratio": 1.0,
  "similarity": 0.9,
  "smoothness": 0.9,
  "variability": 0.05,
  "rep_count": 5
}
```

## POST /api/evaluate/rep

Body: `RepMetrics`. Returns:

```json
{
  "metrics": { "...": "echoed input, with derived ratios" },
  "decision": { "primary_issue": "TOO_FAST", "coaching_priority": "TEMPO", "...": "..." },
  "coaching": { "text": "Slow down slightly...", "short_label": "Control your tempo" },
  "timings_ms": { "decision": 0.1, "coaching": 0.2 }
}
```

## POST /api/evaluate/set

Body: `SetMetrics`. Same response shape as above.

## POST /api/tts

Body: `{ "text": "..." }`.

- `200` + `audio/mpeg` when ElevenLabs succeeds.
- `502` + JSON `{ "detail": { "voice_provider": "browser", "message": "..." } }` when it
  falls back — the frontend then uses browser `speechSynthesis`.

## GET /api/exercises

List exercise profiles.

## GET /api/providers

Same safe provider summary as `/health`. Never returns keys.
