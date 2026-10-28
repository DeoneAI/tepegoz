"""Depth Anything V2 ONNX inference and robust interior box association.

Relative inverse depth and learned metric depth retain different, explicit units.
Learned metric predictions are not validated distances on these recordings.
"""
import cv2
import numpy as np
from perception.models import OnnxModel


class DepthAnythingOnnx(OnnxModel):
    def __init__(self, model, representation="relative", input_size=518, threads=4):
        super().__init__(model, threads)
        if representation not in {"relative", "metric"} or input_size < 140 or input_size % 14:
            raise ValueError("Depth representation must be relative/metric and input size a multiple of 14 >=140")
        self.representation, self.input_size = representation, input_size
        self.units = "arbitrary_inverse_depth" if representation == "relative" else "model_m_unvalidated"

    def __call__(self, image):
        height, width = image.shape[:2]
        scale = self.input_size / max(height, width)
        nh, nw = max(14, round(height * scale / 14) * 14), max(14, round(width * scale / 14) * 14)
        shape = self.input.shape
        if isinstance(shape[2], int) and isinstance(shape[3], int):
            nh, nw = shape[2:]
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_CUBIC).astype(np.float32) / 255
        tensor = ((resized - np.array([.485, .456, .406])) / np.array([.229, .224, .225])).transpose(2, 0, 1)[None]
        output = np.squeeze(self.run(tensor)[0])
        if output.ndim != 2 or not np.isfinite(output).all():
            raise ValueError("Depth model returned invalid/nonfinite map")
        self.last_input_shape = [1, 3, nh, nw]
        depth = cv2.resize(output.astype(np.float32), (width, height), interpolation=cv2.INTER_CUBIC)
        # Bicubic upsampling may overshoot a nonnegative network output slightly.
        return np.maximum(depth, 0)

    def contract(self):
        return {"model": "Depth Anything V2 ViT-S", "representation": "relative_inverse_depth" if self.representation == "relative" else "learned_metric_depth",
                "units": self.units, "validated_metric": False, "larger_means": "nearer" if self.representation == "relative" else "farther",
                "input_shape": getattr(self, "last_input_shape", None), "resize": "aspect-preserving multiple-of-14 long edge unless model has fixed input",
                "training_domain": "mixed relative-depth training" if self.representation == "relative" else "Virtual KITTI outdoor fine-tuning; domain/scale not validated here"}


def box_depth(depth, xyxy, units, interior_fraction=.5):
    if not 0 < interior_fraction <= 1:
        raise ValueError("Interior fraction must be within (0,1]")
    height, width = depth.shape
    box = np.asarray(xyxy, float)
    if box.shape != (4,) or not np.isfinite(box).all() or np.any(box[2:] <= box[:2]):
        return None
    center = (box[:2] + box[2:]) / 2; half = (box[2:] - box[:2]) * interior_fraction / 2
    low = np.clip(np.floor(center - half).astype(int), 0, [width, height])
    high = np.clip(np.ceil(center + half).astype(int), 0, [width, height])
    if np.any(high <= low):
        return None
    patch = depth[low[1]:high[1], low[0]:high[0]]
    values = patch[np.isfinite(patch) & (patch > 0)]
    if values.size < 16:
        return None
    return {"median": float(np.median(values)), "p10": float(np.percentile(values, 10)), "p90": float(np.percentile(values, 90)),
            "units": units, "validated_metric": False, "pixels": int(values.size), "interior_fraction": interior_fraction,
            "method": "interior_median", "spread_meaning": "pixel-value spread; not calibrated uncertainty", "background_leakage_possible": True}


def normalize_relative(depth):
    finite = depth[np.isfinite(depth)]
    if not finite.size:
        return np.zeros_like(depth, dtype=np.float32), (0., 0.)
    low, high = np.percentile(finite, [2, 98])
    normalized = np.clip((depth - low) / max(1e-9, high - low), 0, 1)
    return normalized.astype(np.float32), (float(low), float(high))


def render_depth(depth, contract, label=""):
    relative = contract["representation"] == "relative_inverse_depth"
    if relative:
        normalized, limits = normalize_relative(depth)
    else:
        normalized, limits = np.clip(depth / 80., 0, 1), (0., 80.)
    display = cv2.applyColorMap((normalized * 255).astype(np.uint8), cv2.COLORMAP_VIRIDIS)
    height, width = display.shape[:2]
    cv2.rectangle(display, (0, 0), (width, 58), (25, 30, 35), -1)
    cv2.putText(display, label, (12, 22), cv2.FONT_HERSHEY_SIMPLEX, .5, (245, 245, 245), 1, cv2.LINE_AA)
    detail = "Relative inverse depth: larger=nearer; no meters" if relative else "Learned model meters: UNVALIDATED; larger=farther"
    cv2.putText(display, detail, (12, 45), cv2.FONT_HERSHEY_SIMPLEX, .42, (240, 240, 240), 1, cv2.LINE_AA)
    # A numeric colorbar labels the exact display normalization instead of implying meters for relative depth.
    gradient = np.tile(np.linspace(0, 255, max(1, width - 40)).astype(np.uint8), (12, 1))
    display[height - 38:height - 26, 20:width - 20] = cv2.applyColorMap(gradient, cv2.COLORMAP_VIRIDIS)
    cv2.putText(display, f"{limits[0]:.2f}", (20, height - 8), cv2.FONT_HERSHEY_SIMPLEX, .4, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(display, f"{limits[1]:.2f} {contract['units']}", (max(20, width - 280), height - 8), cv2.FONT_HERSHEY_SIMPLEX, .4, (255, 255, 255), 1, cv2.LINE_AA)
    return display
