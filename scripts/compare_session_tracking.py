"""Compare RGB-only and real same-session gyro tracking with identical detections."""
from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.benchmark import summarize_run


def compare(rgb, assisted, output):
    rgb, assisted, output = Path(rgb), Path(assisted), Path(output)
    read = lambda folder, name: [json.loads(line) for line in (folder / name).read_text(encoding="utf-8").splitlines()]
    a, b = read(rgb, "detections.jsonl"), read(assisted, "detections.jsonl")
    if not a or a != b:
        raise ValueError("Comparison requires exactly the same indexed detection records; rerun matched inputs/settings")
    runs = [json.loads((folder / "run.json").read_text(encoding="utf-8")) for folder in (rgb, assisted)]
    if runs[0]["source"] != runs[1]["source"] or runs[0]["motion_compensation"].get("enabled") is not False or not runs[1]["motion_compensation"].get("calibration_sha256"):
        raise ValueError("Expected one RGB-only and one calibrated same-source gyro run")
    motion = read(assisted, "camera_motion.jsonl")
    report = {"evidence_type": "Real public dataset same-frame/same-detector tracking ablation; no exhaustive track identity ground truth",
              "frames": len(a), "time_basis": runs[0]["time_basis"], "detections_identical": True,
              "motion_used_frames": sum(row["used"] for row in motion), "motion_unavailable_reasons": dict(Counter(row["reason"] for row in motion if not row["used"])),
              "motion_calibration": runs[1]["motion_compensation"],
              "variants": {name: summarize_run(folder)["metrics"] for name, folder in (("rgb_only", rgb), ("gyro_rotation", assisted))},
              "run_manifest_sha256": {name: hashlib.sha256((folder / "run.json").read_bytes()).hexdigest() for name, folder in (("rgb_only", rgb), ("gyro_rotation", assisted))},
              "limits": ["Observed ID/short-track totals are fragmentation proxies, not labeled ID switches or tracking accuracy", "Pure rotation ignores translation, independent object motion and rolling shutter", "No inference that more smoothing or fewer IDs is always correct", "Functional runs may overlap other processes; do not compare their wall FPS as a controlled speed experiment"]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__); cli.add_argument("rgb"); cli.add_argument("assisted"); cli.add_argument("--output", required=True)
    args = cli.parse_args()
    try:
        print(json.dumps(compare(args.rgb, args.assisted, args.output)))
    except (ValueError, OSError, KeyError) as error:
        cli.exit(1, f"{error}\n")
