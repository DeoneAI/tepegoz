"""Two-stage confidence association with box Kalman prediction and Hungarian IoU matching.

Inspired by SORT/ByteTrack; this is a small research baseline, not their official implementation.
"""
from dataclasses import dataclass, field
import math
import numpy as np
from scipy.optimize import linear_sum_assignment
from localization.filters import LinearKalmanFilter
from perception.camera_motion import compensate_filter


def iou_matrix(a, b):
    a, b = np.asarray(a, float).reshape(-1, 4), np.asarray(b, float).reshape(-1, 4)
    low = np.maximum(a[:, None, :2], b[None, :, :2])
    high = np.minimum(a[:, None, 2:], b[None, :, 2:])
    intersection = np.maximum(0, high - low).prod(axis=2)
    area_a = np.maximum(0, a[:, 2:] - a[:, :2]).prod(axis=1)
    area_b = np.maximum(0, b[:, 2:] - b[:, :2]).prod(axis=1)
    return intersection / np.maximum(1e-12, area_a[:, None] + area_b[None, :] - intersection)


def box_measurement(box):
    x1, y1, x2, y2 = box
    return np.array([(x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1])


def state_box(state):
    cx, cy, width, height = state[:4]
    width, height = max(1, width), max(1, height)
    return [float(cx - width / 2), float(cy - height / 2), float(cx + width / 2), float(cy + height / 2)]


@dataclass
class BoxTrack:
    id: int
    class_id: int
    class_name: str
    filter: LinearKalmanFilter
    score: float
    last_observed_s: float
    hits: int = 1
    observed: bool = True
    trajectory: list = field(default_factory=list)


class BoxTracker:
    def __init__(self, high_threshold=.5, low_threshold=.1, match_iou=.2, max_age_s=.7, prediction=True):
        if not 0 <= low_threshold <= high_threshold <= 1 or not 0 <= match_iou <= 1 or max_age_s <= 0:
            raise ValueError("Invalid tracking thresholds")
        self.high_threshold, self.low_threshold, self.match_iou = high_threshold, low_threshold, match_iou
        self.max_age_s, self.prediction = max_age_s, prediction
        self.tracks, self.next_id, self.last_time = [], 1, None
        self.H, self.R = np.eye(4, 8), np.diag([4., 4., 9., 9.])

    def _associate(self, track_indices, detection_indices, detections):
        if not track_indices or not detection_indices:
            return [], track_indices, detection_indices
        overlaps = iou_matrix([state_box(self.tracks[i].filter.x) for i in track_indices], [detections[i]["xyxy"] for i in detection_indices])
        valid = np.array([[self.tracks[t].class_id == detections[d]["class_id"] for d in detection_indices] for t in track_indices]) & (overlaps >= self.match_iou)
        cost = np.where(valid, 1 - overlaps, 1e6)
        rows, cols = linear_sum_assignment(cost)
        pairs = [(track_indices[r], detection_indices[c]) for r, c in zip(rows, cols) if valid[r, c]]
        return pairs, [i for i in track_indices if all(i != t for t, _ in pairs)], [i for i in detection_indices if all(i != d for _, d in pairs)]

    def update(self, detections, timestamp_s, camera_homography=None):
        if not math.isfinite(timestamp_s) or (self.last_time is not None and timestamp_s <= self.last_time):
            raise ValueError("Tracker timestamps must increase")
        for detection in detections:
            box = np.asarray(detection["xyxy"], float)
            if box.shape != (4,) or not np.isfinite(box).all() or np.any(box[2:] <= box[:2]) or not 0 <= detection["score"] <= 1:
                raise ValueError("Invalid detection box or score")
        dt = timestamp_s - self.last_time if self.last_time is not None else 0
        self.last_time = timestamp_s
        self.tracks = [track for track in self.tracks if timestamp_s - track.last_observed_s <= self.max_age_s]
        for track in self.tracks:
            if camera_homography is not None:
                compensate_filter(track.filter, camera_homography)
            F = np.eye(8)
            if self.prediction:
                F[:4, 4:] = np.eye(4) * dt
            G = np.vstack([np.eye(4) * dt * dt / 2, np.eye(4) * dt])
            track.filter.predict(F, 25 * G @ G.T)
            track.observed = False
        high = [i for i, detection in enumerate(detections) if detection["score"] >= self.high_threshold]
        low = [i for i, detection in enumerate(detections) if self.low_threshold <= detection["score"] < self.high_threshold]
        pairs, unmatched_tracks, unmatched_high = self._associate(list(range(len(self.tracks))), high, detections)
        low_pairs, _, _ = self._associate(unmatched_tracks, low, detections)
        for ti, di in pairs + low_pairs:
            track, detection = self.tracks[ti], detections[di]
            track.filter.update(box_measurement(detection["xyxy"]), self.H, self.R)
            track.hits += 1; track.observed = True; track.score = detection["score"]; track.last_observed_s = timestamp_s
        for di in unmatched_high:
            detection = detections[di]
            state = np.r_[box_measurement(detection["xyxy"]), np.zeros(4)]
            self.tracks.append(BoxTrack(self.next_id, detection["class_id"], detection["class_name"], LinearKalmanFilter(state, np.diag([10.] * 4 + [1000.] * 4)), detection["score"], timestamp_s))
            self.next_id += 1
        result = []
        for track in self.tracks:
            box = state_box(track.filter.x)
            track.trajectory.append([timestamp_s, float(track.filter.x[0]), float(track.filter.x[1])]); track.trajectory = track.trajectory[-50:]
            result.append({"track_id": track.id, "class_id": track.class_id, "class_name": track.class_name, "score": track.score, "xyxy": box,
                           "confirmed": track.hits >= 2, "observed": track.observed, "stale_age_s": timestamp_s - track.last_observed_s,
                           "box_covariance": track.filter.P[:4, :4].tolist(), "trajectory": track.trajectory.copy()})
        return result
