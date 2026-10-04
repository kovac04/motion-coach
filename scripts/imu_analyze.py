"""Objective facts about one recording. Run with `make imu-analyze FILE=...`.

Reports signal statistics only. It does NOT detect reps or classify movement.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.sensors.analysis import analyze_recording, format_report, load_recording_csv  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def resolve(path: Path) -> Path:
    """Accept a path relative to cwd or to the repo root (so `make FILE=...` works)."""
    if path.exists():
        return path
    candidate = REPO_ROOT / path
    return candidate if candidate.exists() else path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--rest-seconds", type=float, default=2.0)
    args = parser.parse_args()
    args.file = resolve(args.file)

    if not args.file.exists():
        print(f"file not found: {args.file}")
        return 2

    rows = load_recording_csv(args.file)
    if not rows:
        print(f"no usable samples in {args.file}")
        return 2

    analysis = analyze_recording(rows, rest_seconds=args.rest_seconds)
    print(format_report(analysis, name=args.file.name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
