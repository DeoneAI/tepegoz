"""Evaluate YOLOX Nano/Tiny on a declared independent COCO val2017 road-user subset."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
from evaluation.detection import evaluate_detections
from perception.models import ROAD_CLASSES, YoloXDetector


def run(dataset, output):
    dataset, output = Path(dataset), Path(output); output.mkdir(parents=True, exist_ok=True)
    source = json.loads((dataset / "subset.json").read_text(encoding="utf-8"))
    class_by_name = {name: identifier for identifier, name in ROAD_CLASSES.items()}
    mapping = {category["id"]: class_by_name[category["name"]] for category in source["categories"]}
    truth = {image["id"]: [] for image in source["images"]}
    for annotation in source["annotations"]:
        if annotation["iscrowd"]:
            raise ValueError("This small-subset protocol excludes target crowd annotations")
        x, y, width, height = annotation["bbox"]
        truth[annotation["image_id"]].append({"xyxy": [x, y, x + width, y + height], "class_id": mapping[annotation["category_id"]]})
    reports = {}
    cv2.setNumThreads(4)
    for variant in ("nano", "tiny"):
        model_file = Path(f".tools/models/yolox_{variant}.onnx")
        model = YoloXDetector(model_file, threshold=.05)
        predictions = {}; elapsed = 0
        with (output / f"{variant}-predictions.jsonl").open("w", encoding="utf-8") as stream:
            for image in source["images"]:
                pixels = cv2.imread(str(dataset / "images" / image["file_name"]))
                if pixels is None:
                    raise ValueError("Missing validation image " + image["file_name"])
                before = time.perf_counter(); detections = model(pixels); elapsed += time.perf_counter() - before
                # Explicit COCO-style max-detections cap, shared across classes in each image.
                predictions[image["id"]] = sorted(detections, key=lambda detection: -detection["score"])[:100]
                stream.write(json.dumps({"image_id": image["id"], "detections": predictions[image["id"]]}) + "\n")
        report = evaluate_detections(predictions, truth, ROAD_CLASSES)
        report.update(images=len(source["images"]), sampling=source["sampling"], model_sha256=hashlib.sha256(model_file.read_bytes()).hexdigest(), model_bytes=model_file.stat().st_size,
                      detector_threshold=.05, max_detections_per_image=100, inference_preprocess_postprocess_seconds=elapsed, fps_excluding_image_io_and_model_load=len(source["images"]) / elapsed,
                      class_mapping=ROAD_CLASSES, output_interpretation="small selected validation subset; not a published/full COCO benchmark score")
        reports[variant] = report
    (output / "summary.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
    return reports


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__); cli.add_argument("--dataset", default=".tools/datasets/coco-road-val"); cli.add_argument("--output", default=".tools/experiments/detector-evaluation")
    args = cli.parse_args()
    try:
        print(json.dumps(run(args.dataset, args.output)))
    except (ValueError, OSError, RuntimeError) as error:
        cli.exit(1, f"{error}\n")
