"""Segment one recording (or all curl recordings) into reps. Run with:

    make imu-segment FILE=data/recordings/curl-good-01.csv
    make imu-segment ALL=1

Prints detected reps and writes a debug plot: projected gyro signal, movement
thresholds, rep starts, turnarounds, and ends. It does not classify movement.
"""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.motion.calibration import CalibrationProfile  # noqa: E402
from app.motion.pipeline import build_set, project_samples  # noqa: E402
from app.motion.segmentation import RepSpan  # noqa: E402
from app.sensors.analysis import load_recording_csv  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = REPO_ROOT / "data" / "profiles" / "bicep_curl.json"


def resolve(path: Path) -> Path:
    if path.exists():
        return path
    candidate = REPO_ROOT / path
    return candidate if candidate.exists() else path


def load_profile(path: Path | None) -> CalibrationProfile | None:
    if path and Path(path).exists():
        return CalibrationProfile.load(path)
    return None


def print_reps(projected, spans: list[RepSpan], metrics) -> None:
    t = projected.t
    print(f"  detected reps: {len(spans)}  (axis variance {projected.axis_variance_fraction * 100:.0f}%, "
          f"noise {projected.rest.noise_dps:.2f} dps)")
    print(f"  {'rep':>3} {'start':>7} {'turn':>7} {'end':>7} {'dur_ms':>8} "
          f"{'exc_deg':>8} {'peak_dps':>9} {'sim':>6}")
    for number, (span, rep) in enumerate(zip(spans, metrics.reps), start=1):
        sim = f"{rep.similarity_score:.2f}" if rep.similarity_score is not None else "  - "
        print(f"  {number:>3} {t[span.start]:>7.2f} {t[span.turnaround]:>7.2f} {t[span.end]:>7.2f} "
              f"{span.duration_ms:>8.0f} {span.excursion_deg:>8.1f} {span.peak_velocity_dps:>9.0f} {sim:>6}")
    if metrics.reps:
        print(f"  set: avg_dur={metrics.average_duration_ms:.0f}ms  consistency={metrics.consistency_score}  "
              f"avg_rom={metrics.average_rom_deg:.1f}  mean_sim={metrics.reference_similarity_mean}")


def plot_segments(projected, spans: list[RepSpan], title: str, save: Path) -> None:
    import matplotlib.pyplot as plt

    t = projected.t
    v = projected.velocity_dps
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(t, v, color="tab:blue", linewidth=1.0, label="projected gyro (filtered)")
    ax.axhline(projected.rest.noise_dps * 6.0, color="gray", linestyle="--", linewidth=0.8, label="+-start threshold")
    ax.axhline(-projected.rest.noise_dps * 6.0, color="gray", linestyle="--", linewidth=0.8)
    for span in spans:
        ax.axvline(t[span.start], color="tab:green", alpha=0.7, linewidth=1.0)
        ax.axvline(t[span.turnaround], color="gold", alpha=0.9, linewidth=1.0)
        ax.axvline(t[span.end], color="tab:red", alpha=0.7, linewidth=1.0)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("angular velocity (dps)")
    ax.set_title(f"{title}  ({len(spans)} reps; green=start gold=turn red=end)")
    ax.grid(True, alpha=0.2)
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    save.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(save, dpi=120)
    plt.close(fig)
    print(f"  debug plot -> {save}")


def segment_file(path: Path, profile: CalibrationProfile | None, self_calibrate: bool,
                 make_plot: bool) -> int:
    rows = load_recording_csv(path)
    if not rows:
        print(f"{path.name}: no samples")
        return -1
    projected, spans, metrics = build_set(rows, profile, "bicep_curl",
                                          self_calibrate=self_calibrate,
                                          source=path.name)
    print(f"\n{path.name}  ({len(rows)} samples)")
    print_reps(projected, spans, metrics)
    if make_plot:
        plot_segments(projected, spans, path.name,
                      REPO_ROOT / "data" / "recordings" / f"{path.stem}-segments.png")
    return len(spans)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=None)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--glob", default="data/recordings/curl-*.csv")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--no-self-calibrate", action="store_true")
    parser.add_argument("--no-plot", action="store_true")
    args = parser.parse_args()

    profile = load_profile(resolve(args.profile) if args.profile else None)
    if profile is None:
        print("(no calibration profile found; using default thresholds)\n")

    if args.all:
        paths = sorted(Path(p) for p in glob.glob(str(REPO_ROOT / args.glob)))
        print(f"{'file':<26}{'detected':>9}")
        for path in paths:
            count = segment_file(path, profile, not args.no_self_calibrate, not args.no_plot)
            print(f"{path.name:<26}{count:>9}")
        return 0

    if not args.file:
        parser.error("provide --file or --all")
    path = resolve(args.file)
    if not path.exists():
        print(f"file not found: {args.file}")
        return 2
    segment_file(path, profile, not args.no_self_calibrate, not args.no_plot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
