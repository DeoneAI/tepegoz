"""Measure depth ROI sensitivity to box interiors; no depth ground-truth accuracy claim."""
import argparse
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from perception.depth import box_depth


def evaluate(run, output):
    run, output = Path(run), Path(output)
    detections = {row["frame_index"]: row["detections"] for line in (run / "detections.jsonl").read_text(encoding="utf-8").splitlines() if (row := json.loads(line))}
    rows = []
    for representation in ("relative", "metric"):
        file = run / f"depth_{representation}.jsonl"
        if not file.exists():
            continue
        for line in file.read_text(encoding="utf-8").splitlines():
            frame = json.loads(line)
            with np.load(run / frame["map_file"]) as archive:
                depth = archive["depth"]
            for index, detection in enumerate(detections[frame["frame_index"]]):
                summaries = {fraction: box_depth(depth, detection["xyxy"], frame["units"], fraction) for fraction in (.3, .5, 1.)}
                row = {"frame_index": frame["frame_index"], "model": representation, "detection_index": index, "class_name": detection["class_name"], "units": frame["units"]}
                for fraction, result in summaries.items():
                    row[f"median_fraction_{fraction}"] = result["median"] if result else None
                    row[f"p90_minus_p10_fraction_{fraction}"] = result["p90"] - result["p10"] if result else None
                row["interior_half_minus_full"] = summaries[.5]["median"] - summaries[1.]["median"] if summaries[.5] and summaries[1.] else None
                rows.append(row)
    if not rows:
        raise ValueError("No depth-associated detections available in this run")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.with_suffix(".csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    report = {"source_run": run.name, "samples": len(rows), "interpretation": "ROI sensitivity only; background leakage is possible, not independently measured by this diagnostic", "units_must_not_be_mixed": True,
              "models": {name: {"objects": len(selected), "mean_abs_half_vs_full_difference": float(np.mean(differences)) if differences else None} for name in ("relative", "metric") if (selected := [row for row in rows if row["model"] == name]) and (differences := [abs(row["interior_half_minus_full"]) for row in selected if row["interior_half_minus_full"] is not None])}}
    output.with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__); cli.add_argument("run"); cli.add_argument("--output", required=True)
    args = cli.parse_args()
    try:
        print(json.dumps(evaluate(args.run, args.output)))
    except (ValueError, OSError, KeyError) as error:
        cli.exit(1, f"{error}\n")
