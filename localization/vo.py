"""Monocular feature/LK/essential-matrix VO demonstration with explicit degeneracy checks."""
import cv2
import numpy as np
from scipy.spatial.transform import Rotation


class EssentialVisualOdometry:
    def __init__(self, intrinsics, distortion=None):
        self.K = np.asarray(intrinsics, float).reshape(3, 3)
        if not np.isfinite(self.K).all() or self.K[0, 0] <= 0 or self.K[1, 1] <= 0:
            raise ValueError("VO requires measured or explicitly assumed camera intrinsics")
        self.distortion = np.asarray(distortion, float) if distortion is not None else np.zeros(4)
        self.previous = None; self.previous_points = None

    @staticmethod
    def features(image):
        return cv2.goodFeaturesToTrack(image, maxCorners=1000, qualityLevel=.01, minDistance=8, blockSize=7)

    def update(self, image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        gray = cv2.undistort(gray, self.K, self.distortion)
        result = {"valid": False, "reason": "initialization", "tracked_features": 0, "inliers": 0, "inlier_fraction": 0., "translation_units": "arbitrary monocular scale", "rotation_delta": None, "translation_direction": None}
        previous, points = self.previous, self.previous_points
        self.previous = gray
        self.previous_points = self.features(gray)
        if previous is None or points is None or len(points) < 20:
            return result
        current, status, _ = cv2.calcOpticalFlowPyrLK(previous, gray, points, None, winSize=(21, 21), maxLevel=3)
        if current is None:
            result["reason"] = "optical flow failed"; return result
        back, back_status, _ = cv2.calcOpticalFlowPyrLK(gray, previous, current, None, winSize=(21, 21), maxLevel=3)
        if back is None:
            result["reason"] = "backward flow failed"; return result
        keep = status.reshape(-1).astype(bool) & back_status.reshape(-1).astype(bool) & (np.linalg.norm(points.reshape(-1, 2) - back.reshape(-1, 2), axis=1) < 1.)
        p0, p1 = points.reshape(-1, 2)[keep], current.reshape(-1, 2)[keep]
        result["tracked_features"] = len(p0)
        if len(p0) < 20:
            result["reason"] = "too few forward-backward consistent features"; return result
        flow = float(np.median(np.linalg.norm(p1 - p0, axis=1))); result["median_flow_px"] = flow
        result["median_flow_dx_px"] = float(np.median((p1 - p0)[:, 0]))
        result["median_flow_dy_px"] = float(np.median((p1 - p0)[:, 1]))
        if flow < .5:
            result["reason"] = "low parallax / near-stationary"; return result
        essential, mask = cv2.findEssentialMat(p0, p1, self.K, method=cv2.RANSAC, prob=.999, threshold=1.)
        if essential is None or mask is None:
            result["reason"] = "essential matrix failed"; return result
        essential = essential[:3, :3]
        # Adjacent high-rate camera frames can place valid points >50 baseline lengths away.
        # A larger cheirality range avoids OpenCV's default distance cutoff rejecting them all.
        recovery = cv2.recoverPose(essential, p0, p1, self.K, distanceThresh=1000., mask=mask)
        inliers, rotation, translation, pose_mask = recovery[:4]
        result["inliers"], result["inlier_fraction"] = int(inliers), inliers / len(p0)
        bearings = np.linalg.solve(self.K, np.c_[p0, np.ones(len(p0))].T)
        rotated = self.K @ rotation @ bearings
        rotation_only_projection = (rotated[:2] / rotated[2]).T
        parallax = float(np.median(np.linalg.norm(p1 - rotation_only_projection, axis=1)))
        result["rotation_compensated_parallax_px"] = parallax
        _, homography_mask = cv2.findHomography(p0, p1, cv2.RANSAC, 2.)
        result["homography_inliers"] = int(homography_mask.sum()) if homography_mask is not None else 0
        if inliers < 20 or inliers / len(p0) < .4:
            result["reason"] = "cheirality / inlier support insufficient"; return result
        if parallax < .6:
            result["reason"] = "rotation-only / insufficient translation parallax"; return result
        if result["homography_inliers"] > inliers * 1.25:
            result["reason"] = "homography dominates: planar scene / rotation degeneracy"; return result
        # recoverPose returns C_current <- C_previous. For camera attitude propagation we need its inverse.
        result.update(valid=True, reason="essential pose accepted", rotation_delta=Rotation.from_matrix(rotation.T), translation_direction=(-rotation.T @ translation).reshape(3).tolist())
        return result
