"""Exact KITTI calendar timestamps and rectified color-camera/IMU calibration."""
from datetime import datetime
from pathlib import Path
import numpy as np


def timestamp_ns(value):
    # Preserve all nine decimal digits; the dataset does not supply a timezone here.
    seconds, fraction = value.strip().split(".")
    if len(fraction) != 9 or not fraction.isdigit():
        raise ValueError("Expected a KITTI nanosecond timestamp")
    parsed = datetime.strptime(seconds, "%Y-%m-%d %H:%M:%S")
    delta = parsed - datetime(1970, 1, 1)
    return (delta.days * 86400 + delta.seconds) * 1000000000 + int(fraction)


def read_calibration(file):
    result = {}
    for line in Path(file).read_text(encoding="utf-8").splitlines():
        key, _, values = line.partition(":")
        try:
            result[key] = np.array([float(value) for value in values.split()])
        except ValueError:
            continue  # calibration date string
    return result


def color_imu_calibration(dataset):
    dataset = Path(dataset)
    camera = read_calibration(dataset / "calib_cam_to_cam.txt")
    velo_camera = read_calibration(dataset / "calib_velo_to_cam.txt")
    imu_velo = read_calibration(dataset / "calib_imu_to_velo.txt")
    # P_rect_02 projects into the common rectified axes. Its baseline is translation;
    # the rotation uses R_rect_00, as in the official-linked pykitti raw loader.
    R_CI = camera["R_rect_00"].reshape(3, 3) @ velo_camera["R"].reshape(3, 3) @ imu_velo["R"].reshape(3, 3)
    return camera["P_rect_02"].reshape(3, 4)[:, :3], R_CI.T
