"""Read indexed recorded frames without inventing phone IMU or capture timestamps."""
from dataclasses import dataclass
import json
from pathlib import Path
import time
import cv2
import numpy as np


@dataclass
class IndexedFrame:
    index: int
    timestamp_ns: str
    timestamp_source: str
    image: np.ndarray
    decode_ms: float


class FrameSequence:
    def __init__(self, source, stride=1, max_frames=None):
        self.source = Path(source).resolve()
        if stride < 1 or (max_frames is not None and max_frames < 1):
            raise ValueError("stride and max_frames must be positive")
        self.stride, self.max_frames = stride, max_frames
        self.fps = None
        if self.source.is_dir():
            manifest = json.loads((self.source / "manifest.json").read_text(encoding="utf-8"))
            if manifest.get("status") not in {"completed", "interrupted"} or manifest.get("storage_error"):
                raise ValueError("Use a finalized session without a storage error")
            self.time_basis = manifest.get("time_basis", "original_phone_monotonic")
        else:
            video = cv2.VideoCapture(str(self.source))
            try:
                if not video.isOpened():
                    raise ValueError(f"Cannot open video: {self.source}")
                self.fps = video.get(cv2.CAP_PROP_FPS)
                if not np.isfinite(self.fps) or self.fps <= 0:
                    raise ValueError("Video FPS is unavailable; cannot construct media timestamps")
            finally:
                video.release()
            self.time_basis = "video_media_estimate_no_phone_imu"

    def __iter__(self):
        count = 0
        if self.source.is_dir():
            frames = [json.loads(line) for line in (self.source / "frames.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            frames.sort(key=lambda frame: (int(frame["timestamp_ns"]), frame["frame_index"]))
            for position, frame in enumerate(frames):
                if position % self.stride:
                    continue
                start = time.perf_counter()
                image = cv2.imread(str(self.source / "frames" / f"{frame['frame_index']:08d}.jpg"))
                if image is None:
                    raise ValueError(f"Missing/unreadable frame {frame['frame_index']}")
                yield IndexedFrame(frame["frame_index"], frame["timestamp_ns"], frame.get("timestamp_source", "unspecified"), image, (time.perf_counter() - start) * 1000)
                count += 1
                if self.max_frames is not None and count >= self.max_frames:
                    return
        else:
            video = cv2.VideoCapture(str(self.source)); index = 0; decode_ms = 0.
            try:
                while True:
                    start = time.perf_counter(); ok, image = video.read(); decode_ms += (time.perf_counter() - start) * 1000
                    if not ok:
                        return
                    if index % self.stride == 0:
                        yield IndexedFrame(index, str(round(index * 1e9 / self.fps)), "video_index_over_reported_fps_estimate", image, decode_ms)
                        decode_ms = 0.; count += 1
                        if self.max_frames is not None and count >= self.max_frames:
                            return
                    index += 1
            finally:
                video.release()
