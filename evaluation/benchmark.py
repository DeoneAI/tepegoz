"""Summarize recorded runs without turning continuity proxies into ground-truth accuracy."""
from collections import Counter
import csv
import json
from pathlib import Path


def summarize_run(directory):
    directory = Path(directory)
    run = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    if not run.get("code_sha256") or run.get("code_changed_during_run"):
        raise ValueError(f"Run has missing/changed code provenance: {directory}")
    observations = Counter(); predicted = 0; classes = Counter()
    for line in (directory / "tracks.jsonl").read_text(encoding="utf-8").splitlines():
        for track in json.loads(line)["tracks"]:
            if track["observed"]:
                observations[track["track_id"]] += 1
            else:
                predicted += 1
    for line in (directory / "detections.jsonl").read_text(encoding="utf-8").splitlines():
        for detection in json.loads(line)["detections"]:
            classes[detection["class_name"]] += 1
    count = run["frames"]
    row = {"scene": Path(run["source"]).stem, "mode": run["config"]["mode"], "depth": run["config"]["depth"], "prediction": not run["config"]["no_prediction"],
           "frames": count, "first_frame_index": run["first_frame_index"], "last_frame_index": run["last_frame_index"], "source_fps": run["source_fps"],
           "wall_s": run["runtime"]["wall_s_excluding_model_load"], "combined_fps": run["runtime"]["combined_fps_including_decode_render_save"],
           "detections_per_frame": run["detections"] / count, "track_ids_observed": len(observations), "short_tracks_at_most_2_observations": sum(n <= 2 for n in observations.values()),
           "predicted_track_records": predicted, "mean_observations_per_track": sum(observations.values()) / len(observations) if observations else None,
           "ground_truth_id_switches": None, "ground_truth_map": None}
    for name, available in run["lane_available_frames"].items():
        row[f"lane_{name}_available_fraction"] = available / count
    for name, timing in run["runtime"]["module_timings"].items():
        row[name + "_mean"] = timing["mean_ms"]; row[name + "_p95"] = timing["p95_ms"]
    for name, value in run.get("depth_temporal_change", {}).items():
        row[f"depth_{name}_unregistered_normalized_change"] = value
    return {"metrics": row, "detection_class_counts": dict(classes), "hardware": run["hardware"], "model_hashes": {name: data["sha256"] for name, data in run["models"].items()},
            "code_hashes": run["code_sha256"], "depth_contracts": run.get("depth_contracts", {}),
            "limits": ["Availability is not lane accuracy", "Track fragmentation proxies are not labeled ID switches", "No mAP without independently labeled ground truth", "Runtime includes decode/render/save and excludes model load"]}


def export_benchmarks(directories, output):
    results = [summarize_run(directory) for directory in directories]
    output = Path(output); output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(key for result in results for key in result["metrics"]))
    with output.with_suffix(".csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(result["metrics"] for result in results)
    output.with_suffix(".json").write_text(json.dumps(results, indent=2, allow_nan=False), encoding="utf-8")
    return results
