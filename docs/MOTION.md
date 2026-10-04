# Motion Analysis Pipeline

Deterministic, exercise-agnostic analysis of wrist IMU motion. No ML. It turns
raw gyro samples into a single signed angular-velocity signal, detects reps, and
produces the existing `RepMetrics` / `SetMetrics`.

```
raw gyro (gx,gy,gz)          backend/app/sensors
   -> quiet-window rest + PCA rotation axis        app/motion/signal.py
   -> signed projected angular velocity (dps)
   -> light centered moving average (window 5 ~= 0.1 s)
   -> rep state machine (hysteresis + duration/excursion gates)   app/motion/segmentation.py
   -> per-rep metrics + waveform similarity        app/motion/calibration.py, pipeline.py
   -> RepMetrics / SetMetrics (existing models)    app/models/metrics.py
```

## Why PCA and not a fixed axis

The dominant physical gyro axis changes with mounting/orientation. PCA over the
clearly-moving samples finds the principal rotation direction, so the pipeline
never assumes gz or any fixed axis. On the real curl recordings PC1 explains
91–98% of the movement variance.

The PCA sign is arbitrary. The axis is canonicalized (largest component
positive) and per-rep waveforms are canonicalized (largest sample positive)
before comparison, so "which way is positive" never matters.

## Resting baseline (not "first 2 seconds")

Recordings may be moving before the assumed still period. Instead we slide a
0.5–1.0 s window over the whole recording and choose the window with the lowest
residual gyro RMS. That window gives the gyro bias and the resting noise scale,
which seeds the detector thresholds. If a recording has no still window, the
noise floor saturates the threshold at a safe cap (40 dps) and segmentation
still works.

## Rep state machine

```
IDLE --|v|>start (debounced)--> PHASE_A
PHASE_A --reversal (v opposite, |v|>start)--> PHASE_B
PHASE_B --v returns to initial direction (>start)--> rep emitted, next rep begins
PHASE_B --near rest for stop_debounce, or set ends--> rep emitted -> IDLE
```

Gates: `min_rep_ms`, `max_rep_ms`, `min_excursion_deg`, `min_phase_deg` (both
directions must contribute), start/stop hysteresis, start/stop debounce, and a
refractory interval. Thresholds are derived from resting noise and the
calibration reference, not hard-coded constants.

For continuous reps (no full stop), the rep closes when motion returns to the
starting direction **and** the integrated angle is genuinely back near the start
(`|angle| <= 0.35 * |turnaround angle|`), sustained for a debounce, and at least
`min_turn_gap_ms` after the turnaround. This is what prevents a brief rebound /
momentum blip from splitting one physical rep into several — a naive
"velocity changed sign" rule over-segments fast reps. `min_turn_gap_ms` is derived
from the reference tempo (≈8% of reference duration), not a raw constant.

Debugging: set `DEBUG_SAVE_LIVE_SETS=true` to persist each finalized set to
`data/debug/live-set-*.csv` (raw gyro + projected/filtered velocity) with a JSON
sidecar (axis, bias, thresholds, rep boundaries), then
`make live-debug FILE=data/debug/live-set-….csv` to replay the exact trace and plot
the signal with start/turnaround/end markers.

## Angular excursion (ROM proxy)

Velocity is integrated to an angle per rep (trapezoidal, reset at each rep
start, limiting drift). `rom_deg` is the peak-to-peak angle of that rep. This is
a relative IMU-derived rotation estimate, **not** a laboratory joint angle;
mapped internally to `rom_deg` for contract compatibility.

## Waveform similarity

Each rep's projected-velocity waveform is resampled to 100 points, sign-
canonicalized, and amplitude-normalized. Similarity is the Pearson correlation
against the reference waveform (mean of calibration reps), clamped to 0..1.
No DTW (ordinary time-normalized correlation behaves well on the recordings).

## Calibration

`make imu-calibrate` builds `data/profiles/<exercise>.json` from the good
recordings: PCA axis, bias, noise, reference duration/excursion/peak velocity
(median + spread), reference waveform, and detector parameters derived from the
data. Each recording is self-calibrated for its own axis so different mounts do
not corrupt the pooled reference statistics.

## Offline tools

```sh
make imu-calibrate
make imu-segment FILE=data/recordings/curl-good-01.csv
make imu-segment ALL=1
```

