"""EuRoC gyro, essential-matrix VO and attitude-only visual-inertial fusion experiment.

This supporting Week 3 demo is not a complete metric VIO/SLAM implementation.
Ground truth is used only for evaluation and a fixed initial orientation alignment.
"""
import argparse
from bisect import bisect_left
from collections import Counter
import csv
import json
from pathlib import Path
import sys
import time
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from scipy.spatial.transform import Rotation
from evaluation.euroc import load_euroc
from localization.orientation import find_initial_quiet_window, integrate_gyro, nearest_orientation, blend_rotation
from localization.vo import EssentialVisualOdometry


def nearest_truth(truth, timestamps, target):
    index = bisect_left(timestamps, target)
    candidates = [i for i in (index - 1, index) if 0 <= i < len(truth)]
    if not candidates:
        return None
    best = min(candidates, key=lambda i: abs(timestamps[i] - target))
    return truth[best] if abs(timestamps[best] - target) <= 10000000 else None


def euler_yaw(rotation):
    # Quaternion/rotation estimates remain authoritative near Euler singularities.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return float(rotation.as_euler("ZYX")[0])


def run(args):
    if args.max_frames < 1 or args.threads < 1 or not 0 <= args.visual_gain <= 1:
        raise ValueError("Positive frame/thread counts and visual gain within [0,1] are required")
    cv2.setNumThreads(args.threads)
    cv2.setRNGSeed(42)
    data = load_euroc(args.dataset, args.max_frames)
    output = Path(args.output); output.mkdir(parents=True, exist_ok=True)
    static = find_initial_quiet_window(data["imu"])
    bias = static["gyro_bias_rad_s"] if static["accepted"] else [0., 0., 0.]
    corrected = integrate_gyro(data["imu"], bias)
    uncorrected = integrate_gyro(data["imu"])
    timestamps = [int(value["timestamp_ns"]) for value in corrected]
    gt_times = [int(value["timestamp_ns"]) for value in data["ground_truth"]]
    R_BC = Rotation.from_matrix(data["T_BC"][:3, :3])
    vo = EssentialVisualOdometry(data["K"], data["distortion"])
    visual_rotation, fused_rotation = Rotation.identity(), Rotation.identity()
    visual_position = np.zeros(3); previous_gyro = None; vo_continuous = True
    alignments = {}; first = int(data["camera"][0]["timestamp_ns"])
    records = []; reasons = Counter(); start = time.perf_counter()
    with (output / "motion.jsonl").open("w", encoding="utf-8") as log:
        for frame_index, frame in enumerate(data["camera"]):
            timestamp = int(frame["timestamp_ns"]); image = cv2.imread(str(frame["image"]), cv2.IMREAD_GRAYSCALE)
            if image is None:
                raise ValueError(f"Missing EuRoC frame: {frame['image']}")
            step_start = time.perf_counter(); visual = vo.update(image)
            reasons[visual["reason"]] += 1
            gyro = nearest_orientation(corrected, timestamps, timestamp)
            raw = nearest_orientation(uncorrected, timestamps, timestamp)
            fusion = {"visual_used": False, "reason": "no valid visual rotation"}
            predicted_dx = None
            if visual["valid"]:
                visual_position += visual_rotation.apply(visual["translation_direction"])
                visual_rotation = visual_rotation * visual["rotation_delta"]
            elif frame_index > 0:
                vo_continuous = False
            if gyro and previous_gyro and gyro["continuous"] and previous_gyro["continuous"]:
                body_delta = previous_gyro["rotation"].inv() * gyro["rotation"]
                camera_delta = R_BC.inv() * body_delta * R_BC
                predicted_dx = -float(data["K"][0, 0]) * float(camera_delta.as_rotvec()[1])
                if visual["valid"]:
                    camera_delta, fusion = blend_rotation(camera_delta, visual["rotation_delta"], args.visual_gain)
                fused_rotation = fused_rotation * camera_delta
            elif frame_index > 0:
                fusion["reason"] = "missing/discontinuous gyro interval"
            previous_gyro = gyro
            truth = nearest_truth(data["ground_truth"], gt_times, timestamp)
            row = {"frame_index": frame_index, "timestamp_ns": str(timestamp), "time_s": (timestamp - first) / 1e9,
                   "gyro_available": gyro is not None, "gyro_bias_assumption_accepted": static["accepted"], "gyro_continuous": gyro["continuous"] if gyro else False,
                   "vo_valid": visual["valid"], "vo_continuous": vo_continuous, "vo_reason": visual["reason"], "vo_tracked_features": visual["tracked_features"], "vo_inlier_fraction": visual["inlier_fraction"],
                   "vo_position_arbitrary_scale": visual_position.tolist(), "fused_quaternion_xyzw": fused_rotation.as_quat().tolist(), "fusion": fusion,
                   "vo_and_fusion_ms": (time.perf_counter() - step_start) * 1000}
            row["optical_flow_median_dx_px"] = visual.get("median_flow_dx_px")
            row["gyro_rotation_only_center_dx_px"] = predicted_dx
            row["gyro_relative_body_quaternion_xyzw"] = gyro["quaternion_xyzw"] if gyro else None
            estimates = {"vo": visual_rotation, "fused": fused_rotation}
            if gyro:
                estimates["gyro"] = gyro["rotation"] * R_BC
            if raw:
                estimates["gyro_uncorrected"] = raw["rotation"] * R_BC
            if truth is not None:
                true_camera = truth["rotation"] * R_BC
                row["ground_truth_yaw_rad"] = euler_yaw(true_camera)
                for name, estimate in estimates.items():
                    if name not in alignments:
                        alignments[name] = true_camera * estimate.inv()
                    aligned = alignments[name] * estimate
                    row[name + "_yaw_rad"] = euler_yaw(aligned)
                    row[name + "_orientation_error_deg"] = float((true_camera.inv() * aligned).magnitude() * 180 / np.pi)
            # Exclude Python/Scipy objects from JSON, retain per-frame provenance and missing conditions.
            log.write(json.dumps(row, allow_nan=False) + "\n"); records.append(row)
            if len(records) % 100 == 0:
                print(f"Motion frames {len(records)}", file=sys.stderr, flush=True)
    correlation_rows = [row for row in records if row["optical_flow_median_dx_px"] is not None and row["gyro_rotation_only_center_dx_px"] is not None]
    measured_flow = [row["optical_flow_median_dx_px"] for row in correlation_rows]
    predicted_flow = [row["gyro_rotation_only_center_dx_px"] for row in correlation_rows]
    correlation = float(np.corrcoef(measured_flow, predicted_flow)[0, 1]) if len(correlation_rows) > 2 and np.std(measured_flow) > 1e-12 and np.std(predicted_flow) > 1e-12 else None
    summary = {"dataset": "EuRoC MAV V1_01_easy subset", "frames": len(records), "imu_samples": len(data["imu"]), "gyro_bias_estimate": static,
               "gyro_optical_flow_correlation": {"pearson_r": correlation, "pairs": len(correlation_rows), "model": "small-rotation center dx=-fx*delta_camera_y; translation, off-center bearings and dynamic objects also affect observed flow"},
               "ground_truth_usage": "evaluation only; one fixed initial orientation alignment per estimator; no GT bias/pose feedback", "camera_imu_extrinsics": data["T_BC"].tolist(),
               "visual_gain": args.visual_gain, "visual_updates_accepted": sum(row["fusion"]["visual_used"] for row in records), "vo_accepted_frames": sum(row["vo_valid"] for row in records),
               "vo_failure_reasons": dict(reasons), "wall_s": time.perf_counter() - start,
               "orientation_error_deg": {name: {"mean": float(np.mean(values)), "max": float(max(values))} for name in ("gyro_uncorrected", "gyro", "vo", "fused") if (values := [row[name + "_orientation_error_deg"] for row in records if name + "_orientation_error_deg" in row])},
               "limitations": ["Attitude-only complementary visual-inertial experiment; not full VIO or SLAM", "VO translation has arbitrary scale and skipped intervals; no validated metric trajectory", "VO accumulated orientation loses continuity at rejected frames; its errors include those failures", "Initial stationary-window bias is an assumption, not an independent calibration", "Euler yaw is for visualization; quaternion/rotation error is authoritative near gimbal lock", "Dynamic points, planar scenes, blur and low parallax can invalidate essential-matrix pose"]}
    (output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8")
    write_plots(output, records, data["imu"], first, static)
    return summary


def write_plots(output, records, imu, origin, quiet=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure, axes = plt.subplots(6, 1, figsize=(12, 16), layout="constrained")
    imu_time = [(int(value["timestamp_ns"]) - origin) / 1e9 for value in imu]
    for i, axis in enumerate("xyz"):
        axes[0].plot(imu_time, [value["angular_velocity"][i] for value in imu], label=axis, linewidth=.7)
        axes[1].plot(imu_time, [value["acceleration"][i] for value in imu], label=axis, linewidth=.7)
    axes[0].set(ylabel="rad/s", title="Real EuRoC body-frame gyro; initial bias assumption reported separately")
    axes[1].set(ylabel="m/s²", title="Real EuRoC specific force; not vehicle acceleration")
    if quiet and quiet["accepted"]:
        offset = (int(imu[0]["timestamp_ns"]) - origin) / 1e9
        for ax in axes[:2]:
            ax.axvspan(offset + quiet["start_offset_s"], offset + quiet["end_offset_s"], color="gold", alpha=.3,
                       label="assumed quiet bias window; not proven stationary")
    for name in ("ground_truth", "gyro_uncorrected", "gyro", "vo", "fused"):
        selected = [row for row in records if name + "_yaw_rad" in row]
        if selected:
            axes[2].plot([row["time_s"] for row in selected], np.unwrap([row[name + "_yaw_rad"] for row in selected]) * 180 / np.pi, label=name, linewidth=.9)
        if name != "ground_truth":
            selected = [row for row in records if name + "_orientation_error_deg" in row]
            axes[3].plot([row["time_s"] for row in selected], [row[name + "_orientation_error_deg"] for row in selected], label=name, linewidth=.9)
    axes[2].set(ylabel="Yaw (deg)", title="Fixed initial GT alignment for evaluation; camera yaw is not phone/car heading")
    axes[3].set(ylabel="SO(3) error (deg)", xlabel="Seconds since first selected camera frame", title="Orientation error; failed VO intervals remain part of the result")
    disagreements = [row for row in records if "disagreement_deg" in row["fusion"]]
    axes[4].scatter([row["time_s"] for row in disagreements], [row["fusion"]["disagreement_deg"] for row in disagreements], s=5, label="per-frame gyro/VO rotation disagreement")
    axes[4].axhline(8, linestyle="--", color="gray", label="visual update gate (8 deg)")
    axes[4].set(ylabel="Degrees", xlabel="Seconds", title="Rotation disagreement; missing visual estimates are omitted")
    for key, label in (("optical_flow_median_dx_px", "measured median horizontal flow"), ("gyro_rotation_only_center_dx_px", "gyro small-rotation center prediction")):
        selected = [row for row in records if row[key] is not None]
        axes[5].plot([row["time_s"] for row in selected], [row[key] for row in selected], label=label, linewidth=.8)
    axes[5].set(ylabel="Pixels / frame", xlabel="Seconds", title="Optical flow and calibrated camera-axis gyro cue; not world velocity")
    for ax in axes:
        ax.legend(fontsize=8, ncols=5); ax.grid(alpha=.2)
    figure.suptitle("Public visual-inertial dataset demonstration: gyro, monocular VO and attitude-only fusion")
    figure.savefig(output / "motion.svg"); figure.savefig(output / "motion.png", dpi=150); plt.close(figure)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=".tools/datasets/euroc-v101")
    parser.add_argument("--output", default=".tools/experiments/motion-euroc")
    parser.add_argument("--max-frames", type=int, default=600)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--visual-gain", type=float, default=.2)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args)))
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"{error}\n")
