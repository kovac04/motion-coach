"""Replay and plot a saved live-set debug capture.

    make live-debug FILE=data/debug/live-set-20261004-031000.csv

Re-runs the *same* segmentation on the saved filtered velocity and prints the
detected reps, then draws the projected velocity with start/stop thresholds and
REP START / TURNAROUND / REP END markers so false splits are obvious.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.motion.segmentation import DetectorParams, detect_reps  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def resolve(path: Path) -> Path:
    if path.exists():
        return path
    candidate = REPO_ROOT / path
    return candidate if candidate.exists() else path


def load(path: Path):
    t, g, raw, filt = [], [], [], []
    with path.open(newline="") as csv_file:
        for row in csv.DictReader(csv_file):
            t.append(float(row["timestamp"]))
            g.append([float(row["gx_raw"]), float(row["gy_raw"]), float(row["gz_raw"])])
            raw.append(float(row["projected_velocity_dps"]))
            filt.append(float(row["filtered_velocity_dps"]))
    return np.array(t), np.array(g), np.array(raw), np.array(filt)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--no-plot", action="store_true")
    args = parser.parse_args()
    path = resolve(args.file)
    if not path.exists():
        print(f"file not found: {args.file}")
        return 2

    meta_path = path.with_suffix(".json")
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    params = DetectorParams.from_dict(meta.get("params", {}))

    t, g, raw, filt = load(path)
    spans = detect_reps(t, filt, params)

    print(f"file: {path.name}  samples={len(t)}  duration={t[-1]:.2f}s")
    print(f"recorded rep_count={meta.get('rep_count')}  replayed rep_count={len(spans)}")
    print(f"start_dps={params.start_dps} stop_dps={params.stop_dps} "
          f"min_rep_ms={params.min_rep_ms} min_exc={params.min_excursion_deg} "
          f"min_phase={params.min_phase_deg}")
    print(f"  {'rep':>3} {'start':>7} {'turn':>7} {'end':>7} {'dur_ms':>8} "
          f"{'exc_deg':>8} {'peak_dps':>9} {'phA':>7} {'phB':>7}")
    for i, s in enumerate(spans, start=1):
        print(f"  {i:>3} {t[s.start]:>7.2f} {t[s.turnaround]:>7.2f} {t[s.end]:>7.2f} "
              f"{s.duration_ms:>8.0f} {s.excursion_deg:>8.1f} {s.peak_velocity_dps:>9.0f} "
              f"{s.phase_a_deg:>7.1f} {s.phase_b_deg:>7.1f}")

    if not args.no_plot:
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(15, 6))
        ax.plot(t, raw, color="tab:blue", linewidth=0.7, alpha=0.35, label="projected (raw)")
        ax.plot(t, filt, color="tab:blue", linewidth=1.6, label="projected (filtered)")
        ax.axhline(params.start_dps, color="gray", linestyle="--", linewidth=0.8, label="+-start")
        ax.axhline(-params.start_dps, color="gray", linestyle="--", linewidth=0.8)
        ax.axhline(params.stop_dps, color="silver", linestyle=":", linewidth=0.8)
        ax.axhline(-params.stop_dps, color="silver", linestyle=":", linewidth=0.8)
        for s in spans:
            ax.axvline(t[s.start], color="tab:green", alpha=0.75)
            ax.axvline(t[s.turnaround], color="gold", alpha=0.95)
            ax.axvline(t[s.end], color="tab:red", alpha=0.75)
        ax.set_xlabel("time (s)")
        ax.set_ylabel("projected angular velocity (dps)")
        ax.set_title(f"{path.name} — {len(spans)} reps (green=start, gold=turn, red=end)")
        ax.grid(True, alpha=0.2)
        ax.legend(loc="upper right", fontsize=8)
        fig.tight_layout()
        out = path.with_suffix(".png")
        fig.savefig(out, dpi=120)
        plt.close(fig)
        print(f"plot -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
