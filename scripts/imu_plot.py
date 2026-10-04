"""Plot a recorded IMU CSV. Run with `make imu-plot FILE=data/recordings/good-01.csv`.

Plots the six raw axes plus derived acceleration and gyro magnitude.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


def load(path: Path) -> dict[str, list[float]]:
    columns: dict[str, list[float]] = {}
    with path.open(newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for key in ("host_timestamp", "ax_raw", "ay_raw", "az_raw", "gx_raw", "gy_raw", "gz_raw"):
            columns[key] = []
        for row in reader:
            for key in columns:
                raw = row.get(key, "")
                columns[key].append(float(raw) if raw not in ("", None) else float("nan"))
    columns["accel_mag"] = [
        math.sqrt(a * a + b * b + c * c)
        for a, b, c in zip(columns["ax_raw"], columns["ay_raw"], columns["az_raw"])
    ]
    columns["gyro_mag"] = [
        math.sqrt(a * a + b * b + c * c)
        for a, b, c in zip(columns["gx_raw"], columns["gy_raw"], columns["gz_raw"])
    ]
    return columns


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--save", type=Path, default=None, help="save PNG instead of showing")
    args = parser.parse_args()

    if not args.file.exists():
        print(f"file not found: {args.file}")
        return 2

    import matplotlib.pyplot as plt

    data = load(args.file)
    t = data["host_timestamp"]
    if all(math.isnan(v) for v in t):
        t = list(range(len(data["ax_raw"])))

    fig, axes = plt.subplots(4, 1, sharex=True, figsize=(12, 10))
    fig.suptitle(f"IMU recording: {args.file.name}  ({len(t)} samples)")

    for axis in ("ax_raw", "ay_raw", "az_raw"):
        axes[0].plot(t, data[axis], label=axis)
    axes[0].set_ylabel("accel raw")
    axes[0].legend(loc="upper right", ncol=3)

    for axis in ("gx_raw", "gy_raw", "gz_raw"):
        axes[1].plot(t, data[axis], label=axis)
    axes[1].set_ylabel("gyro raw")
    axes[1].legend(loc="upper right", ncol=3)

    axes[2].plot(t, data["accel_mag"], color="tab:blue")
    axes[2].set_ylabel("|accel|")

    axes[3].plot(t, data["gyro_mag"], color="tab:red")
    axes[3].set_ylabel("|gyro|")
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
