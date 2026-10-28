"""Create an explicitly labeled offline replay session from real EuRoC camera/IMU data.

This is a derived public-dataset import, not a browser/phone/USB acceptance recording.
Original times are preserved and a common integer origin is subtracted for replay.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from evaluation.euroc import load_euroc
from localization.orientation import find_initial_quiet_window


def run(dataset, output, max_frames=600):
    dataset, output = Path(dataset), Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Import output must be empty; original dataset and earlier imports are preserved")
    data = load_euroc(dataset, max_frames)
    origin = min(int(data["imu"][0]["timestamp_ns"]), int(data["camera"][0]["timestamp_ns"]))
    identity = hashlib.sha256((dataset / "camera_selection.csv").read_bytes()).hexdigest()[:24]
    axes = "euroc_imu_sensor_native"
    calibration = {"camera_intrinsics": data["calibration"]["intrinsics"], "R_body_camera": data["T_BC"][:3, :3].tolist(), "image_width": data["calibration"]["resolution"][0], "image_height": data["calibration"]["resolution"][1], "imu_frame_axes": axes}
    quiet = find_initial_quiet_window(data["imu"])
    calibration["gyro_bias_rad_s"] = quiet["gyro_bias_rad_s"] if quiet["accepted"] else None
    calibration["gyro_bias_assumption"] = quiet
    calibration["source"] = "EuRoC measured camera/IMU calibration; derived images undistorted with original K"
    manifest = {"schema_version": 2, "id": identity, "name": "EuRoC V1_01_easy PUBLIC DATASET IMPORT", "status": "importing", "source_type": "public_dataset_import",
                "time_basis": "euroc_dataset_relative_sensor_time", "original_origin_timestamp_ns": str(origin), "clock_basis": "Original synchronized dataset times minus one common integer origin; no phone/PC clock exchange",
                "axes": "EuRoC native IMU axes, not phone portrait axes; measured R_body_camera supplied separately", "source_dataset": "https://projects.asl.ethz.ch/datasets/euroc-mav/",
                "image_transform": "source monochrome PNG -> calibrated undistortion with original K -> derived JPEG quality 95; original PNGs remain unchanged",
                "calibration": {"intrinsics": data["K"].tolist(), "distortion": [0, 0, 0, 0], "original_distortion": data["distortion"], "camera_to_body": data["T_BC"].tolist(), "phone_to_vehicle": None, "status": "public dataset camera/IMU calibration; no phone/vehicle calibration"},
                "acceptance_limit": "This import does not prove real phone, USB, capture-to-display latency or sustained browser acquisition"}
    output.mkdir(parents=True, exist_ok=True); (output / "frames").mkdir()
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with (output / "frames.jsonl").open("w", encoding="utf-8") as log, (output / "frames.csv").open("w", encoding="utf-8", newline="") as table:
        writer = csv.writer(table); writer.writerow(["frame_index", "timestamp_ns", "timestamp_source", "width", "height", "bytes", "original_dataset_timestamp_ns"])
        for index, frame in enumerate(data["camera"]):
            image = cv2.imread(str(frame["image"]))
            if image is None:
                raise ValueError("Unreadable EuRoC source image")
            image = cv2.undistort(image, data["K"], np.array(data["distortion"]))
            ok, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
            if not ok:
                raise ValueError("Could not encode derived JPEG")
            (output / "frames" / f"{index:08d}.jpg").write_bytes(jpeg.tobytes())
            record = {"session_id": identity, "frame_index": index, "timestamp_ns": str(int(frame["timestamp_ns"]) - origin), "timestamp_source": "dataset_sensor_timestamp",
                      "original_dataset_timestamp_ns": frame["timestamp_ns"], "width": image.shape[1], "height": image.shape[0], "bytes": int(jpeg.size)}
            log.write(json.dumps(record) + "\n"); writer.writerow([record[key] for key in ("frame_index", "timestamp_ns", "timestamp_source", "width", "height", "bytes", "original_dataset_timestamp_ns")])
    with (output / "telemetry.jsonl").open("w", encoding="utf-8") as log, (output / "imu.csv").open("w", encoding="utf-8", newline="") as table:
        writer = csv.writer(table); writer.writerow(["session_id", "sensor_type", "timestamp_ns", "sequence_id", "x", "y", "z", "units", "quality", "server_receive_ns"])
        for sequence, sample in enumerate(data["imu"]):
            for sensor, key, unit in (("accelerometer", "acceleration", "m_s2"), ("gyroscope", "angular_velocity", "rad_s")):
                values = dict(zip("xyz", sample[key]))
                record = {"session_id": identity, "sensor_type": sensor, "timestamp_ns": str(int(sample["timestamp_ns"]) - origin), "original_dataset_timestamp_ns": sample["timestamp_ns"],
                          "timestamp_source": "dataset_sensor_timestamp", "sequence_id": sequence, "frame_axes": axes, "values": values, "units": unit, "quality": "public_native_dataset_no_browser_accuracy_claim"}
                log.write(json.dumps(record) + "\n"); writer.writerow([identity, sensor, record["timestamp_ns"], sequence, *sample[key], unit, record["quality"], ""])
    (output / "clock.jsonl").write_text("", encoding="utf-8")
    (output / "gnss.csv").write_text("session_id,timestamp_ns,sequence_id,latitude,longitude\n", encoding="utf-8")
    (output / "motion-calibration.json").write_text(json.dumps(calibration, indent=2), encoding="utf-8")
    manifest.update(status="completed", source_frames=len(data["camera"]), source_imu_samples=len(data["imu"]))
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"output": str(output.resolve()), "frames": len(data["camera"]), "imu_samples": len(data["imu"]), "source_type": manifest["source_type"]}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__); cli.add_argument("--dataset", default=".tools/datasets/euroc-v101"); cli.add_argument("--output", default=".tools/datasets/euroc-replay"); cli.add_argument("--max-frames", type=int, default=600)
    args = cli.parse_args()
    try:
        print(json.dumps(run(args.dataset, args.output, args.max_frames)))
    except (ValueError, OSError, RuntimeError) as error:
        cli.exit(1, f"{error}\n")
