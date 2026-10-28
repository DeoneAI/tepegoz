"""Inspect finalized camera/IMU recordings and export alignment evidence without changing raw logs."""
import argparse
from bisect import bisect_left
from collections import Counter
import csv
import json
import math
from pathlib import Path
import re
from statistics import median


SENSORS = ("accelerometer", "linear_acceleration", "gyroscope", "gnss")
REQUIRED = ("accelerometer", "gyroscope")


def read_records(file):
    records = []
    with file.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError("expected a JSON object")
                if not isinstance(record.get("timestamp_ns"), str) or not re.fullmatch(r"[0-9]{1,18}", record["timestamp_ns"]):
                    raise ValueError("timestamp_ns must be a decimal nanosecond string")
                key = "frame_index" if file.name == "frames.jsonl" else "sequence_id"
                if type(record.get(key)) is not int or record[key] < 0:
                    raise ValueError(f"{key} must be a nonnegative integer")
                if "session_id" in record and not isinstance(record["session_id"], str):
                    raise ValueError("session_id must be a string")
                if "timestamp_source" in record and not isinstance(record["timestamp_source"], str):
                    raise ValueError("timestamp_source must be a string")
                if key == "sequence_id":
                    if record.get("sensor_type") not in SENSORS:
                        raise ValueError("unknown sensor_type")
                    expected_unit = {"accelerometer": "m_s2", "linear_acceleration": "m_s2", "gyroscope": "rad_s", "gnss": "deg_m_mps"}[record["sensor_type"]]
                    if record.get("units") != expected_unit:
                        raise ValueError(f"{record['sensor_type']} units must be {expected_unit}")
                    if record["sensor_type"] != "gnss":
                        values = record.get("values")
                        if not isinstance(values, dict) or not all(type(values.get(axis)) in (int, float) and math.isfinite(values[axis]) for axis in "xyz"):
                            raise ValueError("inertial axes must be finite numbers")
                records.append(record)
            except (ValueError, TypeError) as error:
                raise ValueError(f"{file.name}:{number}: {error}") from error
    return records


def stream_stats(records, key):
    ids = sorted({record[key] for record in records})
    times = [int(record["timestamp_ns"]) for record in records]
    span = (max(times) - min(times)) / 1e9 if times else 0
    gaps = ids[0] + sum(max(0, b - a - 1) for a, b in zip(ids, ids[1:])) if ids else 0
    return {
        "count": len(records), "span_s": span,
        "observed_hz": (len(records) - 1) / span if len(records) > 1 and span > 0 else None,
        "sequence_gaps": gaps, "duplicate_ids": len(records) - len(ids),
        "timestamp_regressions": sum(b < a for a, b in zip(times, times[1:])),
    }


def nearest_sample(samples, times, target, max_gap_ns):
    index = bisect_left(times, target)
    candidates = [i for i in (index - 1, index) if 0 <= i < len(times)]
    if not candidates:
        return None
    # The earlier sample wins a tie, as in PC and browser replay.
    best = min(candidates, key=lambda i: abs(times[i] - target))
    delta = times[best] - target
    if abs(delta) > max_gap_ns:
        return None
    return {"sequence_id": samples[best]["sequence_id"], "timestamp_ns": samples[best]["timestamp_ns"], "delta_ms": delta / 1e6}


