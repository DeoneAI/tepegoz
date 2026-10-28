"""Read a provenance-recorded EuRoC subset; preserve original integer nanosecond times."""
import csv
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation


def rows(file):
    with Path(file).open(encoding="utf-8") as stream:
        return [row for row in csv.reader(stream) if row and not row[0].startswith("#")]


def load_euroc(folder, max_frames=None):
    try:
        import yaml
    except ImportError as error:
        raise RuntimeError("Install PyYAML from scripts/requirements-vision.txt") from error
    folder = Path(folder)
    calibration = yaml.safe_load((folder / "mav0/cam0/sensor.yaml").read_text(encoding="utf-8"))
    if calibration["camera_model"] != "pinhole" or calibration["distortion_model"] != "radial-tangential":
        raise ValueError("This VO adapter supports EuRoC pinhole/radial-tangential cameras")
    fx, fy, cx, cy = calibration["intrinsics"]
    K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], float)
    T_BC = np.array(calibration["T_BS"]["data"], float).reshape(4, 4)
    selected = rows(folder / "camera_selection.csv")
    if selected and selected[0][0] == "timestamp_ns":
        selected = selected[1:]
    if max_frames is not None:
        selected = selected[:max_frames]
    if not selected:
        raise ValueError("Dataset contains no selected camera frames")
    camera = [{"timestamp_ns": row[0], "image": folder / "mav0/cam0/data" / row[1].strip()} for row in selected]
    last = int(camera[-1]["timestamp_ns"]) + 10000000
    imu = [{"timestamp_ns": row[0], "angular_velocity": list(map(float, row[1:4])), "acceleration": list(map(float, row[4:7]))} for row in rows(folder / "mav0/imu0/data.csv") if int(row[0]) <= last]
    ground_truth = [{"timestamp_ns": row[0], "position": list(map(float, row[1:4])), "rotation": Rotation.from_quat([float(row[5]), float(row[6]), float(row[7]), float(row[4])])} for row in rows(folder / "mav0/state_groundtruth_estimate0/data.csv") if int(row[0]) <= last]
    if not imu or not ground_truth:
        raise ValueError("Camera/IMU/ground-truth overlap is unavailable")
    return {"camera": camera, "imu": imu, "ground_truth": ground_truth, "K": K, "distortion": calibration["distortion_coefficients"], "T_BC": T_BC, "calibration": calibration}
