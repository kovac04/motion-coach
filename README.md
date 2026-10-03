# Motion Coach — StormHacks 2026

A wearable intelligent movement coach: deterministic movement metrics are evaluated by a
bounded decision model (Jev), converted into one concise coaching cue by Gemini, and spoken
aloud via ElevenLabs.

> **This repository was created fresh during the StormHacks 2026 hacking period.** See
> `docs/BUILD_LOG.md` for initial timestamps and `docs/ARCHITECTURE.md` for the design.

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
make test-backend   # 36 tests: models, scenarios, fallbacks, providers, API, pipeline
```

The entire application must work with zero API keys — that is enforced by tests.

## Sensor integration boundary

Hardware/signal-processing code only needs to produce a valid `RepMetrics` or `SetMetrics`
(`backend/app/models/metrics.py`) and POST it to `/api/evaluate/rep` or `/api/evaluate/set`.
No architectural change is required. The metrics contract and conventions are documented in
`docs/ARCHITECTURE.md`.

## Docs

- `docs/ARCHITECTURE.md` — layers, boundaries, metric conventions, sensor boundary
- `docs/API.md` — HTTP endpoints
- `docs/JEV_PROVIDER.md` — what must be verified before the real Jev adapter
- `docs/BUILD_LOG.md` — provenance / timestamps
