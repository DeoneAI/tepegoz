"""Research overlays: pixel geometry, track identity, confidence and stale state."""
import cv2
import numpy as np
from perception.lanes import LANE_GEOMETRY_CONFIDENCE, LANE_DEPARTURE_CONFIDENCE


def render_overlay(image, lane=None, tracks=(), label=""):
    output = image.copy(); height, width = output.shape[:2]
    geometry_visible = bool(lane) and lane["confidence"] >= LANE_GEOMETRY_CONFIDENCE
    indicator = None
    if geometry_visible:
        if lane.get("corridor"):
            layer = output.copy()
            cv2.fillPoly(layer, [np.array(lane["corridor"], np.int32)], (50, 130, 40))
            output = cv2.addWeighted(output, .75, layer, .25, 0)
        for key, color in (("left", (0, 220, 240)), ("right", (0, 220, 240)), ("centerline", (240, 170, 50))):
            if lane.get(key):
                cv2.polylines(output, [np.array(lane[key], np.int32)], False, color, 2)
        if (lane["confidence"] >= LANE_DEPARTURE_CONFIDENCE and lane.get("centerline")
                and lane.get("corridor") and lane.get("image_departure_indicator") in {"left", "right", "centered"}):
            indicator = lane["image_departure_indicator"]
    for track in tracks:
        box = np.array(track["xyxy"], int); box[[0, 2]] = np.clip(box[[0, 2]], 0, width - 1); box[[1, 3]] = np.clip(box[[1, 3]], 0, height - 1)
        color = (70, 220, 70) if track["observed"] else (150, 150, 150)
        cv2.rectangle(output, tuple(box[:2]), tuple(box[2:]), color, 2)
        text = f"#{track['track_id']} {track['class_name']} {track['score']:.2f}"
        if not track["observed"]:
            text += f" predicted {track['stale_age_s']:.2f}s"
        cv2.putText(output, text, (box[0], max(18, box[1] - 6)), cv2.FONT_HERSHEY_SIMPLEX, .45, color, 1, cv2.LINE_AA)
        depth = track.get("depth", {})
        estimates = []
        if depth.get("relative"):
            estimates.append(f"rel={depth['relative']['median']:.2f}")
        if depth.get("metric"):
            estimates.append(f"model-m={depth['metric']['median']:.1f} UNVALIDATED")
        if estimates:
            cv2.putText(output, " | ".join(estimates), (box[0], min(height - 6, box[1] + 16)), cv2.FONT_HERSHEY_SIMPLEX, .35, color, 1, cv2.LINE_AA)
        points = np.array([[value[1], value[2]] for value in track["trajectory"]], np.int32)
        if len(points) > 1:
            cv2.polylines(output, [points], False, color, 1)
    cv2.rectangle(output, (0, 0), (width, 82 if indicator else 58), (25, 30, 35), -1)
    cv2.putText(output, label, (12, 22), cv2.FONT_HERSHEY_SIMPLEX, .5, (245, 245, 245), 1, cv2.LINE_AA)
    detail = f"lane confidence {lane['confidence']:.2f} | pixel geometry / uncalibrated" if lane else "image-coordinate tracks / no metric velocity"
    cv2.putText(output, detail, (12, 45), cv2.FONT_HERSHEY_SIMPLEX, .42, (210, 210, 210), 1, cv2.LINE_AA)
    if indicator:
        cv2.putText(output, f"Lane offset (image): {indicator.upper()} | UNCALIBRATED", (12, 69),
                    cv2.FONT_HERSHEY_SIMPLEX, .42, (110, 225, 245), 1, cv2.LINE_AA)
    return output
