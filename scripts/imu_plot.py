"""Plot one recording. Run with `make imu-plot FILE=data/recordings/good-01.csv`.

Produces clear plots for the six raw axes plus acceleration and gyro magnitude,
with time in seconds. Optional centered smoothing is for visualization only and
is drawn on top of the raw signal, never replacing it.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.sensors.analysis import (  # noqa: E402
    ACCEL_AXES,
    GYRO_AXES,
    load_recording_csv,
    magnitudes,
    moving_average,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def resolve(path: Path) -> Path:
    """Accept a path relative to cwd or to the repo root (so `make FILE=...` works)."""
    if path.exists():
        return path
    candidate = REPO_ROOT / path
    return candidate if candidate.exists() else path


def time_axis(rows: list[dict[str, float]]) -> list[float]:
    stamps = [row["host_timestamp"] for row in rows if not math.isnan(row["host_timestamp"])]
    if len(stamps) == len(rows) and len(stamps) >= 2:
        t0 = stamps[0]
        return [stamp - t0 for stamp in stamps]
    # Fallback: sample index if host timestamps are missing.
    return list(range(len(rows)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--save", type=Path, default=None, help="save PNG instead of showing")
    parser.add_argument("--smooth", type=int, default=0,
                        help="centered moving-average window for a visualization overlay")
    args = parser.parse_args()
    args.file = resolve(args.file)

    if not args.file.exists():
        print(f"file not found: {args.file}")
        return 2

    rows = load_recording_csv(args.file)
    if not rows:
        print(f"no usable samples in {args.file}")
        return 2

    import matplotlib.pyplot as plt

    t = time_axis(rows)
    smoothed = args.smooth > 1
    series = {axis: [row[axis] for row in rows] for axis in ACCEL_AXES + GYRO_AXES}
    accel_mag = magnitudes(rows, ACCEL_AXES)
    gyro_mag = magnitudes(rows, GYRO_AXES)

    fig, axes = plt.subplots(4, 1, sharex=True, figsize=(13, 11))
    title = f"{args.file.name}  ({len(rows)} samples)"
    if smoothed:
        title += f"  [raw + moving average window={args.smooth}]"
    fig.suptitle(title)

    axis_colors = ["tab:blue", "tab:orange", "tab:green"]

    def plot_group(ax, keys, values_map, ylabel):
        for key, color in zip(keys, axis_colors):
            raw = values_map[key]
            ax.plot(t, raw, color=color, linewidth=0.8, alpha=0.35,
                    label=f"{key} raw" if smoothed else f"{key}")
            if smoothed:
                ax.plot(t, moving_average(raw, args.smooth), color=color, linewidth=1.8,
                        label=f"{key} smoothed")
        ax.set_ylabel(ylabel)
        ax.legend(loc="upper right", ncol=2, fontsize=8)
        ax.grid(True, alpha=0.2)

    def plot_scalar(ax, values, ylabel, color):
        ax.plot(t, values, color=color, linewidth=0.8, alpha=0.35, label="raw" if smoothed else ylabel)
        if smoothed:
            ax.plot(t, moving_average(values, args.smooth), color=color, linewidth=1.8,
                    label="smoothed")
        ax.set_ylabel(ylabel)
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(True, alpha=0.2)

    plot_group(axes[0], ACCEL_AXES, series, "accel raw")
    plot_group(axes[1], GYRO_AXES, series, "gyro raw")
    plot_scalar(axes[2], accel_mag, "|accel|", "tab:blue")
    plot_scalar(axes[3], gyro_mag, "|gyro|", "tab:red")
    axes[3].set_xlabel("time (s)")

    fig.tight_layout()
    if args.save:
        fig.savefig(args.save, dpi=120)
        print(f"saved {args.save}")
    else:
        plt.show()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
