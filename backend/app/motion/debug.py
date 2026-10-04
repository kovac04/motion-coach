"""Persist a finalized live set for offline diagnosis.

Writes a CSV of the raw gyro + projected/filtered velocity and a JSON sidecar with
the profile, thresholds, and detected rep boundaries. Used to debug segmentation
from real live data. Captures are gitignored.
"""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path

import numpy as np

from app.motion.calibration import CalibrationProfile
from app.motion.live import CompletedSet
from app.motion.segmentation import DetectorParams

REPO_ROOT = Path(__file__).resolve().parents[3]
DEBUG_DIR = REPO_ROOT / "data" / "debug"

CSV_HEADER = [
    "timestamp",
    "gx_raw",
    "gy_raw",
    "gz_raw",
    "projected_velocity_dps",
    "filtered_velocity_dps",
]


def save_live_set(completed: CompletedSet, profile: CalibrationProfile,
                  directory: Path = DEBUG_DIR, tag: str = "") -> dict[str, str]:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    name = f"live-set-{stamp}{('-' + tag) if tag else ''}"
    csv_path = directory / f"{name}.csv"
    json_path = directory / f"{name}.json"

    t = completed.t if completed.t is not None else np.array([])
    g = completed.gyro_raw if completed.gyro_raw is not None else np.zeros((len(t), 3))
    raw = completed.velocity_raw_dps if completed.velocity_raw_dps is not None else np.zeros(len(t))
    filt = completed.velocity_filtered_dps if completed.velocity_filtered_dps is not None else np.zeros(len(t))

    with csv_path.open("w", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(CSV_HEADER)
        for i in range(len(t)):
            writer.writerow([f"{t[i]:.4f}", int(round(g[i, 0])), int(round(g[i, 1])),
                             int(round(g[i, 2])), f"{raw[i]:.3f}", f"{filt[i]:.3f}"])

    meta = {
        "exercise_id": profile.exercise_id,
        "axis": [float(x) for x in profile.axis],
        "bias": [float(x) for x in profile.bias],
        "noise_dps": profile.noise_dps,
        "axis_variance_fraction": profile.axis_variance_fraction,
        "params": profile.params,
        "start_dps": DetectorParams.from_dict(profile.params).start_dps,
        "stop_dps": DetectorParams.from_dict(profile.params).stop_dps,
        "reference_duration_ms": profile.reference_duration_ms,
        "reference_excursion_deg": profile.reference_excursion_deg,
        "reference_peak_dps": profile.reference_peak_dps,
        "rep_count": completed.rep_count,
        "rejected": completed.rejected,
        "reps": [
            {
                "start": s.start, "turnaround": s.turnaround, "end": s.end,
                "duration_ms": s.duration_ms, "excursion_deg": s.excursion_deg,
                "peak_velocity_dps": s.peak_velocity_dps,
                "phase_a_deg": s.phase_a_deg, "phase_b_deg": s.phase_b_deg,
            }
            for s in completed.spans
        ],
    }
    json_path.write_text(json.dumps(meta, indent=2))
    return {"csv": str(csv_path), "json": str(json_path)}
