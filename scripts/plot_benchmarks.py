"""Plot model-only inference benchmarks from scripts/bench_inference.py results.

Reads every <experiments>/*/results.csv (status=ok rows) and writes PNG charts:
  latency_by_device.png   p50 latency per device, one panel per model (FP32)
  thread_sweep.png        CPU p50 latency vs intra-op threads (ONNX Runtime vs OpenVINO)
  int8_vs_fp32.png        INT8 vs FP32 per device with speed-up ratios
  tail_latency.png        p50 -> p95 spread per device (YOLOX-Tiny)
  realtime_budget.png     model-only FPS per device vs camera frame rates (YOLOX-Tiny)

  python scripts/plot_benchmarks.py --experiments .tools/experiments --output .tools/plots

Colors: a fixed, colorblind-validated categorical order (one hue per device, never cycled).
Values are direct-labeled because three hues are below 3:1 contrast on white.
"""
import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

TARGETS = [  # (target id, label, color) in fixed order
    ("ort:cpu", "ONNX Runtime · CPU", "#2a78d6"),
    ("ov:CPU", "OpenVINO · CPU", "#eb6834"),
    ("ov:GPU.0", "OpenVINO · Intel iGPU", "#1baf7a"),
    ("ort:dml-minpower", "DirectML · Intel iGPU", "#eda100"),
    ("ort:dml-highperf", "DirectML · RTX 4050", "#e87ba4"),
    ("ov:GPU.1", "OpenVINO · RTX 4050", "#6250d6"),
]
LABEL = {t: l for t, l, _ in TARGETS}
COLOR = {t: c for t, _, c in TARGETS}
MODELS = [("yolox_nano.onnx", "YOLOX-Nano (416)"), ("yolox_tiny.onnx", "YOLOX-Tiny (416)"), ("yolox_s.onnx", "YOLOX-S (640)")]
INT8 = {"yolox_tiny.onnx": "yolox_tiny.int8-synthcal.onnx", "yolox_s.onnx": "yolox_s.int8-synthcal.onnx"}
FP32_COLOR, INT8_COLOR = "#2a78d6", "#eb6834"
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e6e5e1"
# White backing so reference lines and gridlines never run through a label.
BOX = dict(boxstyle="square,pad=0.12", facecolor="white", edgecolor="none")
# The YOLOX-S CPU rows overlapped another workload (see the report); they are drawn but flagged.
NOISY = {("yolox_s.onnx", "ort:cpu"), ("yolox_s.onnx", "ov:CPU"), ("yolox_s.int8-synthcal.onnx", "ort:cpu"), ("yolox_s.int8-synthcal.onnx", "ov:CPU")}

plt.rcParams.update({
    "font.family": ["Segoe UI", "Arial", "DejaVu Sans"], "font.size": 9, "axes.edgecolor": GRID,
    "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED, "axes.titleweight": "bold",
    "axes.titlesize": 10, "axes.titlepad": 10, "axes.titlecolor": INK, "axes.spines.top": False, "axes.spines.right": False,
    "figure.dpi": 160, "savefig.bbox": "tight", "savefig.facecolor": "white",
})


def load(experiments):
    rows = []
    for path in sorted(Path(experiments).glob("*/results.csv")):
        with open(path, encoding="utf-8") as handle:
            rows += [r for r in csv.DictReader(handle) if r["status"] == "ok"]
    for r in rows:
        for key in ("p50_ms", "p95_ms", "mean_ms", "model_only_fps"):
            r[key] = float(r[key])
        r["threads"] = int(r["threads"]) if r["threads"] else None
    return rows


def best(rows, model, target):
    """Lowest-mean configuration (best thread count on CPU targets), or None."""
    hits = [r for r in rows if r["model"] == model and r["target"] == target]
    return min(hits, key=lambda r: r["mean_ms"]) if hits else None


