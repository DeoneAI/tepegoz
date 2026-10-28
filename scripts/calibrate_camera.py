"""Fit camera intrinsics from diverse checkerboard images; never infer a phone mount."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from evaluation.camera_calibration import fit_checkerboards


def run(source, output, pattern=(9, 6), square_size_m=None, holdout=2):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_dir() or output == source or (output.exists() and any(output.iterdir())):
        raise ValueError("Use an existing image directory and a separate empty output directory")
    files = sorted(file for file in source.iterdir() if file.suffix.lower() in {".jpg", ".jpeg", ".png"})
    corners, accepted, skipped, images = [], [], [], []
    hashes = set(); size = None
    for file in files:
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        if digest in hashes:
            skipped.append({"file": file.name, "reason": "duplicate image bytes"}); continue
        hashes.add(digest)
        image = cv2.imread(str(file))
        if image is None:
            skipped.append({"file": file.name, "reason": "unreadable image"}); continue
        dimensions = (image.shape[1], image.shape[0])
        if size is not None and dimensions != size:
            raise ValueError(f"Mixed image sizes: {file.name}; calibration requires fixed capture settings")
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        found, points = cv2.findChessboardCornersSB(gray, pattern, flags=cv2.CALIB_CB_NORMALIZE_IMAGE)
        if not found:
            skipped.append({"file": file.name, "reason": "checkerboard not found"}); continue
        size = dimensions
        if any(np.sqrt(np.mean((points - previous) ** 2)) < .25 for previous in corners):
            skipped.append({"file": file.name, "reason": "duplicate corner geometry within 0.25 px RMS"}); continue
        corners.append(points); images.append(image); accepted.append({"file": file.name, "sha256": digest})
    if len(corners) - holdout < 10:
        raise ValueError(f"Only {len(corners)} distinct detected views; need 10 training + {holdout} held out. Skipped: {skipped}")
    report, residuals = fit_checkerboards(corners, size, pattern, square_size_m, holdout)
    report.update(opencv_version=cv2.__version__, input_images=accepted, skipped_images=skipped, split="sorted accepted filenames; final views held out; duplicate images/geometry excluded",
                  corner_detector="findChessboardCornersSB; subpixel output", calibration_code_sha256={str(file.relative_to(Path(__file__).resolve().parents[1])).replace(chr(92), "/"): hashlib.sha256(file.read_bytes()).hexdigest() for file in [Path(__file__).resolve(), Path(__file__).resolve().parents[1] / "evaluation/camera_calibration.py"]})
    output.mkdir(parents=True, exist_ok=True); (output / "corners").mkdir()
    for index, (image, points, metadata) in enumerate(zip(images, corners, report["views"])):
        display = image.copy(); cv2.drawChessboardCorners(display, pattern, points, True)
        cv2.putText(display, f"{metadata['role']} | RMS {metadata['rms_px']:.3f} px", (12, 25), cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 255, 0), 2)
        if not cv2.imwrite(str(output / "corners" / f"{index:03d}.jpg"), display):
            raise OSError("Could not save corner preview")
    K, distortion, new_K = np.asarray(report["camera_intrinsics"]), np.asarray(report["distortion_coefficients"]), np.asarray(report["undistorted_intrinsics"])
    undistorted = cv2.undistort(images[0], K, distortion, None, new_K)
    if not cv2.imwrite(str(output / "undistorted-preview.jpg"), undistorted):
        raise OSError("Could not save undistortion preview")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout="constrained")
    for index, (metadata, residual) in enumerate(zip(report["views"], residuals)):
        color = "tab:blue" if metadata["role"] == "training" else "tab:orange"
        axes[0].bar(index + 1, metadata["rms_px"], color=color)
        axes[1].scatter(residual[:, 0], residual[:, 1], color=color, s=4, alpha=.35)
    axes[0].set(xlabel="Accepted view, sorted filename order", ylabel="RMS reprojection error (px)", title="Blue: training; orange: held-out pose fits")
    axes[1].set(xlabel="Horizontal residual (px)", ylabel="Vertical residual (px)", title="Residuals do not certify calibration accuracy")
    axes[1].axis("equal"); fig.suptitle("Checkerboard camera fit: intrinsics/distortion, no mount calibration")
    fig.savefig(output / "reprojection.png", dpi=150); fig.savefig(output / "reprojection.svg"); plt.close(fig)
    (output / "camera-calibration.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return {"output": str(output), "training_views": report["training_views"], "held_out_views": holdout, "training_rms_px": report["training_rms_px"], "held_out_rms_px": [row["rms_px"] for row in report["views"] if row["role"] != "training"], "quality_warnings": report["quality_warnings"]}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__); cli.add_argument("source"); cli.add_argument("--output", required=True); cli.add_argument("--columns", type=int, default=9); cli.add_argument("--rows", type=int, default=6); cli.add_argument("--square-size-m", type=float); cli.add_argument("--holdout", type=int, default=2)
    args = cli.parse_args()
    try:
        if min(args.columns, args.rows) < 3 or args.holdout < 1 or (args.square_size_m is not None and (not np.isfinite(args.square_size_m) or args.square_size_m <= 0)):
            raise ValueError("Invalid board dimensions, square size or held-out view count")
        print(json.dumps(run(args.source, args.output, (args.columns, args.rows), args.square_size_m, args.holdout)))
    except (ValueError, OSError, cv2.error) as error:
        cli.exit(1, f"{error}\n")
