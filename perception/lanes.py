"""Classical lane baseline and confidence-limited pixel geometry from lane masks."""
import cv2
import numpy as np

LANE_GEOMETRY_CONFIDENCE = .4
LANE_DEPARTURE_CONFIDENCE = .6


def fit_lane_mask(mask, method="mask", top_fraction=.58):
    height, width = mask.shape[:2]
    points = {"left": [], "right": []}
    for y in range(int(height * .94), int(height * top_fraction), -max(1, height // 70)):
        active = np.flatnonzero(mask[y] > 0)
        for side, candidates in (("left", active[active < width * .5]), ("right", active[active >= width * .5])):
            if candidates.size:
                # Closest marking to image center is the candidate ego-lane boundary.
                center = candidates.max() if side == "left" else candidates.min()
                cluster = candidates[np.abs(candidates - center) <= max(4, width * .018)]
                points[side].append((float(np.median(cluster)), y))
    curves, confidence = {}, {}
    ys = np.linspace(height * top_fraction, height * .94, 24)
    for side, values in points.items():
        if len(values) < 6:
            curves[side], confidence[side] = None, 0.; continue
        data = np.array(values, float); y = data[:, 1] / height; x = data[:, 0] / width
        keep = np.ones(len(x), dtype=bool)
        for _ in range(3):
            if keep.sum() < 6:
                break
            polynomial = np.polyfit(y[keep], x[keep], 2)
            residual = np.abs(np.polyval(polynomial, y) - x)
            keep = residual < max(.012, 2.5 * np.median(residual[keep]))
        if keep.sum() < 6:
            curves[side], confidence[side] = None, 0.; continue
        polynomial = np.polyfit(y[keep], x[keep], 2)
        fitted = np.polyval(polynomial, ys / height) * width
        if np.any((fitted < 0) | (fitted >= width)):
            curves[side], confidence[side] = None, 0.; continue
        support = np.ptp(y[keep]) / (.94 - top_fraction)
        error = float(np.median(np.abs(np.polyval(polynomial, y[keep]) - x[keep])))
        confidence[side] = float(np.clip(support * (keep.sum() / len(x)) * np.exp(-error * 80), 0, 1))
        curves[side] = [[float(px), float(py)] for px, py in zip(fitted, ys)]
    left, right = curves["left"], curves["right"]
    result = {"method": method, "left": left, "right": right, "confidence": min(confidence.values()), "centerline": None, "corridor": None,
              "image_center_offset_lane_widths": None, "image_departure_indicator": None, "units": "pixels", "calibrated": False}
    if left is not None and right is not None:
        l, r = np.array(left), np.array(right); widths = r[:, 0] - l[:, 0]
        # Perspective legitimately narrows the lane near the horizon; reject crossings, not convergence.
        if np.any(widths <= 0) or widths[-1] < width * .2 or widths[-1] > width * .95:
            result["confidence"] = 0.; return result
        center = (l + r) / 2
        result["centerline"] = center.tolist(); result["corridor"] = np.vstack([l, r[::-1]]).tolist()
        if result["confidence"] >= LANE_DEPARTURE_CONFIDENCE:
            offset = float((width / 2 - center[-1, 0]) / widths[-1])
            result["image_center_offset_lane_widths"] = offset
            result["image_departure_indicator"] = "right" if offset > .25 else "left" if offset < -.25 else "centered"
    return result


class ClassicalLaneDetector:
    def __call__(self, image):
        height, width = image.shape[:2]
        hls = cv2.cvtColor(image, cv2.COLOR_BGR2HLS)
        white = cv2.inRange(hls, (0, 170, 0), (180, 255, 255))
        yellow = cv2.inRange(hls, (12, 55, 65), (42, 255, 255))
        edges = cv2.Canny(cv2.GaussianBlur(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (5, 5), 0), 60, 150)
        colored = cv2.bitwise_and(edges, cv2.bitwise_or(white, yellow))
        roi = np.zeros_like(colored)
        polygon = np.array([[(.06 * width, height), (.42 * width, .58 * height), (.58 * width, .58 * height), (.94 * width, height)]], dtype=np.int32)
        cv2.fillPoly(roi, polygon, 255)
        edges = cv2.bitwise_and(colored, roi)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=25, minLineLength=max(15, width // 35), maxLineGap=max(15, width // 30))
        mask = np.zeros_like(edges)
        if lines is not None:
            for x1, y1, x2, y2 in lines.reshape(-1, 4):
                slope = (y2 - y1) / (x2 - x1) if x2 != x1 else 100
                if .35 < abs(slope) < 8:
                    cv2.line(mask, (x1, y1), (x2, y2), 255, max(2, width // 320))
        return fit_lane_mask(mask, "classical_color_canny_hough"), mask