def tidy(ax, axis="x"):
    ax.grid(axis=axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def footnote(fig, text):
    fig.text(0.0, -0.02, text, fontsize=7, color=MUTED, ha="left", va="top")


def latency_by_device(rows, out):
    fig, axes = plt.subplots(3, 1, figsize=(7.2, 7.6))
    for ax, (model, title) in zip(axes, MODELS):
        data = [(t, best(rows, model, t)) for t, _, _ in TARGETS]
        data = [(t, r) for t, r in data if r][::-1]
        y = range(len(data))
        bars = ax.barh(y, [r["p50_ms"] for _, r in data], color=[COLOR[t] for t, _ in data], height=0.64, edgecolor="white", linewidth=1)
        ax.set_yticks(list(y), [LABEL[t] + (f"  ({r['threads']} thr)" if r["threads"] else "") for t, r in data], fontsize=8)
        for bar, (t, r) in zip(bars, data):
            flag = " *" if (model, t) in NOISY else ""
            ax.annotate(f"{r['p50_ms']:.1f} ms{flag}", (bar.get_width(), bar.get_y() + bar.get_height() / 2), textcoords="offset points", xytext=(4, 0), va="center", fontsize=8, color=INK, bbox=BOX)
        ax.set_title(title, loc="left")
        ax.set_xlabel("p50 ms per inference (lower is better)")
        ax.set_xlim(0, max(r["p50_ms"] for _, r in data) * 1.35)
        tidy(ax)
    fig.suptitle("Model-only latency by device (FP32, batch 1)", x=0.0, ha="left", fontweight="bold", fontsize=11)
    fig.tight_layout()
    footnote(fig, "CPU rows show the best thread count. * YOLOX-S CPU runs overlapped other work and are noisy.")
    fig.savefig(out / "latency_by_device.png")
    plt.close(fig)


def thread_sweep(rows, out):
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.4), sharey=False)
    for ax, (model, title) in zip(axes, MODELS[:2]):
        for target in ("ort:cpu", "ov:CPU"):
            pts = sorted((r["threads"], r["p50_ms"]) for r in rows if r["model"] == model and r["target"] == target and r["threads"])
            if not pts:
                continue
            xs, ys = zip(*pts)
            k = min(range(len(ys)), key=ys.__getitem__)
            ax.plot(xs, ys, color=COLOR[target], linewidth=2, marker="o", markersize=5, markeredgecolor="white",
                    label=f"{LABEL[target]} · best {ys[k]:.1f} ms @ {xs[k]} thr")
            ax.scatter([xs[k]], [ys[k]], s=130, facecolor="none", edgecolor=COLOR[target], linewidth=1.5, zorder=4)  # ring = best
            ax.annotate(f"{ys[-1]:.0f} ms", (xs[-1], ys[-1]), textcoords="offset points", xytext=(5, 0), fontsize=7.5, color=INK, va="center", bbox=BOX)
        ax.axvline(12, color=MUTED, linewidth=0.8, linestyle=":", zorder=0.5)
        ax.text(11.8, ax.get_ylim()[1] * 0.62, "12 logical\nCPUs", fontsize=6.5, color=MUTED, va="top", ha="right", bbox=BOX)
        ax.set_xticks([1, 2, 4, 6, 8, 12, 16])
        ax.set_xlabel("intra-op threads")
        ax.set_ylabel("p50 latency (ms)")
        ax.set_title(title, loc="left")
        ax.legend(frameon=True, facecolor="white", edgecolor="none", framealpha=1, fontsize=7, loc="upper center", bbox_to_anchor=(0.42, 1.02))
        ax.set_ylim(bottom=0)
        tidy(ax, "y")
    fig.suptitle("CPU thread sweep: more threads stop helping past the core count", x=0.0, ha="left", fontweight="bold", fontsize=10.5)
    fig.tight_layout()
    footnote(fig, "Intel Core 5 210H (8 cores: 4P + 4E, 12 logical CPUs). 16 threads oversubscribes the CPU.")
    fig.savefig(out / "thread_sweep.png")
    plt.close(fig)


def int8_vs_fp32(rows, out):
    targets = ["ort:cpu", "ov:CPU", "ov:GPU.0", "ort:dml-minpower", "ort:dml-highperf"]
    fig, axes = plt.subplots(2, 1, figsize=(7.2, 6.6))
    for ax, (model, title) in zip(axes, [MODELS[1], MODELS[2]]):
        pairs = [(t, best(rows, model, t), best(rows, INT8[model], t)) for t in targets]
        pairs = [p for p in pairs if p[1] and p[2]]
        x = range(len(pairs))
        w = 0.38
        fb = ax.bar([i - w / 2 - 0.01 for i in x], [p[1]["p50_ms"] for p in pairs], w, color=FP32_COLOR, label="FP32")
        ib = ax.bar([i + w / 2 + 0.01 for i in x], [p[2]["p50_ms"] for p in pairs], w, color=INT8_COLOR, label="INT8 (latency test only)")
        top = max(max(p[1]["p50_ms"], p[2]["p50_ms"]) for p in pairs)
        for i, (t, f, q) in enumerate(pairs):
            ratio = f["p50_ms"] / q["p50_ms"]
            word = f"{ratio:.2f}× faster" if ratio >= 1 else f"{1 / ratio:.1f}× slower"
            ax.text(i, max(f["p50_ms"], q["p50_ms"]) + top * 0.14, word, ha="center", fontsize=7.5, color=INK, fontweight="bold" if ratio >= 1 else "normal", bbox=BOX)
        for bar in list(fb) + list(ib):
            ax.annotate(f"{bar.get_height():.0f}", (bar.get_x() + bar.get_width() / 2, bar.get_height()), textcoords="offset points", xytext=(0, 3), ha="center", va="bottom", fontsize=6.5, color=MUTED, bbox=BOX)
        ax.set_xticks(list(x), [LABEL[p[0]].replace(" · ", "\n") for p in pairs], fontsize=7.5)
        ax.set_ylabel("p50 latency (ms)")
        ax.set_ylim(0, top * 1.38)
        ax.set_title(title, loc="left")
        ax.legend(frameon=False, fontsize=8, loc="upper right")
        tidy(ax, "y")
    fig.suptitle("INT8 only helps through OpenVINO; it slows ONNX Runtime and DirectML", x=0.0, ha="left", fontweight="bold", fontsize=10.5)
    fig.tight_layout()
    footnote(fig, "INT8 models used random calibration: their speed is meaningful, their accuracy is not. YOLOX-S CPU runs are noisy.")
    fig.savefig(out / "int8_vs_fp32.png")
    plt.close(fig)


