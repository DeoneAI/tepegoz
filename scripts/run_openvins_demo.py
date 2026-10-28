"""Run pinned OpenVINS on public EuRoC inputs in Docker, then evaluate without feedback."""
import argparse
from bisect import bisect_left
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from scipy.spatial.transform import Rotation
from evaluation.euroc import load_euroc

IMAGE = "tepegoz-openvins:6948812"
REVISION = "69488123ed9362dd44b6f28e7f4680abbff1442b"


def evaluate(dataset, output):
    data = load_euroc(dataset)
    origin = min(int(data["camera"][0]["timestamp_ns"]), int(data["imu"][0]["timestamp_ns"]))
    with (output / "poses.csv").open(encoding="utf-8") as stream:
        poses = list(csv.DictReader(stream))
    truth = data["ground_truth"]; timestamps = [int(value["timestamp_ns"]) for value in truth]
    matched = []
    for pose in poses:
        timestamp = origin + round(float(pose["time_s"]) * 1e9)
        index = bisect_left(timestamps, timestamp)
        candidates = [i for i in (index - 1, index) if 0 <= i < len(timestamps)]
        if not candidates:
            continue
        best = min(candidates, key=lambda i: abs(timestamps[i] - timestamp))
        if abs(timestamps[best] - timestamp) <= 10000000:
            matched.append((pose, truth[best], (timestamps[best] - timestamp) / 1e6))
    if len(matched) < 2:
        raise ValueError("Insufficient initialized VIO/reference overlap")
    estimated_positions = np.array([[float(pose[key]) for key in ("px", "py", "pz")] for pose, _, _ in matched])
    estimated_rotations = Rotation.from_quat([[float(pose[key]) for key in ("qx", "qy", "qz", "qw")] for pose, _, _ in matched])
    true_positions = np.array([value["position"] for _, value, _ in matched])
    true_rotations = Rotation.concatenate([value["rotation"] for _, value, _ in matched])
    alignment = true_rotations[0] * estimated_rotations[0].inv()
    offset = true_positions[0] - alignment.apply(estimated_positions[0])
    aligned_positions = alignment.apply(estimated_positions) + offset
    aligned_rotations = alignment * estimated_rotations
    position_error = np.linalg.norm(aligned_positions - true_positions, axis=1)
    orientation_error = (true_rotations.inv() * aligned_rotations).magnitude() * 180 / np.pi
    times = np.array([float(pose["time_s"]) for pose, _, _ in matched])
    report = {"dataset": "EuRoC V1_01_easy selected cam0/IMU subset", "estimator": "OpenVINS mono MSCKF with local SLAM features, fixed supplied camera calibration",
              "upstream_commit": REVISION, "source_camera_frames": len(data["camera"]), "initialized_poses": len(poses), "matched_reference_poses": len(matched),
              "first_matched_pose_s": float(times[0]), "last_matched_pose_s": float(times[-1]), "original_origin_timestamp_ns": str(origin),
              "ground_truth_usage": "Evaluation only after the isolated estimator exits; one fixed first-matched-pose SE(3) alignment, no scale fit or trajectory-wide alignment; no GT initialization/feedback",
              "alignment_rotation": alignment.as_matrix().tolist(), "alignment_translation_m": offset.tolist(), "alignment_scale": 1,
              "reference_matching": {"method": "nearest provided ground-truth sample, maximum 10 ms; no interpolated reference", "max_abs_delta_ms": max(abs(delta) for _, _, delta in matched)},
              "position_error_m": {"rmse": float(np.sqrt(np.mean(position_error ** 2))), "mean": float(position_error.mean()), "max": float(position_error.max()), "final": float(position_error[-1])},
              "orientation_error_deg": {"mean": float(orientation_error.mean()), "max": float(orientation_error.max()), "final": float(orientation_error[-1])},
              "limitations": ["Only a short public monochrome dataset subset, not phone/road acceptance", "Mono VIO, not a global loop-closing/relocalizing SLAM demonstration", "Initial static initialization is stock OpenVINS; initialization delay remains visible", "No GT read by the C++ runner; CSV positions have estimator scale before evaluation", "Docker wall time includes startup, decode and mounted-file I/O; not a matched speed comparison with Windows ONNX runs"]}
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(12, 9), layout="constrained")
    axes[0, 0].plot(true_positions[:, 0], true_positions[:, 1], label="reference")
    axes[0, 0].plot(aligned_positions[:, 0], aligned_positions[:, 1], label="mono OpenVINS")
    axes[0, 0].set(xlabel="World X (m)", ylabel="World Y (m)", title="One fixed initial-pose alignment; scale=1"); axes[0, 0].axis("equal"); axes[0, 0].legend()
    axes[0, 1].plot(times, position_error); axes[0, 1].set(xlabel="Dataset-relative seconds", ylabel="Position error (m)", title="Uninitialized frames are not estimates")
    axes[1, 0].plot(times, orientation_error); axes[1, 0].set(xlabel="Dataset-relative seconds", ylabel="SO(3) error (degrees)", title="Reference used only after estimation")
    for axis, key in enumerate(("bgx", "bgy", "bgz")):
        axes[1, 1].plot(times, [float(pose[key]) for pose, _, _ in matched], label="xyz"[axis])
    axes[1, 1].set(xlabel="Dataset-relative seconds", ylabel="Estimated gyro bias (rad/s)", title="Online bias state, not GT bias"); axes[1, 1].legend()
    for ax in axes.flat:
        ax.grid(alpha=.2)
    fig.suptitle("Independent pinned OpenVINS demonstration: real public camera + IMU")
    fig.savefig(output / "openvins.png", dpi=150); fig.savefig(output / "openvins.svg"); plt.close(fig)
    return report


def run(dataset, output, build=True):
    dataset, output = Path(dataset).resolve(), Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output must be empty; preserve earlier evidence")
    if build:
        subprocess.run(["docker", "build", "-t", IMAGE, str(ROOT / "integrations/openvins")], check=True)
    image_info = json.loads(subprocess.run(["docker", "image", "inspect", IMAGE], check=True, capture_output=True, text=True).stdout)[0]
    output.mkdir(parents=True, exist_ok=True)
    command = ["docker", "run", "--rm", "--network", "none", "--cpus", "2", "--mount", f"type=bind,src={dataset},target=/dataset,readonly", "--mount", f"type=bind,src={output},target=/output", IMAGE,
               "/dataset", "/output/poses.csv", "/opt/euroc_mono/estimator_config.yaml"]
    before = time.perf_counter(); result = subprocess.run(command, capture_output=True, text=True); wall = time.perf_counter() - before
    (output / "run.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"OpenVINS exited {result.returncode}; inspect {output / 'run.log'}")
    report = evaluate(dataset, output)
    report.update(docker_image_id=image_info["Id"], wall_s_including_container_and_io=wall,
                  adapter_sha256={file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in (ROOT / "integrations/openvins").iterdir() if file.is_file()},
                  dataset_selection_sha256=hashlib.sha256((dataset / "camera_selection.csv").read_bytes()).hexdigest())
    (output / "summary.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__); cli.add_argument("--dataset", default=".tools/datasets/euroc-v101"); cli.add_argument("--output", required=True); cli.add_argument("--skip-build", action="store_true")
    args = cli.parse_args()
    try:
        print(json.dumps(run(args.dataset, args.output, not args.skip_build)))
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as error:
        cli.exit(1, f"{error}\n")
