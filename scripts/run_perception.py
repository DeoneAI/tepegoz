"""Run indexed lane/detection/tracking baselines on saved phone frames or a recorded video."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import platform
import os
import sys
import time
from contextlib import ExitStack

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from perception.lanes import ClassicalLaneDetector
from perception.depth import DepthAnythingOnnx, box_depth, normalize_relative, render_depth
from perception.models import YoloPLaneDetector, YoloXDetector, ROAD_CLASSES
from perception.motion_input import SessionRotationCompensation
from perception.render import render_overlay
from perception.sequence import FrameSequence
from perception.tracking import BoxTracker


def run(args):
    cv2.setNumThreads(args.threads)
    code_files = [Path(__file__).resolve(), *sorted((Path(__file__).resolve().parents[1] / "perception").glob("*.py")), *sorted((Path(__file__).resolve().parents[1] / "localization").glob("*.py"))]
    code_hashes = {file.relative_to(Path(__file__).resolve().parents[1]).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest() for file in code_files}
    sequence = FrameSequence(args.source, args.stride, args.max_frames)
    output = Path(args.output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory must be empty; use a new run directory to preserve previous evidence")
    if output == sequence.source or output == sequence.source / "frames":
        raise ValueError("Do not write analysis over source recordings")
    models = {}; lanes = {}
    if args.mode not in {"objects", "depth"}:
        if args.lanes in {"classical", "both"}:
            lanes["classical"] = ClassicalLaneDetector()
        if args.lanes in {"yolop", "both"}:
            lanes["yolop"] = YoloPLaneDetector(args.lane_model, args.threads); models["lane"] = args.lane_model
    detector = None
    if args.mode not in {"lanes", "depth"}:
        detector = YoloXDetector(args.detector_model, args.confidence, args.nms_iou, args.threads); models["detector"] = args.detector_model
    compensation = None
    if args.imu_assist:
        if not sequence.source.is_dir() or not args.calibration or detector is None:
            raise ValueError("IMU-assisted tracking needs a finalized session, --calibration and object tracking")
        compensation = SessionRotationCompensation(sequence.source, args.calibration)
    depth_models = {}
    for name in ("relative", "metric"):
        if args.depth in {name, "both"}:
            model_path = args.relative_depth_model if name == "relative" else args.metric_depth_model
            depth_models[name] = DepthAnythingOnnx(model_path, name, args.depth_input_size, args.threads); models["depth_" + name] = model_path
    tracker = BoxTracker(high_threshold=max(.4, args.confidence), low_threshold=args.confidence, prediction=not args.no_prediction)
    output.mkdir(parents=True, exist_ok=True); (output / "previews").mkdir()
    for name in depth_models:
        (output / ("depth_" + name)).mkdir()
    previous_depth = {}
    rows = []; writer = None; first_time = None; detections_total = 0; lane_available = {name: 0 for name in lanes}
    start_run = time.perf_counter()
    try:
        with ExitStack() as stack:
            logs = {name: stack.enter_context((output / f"{name}.jsonl").open("w", encoding="utf-8")) for name in [*("lanes_" + name for name in lanes), *("depth_" + name for name in depth_models), "detections", "tracks", "camera_motion"]}
            for frame in sequence:
                start = time.perf_counter(); timing = {"frame_index": frame.index, "timestamp_ns": frame.timestamp_ns, "decode_ms": frame.decode_ms}
                metadata = {"frame_index": frame.index, "timestamp_ns": frame.timestamp_ns, "timestamp_source": frame.timestamp_source, "time_basis": sequence.time_basis}
                first_time = int(frame.timestamp_ns) if first_time is None else first_time
                elapsed = (int(frame.timestamp_ns) - first_time) / 1e9
                estimates = {}
                for name, model in lanes.items():
                    before = time.perf_counter(); estimate, mask = model(frame.image); timing[f"lane_{name}_ms"] = (time.perf_counter() - before) * 1000
                    estimates[name] = estimate; lane_available[name] += estimate["confidence"] >= .4
                    logs["lanes_" + name].write(json.dumps({**metadata, **estimate}, allow_nan=False) + "\n")
                before = time.perf_counter(); detections = detector(frame.image) if detector else []; timing["detector_ms"] = (time.perf_counter() - before) * 1000
                detections_total += len(detections)
                before = time.perf_counter()
                H, motion = compensation.for_frame(frame.timestamp_ns, frame.image.shape) if compensation else (None, {"used": False, "reason": "disabled"})
                tracks = tracker.update(detections, elapsed, H) if detector else []; timing["tracker_ms"] = (time.perf_counter() - before) * 1000
                logs["camera_motion"].write(json.dumps({**metadata, **motion}) + "\n")
                logs["detections"].write(json.dumps({**metadata, "detections": detections}, allow_nan=False) + "\n")
                depth_panels = []
                for name, model in depth_models.items():
                    before = time.perf_counter(); depth = model(frame.image); timing[f"depth_{name}_ms"] = (time.perf_counter() - before) * 1000
                    before_post = time.perf_counter()
                    contract = model.contract(); objects = []
                    for track in tracks:
                        associated = box_depth(depth, track["xyxy"], model.units) if track["observed"] else None
                        track.setdefault("depth", {})[name] = associated
                        objects.append({"track_id": track["track_id"], "observed": track["observed"], "depth": associated})
                    normalized, _ = normalize_relative(depth)
                    if name in previous_depth and previous_depth[name].shape == normalized.shape:
                        timing[f"depth_{name}_normalized_change"] = float(np.mean(np.abs(normalized - previous_depth[name])))
                    previous_depth[name] = normalized
                    map_file = f"depth_{name}/{frame.index:08d}.npz"
                    before = time.perf_counter(); np.savez_compressed(output / map_file, depth=depth); timing[f"depth_{name}_save_ms"] = (time.perf_counter() - before) * 1000
                    logs["depth_" + name].write(json.dumps({**metadata, **contract, "map_file": map_file, "objects": objects,
                                                           "detections": [box_depth(depth, detection["xyxy"], model.units) for detection in detections]}, allow_nan=False) + "\n")
                    depth_panels.append(render_depth(depth, contract, f"{name} depth | frame {frame.index}"))
                    timing[f"depth_{name}_postprocess_ms"] = (time.perf_counter() - before_post) * 1000 - timing[f"depth_{name}_save_ms"]
                logs["tracks"].write(json.dumps({**metadata, "tracks": tracks}, allow_nan=False) + "\n")
                before = time.perf_counter()
                panels = [render_overlay(frame.image, estimate, tracks, f"{name} | frame {frame.index} | {elapsed:.3f}s") for name, estimate in estimates.items()]
                if not panels:
                    panels = [render_overlay(frame.image, None, tracks, f"RGB + tracks | frame {frame.index} | {elapsed:.3f}s")]
                panels.extend(depth_panels)
                if len(panels) > 2:
                    if len(panels) % 2:
                        panels.append(np.zeros_like(frame.image))
                    display = np.vstack([np.hstack(panels[i:i + 2]) for i in range(0, len(panels), 2)])
                else:
                    display = np.hstack(panels)
                timing["render_ms"] = (time.perf_counter() - before) * 1000
                before = time.perf_counter()
                if writer is None:
                    fps = sequence.fps / args.stride if sequence.fps else 10
                    writer = cv2.VideoWriter(str(output / "overlay.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), fps, (display.shape[1], display.shape[0]))
                    if not writer.isOpened():
                        raise ValueError("Video encoder unavailable")
                writer.write(display)
                if len(rows) % args.preview_every == 0:
                    if not cv2.imwrite(str(output / "previews" / f"{frame.index:08d}.jpg"), display):
                        raise OSError("Could not write preview image")
                timing["save_ms"] = (time.perf_counter() - before) * 1000
                timing["total_processing_ms"] = (time.perf_counter() - start) * 1000 + frame.decode_ms
                rows.append(timing)
                if len(rows) % 25 == 0:
                    print(f"Processed {len(rows)} frames", file=sys.stderr, flush=True)
    finally:
        if writer is not None:
            writer.release()
    elapsed_wall = time.perf_counter() - start_run
    if not rows:
        raise ValueError("Input contains no readable frames")
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with (output / "benchmark.csv").open("w", newline="", encoding="utf-8") as stream:
        csv_writer = csv.DictWriter(stream, fieldnames=fields); csv_writer.writeheader(); csv_writer.writerows(rows)
    timings = {key: {"mean_ms": float(np.mean([row[key] for row in rows if key in row])), "p95_ms": float(np.percentile([row[key] for row in rows if key in row], 95))} for key in fields if key.endswith("_ms")}
    manifest = {"schema_version": 1, "source": str(sequence.source), "time_basis": sequence.time_basis, "source_fps": sequence.fps, "frames": len(rows), "first_frame_index": rows[0]["frame_index"], "last_frame_index": rows[-1]["frame_index"],
                "config": vars(args), "code_sha256": code_hashes,
                "code_changed_during_run": any(hashlib.sha256(file.read_bytes()).hexdigest() != code_hashes[file.relative_to(Path(__file__).resolve().parents[1]).as_posix()] for file in code_files),
                "models": {name: {"path": str(Path(file).resolve()), "bytes": Path(file).stat().st_size, "sha256": hashlib.sha256(Path(file).read_bytes()).hexdigest()} for name, file in models.items()},
                "hardware": {"system": platform.platform(), "cpu": platform.processor(), "logical_cpus": os.cpu_count(), "python": platform.python_version(), "opencv": cv2.__version__, "threads": args.threads, "inference_provider": "CPUExecutionProvider", "gpu_vram_measured_bytes": None,
                             "onnxruntime": getattr(detector, "runtime_version", next((model.runtime_version for model in [*lanes.values(), *depth_models.values()] if hasattr(model, "runtime_version")), None))},
                "runtime": {"wall_s_excluding_model_load": elapsed_wall, "combined_fps_including_decode_render_save": len(rows) / elapsed_wall, "module_timings": timings},
                "detections": detections_total, "lane_available_frames": lane_available, "class_mapping": ROAD_CLASSES,
                "depth_contracts": {name: model.contract() for name, model in depth_models.items()},
                "motion_compensation": compensation.metadata if compensation else {"enabled": False},
                "depth_temporal_change": {name: float(np.mean([row[f'depth_{name}_normalized_change'] for row in rows if f'depth_{name}_normalized_change' in row])) if len(rows) > 1 else None for name in depth_models},
                "preview_timing": "constant FPS media preview; original phone times in JSONL are authoritative" if sequence.fps is None else "source FPS divided by stride",
                "limitations": ["Research baselines: pixel geometry, not calibrated vehicle position or roadworthiness", "Public video media timestamps do not establish phone capture/IMU synchronization", "Predicted tracks are explicitly stale; IDs and confidence are not ground truth", "Depth temporal change is unregistered normalized map change, including true motion; not a pure flicker error", "Learned metric outputs are unvalidated model meters, not independently measured distance"]}
    (output / "run.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    return {"output": str(output), "frames": len(rows), "fps": manifest["runtime"]["combined_fps_including_decode_render_save"]}


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("source", help="finalized phone session directory or recorded video")
    cli.add_argument("--output", required=True)
    cli.add_argument("--mode", choices=("lanes", "objects", "depth", "combined"), default="combined")
    cli.add_argument("--lanes", choices=("classical", "yolop", "both"), default="both")
    cli.add_argument("--lane-model", default=".tools/models/yolop-320-320.onnx")
    cli.add_argument("--detector-model", default=".tools/models/yolox_tiny.onnx")
    cli.add_argument("--depth", choices=("none", "relative", "metric", "both"), default="none")
    cli.add_argument("--relative-depth-model", default=".tools/models/depth_anything_v2_vits_dynamic.onnx")
    cli.add_argument("--metric-depth-model", default=".tools/models/depth_anything_v2_vits_outdoor_dynamic.onnx")
    cli.add_argument("--depth-input-size", type=int, default=518, help="dynamic model long edge, multiple of 14")
    cli.add_argument("--confidence", type=float, default=.25)
    cli.add_argument("--nms-iou", type=float, default=.45)
    cli.add_argument("--threads", type=int, default=4)
    cli.add_argument("--stride", type=int, default=1)
    cli.add_argument("--max-frames", type=int)
    cli.add_argument("--preview-every", type=int, default=30)
    cli.add_argument("--no-prediction", action="store_true", help="tracker ablation: no Kalman motion transition")
    cli.add_argument("--imu-assist", action="store_true", help="rotation-only tracking compensation from same-session gyro; measured calibration required")
    cli.add_argument("--calibration", help="camera intrinsics, camera-to-body rotation and saved image size JSON")
    return cli


if __name__ == "__main__":
    try:
        options = parser().parse_args()
        if options.mode == "depth" and options.depth == "none":
            options.depth = "relative"
        if not 0 < options.confidence <= 1 or not 0 <= options.nms_iou <= 1 or options.threads < 1 or options.preview_every < 1:
            raise ValueError("Invalid confidence, NMS, thread or preview setting")
        print(json.dumps(run(options)))
    except (ValueError, OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr); sys.exit(1)