def tail_latency(rows, out, model="yolox_tiny.onnx"):
    data = [(t, best(rows, model, t)) for t, _, _ in TARGETS]
    data = [(t, r) for t, r in data if r][::-1]
    fig, ax = plt.subplots(figsize=(7.2, 3.1))
    for i, (t, r) in enumerate(data):
        ax.plot([r["p50_ms"], r["p95_ms"]], [i, i], color=GRID, linewidth=3, solid_capstyle="round", zorder=1)
        ax.scatter([r["p50_ms"]], [i], s=60, color=COLOR[t], edgecolor="white", linewidth=1.5, zorder=3)
        ax.scatter([r["p95_ms"]], [i], s=60, facecolor="white", edgecolor=COLOR[t], linewidth=2, zorder=3)
        ax.annotate(f"p50 {r['p50_ms']:.1f} → p95 {r['p95_ms']:.1f} ms", (r["p95_ms"], i), textcoords="offset points", xytext=(9, 0), va="center", fontsize=7.5, color=INK, bbox=BOX)
    ax.set_yticks(range(len(data)), [LABEL[t] for t, _ in data], fontsize=8)
    ax.set_xlabel("latency (ms): filled = p50 (typical), hollow = p95 (slow tail)")
    ax.set_xlim(0, max(r["p95_ms"] for _, r in data) * 1.6)
    ax.set_title("YOLOX-Tiny: typical vs slow-tail latency", loc="left", fontsize=11)
    tidy(ax)
    fig.tight_layout()
    fig.savefig(out / "tail_latency.png")
    plt.close(fig)


def realtime_budget(rows, out, model="yolox_tiny.onnx"):
    data = [(t, best(rows, model, t)) for t, _, _ in TARGETS]
    data = sorted([(t, r) for t, r in data if r], key=lambda d: d[1]["model_only_fps"])
    fig, ax = plt.subplots(figsize=(7.2, 3.1))
    bars = ax.barh(range(len(data)), [r["model_only_fps"] for _, r in data], color=[COLOR[t] for t, _ in data], height=0.64, edgecolor="white", zorder=2)
    for bar, (_, r) in zip(bars, data):
        ax.annotate(f"{r['model_only_fps']:.0f} FPS", (bar.get_width(), bar.get_y() + bar.get_height() / 2), textcoords="offset points", xytext=(4, 0), va="center", fontsize=8, color=INK, bbox=BOX)
    for fps, name, align in ((15, "15 fps capture ", "right"), (30, " 30 fps capture", "left")):
        ax.axvline(fps, color=MUTED, linewidth=1, linestyle="--", zorder=0.5)
        ax.text(fps, -0.75, name, fontsize=7, color=MUTED, va="center", ha=align, bbox=BOX)
    ax.set_ylim(-1.1, len(data) - 0.5)
    ax.set_yticks(range(len(data)), [LABEL[t] for t, _ in data], fontsize=8)
    ax.set_xlabel("model-only frames per second (higher is better)")
    ax.set_xlim(0, max(r["model_only_fps"] for _, r in data) * 1.2)
    ax.set_title("YOLOX-Tiny headroom vs phone capture rate", loc="left", fontsize=11)
    tidy(ax)
    fig.tight_layout()
    footnote(fig, "Model-only: excludes decode, pre/post-processing, tracking, lanes, depth and rendering, so end-to-end FPS is lower.")
    fig.savefig(out / "realtime_budget.png")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--experiments", default=".tools/experiments")
    parser.add_argument("--output", default=".tools/plots")
    args = parser.parse_args()
    rows = load(args.experiments)
    if not rows:
        raise SystemExit(f"No successful benchmark rows under {args.experiments}")
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    for plot in (latency_by_device, thread_sweep, int8_vs_fp32, tail_latency, realtime_budget):
        plot(rows, out)
    print(f"{len(rows)} rows -> {out.resolve()}")


if __name__ == "__main__":
    main()
