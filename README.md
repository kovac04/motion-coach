# Motion Coach — StormHacks 2026

A wearable intelligent movement coach: deterministic movement metrics are evaluated by a
bounded decision model (Jev), converted into one concise coaching cue by Gemini, and spoken
aloud via ElevenLabs.

> **This repository was created fresh during the StormHacks 2026 hacking period.** See
> `docs/BUILD_LOG.md` for initial timestamps and `docs/ARCHITECTURE.md` for the design.

## Demo

▶️ **Watch the demo:** https://www.youtube.com/watch?v=WHgj9EYAbHU

The sensor pipeline is **not built yet**. This repo implements everything *after* the metrics
boundary and runs end-to-end on synthetic metrics.

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

## Stack

Python 3.12 · FastAPI · Pydantic · uv · Vite · React · TypeScript · pytest.
No Docker, no queue, no database (in-memory demo state only).

## Quick start (no credentials required)

```bash
make install     # uv sync (backend) + npm install (frontend)
make backend     # http://localhost:8000
make frontend    # http://localhost:5173
```

Everything defaults to mock providers, so the full demo works offline.

Then in the browser: pick a scenario → **Analyze Set** (or **Run Full Demo** to also speak).

## Demo simulator

Six synthetic sets: Perfect Set, Too Fast, Too Slow, Low Range of Motion, Inconsistent
Reps, Fatigue Drift. A collapsible **Developer metrics** panel lets you drive
`duration_ratio`, `rom_ratio`, `similarity`, `smoothness`, and `variability` manually and
evaluate. These scenarios will later be replaced by real `SetMetrics` with no backend change.

## Provider modes

Set in `.env` (copy `.env.example`):

| Variable             | Values                              | Default    |
| -------------------- | ----------------------------------- | ---------- |
| `DECISION_PROVIDER`  | `mock` `jev` `fallback`             | `mock`     |
| `LANGUAGE_PROVIDER`  | `mock` `gemini` `fallback`          | `mock`     |
| `VOICE_PROVIDER`     | `elevenlabs` `browser` `disabled`   | `browser`  |

Switch one at a time so failures stay isolated.

### Fail-soft behavior

| Boundary | Real provider | On failure / no key        |
| -------- | ------------- | -------------------------- |
| Decision | Jev           | deterministic rules engine |
| Language | Gemini        | deterministic templates    |
| Voice    | ElevenLabs    | browser `speechSynthesis`  |

The UI shows "using local evaluator/template/voice" rather than crashing.

## Commands

```bash
make backend          # run FastAPI (reload)
make frontend         # run Vite dev server
make test             # backend pytest + frontend production build
make test-backend     # backend tests only
make build            # frontend production build
make lint             # frontend oxlint
make smoke            # list smoke tests
make smoke-pipeline   # offline full pipeline over all scenarios (no keys)
make smoke-gemini     # one real Gemini request (needs GEMINI_API_KEY)
make smoke-elevenlabs # one real ElevenLabs request (needs key + voice id)
make smoke-jev        # gated until Jev contract verified (see docs/JEV_PROVIDER.md)
```

```bash
# ESP32-C5 wearable firmware (PlatformIO)
make firmware-build   # compile
make firmware-upload  # flash over USB-C
make firmware-monitor # 115200 serial monitor

# IMU over BLE (wearable must be powered and advertising)
make imu-monitor                 # live ~50 Hz diagnostics
make imu-record NAME=good-01     # record to data/recordings/good-01.csv (Ctrl-C to stop)
make imu-plot FILE=data/recordings/good-01.csv
make imu-analyze FILE=data/recordings/good-01.csv
make imu-calibrate                          # build data/profiles/bicep_curl.json
make imu-segment FILE=data/recordings/curl-good-01.csv   # detect reps + debug plot
make imu-segment ALL=1                      # run across all curl recordings
```

Recording protocol and inspection workflow: `docs/DATA_COLLECTION.md`.

Smoke tests never run during `pytest` and never print keys.

## Real-provider setup order

1. **Mock everything** (default) — prove the full loop offline.
2. **Gemini only** — `LANGUAGE_PROVIDER=gemini`, `make smoke-gemini`.
3. **ElevenLabs only** — `VOICE_PROVIDER=elevenlabs`, `make smoke-elevenlabs`.
4. **Jev only** — verify the provider contract first (`docs/JEV_PROVIDER.md`), then
   `DECISION_PROVIDER=jev` and `make smoke-jev`.
5. **Full real pipeline** — all three on.

Credentials live only on the server (`.env`, gitignored). They are never exposed to the
frontend or Vite env.

## Tests

```bash
make test-backend   # 50 tests: models, scenarios, providers, API, pipeline, BLE packets/recorder
```

The entire application must work with zero API keys and without BLE hardware — enforced by
tests. Packet decoding and CSV recording are pure and hardware-independent.

## Hardware / sensor pipeline

The wearable is a single XIAO ESP32-C5 reading an MPU6050 directly and streaming
18-byte packets over BLE:

```
MPU6050 --I2C--> XIAO ESP32-C5 --BLE notify--> Mac (backend/app/sensors)
```

- Firmware + wiring + bring-up: `firmware/esp32-wearable/README.md`
- SDA=`D4`/GPIO23, SCL=`D5`/GPIO24, sensor address `0x68`
- Rep segmentation and calibration are **not built yet** — first we record real data,
  then derive thresholds from it.

### Live sensor in the dashboard

Set `SENSOR_ENABLED=true` in `.env` (and have the powered wearable in BLE range), then
`make backend` + `make frontend`. The dashboard shows a **Live Sensor** panel: connection
state, effective Hz, sequence gaps, current accel/gyro, and a small gyro/accel magnitude
chart. The backend owns a single BLE connection (`SensorRuntime`) with automatic reconnect;
a power-cycle of the wearable is recovered without restarting FastAPI.

`GET /api/sensor/status` returns the live status as JSON; `WS /api/sensor/stream` pushes a
~2.5 s window about 10×/second. Keep `SENSOR_ENABLED=false` for the offline demo and tests.

The downstream metrics contract is unchanged: when segmentation exists it only needs to
produce a valid `RepMetrics` / `SetMetrics` (`backend/app/models/metrics.py`) and POST it to
`/api/evaluate/rep` or `/api/evaluate/set`.

## Docs

- `docs/ARCHITECTURE.md` — layers, boundaries, metric conventions, sensor boundary
- `docs/DATA_COLLECTION.md` — how to record and inspect real motion data
- `docs/MOTION.md` — rep detection, PCA projection, calibration, metrics
- `docs/API.md` — HTTP endpoints
- `docs/JEV_PROVIDER.md` — what must be verified before the real Jev adapter
- `docs/BUILD_LOG.md` — provenance / timestamps