`imu-segment` prints each rep (start, turnaround, end, duration, excursion, peak
velocity, similarity) and writes a debug plot
(`data/recordings/<name>-segments.png`) showing the projected signal, thresholds,
and rep boundaries, so boundaries can be verified visually.

## Live pipeline (explicit control for the demo)

`LiveMotionService` subscribes to the single `SensorRuntime` BLE owner (no second
connection). The set lifecycle is explicit and driven by the UI:

```
NO_PROFILE -> CALIBRATING -> READY -> SET_ACTIVE -> ANALYZING -> COACHING -> READY
```

- **Calibration phases** (`start`/`finish`): 3-2-1 countdown → **HOLD STILL** (the
  backend requires ~0.75 s of genuinely quiet gyro, judged by residual variance, and
  captures the resting baseline) → **REFERENCE REPS** (buffer cleared at the transition;
  detects reps and auto-finishes at 5) → **COMPLETE**. If no quiet baseline appears within
  ~15 s it fails clearly so calibration can be retried. This keeps contaminated baselines
  (e.g. ~70 dps noise) out of the profile; a good run measures ~1–3 dps.
- **Latency budgets**: `LIVE_JEV_TIMEOUT_S` (default 2 s) and `LIVE_GEMINI_TIMEOUT_S`
  (default 2 s). If a real provider exceeds its budget the pipeline immediately uses the
  deterministic fallback/template (`JEV TIMEOUT → FALLBACK`, `GEMINI TIMEOUT → TEMPLATE`)
  so the spoken cue never waits on the network. The provider actually used is logged and
  shown in the UI debug panel.
- **Start Set** clears the buffer; movement before it is never part of a set.
- **Finish Set** finalizes immediately. A configurable idle auto-finish (~3 s) is an
  optional backup; manual finish overrides it.
- Exactly **one** coaching event per completed set; a new set stops any in-flight audio.
  Sets with too few valid reps return `SET_REJECTED` instead of reaching Jev.
- Latency is measured and surfaced: metrics / Jev / Gemini (backend) and ElevenLabs
  (via the `X-TTS-Ms` response header) plus total-to-audio (browser).

The browser dashboard has two separated tabs — **LIVE WEARABLE** (primary) and
**SYNTHETIC DEMO** — so synthetic scenarios can never be mistaken for a live set.
Live results populate the main Set/Decision/Coach panels with `source=live` logged.

## Multiple exercises

Each exercise has its own calibration profile (`data/profiles/<exercise_id>.json`) and
its own PCA axis — nothing is shared. `POST /api/motion/exercise` switches the active
exercise and auto-loads its saved profile; switching is rejected during an active set or
calibration. Live-selectable exercises are limited to clear cyclical rotational wrist
motion: bicep curl, lateral raise, triceps extension, front raise. Bench press is
deliberately excluded (translation with little orientation change makes gyro excursion
untrustworthy). This proves "exercise-specific calibration lets one generic pipeline adapt",
not "any exercise works".

## Decision layer: deterministic candidates, bounded Jev

Deterministic code (`app/motion/assessment.py`) decides WHICH deviations exist,
using **median** (robust) per-rep ratios and a **majority rule** (a single odd rep
cannot classify a set) with centralized bands:
tempo `0.85–1.15`, ROM `0.90–1.15`, consistency `>= 0.85`. It produces
`candidate_issues`. Similarity is evidence only and never creates a candidate.

Jev then only chooses WHICH valid deviation to coach:
- no candidates → deterministic GOOD, `should_speak=false`, **Jev is not called**;
- one candidate → primary issue fixed, Jev is asked only for severity;
- multiple candidates → Jev chooses among the supplied candidates only and can never
  return an issue the facts did not establish.

`rom_ratio` is *movement excursion relative to the personal reference*, not true joint
ROM. Fast reps overshoot the integrated excursion, so an elevated `rom_ratio` during a
clearly-fast set is not emitted as `EXCESSIVE_ROM`.

## When coaching is spoken

The decision's `should_speak` is the single source of truth. A GOOD set with no meaningful
deviation returns `should_speak=false`: the UI still shows the result and positive text, but
ElevenLabs is not called. Only a meaningful actionable deviation requests speech. This
applies to both the Jev question and the deterministic fallback (`should_speak = severity != NONE`).

## Honest limitations

- `rom_deg` is a relative rotation estimate, not joint angle.
- Similarity compares shape; tempo/range are separate metrics.
- Resting-noise estimation assumes at least one quiet window exists.
- Calibration is per exercise and per mounting; recalibrate if the mount changes.
