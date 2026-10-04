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

## GET /api/sensor/status

Live IMU status (no secrets). `connected`, `device_name`, `address`, `sample_rate_hz`,
`sequence_gaps`, `missing_samples`, `malformed`, `connections`, `last_error`, and the latest
`sample` (raw ax..gz plus accel/gyro magnitude). Works even when `SENSOR_ENABLED=false`
(returns `connected: false`).

## WS /api/sensor/stream

WebSocket. Pushes ~10×/second:

```json
{
  "type": "sensor",
  "status": { "...": "same shape as /api/sensor/status" },
  "samples": [[host_timestamp, gyro_magnitude, accel_magnitude], "..."]
}
```

`samples` is the last ~2.5 s of the bounded ring buffer, ready to render directly.

## Live motion control

`GET /api/motion/status`
: `mode` = `NO_PROFILE` | `CALIBRATING` | `READY` | `SET_ACTIVE` | `ANALYZING` | `COACHING`;
also `rep_count`, `auto_finish`, `idle_timeout_s`, `has_profile`, `available_profiles`,
`calibration` (`{active, reps, target, result}`), `last_evaluation`, and `latency_ms`
(`{metrics, jev, gemini}`).

`POST /api/motion/calibrate/start`
: Starts capturing the live stream. Detects reps as they happen and **auto-finishes at
  5 valid reps**, building and saving the profile. Returns `{ ok, target_reps }`.

`POST /api/motion/calibrate/finish`
: Manual fallback finish. Returns the calibration result.

`POST /api/motion/set/start`
: Clears the set buffer and enters `SET_ACTIVE`. Movement before this is never part of a set.

`POST /api/motion/set/finish`
: Finalizes immediately, builds `SetMetrics`, and runs the pipeline once. Returns
  `{ ok, rejected?, reason?, source:"live", rep_count, metrics, decision, coaching, timings_ms }`
  or `{ ok:false, error }` if no set is active.

`POST /api/motion/auto-finish`
: `{ "enabled": true }` toggles the 3 s idle auto-finish backup.

## WS /api/sensor/stream (motion field)

Each stream message also includes `motion` (same shape as `/api/motion/status`),
so the dashboard can show SET ACTIVE / REP N / SET COMPLETE and the coaching cue.

## GET /api/exercises

List exercise profiles.

## GET /api/providers

Same safe provider summary as `/health`. Never returns keys.
