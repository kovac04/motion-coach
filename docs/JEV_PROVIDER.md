# Jev Provider Verification

**Status: NOT VERIFIED — the real adapter is intentionally not implemented yet.**

The project rules forbid guessing the Jev/System-One API. Before writing the real
adapter we must confirm the contract from the provider associated with *this* account.

## How the adapter is wired

`backend/app/services/jev.py` selects the decision provider from `DECISION_PROVIDER`:

- `mock` — scenario-aware fake decisions (default, no credentials)
- `fallback` — deterministic rules engine
- `jev` — real provider (currently raises `JevNotVerifiedError` and **fails soft** to the
  rules engine, so the pipeline keeps working)

Environment variables (see `.env.example`):

```
JEV_API_KEY=
JEV_BASE_URL=
JEV_MODEL=
```

If the real provider uses differently named credentials, the mapping must be documented
here and implemented in `config.py`. Secrets stay server-side only.

## What must be confirmed before implementing

Fill these in from the provider's **current official documentation** and/or account
dashboard. Do not rely on model memory or third-party blog posts.

- [ ] Provider / company / domain (exact)
- [ ] Base URL
- [ ] Endpoint path (e.g. `/v1/...`)
- [ ] Auth header format (Bearer? `x-api-key`?)
- [ ] API key env var name used by the provider (mapping to `JEV_API_KEY`)
- [ ] Model identifier(s) (mapping to `JEV_MODEL`)
- [ ] Request schema (state + typed questions) — exact JSON
- [ ] Question types supported (`choice`, `score`, `noul`/yes-no probability, ...)
- [ ] Response schema — where answers/probabilities live
- [ ] Rate limits
- [ ] Error format / status codes
- [ ] Pricing implications per call

## Verification test (one cheap call)

Once verified, `scripts/smoke_jev.py` sends a single obvious **TOO_FAST** state and checks:

- HTTP 200
- structured answer fields present
- probability/confidence values parse
- translation into our `MovementDecision`
- model/version if returned
- latency (via `time.perf_counter`)

Then run one **GOOD** state. Do not burn credits experimenting randomly.

## Translation rule

The provider's raw response must be translated into our internal `MovementDecision`
(`backend/app/models/decisions.py`). The rest of the application never sees provider
wire formats.
