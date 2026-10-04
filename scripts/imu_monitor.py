"""Live BLE IMU monitor. Run with `make imu-monitor`.

Prints one line per second: device, packet count, effective Hz, last raw axes,
and sequence gaps. Never dumps 50 lines/second.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.sensors import BleImuClient, DeviceNotFoundError, SequenceTracker  # noqa: E402


async def run(device_name: str) -> int:
    client = BleImuClient(device_name=device_name)
    tracker = SequenceTracker()

    print(f"Scanning for {device_name!r} ...")
    window_count = 0
    window_start = time.monotonic()
    last_report = window_start
    latest = None

    try:
        async for sample in client.stream():
            tracker.observe(sample.sequence)
            latest = sample
            window_count += 1

            now = time.monotonic()
            if now - last_report >= 1.0:
                elapsed = now - window_start
                hz = window_count / elapsed if elapsed > 0 else 0.0
                assert latest is not None
                print(
                    f"{client.address} | ~{hz:5.1f} Hz | seq={latest.sequence:5d} | "
                    f"acc=({latest.ax:6d},{latest.ay:6d},{latest.az:6d}) | "
                    f"gyro=({latest.gx:6d},{latest.gy:6d},{latest.gz:6d}) | "
                    f"gaps={tracker.gaps}"
                )
                window_count = 0
                window_start = now
                last_report = now
    except DeviceNotFoundError as exc:
        print(f"NOT FOUND: {exc}")
        print("Is the wearable powered and advertising MotionCoach-IMU?")
        return 2
    except KeyboardInterrupt:
        pass

    print(f"\nDisconnected. total_gaps={tracker.gaps} missing={tracker.missing} malformed={client.malformed}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="MotionCoach-IMU")
    return asyncio.run(run(parser.parse_args().name))


if __name__ == "__main__":
    raise SystemExit(main())
