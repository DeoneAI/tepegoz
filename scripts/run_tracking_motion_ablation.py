"""Controlled road-image tracking ablation with known synthetic camera rotations.

Real public RGB is warped; rotations/IMU are synthetic. This is an algorithm experiment,
not a phone recording or independent detector-accuracy benchmark.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial.transform import Rotation
from perception.camera_motion import rotation_homography, warp_box
from perception.models import YoloXDetector
from perception.render import render_overlay
from perception.tracking import BoxTracker, iou_matrix


# Approximate, non-exhaustive visual reference boxes on the first solidWhiteRight frame.
# They are used only to assess known-warp ID continuity, not detection AP/precision.
REFERENCE_BOXES = [[1, 298, 40, 367], [292, 300, 332, 330], [356, 303, 390, 330], [406, 301, 440, 330]]


def run(output, frames=60):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    cv2.setNumThreads(4)
    capture = cv2.VideoCapture(".tools/datasets/roads/solidWhiteRight.mp4"); ok, source = capture.read(); capture.release()
    if not ok:
        raise ValueError("Fetch the pinned public road sample first")
    height, width = source.shape[:2]
    if (width, height) != (960, 540):
        raise ValueError("Reference boxes are defined for the pinned 960x540 public sample")
    K = np.array([[700., 0, width / 2], [0, 700., height / 2], [0, 0, 1.]])
    detector = YoloXDetector(".tools/models/yolox_tiny.onnx")
    trackers = {name: BoxTracker(max_age_s=.3) for name in ("rgb_only", "rotation_assisted", "wrong_rotation_sign")}
    metrics = {name: {"matched_reference_observations": 0, "missing_reference_observations": 0, "id_switches_reference_subset": 0} for name in trackers}
    previous_ids = {name: {} for name in trackers}; previous_rotation = Rotation.identity()
    writer = cv2.VideoWriter(str(output / "tracking-ablation.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 20, (width * 3, height))
    if not writer.isOpened():
        raise ValueError("Video encoder unavailable")
    records = []
    try:
        for index in range(frames):
            angle = [0, 6, -6, 3, -3][index % 5]
            rotation = Rotation.from_euler("y", angle, degrees=True)
            absolute_H = rotation_homography(K, rotation.inv().as_matrix())
            image = cv2.warpPerspective(source, absolute_H, (width, height), borderMode=cv2.BORDER_CONSTANT)
            delta_H = rotation_homography(K, (rotation.inv() * previous_rotation).as_matrix())
            references = []
            for identifier, box in enumerate(REFERENCE_BOXES):
                warped = np.array(warp_box(box, absolute_H)); warped[[0, 2]] = np.clip(warped[[0, 2]], 0, width); warped[[1, 3]] = np.clip(warped[[1, 3]], 0, height)
                if np.all(warped[2:] - warped[:2] > 6):
                    references.append((identifier, warped.tolist()))
            detections = detector(image); panels = []
            for name, tracker in trackers.items():
                H = delta_H if name == "rotation_assisted" else np.linalg.inv(delta_H) if name == "wrong_rotation_sign" else None
                tracks = tracker.update(detections, index / 20, H)
                observed = [track for track in tracks if track["observed"]]
                pairs = []
                if references and observed:
                    overlaps = iou_matrix([box for _, box in references], [track["xyxy"] for track in observed])
                    rows, columns = linear_sum_assignment(1 - overlaps)
                    pairs = [(references[r][0], observed[c]["track_id"]) for r, c in zip(rows, columns) if overlaps[r, c] >= .3]
                for object_id, track_id in pairs:
                    if object_id in previous_ids[name] and previous_ids[name][object_id] != track_id:
                        metrics[name]["id_switches_reference_subset"] += 1
                    previous_ids[name][object_id] = track_id
                metrics[name]["matched_reference_observations"] += len(pairs)
                metrics[name]["missing_reference_observations"] += len(references) - len(pairs)
                panels.append(render_overlay(image, None, tracks, name + " | SYNTHETIC rotation " + str(angle) + " deg"))
                records.append({"frame_index": index, "synthetic_time_s": index / 20, "synthetic_camera_y_degrees": angle, "variant": name, "tracks": tracks, "reference_matches": pairs})
            preview = np.hstack(panels); writer.write(preview)
            if index in {0, 1, 2, 20, 59}:
                cv2.imwrite(str(output / f"frame-{index:03d}.jpg"), preview)
            previous_rotation = rotation
    finally:
        writer.release()
    (output / "tracking.jsonl").write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    report = {"evidence_type": "controlled synthetic rotation stress test on a real public still frame; no real IMU or capture timing", "frames": frames, "intrinsics": K.tolist(),
              "intrinsics_status": "chosen simulation intrinsics; not measured camera calibration", "reference_boxes": REFERENCE_BOXES, "reference_annotation": "approximate visual subset, not exhaustive detector ground truth", "matching_iou": .3,
              "metrics": metrics, "limits": ["Known pure rotation favors the correct compensation model", "Translation, rolling shutter, timing error, moving objects and bad extrinsics violate the model", "Wrong-sign rotation is a deliberate negative case", "This result does not establish field tracking accuracy or road safety"]}
    (output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__); cli.add_argument("--output", default=".tools/experiments/tracking-motion-ablation"); cli.add_argument("--frames", type=int, default=60)
    args = cli.parse_args()
    try:
        print(json.dumps(run(args.output, args.frames)))
    except (ValueError, OSError, RuntimeError) as error:
        cli.exit(1, f"{error}\n")
