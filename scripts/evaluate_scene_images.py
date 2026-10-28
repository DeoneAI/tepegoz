"""Day/night/snow/shadow sanity checks on pinned upstream public example images."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from perception.lanes import ClassicalLaneDetector
from perception.models import YoloPLaneDetector, YoloXDetector
from perception.render import render_overlay


CONDITIONS = {"0ace96c3-48481887": "day / tree shade / parked traffic", "3c0e7240-96e390d2": "night / weak lighting", "7dd9ef45-f197db95": "snow / obscured markings", "8e1c1ab0-a8b92173": "day / highway / shadows", "9aa94005-ff1d4c9a": "night / glare", "adb4871d-4d063244": "day / urban / parked traffic"}


def run(folder, output):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    cv2.setNumThreads(4)
    models = {"classical": ClassicalLaneDetector(), "yolop": YoloPLaneDetector(".tools/models/yolop-320-320.onnx")}
    detector = YoloXDetector(".tools/models/yolox_tiny.onnx")
    records = []; metrics = []
    for file in sorted(Path(folder).glob("*.jpg")):
        image = cv2.imread(str(file))
        if image is None:
            raise ValueError(f"Unreadable public image: {file}")
        condition = CONDITIONS.get(file.stem, "unlabeled condition")
        before = time.perf_counter(); detections = detector(image); det_ms = (time.perf_counter() - before) * 1000
        estimates, panels = {}, []
        row = {"image": file.name, "condition": condition, "detections": len(detections), "detector_ms": det_ms}
        for name, model in models.items():
            before = time.perf_counter(); estimate, mask = model(image); row[name + "_ms"] = (time.perf_counter() - before) * 1000
            row[name + "_confidence"] = estimate["confidence"]; estimates[name] = estimate
            panel = render_overlay(image, estimate, (), name + " | " + condition)
            for detection in detections:
                x1, y1, x2, y2 = map(int, detection["xyxy"])
                cv2.rectangle(panel, (x1, y1), (x2, y2), (50, 200, 220), 2)
                cv2.putText(panel, f"{detection['class_name']} {detection['score']:.2f}", (x1, max(65, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, .4, (50, 200, 220), 1)
            panels.append(panel)
        cv2.imwrite(str(output / (file.stem + "-comparison.jpg")), np.hstack(panels))
        records.append({"image": file.name, "sha256": hashlib.sha256(file.read_bytes()).hexdigest(), "condition": condition, "capture_timestamp_ns": None,
                        "detections": detections, "lanes": estimates, "class_counts": dict(Counter(d["class_name"] for d in detections)), "quality_labels": "visual condition labels only; not exhaustive ground-truth object/lane annotation"})
        metrics.append(row)
    (output / "scenes.json").write_text(json.dumps(records, indent=2, allow_nan=False), encoding="utf-8")
    if metrics:
        with (output / "scenes.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(metrics[0])); writer.writeheader(); writer.writerows(metrics)
    return {"output": str(output.resolve()), "images": len(records)}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--input", default=".tools/datasets/yolop-images")
    cli.add_argument("--output", default=".tools/experiments/scene-images")
    args = cli.parse_args()
    try:
        print(json.dumps(run(args.input, args.output)))
    except (OSError, ValueError, RuntimeError) as error:
        cli.exit(1, f"{error}\n")
