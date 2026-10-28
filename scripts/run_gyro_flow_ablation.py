"""Real EuRoC RGB-only versus gyro-seeded optical-flow tracking, including wrong-sign control."""
import argparse
from bisect import bisect_left
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from scipy.spatial.transform import Rotation
from evaluation.euroc import load_euroc
from localization.orientation import find_initial_quiet_window, integrate_gyro, nearest_orientation
from perception.camera_motion import rotation_homography


def nearest(values, times, timestamp):
    index = bisect_left(times, timestamp)
    choices = [i for i in (index - 1, index) if 0 <= i < len(times)]
    if not choices:
        return None
    best = min(choices, key=lambda i: abs(times[i] - timestamp))
    return values[best] if abs(times[best] - timestamp) <= 10000000 else None


def skew(vector):
    x, y, z = vector
    return np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])


def run(dataset, output, stride=4):
    cv2.setNumThreads(4); data = load_euroc(dataset, 600); output = Path(output); output.mkdir(parents=True, exist_ok=True)
    quiet = find_initial_quiet_window(data["imu"])
    gyro = integrate_gyro(data["imu"], quiet["gyro_bias_rad_s"] if quiet["accepted"] else [0, 0, 0])
    times = [int(value["timestamp_ns"]) for value in gyro]
    truth_times = [int(value["timestamp_ns"]) for value in data["ground_truth"]]
    R_BC = Rotation.from_matrix(data["T_BC"][:3, :3]); K = data["K"]; K_inv = np.linalg.inv(K)
    previous = None; records = []
    for frame_index in range(0, len(data["camera"]), stride):
        frame = data["camera"][frame_index]; timestamp = int(frame["timestamp_ns"])
        image = cv2.imread(str(frame["image"]), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError("Missing dataset image")
        image = cv2.undistort(image, K, np.array(data["distortion"]))
        orientation = nearest_orientation(gyro, times, timestamp)
        truth = nearest(data["ground_truth"], truth_times, timestamp)
        if previous is not None:
            prev_image, prev_orientation, prev_truth = previous
            points = cv2.goodFeaturesToTrack(prev_image, maxCorners=600, qualityLevel=.01, minDistance=8)
            if points is not None and orientation and prev_orientation:
                body_delta = orientation["rotation"].inv() * prev_orientation["rotation"]
                camera_delta = R_BC.inv() * body_delta * R_BC
                H = rotation_homography(K, camera_delta.as_matrix())
                F_gt = None
                if truth is not None and prev_truth is not None:
                    current_R = truth["rotation"] * R_BC; previous_R = prev_truth["rotation"] * R_BC
                    current_p = np.array(truth["position"]) + truth["rotation"].apply(data["T_BC"][:3, 3])
                    previous_p = np.array(prev_truth["position"]) + prev_truth["rotation"].apply(data["T_BC"][:3, 3])
                    relative_t = current_R.inv().apply(previous_p - current_p)
                    if np.linalg.norm(relative_t) >= .005:
                        E_gt = skew(relative_t) @ (current_R.inv() * previous_R).as_matrix()
                        F_gt = K_inv.T @ E_gt @ K_inv
                for name in ("rgb_only", "gyro_seeded", "wrong_gyro_sign"):
                    initial = None; flags = 0
                    if name != "rgb_only":
                        matrix = H if name == "gyro_seeded" else np.linalg.inv(H)
                        homogeneous = matrix @ np.c_[points.reshape(-1, 2), np.ones(len(points))].T
                        initial = np.ascontiguousarray((homogeneous[:2] / homogeneous[2]).T.astype(np.float32).reshape(points.shape))
                        flags = cv2.OPTFLOW_USE_INITIAL_FLOW
                    tracked, status, _ = cv2.calcOpticalFlowPyrLK(prev_image, image, points, initial, winSize=(15, 15), maxLevel=2, flags=flags)
                    if tracked is None:
                        continue
                    backward, back_status, _ = cv2.calcOpticalFlowPyrLK(image, prev_image, tracked, None, winSize=(15, 15), maxLevel=2)
                    if backward is None:
                        continue
                    p0, p1 = points.reshape(-1, 2), tracked.reshape(-1, 2)
                    fb = np.linalg.norm(p0 - backward.reshape(-1, 2), axis=1)
                    keep = status.reshape(-1).astype(bool) & back_status.reshape(-1).astype(bool) & (fb < 1.) & (p1[:, 0] >= 0) & (p1[:, 0] < image.shape[1]) & (p1[:, 1] >= 0) & (p1[:, 1] < image.shape[0])
                    epipolar = None
                    if F_gt is not None and keep.any():
                        x0 = np.c_[p0[keep], np.ones(keep.sum())]; x1 = np.c_[p1[keep], np.ones(keep.sum())]
                        Fx = (F_gt @ x0.T).T; Ftx = (F_gt.T @ x1.T).T
                        error = np.abs(np.sum(x1 * Fx, axis=1)) / np.sqrt(np.maximum(1e-18, np.sum(Fx[:, :2] ** 2, axis=1) + np.sum(Ftx[:, :2] ** 2, axis=1)))
                        epipolar = float(np.median(error))
                    records.append({"frame_index": frame_index, "time_s": (timestamp - int(data["camera"][0]["timestamp_ns"])) / 1e9, "variant": name, "attempted": len(points), "fb_consistent": int(keep.sum()),
                                    "fb_median_px": float(np.median(fb[keep])) if keep.any() else None, "gt_sampson_median_px": epipolar})
        previous = (image, orientation, truth)
    if not records:
        raise ValueError("No aligned feature-tracking pairs")
    with (output / "tracking.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0])); writer.writeheader(); writer.writerows(records)
    variants = {}
    for name in ("rgb_only", "gyro_seeded", "wrong_gyro_sign"):
        selected = [row for row in records if row["variant"] == name]
        epipolar = [row["gt_sampson_median_px"] for row in selected if row["gt_sampson_median_px"] is not None]
        variants[name] = {"pairs": len(selected), "attempted_features": sum(row["attempted"] for row in selected), "fb_consistent_features": sum(row["fb_consistent"] for row in selected),
                          "fb_consistent_fraction": sum(row["fb_consistent"] for row in selected) / sum(row["attempted"] for row in selected), "median_pair_gt_sampson_px": float(np.median(epipolar)) if epipolar else None}
    report = {"dataset": "Real EuRoC V1_01_easy subset", "camera_stride": stride, "gyro_bias_assumption": quiet, "variants": variants,
              "ground_truth_usage": "epipolar residual evaluation only, never flow initialization", "limits": ["Feature tracking, not semantic road-user tracking or full VIO", "Forward-backward consistency and epipolar residual do not prove exact landmark identity", "Wrong gyro sign is a deliberate negative control", "Rotation-only initialization ignores translation, rolling shutter and bias/calibration error"]}
    (output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__); cli.add_argument("--dataset", default=".tools/datasets/euroc-v101"); cli.add_argument("--output", default=".tools/experiments/gyro-flow-ablation")
    args = cli.parse_args()
    try:
        print(json.dumps(run(args.dataset, args.output)))
    except (ValueError, OSError, RuntimeError) as error:
        cli.exit(1, f"{error}\n")
