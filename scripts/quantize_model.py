"""Post-training INT8 quantization of an ONNX model with ONNX Runtime (QDQ format).

Pipeline (matches the ONNX Runtime guidance for CNN detectors):
  1. quant_pre_process: symbolic shape inference + graph optimization
  2. static quantization, QDQ format, S8 activations / S8 weights, per-channel weights
  3. calibration on real, representative road images (100-500 recommended, never the test split)

  python scripts/quantize_model.py --model .tools/models/yolox_tiny.onnx --calib-dir .tools/calib/road \
      --preprocess yolox --input-shape 1,3,416,416 --output .tools/models/yolox_tiny.int8.onnx

--synthetic-calibration uses random tensors. That produces a model that is only valid for
LATENCY experiments; its accuracy is meaningless, and the output metadata says so.
Accuracy must be re-measured with scripts/evaluate_detector.py before an INT8 model is adopted.
"""
import argparse
import json
from pathlib import Path
import tempfile

import numpy as np


def letterbox_yolox(image, height, width):
    import cv2
    scale = min(height / image.shape[0], width / image.shape[1])
    resized = cv2.resize(image, (int(image.shape[1] * scale), int(image.shape[0] * scale)), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((height, width, 3), 114, dtype=np.uint8)
    canvas[:resized.shape[0], :resized.shape[1]] = resized
    return canvas.transpose(2, 0, 1).astype(np.float32)  # BGR, 0-255, CHW (YOLOX convention)


def imagenet(image, height, width):
    import cv2
    rgb = cv2.cvtColor(cv2.resize(image, (width, height), interpolation=cv2.INTER_CUBIC), cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    rgb = (rgb - np.array([0.485, 0.456, 0.406])) / np.array([0.229, 0.224, 0.225])
    return rgb.transpose(2, 0, 1).astype(np.float32)  # Depth Anything / ViT convention


PREPROCESS = {"yolox": letterbox_yolox, "imagenet": imagenet}


class Reader:
    """onnxruntime.quantization CalibrationDataReader over images or seeded random tensors."""

    def __init__(self, input_name, shape, images=None, preprocess=None, synthetic=0):
        self.items = []
        if images:
            import cv2
            for path in images:
                image = cv2.imread(str(path))
                if image is not None:
                    self.items.append(PREPROCESS[preprocess](image, shape[2], shape[3])[None])
        rng = np.random.default_rng(0)
        self.items += [rng.uniform(0, 255, size=shape).astype(np.float32) for _ in range(synthetic)]
        if not self.items:
            raise ValueError("No calibration data: pass --calib-dir with images or --synthetic-calibration N")
        self.name = input_name; self.iterator = iter(self.items)

    def get_next(self):
        item = next(self.iterator, None)
        return None if item is None else {self.name: item}

    def rewind(self):
        self.iterator = iter(self.items)


def quantize(args):
    import onnx
    from onnxruntime.quantization import CalibrationMethod, QuantFormat, QuantType, quantize_static
    from onnxruntime.quantization.shape_inference import quant_pre_process
    shape = [int(x) for x in args.input_shape.split(",")]
    output = Path(args.output)
    if output.exists():
        raise ValueError("Output model already exists; choose a new path")
    images = sorted(p for p in Path(args.calib_dir).rglob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"})[:args.max_images] if args.calib_dir else None
    with tempfile.TemporaryDirectory() as scratch:
        source = Path(args.model)
        model = onnx.load(str(source))
        opset = next((o.version for o in model.opset_import if o.domain in ("", "ai.onnx")), 0)
        if opset < 13:  # per-channel Q/DQ (the axis attribute) needs opset >= 13
            from onnx import version_converter
            source = Path(scratch) / "opset13.onnx"
            onnx.save(version_converter.convert_version(model, 13), str(source))
        prepared = Path(scratch) / "prepared.onnx"
        # skip_optimization keeps the graph portable: ORT's CPU-only NCHWc ops would break OpenVINO/DirectML.
        quant_pre_process(str(source), str(prepared), skip_symbolic_shape=False, skip_optimization=True)
        input_name = onnx.load(str(prepared)).graph.input[0].name
        reader = Reader(input_name, shape, images, args.preprocess, args.synthetic_calibration)
        method = {"minmax": CalibrationMethod.MinMax, "entropy": CalibrationMethod.Entropy, "percentile": CalibrationMethod.Percentile}[args.calibration]
        quantize_static(str(prepared), str(output), reader, quant_format=QuantFormat.QDQ, per_channel=not args.per_tensor,
                        activation_type=QuantType.QInt8, weight_type=QuantType.QInt8, calibrate_method=method,
                        nodes_to_exclude=args.exclude or [])
    meta = {"source_model": str(args.model), "source_opset": opset, "output_model": str(output), "format": "QDQ", "activations": "int8", "weights": "int8",
            "per_channel": not args.per_tensor, "calibration": args.calibration, "calibration_images": len(images or []),
            "synthetic_calibration_tensors": args.synthetic_calibration, "excluded_nodes": args.exclude or [],
            "accuracy_status": "LATENCY-ONLY: synthetic calibration, accuracy invalid" if not images else "unvalidated: run evaluate_detector.py and compare with FP32"}
    Path(str(output) + ".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--input-shape", required=True, help="e.g. 1,3,416,416")
    parser.add_argument("--calib-dir", help="folder of representative images (not the evaluation split)")
    parser.add_argument("--max-images", type=int, default=300)
    parser.add_argument("--preprocess", choices=sorted(PREPROCESS), default="yolox")
    parser.add_argument("--synthetic-calibration", type=int, default=0, metavar="N", help="random tensors; latency experiments only")
    parser.add_argument("--calibration", choices=["minmax", "entropy", "percentile"], default="minmax")
    parser.add_argument("--per-tensor", action="store_true", help="per-tensor instead of per-channel weights")
    parser.add_argument("--exclude", action="append", help="node name to keep in FP32 (repeatable), e.g. the detection head")
    quantize(parser.parse_args())


if __name__ == "__main__":
    main()
