"""ONNX adapters with model-specific preprocessing and explicit class/output contracts.

Reference contracts: Megvii-BaseDetection/YOLOX demo/ONNXRuntime and hustvl/YOLOP test_onnx.py.
The adapter implementations below are local, not vendored training code.
"""
from pathlib import Path
import cv2
import numpy as np
from perception.lanes import fit_lane_mask
from perception.tracking import iou_matrix


ROAD_CLASSES = {0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


class OnnxModel:
    def __init__(self, model, threads=4):
        if not Path(model).is_file() or Path(model).stat().st_size < 1000:
            raise ValueError(f"Model missing/incomplete: {model}. Run scripts/fetch_assets.py first.")
        try:
            import onnxruntime as ort
        except ImportError as error:
            raise RuntimeError("Install scripts/requirements-vision.txt before running models") from error
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads; options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(model), options, providers=["CPUExecutionProvider"])
        self.input = self.session.get_inputs()[0]
        self.runtime_version = ort.__version__
        self.path = str(Path(model).resolve())

    def run(self, tensor):
        return self.session.run(None, {self.input.name: np.ascontiguousarray(tensor, dtype=np.float32)})


def decode_yolox(output, size, threshold=.25, nms_iou=.45, image_shape=None):
    prediction = np.asarray(output, float).reshape(-1, 85).copy()
    grids, strides = [], []
    for stride in (8, 16, 32):
        gy, gx = np.meshgrid(np.arange(size // stride), np.arange(size // stride), indexing="ij")
        grids.append(np.stack([gx, gy], axis=-1).reshape(-1, 2))
        strides.append(np.full((gx.size, 1), stride))
    grid, stride = np.concatenate(grids), np.concatenate(strides)
    if len(prediction) != len(grid):
        raise ValueError("YOLOX output shape does not match the configured raw-head input size")
    prediction[:, :2] = (prediction[:, :2] + grid) * stride
    prediction[:, 2:4] = np.exp(np.clip(prediction[:, 2:4], -20, 20)) * stride
    class_ids = np.argmax(prediction[:, 5:], axis=1)
    scores = prediction[:, 4] * prediction[np.arange(len(prediction)), class_ids + 5]
    indices = np.flatnonzero((scores >= threshold) & np.isin(class_ids, list(ROAD_CLASSES)))
    boxes = np.c_[prediction[:, :2] - prediction[:, 2:4] / 2, prediction[:, :2] + prediction[:, 2:4] / 2]
    if image_shape is not None:
        height, width = image_shape[:2]
        boxes /= min(size / height, size / width)
        boxes[:, [0, 2]] = np.clip(boxes[:, [0, 2]], 0, width)
        boxes[:, [1, 3]] = np.clip(boxes[:, [1, 3]], 0, height)
    kept = []
    for class_id in ROAD_CLASSES:
        order = indices[class_ids[indices] == class_id]
        order = order[np.argsort(-scores[order], kind="stable")]
        while order.size:
            index = order[0]; kept.append(int(index))
            if order.size == 1:
                break
            overlap = iou_matrix(boxes[index:index + 1], boxes[order[1:]])[0]
            order = order[1:][overlap <= nms_iou]
    return [{"xyxy": boxes[i].tolist(), "score": float(scores[i]), "class_id": int(class_ids[i]), "class_name": ROAD_CLASSES[int(class_ids[i])]} for i in sorted(kept, key=lambda k: -scores[k]) if boxes[i, 2] > boxes[i, 0] and boxes[i, 3] > boxes[i, 1]]


class YoloXDetector(OnnxModel):
    def __init__(self, model, threshold=.25, nms_iou=.45, threads=4):
        super().__init__(model, threads)
        shape = self.input.shape
        if len(shape) != 4 or shape[2] != shape[3] or not isinstance(shape[2], int):
            raise ValueError("Expected a fixed square NCHW YOLOX model")
        self.size, self.threshold, self.nms_iou = shape[2], threshold, nms_iou

    def __call__(self, image):
        height, width = image.shape[:2]
        scale = min(self.size / height, self.size / width)
        # Official YOLOX non-legacy contract: BGR, raw 0..255, top-left placement in 114 padding.
        resized = cv2.resize(image, (int(width * scale), int(height * scale)))
        padded = np.full((self.size, self.size, 3), 114, np.float32)
        padded[:resized.shape[0], :resized.shape[1]] = resized
        output = self.run(padded.transpose(2, 0, 1)[None])[0]
        return decode_yolox(output, self.size, self.threshold, self.nms_iou, image.shape)


class YoloPLaneDetector(OnnxModel):
    def __init__(self, model, threads=4):
        super().__init__(model, threads)
        self.height, self.width = self.input.shape[2:]
        names = [output.name for output in self.session.get_outputs()]
        if "lane_line_seg" not in names:
            raise ValueError("YOLOP lane_line_seg output is required")
        self.lane_index = names.index("lane_line_seg")

    def __call__(self, image):
        height, width = image.shape[:2]
        scale = min(self.width / width, self.height / height)
        rw, rh = round(width * scale), round(height * scale)
        left, top = (self.width - rw) // 2, (self.height - rh) // 2
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        padded = np.full((self.height, self.width, 3), 114, np.float32)
        padded[top:top + rh, left:left + rw] = cv2.resize(rgb, (rw, rh), interpolation=cv2.INTER_AREA)
        normalized = (padded / 255 - np.array([.485, .456, .406])) / np.array([.229, .224, .225])
        output = self.run(normalized.transpose(2, 0, 1)[None])[self.lane_index]
        mask = (np.argmax(output[0, :, top:top + rh, left:left + rw], axis=0) * 255).astype(np.uint8)
        mask = cv2.resize(mask, (width, height), interpolation=cv2.INTER_NEAREST)
        return fit_lane_mask(mask, "yolop_lane_segmentation"), mask
