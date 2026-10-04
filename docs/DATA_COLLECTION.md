# Data Collection

Goal: record **real signal data** for later inspection. No rep detection, thresholds,
or ML happen here — we only capture raw motion and look at it.

## Setup

1. Power the wearable (power bank is fine) and confirm it advertises:
   ```sh
   make imu-monitor        # expect "Connected ... ~50 Hz ... gaps=0"; Ctrl-C to stop
   ```
2. Only **one** process may own the BLE connection at a time. Stop `imu-monitor` (and the
   backend if `SENSOR_ENABLED=true`) before recording.
3. Keep the sensor mounting/orientation consistent across a session.

## Recording

```sh
make imu-record NAME=good-01          # runs until Ctrl-C, then prints a summary
make imu-record NAME=good-01 SECONDS=15   # optional: auto-stop after 15 s
```

Files are written to `data/recordings/<NAME>.csv` (gitignored). Each row preserves the raw
axes, device timestamp, sequence number, and host arrival time.

Stop with **Ctrl-C**; the summary reports samples, duration, measured Hz, sequence gaps,
and malformed packets, and the file is flushed.

## Protocols

Do each of these, sitting/standing the same way, sensor mounted the same way. Stay still at
the start so we always have a resting baseline.

| Dataset | Sequence |
| --- | --- |
| `good-01` | 2 s still → **5 controlled reps** → 2–3 s still |
| `good-02` | same as `good-01` (repeat for a second controlled set) |
| `fast-01` | 2 s still → **5 clearly faster reps** → 2–3 s still |
| `slow-01` | 2 s still → **5 clearly slower reps** → 2–3 s still |
| `short-rom-01` | 2 s still → **5 clearly shortened reps** → 2–3 s still |
| `mixed-01` | 2 s still → a few normal reps → **1–2 deliberately altered reps** → still at end |

Record 2–3 takes of each so we can compare. Use the exact suffix (`-01`, `-02`) so files
sort predictably.

## Inspect a recording

```sh
make imu-analyze FILE=data/recordings/good-01.csv
make imu-plot FILE=data/recordings/good-01.csv
make imu-plot FILE=data/recordings/good-01.csv SMOOTH=5     # optional visualization overlay
```

- `imu-analyze` prints objective facts only (sample count, duration, measured Hz, per-axis
  min/max, clipping %, resting noise from the first ~2 s, dominant gyro/accel axis by
  variance, and gyro/accel magnitude ranges). It does **not** classify movement.
- `imu-plot` draws ax/ay/az, gx/gy/gz, |accel|, and |gyro| against time in seconds. Smoothing
  (moving average) is drawn **on top of** the raw signal and is visualization-only; raw CSV
  values are never modified.

## Notes

- Ranges are ±4 g and ±1000 dps. If a dataset clips, `imu-analyze` will show it.
- Do not compare across different sensor orientations without noting it.
- Commit only code/docs. Recordings stay local unless we deliberately export them.
