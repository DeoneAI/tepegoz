"""Model-only inference benchmark across runtimes, devices, thread counts and precisions.

Measures ONE thing: the time of a single synchronous inference call on a fixed input
(batch 1, the MLPerf "single-stream" pattern). It does NOT measure decode, preprocessing,
NMS, tracking, rendering or I/O, so its FPS must never be reported as end-to-end FPS.

Targets (repeat --target):
  ort:cpu                       ONNX Runtime CPUExecutionProvider (thread sweep applies)
  ort:dml / ort:dml-highperf / ort:dml-minpower
                                ONNX Runtime DirectML (onnxruntime-directml wheel). highperf usually
                                selects the discrete GPU and minpower the integrated GPU.
  ort:cuda / ort:trt            ONNX Runtime CUDA / TensorRT (onnxruntime-gpu wheel)
  ov:CPU / ov:GPU.0 / ov:GPU.1 / ov:NPU
                                OpenVINO device (thread sweep applies to ov:CPU only)

Example:
  python scripts/bench_inference.py --model .tools/models/yolox_tiny.onnx --input-shape 1,3,416,416 \
      --target ort:cpu --target ov:GPU.0 --threads 1,2,4,8,12,16 --output .tools/experiments/bench-001
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time

import numpy as np

FIELDS = ["model", "model_sha256", "precision_label", "runtime", "runtime_version", "target", "device_name",
          "threads", "input_shape", "warmup", "iterations", "load_ms", "first_run_ms", "mean_ms", "std_ms",
          "p50_ms", "p90_ms", "p95_ms", "p99_ms", "min_ms", "max_ms", "model_only_fps", "status", "note"]


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def percentile(values, q):
    ordered = sorted(values)
    position = (len(ordered) - 1) * q / 100
    low, high = int(position), min(int(position) + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def host_info():
    info = {"os": platform.platform(), "python": platform.python_version(), "machine": platform.machine(),
            "logical_cpus": os.cpu_count(), "processor": platform.processor()}
    try:
        import psutil
        info["ram_gib"] = round(psutil.virtual_memory().total / 2**30, 1)
        info["physical_cores"] = psutil.cpu_count(logical=False)
    except ImportError:
        pass
    try:
        import openvino as ov
        info["cpu_name"] = ov.Core().get_property("CPU", "FULL_DEVICE_NAME")
    except Exception:
        pass
    return info


def parse_shape(text):
    return [int(x) for x in text.split(",")] if text else None


def make_input(shape, dtype, seed):
    rng = np.random.default_rng(seed)
    if np.issubdtype(dtype, np.floating):
        return rng.uniform(0, 255, size=shape).astype(dtype)
    return rng.integers(0, 255, size=shape).astype(dtype)


def time_runs(run, warmup, iterations, min_seconds):
    started = time.perf_counter(); run(); first = (time.perf_counter() - started) * 1000
    for _ in range(warmup):
        run()
    samples = []; begin = time.perf_counter()
    while len(samples) < iterations or (time.perf_counter() - begin) < min_seconds:
        tick = time.perf_counter(); run(); samples.append((time.perf_counter() - tick) * 1000)
    return first, samples


def ort_session(model, target, threads):
    import onnxruntime as ort
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    kind = target.split(":", 1)[1]
    if kind == "cpu":
        options.intra_op_num_threads = threads; options.inter_op_num_threads = 1
        providers = ["CPUExecutionProvider"]
    elif kind.startswith("dml"):
        options.enable_mem_pattern = False
        dml = {}
        if kind == "dml-highperf":
            dml["performance_preference"] = "high_performance"
        elif kind == "dml-minpower":
            dml["performance_preference"] = "minimum_power"
        elif kind.startswith("dml") and kind[3:].isdigit():
            dml["device_id"] = int(kind[3:])
        providers = [("DmlExecutionProvider", dml), "CPUExecutionProvider"]
    elif kind == "cuda":
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    elif kind == "trt":
        providers = [("TensorrtExecutionProvider", {"trt_fp16_enable": True}), "CUDAExecutionProvider", "CPUExecutionProvider"]
    else:
        raise ValueError(f"Unknown ONNX Runtime target {target}")
    available = ort.get_available_providers()
    wanted = providers[0][0] if isinstance(providers[0], tuple) else providers[0]
    if wanted not in available:
        raise RuntimeError(f"{wanted} not available in this onnxruntime build ({available})")
    session = ort.InferenceSession(str(model), options, providers=providers)
    if session.get_providers()[0] != wanted:
        raise RuntimeError(f"Fell back to {session.get_providers()[0]}; refusing to report it as {target}")
    return session, ort.__version__


def run_ort(model, target, threads, shape_override, args):
    started = time.perf_counter()
    session, version = ort_session(model, target, threads)
    load_ms = (time.perf_counter() - started) * 1000
    feeds = {}
    for item in session.get_inputs():
        shape = shape_override or [d if isinstance(d, int) else 1 for d in item.shape]
        dtype = np.float16 if "float16" in item.type else np.float32 if "float" in item.type else np.int64
        feeds[item.name] = make_input(shape, dtype, args.seed)
    first, samples = time_runs(lambda: session.run(None, feeds), args.warmup, args.iterations, args.min_seconds)
    device = "CPU" if target == "ort:cpu" else target
    return "onnxruntime", version, device, load_ms, first, samples, list(feeds.values())[0].shape


def run_ov(model, target, threads, shape_override, args):
    import openvino as ov
    core = ov.Core(); device = target.split(":", 1)[1]
    if device not in core.available_devices:
        raise RuntimeError(f"OpenVINO device {device} not present ({core.available_devices})")
    started = time.perf_counter()
    network = core.read_model(str(model))
    if shape_override:
        network.reshape({network.inputs[0].any_name: shape_override})
    config = {"PERFORMANCE_HINT": "LATENCY"}
    if device == "CPU":
        config["INFERENCE_NUM_THREADS"] = threads
    if args.ov_precision:
        config["INFERENCE_PRECISION_HINT"] = args.ov_precision
    compiled = core.compile_model(network, device, config)
    load_ms = (time.perf_counter() - started) * 1000
    request = compiled.create_infer_request()
    port = compiled.inputs[0]
    shape = shape_override or [d if d > 0 else 1 for d in port.get_partial_shape().get_min_shape()]
    data = make_input(shape, np.float32, args.seed)
    first, samples = time_runs(lambda: request.infer({0: data}), args.warmup, args.iterations, args.min_seconds)
    return "openvino", ov.__version__, core.get_property(device, "FULL_DEVICE_NAME"), load_ms, first, samples, data.shape


def bench(args):
    output = Path(args.output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Benchmark output must be empty; use a new directory")
    output.mkdir(parents=True, exist_ok=True)
    shape = parse_shape(args.input_shape)
    rows = []
    for model in map(Path, args.model):
        digest = sha256(model)
        for target in args.target:
            sweep = args.threads if target in ("ort:cpu", "ov:CPU") else [0]
            for threads in sweep:
                row = {"model": model.name, "model_sha256": digest, "precision_label": args.precision_label or ("int8" if "int8" in model.stem else "fp32"),
                       "target": target, "threads": threads or "", "warmup": args.warmup, "status": "ok", "note": ""}
                print(f"bench {model.name} on {target} threads={threads or '-'}", file=sys.stderr, flush=True)
                try:
                    runner = run_ort if target.startswith("ort:") else run_ov
                    runtime, version, device, load_ms, first, samples, used = runner(model, target, threads, shape, args)
                    mean = statistics.fmean(samples)
                    row.update(runtime=runtime, runtime_version=version, device_name=device, input_shape="x".join(map(str, used)),
                               iterations=len(samples), load_ms=round(load_ms, 1), first_run_ms=round(first, 2), mean_ms=round(mean, 3),
                               std_ms=round(statistics.pstdev(samples), 3), p50_ms=round(percentile(samples, 50), 3),
                               p90_ms=round(percentile(samples, 90), 3), p95_ms=round(percentile(samples, 95), 3),
                               p99_ms=round(percentile(samples, 99), 3), min_ms=round(min(samples), 3), max_ms=round(max(samples), 3),
                               model_only_fps=round(1000 / mean, 2))
                    if threads and os.cpu_count() and threads > os.cpu_count():
                        row["note"] = f"oversubscribed: {threads} threads > {os.cpu_count()} logical CPUs"
                except Exception as error:  # record the failure instead of hiding the target
                    row.update(status="failed", note=str(error).splitlines()[0][:300])
                rows.append(row)
    with open(output / "results.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS); writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in FIELDS})
    meta = {"script_sha256": sha256(__file__), "host": host_info(), "argv": sys.argv[1:],
            "protocol": {"pattern": "single-stream, batch 1, synchronous", "input": f"seeded uniform random (seed {args.seed})",
                         "warmup_runs": args.warmup, "min_iterations": args.iterations, "min_seconds": args.min_seconds,
                         "excluded": ["model download", "image decode", "preprocessing", "postprocessing/NMS", "rendering", "I/O"],
                         "notes": ["Run serially on an otherwise idle, plugged-in machine", "Model-only FPS is not end-to-end FPS"]}}
    (output / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "rows": len(rows), "failed": sum(r["status"] != "ok" for r in rows)}))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", action="append", required=True, help="ONNX model path (repeatable)")
    parser.add_argument("--target", action="append", default=None, help="runtime:device (repeatable), default ort:cpu")
    parser.add_argument("--threads", default="1,2,4,8", help="comma list for ort:cpu / ov:CPU")
    parser.add_argument("--input-shape", help="e.g. 1,3,416,416; needed for dynamic models")
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--min-seconds", type=float, default=10.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--ov-precision", choices=["f32", "f16", "bf16"], help="OpenVINO INFERENCE_PRECISION_HINT")
    parser.add_argument("--precision-label", help="override the precision column (fp32/fp16/int8)")
    parser.add_argument("--output", required=True, help="new, empty output directory")
    args = parser.parse_args()
    args.target = args.target or ["ort:cpu"]
    args.threads = [int(x) for x in args.threads.split(",")]
    bench(args)


if __name__ == "__main__":
    main()
