"""Pure-camera-rotation compensation for image-coordinate tracking; no translation/depth model."""
import numpy as np


def rotation_homography(intrinsics, rotation_current_from_previous):
    K, R = np.asarray(intrinsics, float), np.asarray(rotation_current_from_previous, float)
    if K.shape != (3, 3) or R.shape != (3, 3) or not np.isfinite(K).all() or not np.isfinite(R).all():
        raise ValueError("Finite 3x3 camera intrinsics and rotation are required")
    if K[0, 0] <= 0 or K[1, 1] <= 0 or not np.allclose(R.T @ R, np.eye(3), atol=1e-5) or np.linalg.det(R) <= 0:
        raise ValueError("Invalid intrinsics/rotation convention")
    return K @ R @ np.linalg.inv(K)


def warp_box(box, homography):
    x1, y1, x2, y2 = box
    points = np.array([[x1, y1, 1], [x2, y1, 1], [x2, y2, 1], [x1, y2, 1]], float).T
    warped = np.asarray(homography, float) @ points
    if not np.isfinite(warped).all() or np.any(warped[2] <= 1e-8):
        return None
    xy = warped[:2] / warped[2]
    return np.r_[xy.min(axis=1), xy.max(axis=1)].tolist()


def _warp_measurement(value, homography):
    center, size = value[:2], value[2:]
    box = warp_box(np.r_[center - size / 2, center + size / 2], homography)
    if box is None:
        raise ValueError("Box projects behind the camera")
    box = np.asarray(box)
    return np.r_[(box[:2] + box[2:]) / 2, box[2:] - box[:2]]


def compensate_filter(filter, homography):
    """Warp box position/size/velocity and propagate covariance through a numerical Jacobian."""
    H = np.asarray(homography, float)
    if H.shape != (3, 3) or not np.isfinite(H).all():
        raise ValueError("Camera homography must be finite 3x3")
    def transform(state):
        position = _warp_measurement(state[:4], H)
        future = _warp_measurement(state[:4] + state[4:] * .001, H)
        return np.r_[position, (future - position) / .001]
    before = filter.x.copy(); after = transform(before)
    J = np.empty((8, 8))
    for column in range(8):
        shifted = before.copy(); shifted[column] += .001
        J[:, column] = (transform(shifted) - after) / .001
    covariance = J @ filter.P @ J.T + np.diag([1.] * 4 + [4.] * 4)
    filter.x = after; filter.P = (covariance + covariance.T) / 2
