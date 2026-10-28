"""Export aggregate CSV/JSON evidence from completed, provenance-recorded perception runs."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.benchmark import export_benchmarks


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("runs", nargs="+", help="run directories containing run.json")
    cli.add_argument("--output", required=True, help="CSV/JSON output stem")
    args = cli.parse_args()
    try:
        results = export_benchmarks(args.runs, args.output)
        print(f"Exported {len(results)} measured runs to {args.output}.csv and .json")
    except (OSError, ValueError) as error:
        cli.exit(1, f"{error}\n")
