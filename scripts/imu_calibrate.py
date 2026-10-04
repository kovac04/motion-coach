"""Build a calibration profile from good recordings. Run with `make imu-calibrate`.

Example:
    make imu-calibrate
    make imu-calibrate GLOB='data/recordings/curl-good-*.csv'

Outputs JSON to data/profiles/<exercise>.json (gitignored).
"""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.motion.calibration import build_profile  # noqa: E402
from app.sensors.analysis import load_recording_csv  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exercise", default="bicep_curl")
    parser.add_argument("--glob", default="data/recordings/curl-good-*.csv")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    paths = sorted(Path(p) for p in glob.glob(str(REPO_ROOT / args.glob)))
    if not paths:
        print(f"no recordings matched {args.glob}")
        return 2

    recordings = []
    for path in paths:
        rows = load_recording_csv(path)
        if rows:
            recordings.append(rows)
            print(f"  loaded {path.name}: {len(rows)} samples")
    if not recordings:
        print("no usable recordings")
        return 2

    profile = build_profile(args.exercise, recordings, source=",".join(p.name for p in paths))
    output = args.output or (REPO_ROOT / "data" / "profiles" / f"{args.exercise}.json")
    profile.save(output)

    print(f"\nCalibration profile: {profile.exercise_id}")
    print(f"  reps used: {profile.reps_used} from {len(recordings)} recordings")
    print(f"  gyro noise: {profile.noise_dps:.2f} dps")
    print(f"  PCA axis: [{profile.axis[0]:+.2f}, {profile.axis[1]:+.2f}, {profile.axis[2]:+.2f}]"
          f"  (PC1 variance {profile.axis_variance_fraction * 100:.0f}%)")
    print(f"  reference duration: {profile.reference_duration_ms:.0f} ms "
          f"(spread {profile.duration_spread_ms:.0f})")
    print(f"  reference excursion: {profile.reference_excursion_deg:.1f} deg "
          f"(spread {profile.excursion_spread_deg:.1f})")
    print(f"  reference peak velocity: {profile.reference_peak_dps:.0f} dps "
          f"(spread {profile.peak_spread_dps:.0f})")
    print(f"  detector: {profile.params}")
    print(f"  saved -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