def analyze_session(directory, max_gap_ms=100):
    if not math.isfinite(max_gap_ms) or max_gap_ms <= 0:
        raise ValueError("max_gap_ms must be finite and positive")
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") not in {"completed", "interrupted"}:
        raise ValueError("Stop & save the session before analysis; active recordings are not stable input.")
    if manifest.get("storage_error"):
        raise ValueError("Inspect and repair this session's storage error before analysis.")
    raw_frames = read_records(directory / "frames.jsonl")
    samples = read_records(directory / "telemetry.jsonl")
    session_ids = {record["session_id"] for record in [*raw_frames, *samples] if "session_id" in record}
    if len(session_ids) > 1 or (session_ids and manifest.get("id") and session_ids != {manifest["id"]}):
        raise ValueError("Recording contains conflicting session IDs; do not align different phone-clock sessions.")
    frames = sorted(raw_frames, key=lambda frame: (int(frame["timestamp_ns"]), frame["frame_index"]))
    groups = {sensor: [sample for sample in samples if sample["sensor_type"] == sensor] for sensor in SENSORS}
    stats = {sensor: stream_stats(group, "sequence_id") for sensor, group in groups.items()}
    for group in groups.values():
        group.sort(key=lambda sample: (int(sample["timestamp_ns"]), sample["sequence_id"]))
    times = {sensor: [int(sample["timestamp_ns"]) for sample in group] for sensor, group in groups.items()}
    alignments = []
    for frame in frames:
        target = int(frame["timestamp_ns"])
        alignments.append({"frame_index": frame["frame_index"], "timestamp_ns": frame["timestamp_ns"], "timestamp_source": frame.get("timestamp_source", "unspecified"),
                           "sensors": {sensor: nearest_sample(groups[sensor], times[sensor], target, round(max_gap_ms * 1e6)) for sensor in SENSORS}})
    coverage = {}
    for sensor in SENSORS:
        deltas = sorted(abs(row["sensors"][sensor]["delta_ms"]) for row in alignments if row["sensors"][sensor] is not None)
        coverage[sensor] = {"matched_frames": len(deltas), "missing_frames": len(frames) - len(deltas),
                            "max_abs_delta_ms": max(deltas) if deltas else None,
                            "p95_abs_delta_ms": deltas[math.floor((len(deltas) - 1) * .95)] if deltas else None}
    frame_names = {f"{frame['frame_index']:08d}.jpg" for frame in frames}
    actual_names = {file.name for file in (directory / "frames").glob("*.jpg") if file.is_file()}
    missing_files, orphan_files = sorted(frame_names - actual_names), sorted(actual_names - frame_names)
    frame_times = [int(frame["timestamp_ns"]) for frame in frames]
    origin = min([*frame_times, *(time for values in times.values() for time in values)], default=0)
    streams = [frame_times, *(times[sensor] for sensor in REQUIRED)]
    overlap = max(0, min(max(values) for values in streams) - max(min(values) for values in streams)) / 1e9 if all(streams) else 0
    frame_stats = stream_stats(raw_frames, "frame_index")
    checks = {
        "completed_session": manifest["status"] == "completed",
        "required_streams_present": bool(frames) and all(groups[sensor] for sensor in REQUIRED),
        "common_overlap_at_least_120_s": overlap >= 120,
        "all_frames_have_required_imu_match": bool(frames) and all(coverage[sensor]["missing_frames"] == 0 for sensor in REQUIRED),
        "frame_files_consistent": not missing_files and not orphan_files,
        "sequence_integrity": all(not stream[key] for stream in [frame_stats, *stats.values()] for key in ("duplicate_ids", "timestamp_regressions", "sequence_gaps")),
    }
    warnings = [f"No {sensor} samples recorded." for sensor in REQUIRED if not groups[sensor]]
    if not frames:
        warnings.append("No camera frames recorded.")
    if missing_files or orphan_files:
        warnings.append("JPEG files and frame metadata do not match; inspect missing/orphan files.")
    if not checks["sequence_integrity"]:
        warnings.append("Sequence gaps, duplicate IDs or timestamp regressions were found.")
    if manifest["status"] == "interrupted":
        warnings.append("Interrupted session: counts and file consistency require review.")
    warnings.append("Timestamp association is not hardware synchronization accuracy. Physical acceptance, capture-to-display latency and measured calibration require separate evidence.")
    report = {"session_id": manifest.get("id", directory.name), "name": manifest.get("name", directory.name),
              "status": manifest["status"], "acceptance_status": "requires_physical_validation", "time_basis": manifest.get("time_basis", "same-phone monotonic timestamps; relative seconds for plotting"),
              "source_type": manifest.get("source_type", "phone_recording"), "axes": manifest.get("axes", "recorded phone axes"),
              "origin_timestamp_ns": str(origin), "max_alignment_gap_ms": max_gap_ms, "common_camera_accel_gyro_overlap_s": overlap,
              "frames": frame_stats, "frame_timestamp_sources": dict(Counter(frame.get("timestamp_source", "unspecified") for frame in frames)),
              "sensors": stats, "alignment": coverage, "missing_jpeg_files": missing_files, "orphan_jpeg_files": orphan_files,
              "recorded_metrics": manifest.get("metrics", {}), "calibration": manifest.get("calibration"), "checks": checks, "warnings": warnings}
    return report, frames, groups, alignments


