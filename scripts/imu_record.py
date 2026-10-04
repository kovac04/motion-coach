"""Record a continuous BLE IMU stream to CSV. Run with `make imu-record NAME=good-01`.

Ctrl-C stops cleanly and prints packet count, effective Hz, gaps, and duration.
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.sensors import BleImuClient, DeviceNotFoundError, record_stream  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = REPO_ROOT / "data" / "recordings"


async def run(name: str, seconds: float | None, output_dir: Path, device_name: str) -> int:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:  # non-POSIX
            pass

    if seconds is not None:
        loop.call_later(seconds, stop_event.set)

    client = BleImuClient(device_name=device_name)
    path = output_dir / f"{name}.csv"

    print(f"Recording -> {path}")
    if seconds is None:
        print("Press Ctrl-C to stop.")
    else:
        print(f"Recording for {seconds:.1f}s ...")

    try:
        stats = await record_stream(client.stream(), path, stop_event)
    except DeviceNotFoundError as exc:
        print(f"NOT FOUND: {exc}")
        return 2

    stats.malformed = client.malformed
    print(
        f"\nSaved {stats.samples} samples in {stats.duration_s:.1f}s "
        f"(~{stats.effective_hz:.1f} Hz) -> {stats.path}"
    )
    print(
        f"sequence_gaps={stats.sequence_gaps} missing={stats.missing_samples} "
        f"malformed={stats.malformed}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="e.g. good-01")
    parser.add_argument("--seconds", type=float, default=None, help="auto-stop after N seconds")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--device-name", default="MotionCoach-IMU")
    args = parser.parse_args()
    try:
        return asyncio.run(run(args.name, args.seconds, args.output_dir, args.device_name))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
