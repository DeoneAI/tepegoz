"""Optional calibrated same-session gyro input for rotation-only tracking compensation."""
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from localization.orientation import integrate_gyro, nearest_orientation
from perception.camera_motion import rotation_homography


class SessionRotationCompensation:
    def __init__(self, session, calibration_file):
        file = Path(calibration_file)
        self.calibration = json.loads(file.read_text(encoding="utf-8"))
        intrinsics = self.calibration.get("camera_intrinsics")
        self.K = np.asarray(intrinsics, float)
        if self.K.shape == (4,):
            fx, fy, cx, cy = self.K
            self.K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1.]])
        self.R_BC = np.asarray(self.calibration.get("R_body_camera"), float)
        if self.R_BC.shape != (3, 3):
            raise ValueError("Camera-to-body rotation R_body_camera is required; do not assume identity")
        rotation_homography(self.K, self.R_BC)
        self.R_BC = Rotation.from_matrix(self.R_BC)
        self.width, self.height = self.calibration.get("image_width"), self.calibration.get("image_height")
        expected_axes = self.calibration.get("imu_frame_axes", "phone_portrait_x_right_y_up_z_out")
        if type(self.width) is not int or type(self.height) is not int or min(self.width, self.height) <= 0:
            raise ValueError("Calibration image_width/image_height are required")
        bias = self.calibration.get("gyro_bias_rad_s")
        self.bias_method = "provided calibration" if bias is not None else "zero assumed; drift not corrected"
        # Dataset sampling rates differ from phone acquisition. Never silently widen these limits.
        self.max_gap_s = float(self.calibration.get("gyro_max_gap_s", .1))
        self.match_tolerance_ns = round(float(self.calibration.get("gyro_match_tolerance_ms", 25)) * 1e6)
        if not np.isfinite(self.max_gap_s) or self.max_gap_s <= 0 or not 0 < self.match_tolerance_ns <= 100000000:
            raise ValueError("Gyro gap must be positive and matching tolerance must be in (0, 100] ms")
        samples = []
        for line in (Path(session) / "telemetry.jsonl").read_text(encoding="utf-8").splitlines():
            sample = json.loads(line)
            if sample.get("sensor_type") == "gyroscope":
                if sample.get("units") != "rad_s" or sample.get("frame_axes") != expected_axes:
                    raise ValueError("Expected calibrated body-frame gyro in rad/s with matching axes")
                samples.append({"timestamp_ns": sample["timestamp_ns"], "angular_velocity": [sample["values"][axis] for axis in "xyz"]})
        self.orientations = integrate_gyro(samples, [0, 0, 0] if bias is None else bias, max_gap_s=self.max_gap_s)
        self.timestamps = [int(value["timestamp_ns"]) for value in self.orientations]
        self.previous = None
        self.metadata = {"calibration_sha256": hashlib.sha256(file.read_bytes()).hexdigest(), "gyro_bias_method": self.bias_method, "imu_frame_axes": expected_axes, "model": "pure camera rotation; no translation/rolling-shutter correction", "gyro_samples": len(samples), "gyro_max_gap_s": self.max_gap_s, "gyro_match_tolerance_ms": self.match_tolerance_ns / 1e6}

    def for_frame(self, timestamp_ns, image_shape):
        if tuple(image_shape[:2]) != (self.height, self.width):
            raise ValueError("Frame size differs from calibration; rescale/recalibrate explicitly")
        target = int(timestamp_ns)
        current = nearest_orientation(self.orientations, self.timestamps, target, max_gap_ns=self.match_tolerance_ns)
        previous, self.previous = self.previous, current
        if current is None or not current["continuous"]:
            self.previous = None
            return None, {"used": False, "reason": f"missing/discontinuous gyro within {self.match_tolerance_ns / 1e6:g} ms"}
        if previous is None:
            return None, {"used": False, "reason": "first aligned gyro frame"}
        body_current_from_previous = current["rotation"].inv() * previous["rotation"]
        camera_current_from_previous = self.R_BC.inv() * body_current_from_previous * self.R_BC
        H = rotation_homography(self.K, camera_current_from_previous.as_matrix())
        return H, {"used": True, "matched_timestamp_ns": current["timestamp_ns"], "alignment_delta_ms": (int(current["timestamp_ns"]) - target) / 1e6, "model": "rotation_only", "bias_method": self.bias_method}
