"""Live BLE IMU monitor. Run with `make imu-monitor`.

Runs until Ctrl-C. Owns a single BLE connection via ``SensorRuntime``,
reconnects automatically, prints a compact status line about once per second,
and disconnects cleanly on Ctrl-C.
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
import time
from contextlib import suppress
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.sensors.runtime import SensorRuntime  # noqa: E402


async def run(device_name: str, retry_delay: float) -> int:
    runtime = SensorRuntime(device_name=device_name, retry_delay=retry_delay)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    print(f"Scanning for {device_name!r} ... (Ctrl-C to stop)")
    await runtime.start()

    was_connected = False
    last_report = 0.0
    while not stop.is_set():
        await asyncio.sleep(0.2)
        status = runtime.status()
        connected = status["connected"]

        if connected and not was_connected:
            print(f"Connected to {status['address'] or device_name}")
        elif not connected and was_connected:
            print("Disconnected; rescanning ...")
        was_connected = connected

        now = time.monotonic()
        if now - last_report >= 1.0:
            sample = status["sample"]
            if sample:
                print(
                    f"{status['address']} | ~{status['sample_rate_hz']:5.1f} Hz | "
                    f"seq={sample['sequence']:5d} | "
                    f"acc=({sample['ax']:6d},{sample['ay']:6d},{sample['az']:6d}) | "
                    f"gyro=({sample['gx']:6d},{sample['gy']:6d},{sample['gz']:6d}) | "
                    f"gaps={status['sequence_gaps']}"
                )
            else:
                print("Waiting for MotionCoach-IMU ...")
            last_report = now

    await runtime.stop()
    status = runtime.status()
    print(
        f"\nStopped. gaps={status['sequence_gaps']} "
        f"missing={status['missing_samples']} malformed={status['malformed']}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="MotionCoach-IMU")
    parser.add_argument("--retry-delay", type=float, default=2.0)
    args = parser.parse_args()
    try:
        return asyncio.run(run(args.name, args.retry_delay))
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
