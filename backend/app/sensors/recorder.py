"""CSV recording of a BLE IMU stream. Pure consumer of an async sample iterator."""

from __future__ import annotations

import asyncio
import csv
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from .packet import ImuSample, SequenceTracker

CSV_HEADER = [
    "host_timestamp",
    "sequence",
    "device_timestamp_ms",
    "ax_raw",
    "ay_raw",
    "az_raw",
    "gx_raw",
    "gy_raw",
    "gz_raw",
]


@dataclass
class RecordingStats:
    samples: int
    duration_s: float
    effective_hz: float
    sequence_gaps: int
    missing_samples: int
    malformed: int
    path: Path


async def record_stream(
    stream: AsyncIterator[ImuSample],
    path: Path,
    stop_event: asyncio.Event,
    malformed: int = 0,
) -> RecordingStats:
    """Consume `stream` into `path` until Ctrl-C sets `stop_event`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tracker = SequenceTracker()
    count = 0
    start = time.monotonic()

    # Pump the stream from a background task. This keeps the async generator
    # (including its BLE scan/connect phase) from being cancelled by the
    # consumer's short wait, while still letting Ctrl-C stop promptly.
    queue: asyncio.Queue[ImuSample | None] = asyncio.Queue(maxsize=4096)

    async def pump() -> None:
        try:
            async for sample in stream:
                await queue.put(sample)
        finally:
            await queue.put(None)  # sentinel: stream ended

    pump_task = asyncio.create_task(pump())

    with path.open("w", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(CSV_HEADER)
        try:
            while not stop_event.is_set():
                try:
                    sample = await asyncio.wait_for(queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    if pump_task.done():
                        break
                    continue
                if sample is None:
                    break
                tracker.observe(sample.sequence)
                writer.writerow(
                    [
                        f"{sample.host_timestamp:.6f}" if sample.host_timestamp else "",
                        sample.sequence,
                        sample.timestamp_ms,
                        sample.ax,
                        sample.ay,
                        sample.az,
                        sample.gx,
                        sample.gy,
                        sample.gz,
                    ]
                )
                count += 1
                if count % 50 == 0:
                    csv_file.flush()
        finally:
            csv_file.flush()
            pump_task.cancel()
            try:
                await pump_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - teardown
                pass

    duration = time.monotonic() - start
    return RecordingStats(
        samples=count,
        duration_s=duration,
        effective_hz=count / duration if duration > 0 else 0.0,
        sequence_gaps=tracker.gaps,
        missing_samples=tracker.missing,
        malformed=malformed,
        path=path,
    )
