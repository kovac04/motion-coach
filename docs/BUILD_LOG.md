# Build Log — StormHacks 2026

## Provenance

- Repository created during the **StormHacks 2026 hacking period**.
- This is a brand-new directory and a brand-new Git repository; no prior project
  source, history, or scaffold was copied into it.
- The IMU/hardware ingestion pipeline referenced in the concept is **not** part of this
  repository yet and was not imported from anywhere.

## Initial timestamps (from `date` / `date -u` at project creation)

- Local time: `Sat  3 Oct 2026 14:01:36 PDT`
- UTC time:   `Sat  3 Oct 2026 21:01:36 UTC`

## Milestones

- Initial commit `1dccc45` — "Initialize StormHacks 2026 project".
- `a09fd99` — "Add backend schemas and mock coaching pipeline". 32 backend tests passing
  under Python 3.12. Mock pipeline verified end-to-end with zero API credentials.
- `7667bbb` — "Add interactive demo dashboard". Vite production build and oxlint pass;
  dev server proxy to the backend verified.
- `f78eac7` — "Add provider fallbacks, docs, and smoke tests".
- `e35ed3e` — "Add isolated offline pipeline smoke test".
- Jev provider contract verified from the official TypeSafe docs
  (https://docs.typesafe.ai) and the real adapter implemented
  (`POST https://api.typesafe.ai/v1/systemone`, model `jev-latest`).
  Recorded in `docs/JEV_PROVIDER.md`. Adapter parsing and fail-soft covered by
  offline tests; no paid calls are made by `pytest`.
- Real provider smoke tests run manually:
  - Gemini: `gemini-flash-lite-latest`, structured output, ~1.2 s.
  - ElevenLabs: `eleven_turbo_v2_5`, 56 KB MP3 returned.
  - Jev: `jev-1.13.0` — TOO_FAST (severity MODERATE, confidence 0.99, 244 ms) and
    GOOD (quality EXCELLENT, confidence 0.91, 169 ms).
- Full synthetic pipeline verified through the running API with all three real
  providers: set → Jev (TOO_FAST, 0.98, 170 ms) → Gemini cue (1.3 s) → ElevenLabs
  `audio/mpeg` (91 KB). No raw sensor data was used.

## Notes

- No timestamps were altered, backdated, or fabricated.
- Later entries below are appended as milestones are completed. Only verifiable facts
  are recorded here.
