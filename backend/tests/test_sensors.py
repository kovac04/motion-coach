import asyncio
import csv
import struct

import pytest

from app.sensors.packet import (
    PACKET_FORMAT,
    PACKET_SIZE,
    ImuSample,
    SequenceTracker,
    decode_packet,
)
from app.sensors.recorder import CSV_HEADER, record_stream


def test_packet_size_is_18():
    assert PACKET_SIZE == 18
    assert struct.calcsize(PACKET_FORMAT) == 18


def test_decode_valid_packet():
    payload = struct.pack(PACKET_FORMAT, 7, 123456, 1, -2, 3, -4, 5, -6)
    sample = decode_packet(payload, host_timestamp=10.5)
    assert sample.sequence == 7
    assert sample.timestamp_ms == 123456
    assert (sample.ax, sample.ay, sample.az) == (1, -2, 3)
    assert (sample.gx, sample.gy, sample.gz) == (-4, 5, -6)
    assert sample.host_timestamp == 10.5


def test_decode_rejects_wrong_length():
    with pytest.raises(ValueError):
        decode_packet(b"\x00" * 17)
    with pytest.raises(ValueError):
        decode_packet(b"\x00" * 19)


def test_signed_extremes_roundtrip():
    payload = struct.pack(PACKET_FORMAT, 65535, 4294967295, -32768, 32767, -1, 1, 0, -32768)
    sample = decode_packet(payload)
    assert sample.ax == -32768
    assert sample.ay == 32767
    assert sample.gz == -32768
    assert sample.sequence == 65535
    assert sample.timestamp_ms == 4294967295


def test_scaling_helpers():
    sample = ImuSample(1, 0, 16384, 0, 0, 131, 0, 0)
    x_g, _, _ = sample.accel_g()
    assert x_g == pytest.approx(1.0)
    gx_dps, _, _ = sample.gyro_dps()
    assert gx_dps == pytest.approx(1.0)
    assert sample.accel_magnitude == pytest.approx(16384.0)
    assert sample.gyro_magnitude == pytest.approx(131.0)


def test_sequence_tracker_no_gaps():
    tracker = SequenceTracker()
    for seq in range(10):
        assert tracker.observe(seq) == 0
    assert tracker.gaps == 0
    assert tracker.missing == 0


def test_sequence_tracker_detects_gap():
    tracker = SequenceTracker()
    tracker.observe(0)
    tracker.observe(1)
    missing = tracker.observe(5)  # 2,3,4 lost
    assert missing == 3
    assert tracker.gaps == 1
    assert tracker.missing == 3


def test_sequence_tracker_handles_wraparound():
    tracker = SequenceTracker()
    tracker.observe(65534)
    tracker.observe(65535)
    assert tracker.observe(0) == 0  # wrapped, not a gap
    assert tracker.gaps == 0


@pytest.mark.asyncio
async def test_recorder_writes_csv(tmp_path):
    async def fake_stream():
        for i in range(5):
            yield ImuSample(i, i * 20, i, -i, 0, 0, 0, 0, host_timestamp=i * 0.02)

    path = tmp_path / "rec.csv"
    stats = await record_stream(fake_stream(), path, asyncio.Event())
    assert stats.samples == 5
    assert stats.sequence_gaps == 0

    with path.open(newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == CSV_HEADER
    assert len(rows) == 6
    assert rows[1][1] == "0"  # sequence
