"""Single-owner live IMU runtime.

Exactly one component in a process owns the BLE connection. It keeps a
reconnecting sample stream alive in the background and maintains a bounded
in-memory ring buffer plus connection statistics for the API/UI.

This layer is deliberately below the application pipeline: it only produces
`ImuSample` values. No rep detection, metrics, or LLM logic lives here.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from contextlib import suppress
from dataclasses import dataclass

from .ble_client import BleImuClient, reconnecting_stream
from .packet import ImuSample, SequenceTracker

logger = logging.getLogger(__name__)


@dataclass
class SensorStatus:
    connected: bool = False
    device_name: str = "MotionCoach-IMU"
    address: str | None = None
    sample_rate_hz: float = 0.0
    sequence_gaps: int = 0
    missing_samples: int = 0
    malformed: int = 0
    connections: int = 0
    last_error: str | None = None
    last_sample: ImuSample | None = None
    last_seen: float | None = None

    def to_dict(self) -> dict:
        sample = self.last_sample
        return {
            "connected": self.connected,
            "device_name": self.device_name,
            "address": self.address,
            "sample_rate_hz": round(self.sample_rate_hz, 1),
            "sequence_gaps": self.sequence_gaps,
            "missing_samples": self.missing_samples,
            "malformed": self.malformed,
            "connections": self.connections,
            "last_error": self.last_error,
            "last_seen": self.last_seen,
            "sample": None
            if sample is None
            else {
                "sequence": sample.sequence,
                "timestamp_ms": sample.timestamp_ms,
                "ax": sample.ax,
                "ay": sample.ay,
                "az": sample.az,
                "gx": sample.gx,
                "gy": sample.gy,
                "gz": sample.gz,
                "accel_magnitude": round(sample.accel_magnitude, 1),
                "gyro_magnitude": round(sample.gyro_magnitude, 1),
            },
        }


@dataclass
class SensorRuntime:
    device_name: str = "MotionCoach-IMU"
    buffer_seconds: float = 6.0
    max_rate_hz: int = 120
    retry_delay: float = 2.0

    def __post_init__(self) -> None:
        self._client = BleImuClient(device_name=self.device_name)
        self._tracker = SequenceTracker()
        self._samples: deque[ImuSample] = deque(maxlen=int(self.buffer_seconds * self.max_rate_hz))
        self._arrivals: deque[float] = deque(maxlen=self.max_rate_hz * 3)
        self._status = SensorStatus(device_name=self.device_name)
        self._task: asyncio.Task | None = None

    # --- lifecycle ---------------------------------------------------------
    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._pump(), name="imu-sensor-runtime")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        self._status.connected = False

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    # --- data --------------------------------------------------------------
    async def _pump(self) -> None:
        async for sample in reconnecting_stream(self._client, self._on_event, self.retry_delay):
            self._on_sample(sample)

    def _on_event(self, state: str, detail: str | None) -> None:
        if state == "connected":
            self._status.connected = True
            self._status.address = self._client.address
            self._status.connections += 1
            self._status.last_error = None
        else:
            self._status.connected = False
            if detail:
                self._status.last_error = detail

    def _on_sample(self, sample: ImuSample) -> None:
        self._tracker.observe(sample.sequence)
        self._samples.append(sample)
        self._arrivals.append(time.monotonic())
        self._status.connected = True
        self._status.last_sample = sample
        self._status.last_seen = time.monotonic()
        self._status.sequence_gaps = self._tracker.gaps
        self._status.missing_samples = self._tracker.missing
        self._status.malformed = self._client.malformed
        self._status.sample_rate_hz = self._compute_rate()

    def _compute_rate(self) -> float:
        now = time.monotonic()
        while self._arrivals and now - self._arrivals[0] > 1.0:
            self._arrivals.popleft()
        if len(self._arrivals) < 2:
            return 0.0
        span = self._arrivals[-1] - self._arrivals[0]
        return (len(self._arrivals) - 1) / span if span > 0 else 0.0

    def status(self) -> dict:
        return self._status.to_dict()

    def recent(self, seconds: float = 4.0) -> list[ImuSample]:
        cutoff = time.monotonic() - seconds
        return [s for s in self._samples if (s.host_timestamp or 0.0) >= cutoff]
