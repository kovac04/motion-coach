"""Wire format and sample model for the ESP32 wearable.

The firmware sends an 18-byte little-endian notification:

    uint16 sequence | uint32 timestamp_ms | int16 ax, ay, az, gx, gy, gz

Everything here is pure and hardware-independent so it can be unit tested without
a BLE adapter.

Provenance: the raw values come from an MPU6050 14-byte big-endian burst, decoded
on the ESP32. The register behavior originates from the known-good STM32 code in
auto-lock (https://github.com/kovac04/auto-lock, Core/Src/main.c).
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass

# "<" little-endian, H u16, I u32, h int16 x6.
PACKET_FORMAT = "<HIhhhhhh"
PACKET_SIZE = struct.calcsize(PACKET_FORMAT)
assert PACKET_SIZE == 18, f"unexpected packet size {PACKET_SIZE}"

SEQUENCE_WRAP = 1 << 16

# Full-scale sensitivity; must match the firmware configuration
# (ACCEL_CONFIG=0x08 -> +-4 g, GYRO_CONFIG=0x10 -> +-1000 deg/s).
ACCEL_LSB_PER_G = 8192.0   # +-4 g
GYRO_LSB_PER_DPS = 32.8    # +-1000 deg/s


@dataclass(frozen=True)
class ImuSample:
    """One raw MPU6050 reading plus BLE arrival metadata."""

    sequence: int
    timestamp_ms: int
    ax: int
    ay: int
    az: int
    gx: int
    gy: int
    gz: int
    host_timestamp: float | None = None

    @property
    def accel_magnitude(self) -> float:
        return math.sqrt(self.ax * self.ax + self.ay * self.ay + self.az * self.az)

    @property
    def gyro_magnitude(self) -> float:
        return math.sqrt(self.gx * self.gx + self.gy * self.gy + self.gz * self.gz)

    def accel_g(self) -> tuple[float, float, float]:
        return (self.ax / ACCEL_LSB_PER_G, self.ay / ACCEL_LSB_PER_G, self.az / ACCEL_LSB_PER_G)

    def gyro_dps(self) -> tuple[float, float, float]:
        return (self.gx / GYRO_LSB_PER_DPS, self.gy / GYRO_LSB_PER_DPS, self.gz / GYRO_LSB_PER_DPS)


def decode_packet(data: bytes, host_timestamp: float | None = None) -> ImuSample:
    """Decode an 18-byte BLE notification. Raises ValueError on wrong length."""
    if len(data) != PACKET_SIZE:
        raise ValueError(f"expected {PACKET_SIZE} bytes, got {len(data)}")
    sequence, timestamp_ms, ax, ay, az, gx, gy, gz = struct.unpack(PACKET_FORMAT, data)
    return ImuSample(
        sequence=sequence,
        timestamp_ms=timestamp_ms,
        ax=ax,
        ay=ay,
        az=az,
        gx=gx,
        gy=gy,
        gz=gz,
        host_timestamp=host_timestamp,
    )


@dataclass
class SequenceTracker:
    """Counts gaps in the uint16 sequence counter (handles wrap-around)."""

    expected: int | None = None
    gaps: int = 0
    missing: int = 0

    def observe(self, sequence: int) -> int:
        if self.expected is None:
            self.expected = (sequence + 1) % SEQUENCE_WRAP
            return 0
        if sequence != self.expected:
            missing = (sequence - self.expected) % SEQUENCE_WRAP
            self.gaps += 1
            self.missing += missing
        else:
            missing = 0
        self.expected = (sequence + 1) % SEQUENCE_WRAP
        return missing
