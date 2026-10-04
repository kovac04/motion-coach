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

The "return to initial direction" branch is what lets **continuous reps** split
at the bottom turnaround instead of merging when there is no full stop.

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

- **Calibration** (`start`/`finish`): the UI shows a 3-2-1 countdown, then captures;
  the backend detects reps as they happen and **auto-finishes at 5 valid reps**,
  builds and saves the profile. No blind fixed-duration capture, no pre-countdown data.
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

## Honest limitations

- `rom_deg` is a relative rotation estimate, not joint angle.
- Similarity compares shape; tempo/range are separate metrics.
- Resting-noise estimation assumes at least one quiet window exists.
- Calibration is per exercise and per mounting; recalibrate if the mount changes.
