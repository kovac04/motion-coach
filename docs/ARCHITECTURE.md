# Architecture

## The one-sentence version

Deterministic code measures movement, a bounded decision model classifies it, a language
model phrases one cue, and a TTS model speaks it — with a deterministic fallback at every
paid boundary.

## SENSOR PIPELINE — ACQUISITION REAL, SEGMENTATION NOT YET

Frozen transport chain (do not change without a real motion-analysis reason):

```
IMU -> ESP32-C5 -> BLE 50 Hz -> SensorRuntime -> ring buffer -> WebSocket -> React
```

```
MPU6050 (wrist)
        ↓ I2C  (SDA=D4/GPIO23, SCL=D5/GPIO24, addr 0x68)
   XIAO ESP32-C5          firmware/esp32-wearable
        ↓ BLE notify (18-byte little-endian packets, ~50 Hz)
   Mac / Python
        ├─ CLI tools: backend/app/sensors + scripts/imu_{monitor,record,plot}.py
        └─ FastAPI: SensorRuntime (single BLE owner, auto-reconnect)
                    ↓ bounded ring buffer (last ~6 s)
                    ↓ WebSocket /api/sensor/stream + GET /api/sensor/status
                    React "Live Sensor" panel (status + small magnitude chart)
        ↓
   continuous sample log  data/recordings/*.csv
        ↓
   rep segmentation       <-- NOT BUILT YET (needs real data first)
        ↓
   RepMetrics / SetMetrics
```

The acquisition + transport + live-display path is implemented; it produces raw
samples only. Rep detection, calibration, and metric extraction are deliberately
not built until real recordings exist. When built, they produce the exact Pydantic
models in `backend/app/models/metrics.py`, and nothing downstream changes.

Packet (18 bytes, little-endian; Python `struct.unpack("<HIhhhhhh", data)`):
`uint16 sequence | uint32 timestamp_ms | int16 ax,ay,az,gx,gy,gz`.

Sensor ranges (firmware and `packet.py` must stay in sync):
`ACCEL_CONFIG=0x08` (±4 g, 8192 LSB/g), `GYRO_CONFIG=0x10` (±1000 dps, 32.8 LSB/dps).

Files:
- `firmware/esp32-wearable/` — ESP32-C5 firmware (MPU6050 + BLE peripheral)
- `backend/app/sensors/packet.py` — wire format, `ImuSample`, sequence-gap tracking
- `backend/app/sensors/ble_client.py` — bleak central, async stream, reconnecting stream
- `backend/app/sensors/runtime.py` — `SensorRuntime`: single BLE owner + ring buffer + status
- `backend/app/sensors/recorder.py` — CSV recording
- `backend/app/routes/sensor.py` — `/api/sensor/status`, WebSocket `/api/sensor/stream`
- `scripts/imu_monitor.py`, `scripts/imu_record.py`, `scripts/imu_plot.py`

Only one component per process owns the BLE connection. The CLI tools and the
FastAPI runtime are separate processes, so run one at a time.

The STM32 is a reference/fallback only, not in the runtime path.

## APPLICATION PIPELINE (this repo)

```
RepMetrics / SetMetrics          (synthetic demo, or future real metrics)
        ↓
 Decision provider               DECISION_PROVIDER = mock | jev | fallback
        ↓
 MovementDecision                (our stable internal contract)
        ↓
 Language provider               LANGUAGE_PROVIDER = mock | gemini | fallback
        ↓
 CoachingResponse
        ↓
 Voice provider                  VOICE_PROVIDER = elevenlabs | browser | disabled
        ↓
 browser audio + React dashboard
```

## Why each layer exists

- **Metrics (Layer A, deterministic).** Facts only — durations, ratios, range, smoothness,
  similarity, consistency, drift. No LLM computes these. They are reproducible and testable.
- **Decision (Layer B, Jev/mock/fallback).** Answers *bounded* questions: what is the
  primary issue, how severe, what to prioritize, whether to speak, and overall quality.
  It is a decision model, not a chat model. It never writes prose.
- **Language (Layer C, Gemini/mock/fallback).** Turns the structured decision into ONE
  concise, actionable cue. It may not invent metrics or diagnose.
- **Voice (Layer D, ElevenLabs/browser).** Speaks only the final text.

## Fail-soft design

Every paid provider is wrapped so a failure degrades instead of crashing:

| Boundary  | Real          | On failure                        |
| --------- | ------------- | --------------------------------- |
| Decision  | Jev           | deterministic rules engine        |
| Language  | Gemini        | deterministic text templates      |
| Voice     | ElevenLabs    | browser `speechSynthesis`         |

Provider mode is environment-driven, so failures can be isolated one at a time.

## Metric conventions

Defined in `backend/app/models/metrics.py` and enforced by tests.

- `duration_ratio = duration_ms / reference_duration_ms`
  - `< 1` faster than reference, `> 1` slower, `1.0` matched
- `rom_ratio = rom_deg / reference_rom_deg`
- `peak_velocity_ratio = peak_angular_velocity_dps / reference_peak_velocity_dps`
- `smoothness_score`, `similarity_score`, `consistency_score`, `confidence` → `0..1`
- `duration_variability`, `rom_variability` → coefficient of variation (`stdev / mean`), `0..1`
- `tempo_drift_pct`, `rom_drift_pct` → signed percent change from first to last rep

Set-level aggregates are produced by `build_set_metrics()` from per-rep metrics.

## Decision contract

`MovementDecision` (`backend/app/models/decisions.py`) is intentionally independent of any
provider's wire format. The Jev adapter must *translate* into it; the rest of the app never
sees provider-specific payloads.

- `PrimaryIssue`: GOOD, TOO_FAST, TOO_SLOW, INSUFFICIENT_ROM, EXCESSIVE_ROM, INCONSISTENT, UNSTABLE, OTHER
- `CoachingPriority`: TEMPO, ROM, CONTROL, CONSISTENCY, NONE
- `Severity`: NONE, MILD, MODERATE, MAJOR
- `OverallQuality`: POOR, FAIR, GOOD, EXCELLENT

## When coaching is spoken

Every rep/set can be evaluated and displayed. Spoken coaching normally happens once at the
**end of a set** (the demo's `Analyze Set` / `Run Full Demo`). The frontend has an
**Auto speak** toggle. A future severe-issue path could speak mid-set; not enabled now.

## Where persistence will plug in

Raw recordings currently go to local CSV (`data/recordings/`, gitignored). A future store
(e.g. Tiger Data / Timescale) would persist raw IMU samples, reps, sets, and session
analytics behind a small storage interface — no schema is committed yet on purpose.

## Boundaries we deliberately did not cross

Implemented: MPU6050 I2C driver, ESP32-C5 firmware, BLE transport, packet decode, CSV
recording, plotting.

Still out of scope until real data exists: rep segmentation, DTW, reference-rep
comparison, calibration/baselines, and raw-IMU feature extraction. The firmware and BLE
layer stream continuous data only; they make no rep judgements.
