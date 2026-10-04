import csv

import pytest

from app.sensors.analysis import (
    analyze_recording,
    format_report,
    load_recording_csv,
    moving_average,
)


def _rows(count: int, hz: float = 50.0):
    rows = []
    for i in range(count):
        rows.append(
            {
                "ax_raw": 8000.0,
                "ay_raw": 0.0,
                "az_raw": 0.0,
                "gx_raw": float(i % 5) * 10.0,  # varies -> dominant gyro axis
                "gy_raw": 0.0,
                "gz_raw": 0.0,
                "host_timestamp": i / hz,
                "sequence": float(i),
            }
        )
    return rows


def test_moving_average_is_centered_and_pure():
    values = [0.0, 0.0, 10.0, 0.0, 0.0]
    original = list(values)
    out = moving_average(values, 3)
    assert values == original  # input not mutated
    assert out[2] == pytest.approx(10.0 / 3)
    assert out[0] == pytest.approx(0.0)
    assert len(out) == len(values)


def test_moving_average_window_one_returns_copy():
    values = [1.0, 2.0, 3.0]
    out = moving_average(values, 1)
    assert out == values and out is not values


def test_analyze_reports_core_facts():
    analysis = analyze_recording(_rows(100))
    assert analysis["sample_count"] == 100
    assert analysis["measured_hz"] == pytest.approx(50.0, rel=0.01)
    assert analysis["dominant_gyro_axis"] == "gx_raw"
    assert analysis["dominant_accel_axis"] == "ax_raw"
    assert analysis["clip_percent_accel"] == 0.0
    assert analysis["resting"] is not None
    assert analysis["gyro_magnitude"]["max"] >= analysis["gyro_magnitude"]["min"]


def test_analyze_detects_clipping():
    rows = _rows(100)
    rows[10]["ax_raw"] = 32767.0
    rows[11]["gx_raw"] = -32768.0
    analysis = analyze_recording(rows)
    assert analysis["clip_percent_accel"] == pytest.approx(1.0)
    assert analysis["clip_percent_gyro"] == pytest.approx(1.0)


def test_analyze_empty_raises():
    with pytest.raises(ValueError):
        analyze_recording([])


def test_format_report_contains_sections():
    text = format_report(analyze_recording(_rows(50)), name="x.csv")
    assert "x.csv" in text
    assert "measured=" in text
    assert "dominant gyro axis" in text
    assert "clip (near int16 rail)" in text


def test_load_recording_csv_roundtrip(tmp_path):
    path = tmp_path / "rec.csv"
    with path.open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["host_timestamp", "sequence", "device_timestamp_ms",
                         "ax_raw", "ay_raw", "az_raw", "gx_raw", "gy_raw", "gz_raw"])
        writer.writerow(["0.00", "0", "10", "1", "2", "3", "4", "5", "6"])
        writer.writerow(["", "1", "30", "1", "2", "3", "4", "5", "6"])  # missing host ts
        writer.writerow(["0.04", "2"])  # malformed -> skipped
    rows = load_recording_csv(path)
    assert len(rows) == 2
    assert rows[0]["ax_raw"] == 1.0
    assert rows[1]["host_timestamp"] != rows[1]["host_timestamp"]  # NaN
