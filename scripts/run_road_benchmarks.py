"""Run matched road baselines serially, preserving all run settings and outputs."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def run(output, frames=100, depth_frames=12):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Benchmark output must be empty; use a new directory")
    output.mkdir(parents=True, exist_ok=True)
    script = Path(__file__).with_name("run_perception.py")
    results = []
    for scene in ("solidWhiteRight", "solidYellowLeft", "challenge"):
        source = Path(".tools/datasets/roads") / (scene + ".mp4")
        cases = [(mode, ["--mode", mode, "--max-frames", str(frames), "--stride", "2"]) for mode in ("lanes", "objects", "combined")]
        cases += [("objects-no-prediction", ["--mode", "objects", "--no-prediction", "--max-frames", str(frames), "--stride", "2"]),
                  ("depth-both", ["--depth", "both", "--max-frames", str(depth_frames), "--stride", "10", "--preview-every", "4"])]
        for name, options in cases:
            destination = output / f"{scene}-{name}"
            print(f"Benchmark {scene}: {name}", file=sys.stderr, flush=True)
            result = subprocess.run([sys.executable, str(script), str(source), "--output", str(destination), *options], capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError(result.stderr or result.stdout)
            summary = json.loads(result.stdout)
            print(json.dumps(summary), flush=True); results.append(summary)
    (output / "runs.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return output


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__); cli.add_argument("--output", required=True); cli.add_argument("--frames", type=int, default=100); cli.add_argument("--depth-frames", type=int, default=12)
    args = cli.parse_args()
    try:
        if min(args.frames, args.depth_frames) < 1:
            raise ValueError("Frame limits must be positive")
        run(args.output, args.frames, args.depth_frames)
    except (ValueError, OSError, RuntimeError) as error:
        cli.exit(1, f"{error}\n")
