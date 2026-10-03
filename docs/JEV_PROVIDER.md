# Jev Provider (TypeSafe) — VERIFIED

**Status: VERIFIED on 2026-10-03** from the official documentation at
<https://docs.typesafe.ai/introduction> (Quick Start → API). The adapter is implemented in
`backend/app/services/jev.py`.

## Provider

| Item | Value |
| --- | --- |
| Provider | TypeSafe AI — **Jev**, first System One model |
| Docs | https://docs.typesafe.ai/introduction |
| Base URL | `https://api.typesafe.ai` |
| Endpoint | `POST /v1/systemone` |
| Auth | `Authorization: Bearer <JEV_API_KEY>` |
| Model | `jev-latest` (responses return a concrete version such as `jev-1.13.0`) |
| Question types | `choice`, `score`, `noul` (mix any number in one request) |
| SDK (optional) | `typesafe-sdk` (Python ≥ 3.10), default env var `TYPESAFE_API_KEY` |

## Environment variable mapping

We keep Jev config behind our own names (per project rules). The provider names in the
local `.env` are mapped as follows:

| Project variable | Provider / local name | Notes |
| --- | --- | --- |
| `JEV_API_KEY` | `JEV_API_KEY` | sent as `Authorization: Bearer …` |
| `JEV_BASE_URL` | `JEV_API_BASE_URL` | `config.py` accepts either alias |
| `JEV_MODEL` | (not set) | defaults to `jev-latest` |
| `JEV_DOCS` | `JEV_DOCS` | informational docs URL only |

Note: TypeSafe's own SDK reads `TYPESAFE_API_KEY`. We use `httpx` directly (the request and
response schemas are simple JSON), so our `JEV_API_KEY` is used as-is. To use the official
SDK instead you would add `TYPESAFE_API_KEY=$JEV_API_KEY` and `uv add typesafe-sdk`.

## Request (as implemented)

```json
{
  "state": {
    "exercise": "bicep_curl",
    "exercise_context": "Bicep curl. Watch for rushing ...",
    "reference": { "duration_ms": 2000, "rom_deg": 120, "peak_velocity_dps": 210 },
    "current": { "rep_count": 5, "avg_duration_ratio": 0.86, "avg_rom_ratio": 0.98,
                 "reference_similarity_mean": 0.81, "duration_variability": 0.09 },
    "set_context": { "tempo_drift_pct": -23.0, "rom_drift_pct": -1.0, "consistency_score": 0.9 }
  },
  "model": "jev-latest",
  "questions": {
    "primary_issue":     { "type": "choice", "instructions": "...", "criteria": { ... } },
    "severity":          { "type": "score",  "instructions": "...", "criteria": [ ... ] },
    "coaching_priority": { "type": "choice", "instructions": "...", "criteria": { ... } },
    "should_speak":      { "type": "noul",   "instructions": "...", "criteria": { "true": "...", "false": "..." } },
    "overall_quality":   { "type": "score",  "instructions": "...", "criteria": [ ... ] }
  }
}
```

Five questions in **one** request (evaluated in parallel). The `state` contains only derived
facts — never raw 100 Hz sensor arrays.

## Response (as parsed)

```json
{
  "model": "jev-1.13.0",
  "answers": {
    "primary_issue": { "type": "choice", "choice": "too_fast", "confidence": 0.91,
                       "probabilities": { "too_fast": 0.82, "good": 0.11, "inconsistent": 0.07 } },
    "severity": { "type": "score", "score": 1.4, "confidence": 0.7, "probabilities": { ... } },
    "coaching_priority": { "type": "choice", "choice": "tempo", "confidence": 0.8, "probabilities": { ... } },
    "should_speak": { "type": "noul", "noul": 0.93 },
    "overall_quality": { "type": "score", "score": 1.2, "confidence": 0.6, "probabilities": { ... } }
  },
  "usage": { "input_tokens": 300, "output_tokens": 40 }
}
```

Mapping into our `MovementDecision`:

- `primary_issue.choice` → `PrimaryIssue` (upper-cased)
- `severity.score` rounded to nearest level (0–3) → `Severity` (NONE/MILD/MODERATE/MAJOR)
- `coaching_priority.choice` → `CoachingPriority`
- `should_speak.noul >= 0.5` → `should_speak`
- `overall_quality.score` rounded (0–3) → `OverallQuality` (POOR/FAIR/GOOD/EXCELLENT)
- `primary_issue.confidence` and `.probabilities` → `confidence` / `alternatives`
- `model` → `model_version`
- `evidence` is generated deterministically by our code from the metrics.

## Error / reliability handling

- 401/403 → `JevError` (auth) → fallback rules engine
- 429 → one retry, then fallback
- 5xx → one retry, then fallback
- network error / timeout → one retry, then fallback
- malformed response → `JevError` → fallback
- connect timeout 5 s, request timeout 20 s (configurable)
- API key is never logged

## Verification steps

`scripts/smoke_jev.py` (run `make smoke-jev`) sends one obvious TOO_FAST set and one GOOD set,
checks HTTP 200, expected structured fields, probability/confidence values, translation into
`MovementDecision`, model/version, and latency. Offline tests for parsing and fallback live in
`backend/tests/test_jev.py` and never make paid calls.
