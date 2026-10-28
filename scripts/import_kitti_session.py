"""Import a verified KITTI subset for offline replay; no phone acquisition claim."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from evaluation.kitti import timestamp_ns, color_imu_calibration


def run(dataset, output):
    dataset, output = Path(dataset), Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Import output must be empty; earlier evidence is preserved")
    selection_file = dataset / "selection.json"
    selection = json.loads(selection_file.read_text(encoding="utf-8"))
    provenance = json.loads((dataset / "provenance.json").read_text(encoding="utf-8"))
    # Catch source corruption before creating a finalized derived session.
    for relative, expected in provenance["selected_file_sha256"].items():
        if hashlib.sha256((dataset / relative).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Source integrity mismatch: {relative}")
    camera_times = [timestamp_ns(value) for value in selection["camera"]]
    imu_times = [timestamp_ns(value) for value in selection["imu"]]
    if not camera_times or not imu_times or any(b <= a for times in (camera_times, imu_times) for a, b in zip(times, times[1:])):
        raise ValueError("Both source streams must be nonempty and strictly increasing")
    origin = min(camera_times[0], imu_times[0])
    identity = hashlib.sha256(selection_file.read_bytes()).hexdigest()[:24]
    K, R_BC = color_imu_calibration(dataset)
    first = cv2.imread(str(dataset / "image_02/data/0000000000.png"))
    if first is None:
        raise ValueError("Unreadable KITTI color source")
    height, width = first.shape[:2]
    axes = "kitti_oxts_sensor_native"
    calibration = {"camera_intrinsics": K.tolist(), "R_body_camera": R_BC.tolist(), "image_width": width, "image_height": height,
                   "imu_frame_axes": axes, "gyro_bias_rad_s": None, "gyro_max_gap_s": .25, "gyro_match_tolerance_ms": 50,
                   "source": "KITTI date-specific calibration: R_CI=R_rect_00 R_cam0_velo R_velo_imu, K=P_rect_02[:,:3]",
                   "limits": "Synchronized OXTS sampled near 10 Hz, not original high-rate IMU; zero bias assumed, no stationary calibration or translational compensation"}
    manifest = {"schema_version": 2, "id": identity, "name": "KITTI 2011_09_30 drive 0028 PUBLIC DATASET IMPORT", "status": "importing", "source_type": "public_dataset_import",
                "time_basis": "kitti_dataset_relative_sensor_time", "original_calendar_origin_ns": str(origin), "original_timestamp_timezone": "unspecified in source timestamp text",
                "clock_basis": "Dataset calendar timestamps minus one common integer origin; no phone/PC synchronization experiment",
                "axes": axes, "source_dataset": provenance["official_source"], "source_selection_sha256": hashlib.sha256(selection_file.read_bytes()).hexdigest(),
                "image_transform": "already rectified KITTI color PNG -> derived JPEG quality 95; original PNG files unchanged",
                "calibration": {"intrinsics": K.tolist(), "distortion": [0, 0, 0, 0], "camera_to_body_rotation": R_BC.tolist(), "phone_to_vehicle": None, "status": "public dataset measured calibration, not phone calibration"},
                "acceptance_limit": "Public color camera/OXTS replay; does not establish browser/USB, high-rate phone IMU, capture-to-display latency or hardware acceptance"}
    output.mkdir(parents=True, exist_ok=True); (output / "frames").mkdir()
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with (output / "frames.jsonl").open("w", encoding="utf-8") as log, (output / "frames.csv").open("w", encoding="utf-8", newline="") as table:
        columns = ["frame_index", "timestamp_ns", "timestamp_source", "width", "height", "bytes", "original_dataset_timestamp"]
        writer = csv.writer(table); writer.writerow(columns)
        for index, timestamp in enumerate(camera_times):
            image = cv2.imread(str(dataset / f"image_02/data/{index:010d}.png"))
            if image is None or image.shape[:2] != (height, width):
                raise ValueError(f"Unreadable or inconsistent source frame {index}")
            ok, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
            if not ok:
                raise ValueError("Could not encode derived JPEG")
            (output / "frames" / f"{index:08d}.jpg").write_bytes(jpeg.tobytes())
            record = {"session_id": identity, "frame_index": index, "timestamp_ns": str(timestamp - origin), "timestamp_source": "dataset_sensor_timestamp",
                      "original_dataset_timestamp": selection["camera"][index], "width": width, "height": height, "bytes": int(jpeg.size)}
            log.write(json.dumps(record) + "\n"); writer.writerow([record[key] for key in columns])
    with (output / "telemetry.jsonl").open("w", encoding="utf-8") as log, (output / "imu.csv").open("w", encoding="utf-8", newline="") as table:
        writer = csv.writer(table); writer.writerow(["session_id", "sensor_type", "timestamp_ns", "sequence_id", "x", "y", "z", "units", "quality", "server_receive_ns"])
        for index, timestamp in enumerate(imu_times):
            packet = np.loadtxt(dataset / f"oxts/data/{index:010d}.txt").reshape(-1)
            if len(packet) != 30 or not np.isfinite(packet).all():
                raise ValueError(f"Invalid OXTS packet {index}")
            for sensor, values, unit in (("accelerometer", packet[11:14], "m_s2"), ("gyroscope", packet[17:20], "rad_s")):
                record = {"session_id": identity, "sensor_type": sensor, "timestamp_ns": str(timestamp - origin), "sequence_id": index, "frame_axes": axes,
                          "values": dict(zip("xyz", values.tolist())), "units": unit, "timestamp_source": "dataset_sensor_timestamp", "original_dataset_timestamp": selection["imu"][index],
                          "quality": "public_synced_OXTS_subsample_not_phone_high_rate_IMU"}
                log.write(json.dumps(record) + "\n"); writer.writerow([identity, sensor, record["timestamp_ns"], index, *values, unit, record["quality"], ""])
    (output / "clock.jsonl").write_text("", encoding="utf-8")
    (output / "gnss.csv").write_text("session_id,timestamp_ns,sequence_id,latitude,longitude\n", encoding="utf-8")
    (output / "motion-calibration.json").write_text(json.dumps(calibration, indent=2), encoding="utf-8")
    manifest.update(status="completed", source_frames=len(camera_times), source_imu_samples=len(imu_times), source_duration_s=(camera_times[-1] - camera_times[0]) / 1e9)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"output": str(output.resolve()), "frames": len(camera_times), "imu_packets": len(imu_times), "duration_s": manifest["source_duration_s"], "source_type": "public_dataset_import"}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__); cli.add_argument("--dataset", default=".tools/datasets/kitti-0028"); cli.add_argument("--output", default=".tools/datasets/kitti-replay")
    args = cli.parse_args()
    try:
        print(json.dumps(run(args.dataset, args.output)))
    except (ValueError, OSError, KeyError) as error:
        cli.exit(1, f"{error}\n")