def plot_timeline(report, frames, groups, alignments, output):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise RuntimeError("Install plotting support: python -m pip install -r scripts/requirements-analysis.txt; or use --no-plot.") from error
    origin = int(report["origin_timestamp_ns"])
    seconds = lambda timestamp: (int(timestamp) - origin) / 1e9
    colors = ("#b53c30", "#218454", "#3569ba")
    fig, axes = plt.subplots(4, 1, figsize=(12, 10), sharex=True, layout="constrained")
    fig.suptitle(f"Tepegoz: {report['name']}\nRecorded acquisition time; association only, no hardware timing guarantee", fontsize=13)
    event_groups = (frames, groups["accelerometer"], groups["gyroscope"])
    for row, (name, values) in enumerate(zip(("Camera", "Accelerometer", "Gyroscope"), event_groups)):
        axes[0].eventplot([seconds(record["timestamp_ns"]) for record in values], lineoffsets=row, linelengths=.6, linewidths=.6)
    axes[0].set(yticks=range(3), yticklabels=("Camera", "Accelerometer", "Gyroscope"), title="Recorded events (missing streams stay empty)")
    for ax, sensor, unit in ((axes[1], "accelerometer", "m/s²"), (axes[2], "gyroscope", "rad/s")):
        values = groups[sensor]
        ax.set(ylabel=unit, title=sensor.replace("_", " ").capitalize() + " in recorded sensor axes")
        if not values:
            ax.text(.5, .5, f"No {sensor} samples recorded", ha="center", va="center", transform=ax.transAxes)
            continue
        timestamps = [int(sample["timestamp_ns"]) for sample in values]
        intervals = [b - a for a, b in zip(timestamps, timestamps[1:]) if b > a]
        gap = max(250_000_000, 5 * median(intervals)) if intervals else 250_000_000
        for axis, color in zip("xyz", colors):
            x, y = [], []
            for i, sample in enumerate(values):
                if i and timestamps[i] - timestamps[i - 1] > gap:
                    x.append(float("nan")); y.append(float("nan"))
                x.append(seconds(sample["timestamp_ns"])); y.append(sample["values"][axis])
            ax.plot(x, y, label=axis.upper(), color=color, linewidth=.8, marker=".", markersize=2)
        ax.legend(loc="upper right", ncols=3)
    for sensor, marker, color, missing_y in (("accelerometer", "o", "#218454", .04), ("gyroscope", "x", "#3569ba", .1)):
        matched = [row for row in alignments if row["sensors"][sensor] is not None]
        axes[3].scatter([seconds(row["timestamp_ns"]) for row in matched], [row["sensors"][sensor]["delta_ms"] for row in matched], s=10, marker=marker, color=color, label=sensor)
        missing = [seconds(row["timestamp_ns"]) for row in alignments if row["sensors"][sensor] is None]
        if missing:
            axes[3].scatter(missing, [missing_y] * len(missing), transform=axes[3].get_xaxis_transform(), marker="|", color=color, label=f"{sensor}: missing ({len(missing)})")
    for limit in (-report["max_alignment_gap_ms"], report["max_alignment_gap_ms"]):
        axes[3].axhline(limit, color="gray", linestyle="--", linewidth=.7)
    axes[3].set(xlabel="Seconds since first recorded acquisition event", ylabel="Sample − frame (ms)", title="Nearest sample association; missing markers at the bottom are not measurements")
    axes[3].legend(loc="upper right", fontsize=8)
    for ax in axes:
        ax.grid(alpha=.2)
    try:
        fig.savefig(output / "timeline.svg")
        fig.savefig(output / "timeline.png", dpi=160)
    finally:
        plt.close(fig)


def export_analysis(directory, output=None, max_gap_ms=100, make_plot=True):
    report, frames, groups, alignments = analyze_session(directory, max_gap_ms)
    output = Path(output) if output else Path(directory) / "analysis"
    output.mkdir(parents=True, exist_ok=True)
    if make_plot:
        plot_timeline(report, frames, groups, alignments, output)
    (output / "analysis.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    fields = ["frame_index", "frame_timestamp_ns", "timestamp_source"]
    fields += [f"{sensor}_{key}" for sensor in SENSORS for key in ("sequence_id", "timestamp_ns", "delta_ms")]
    with (output / "alignment.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for aligned in alignments:
            row = {"frame_index": aligned["frame_index"], "frame_timestamp_ns": aligned["timestamp_ns"], "timestamp_source": aligned["timestamp_source"]}
            for sensor, sample in aligned["sensors"].items():
                for key in ("sequence_id", "timestamp_ns", "delta_ms"):
                    row[f"{sensor}_{key}"] = sample[key] if sample else ""
            writer.writerow(row)
    return {"output": str(output.resolve()), "frames": len(frames), "acceptance_status": report["acceptance_status"], "plots_written": make_plot}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, help="default: SESSION/analysis")
    parser.add_argument("--max-gap-ms", type=float, default=100, help="nearest-association window, not accuracy (default: 100)")
    parser.add_argument("--no-plot", action="store_true", help="write JSON/CSV using only the Python standard library")
    args = parser.parse_args()
    try:
        print(json.dumps(export_analysis(args.directory, args.output, args.max_gap_ms, not args.no_plot)))
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, f"{error}\n")
