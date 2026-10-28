"""Checkerboard pinhole calibration with separate held-out-view diagnostics."""
import cv2
import numpy as np


def board_points(columns, rows, square_size_m=None):
    if columns < 3 or rows < 3 or (square_size_m is not None and (not np.isfinite(square_size_m) or square_size_m <= 0)):
        raise ValueError("Use at least 3x3 internal corners and a positive measured square size")
    points = np.zeros((columns * rows, 3), np.float32)
    points[:, :2] = np.mgrid[:columns, :rows].T.reshape(-1, 2)
    return points if square_size_m is None else points * square_size_m


def reprojection(points, corners, K, distortion, rotation, translation):
    predicted = cv2.projectPoints(points, rotation, translation, K, distortion)[0].reshape(-1, 2)
    residual = predicted - np.asarray(corners).reshape(-1, 2)
    return float(np.sqrt(np.mean(np.sum(residual ** 2, axis=1)))), residual


def fit_checkerboards(corners, image_size, pattern, square_size_m=None, holdout=2):
    """Fit only training views. Held-out poses are solved separately using the fixed fitted K/D."""
    width, height = image_size
    if width <= 0 or height <= 0 or holdout < 1 or len(corners) - holdout < 10:
        raise ValueError("Need at least 10 training views plus one or more held-out views")
    points = board_points(*pattern, square_size_m)
    views = [np.asarray(value, np.float32).reshape(-1, 1, 2) for value in corners]
    if any(len(value) != len(points) or not np.isfinite(value).all() for value in views):
        raise ValueError("All views must have the same finite checkerboard corner count")
    training = views[:-holdout]
    rms, K, distortion, rotations, translations, std, _, _ = cv2.calibrateCameraExtended([points] * len(training), training, image_size, None, None)
    if not np.isfinite(K).all() or not np.isfinite(distortion).all() or min(K[0, 0], K[1, 1]) <= 0:
        raise ValueError("Calibration did not recover finite positive focal lengths")
    records, residuals, normals = [], [], []
    for index, corners in enumerate(views):
        role = "training" if index < len(training) else "held_out_pose_fit"
        if role == "training":
            rotation, translation = rotations[index], translations[index]
        else:
            ok, rotation, translation = cv2.solvePnP(points, corners, K, distortion)
            if not ok:
                raise ValueError("Could not solve held-out checkerboard pose")
        error, residual = reprojection(points, corners, K, distortion, rotation, translation)
        normals.append(cv2.Rodrigues(rotation)[0][:, 2])
        records.append({"role": role, "rms_px": error, "rotation_board_to_camera_rodrigues": rotation.ravel().tolist(), "translation_board_to_camera": translation.ravel().tolist()})
        residuals.append(residual)
    normals = np.asarray(normals[:len(training)])
    tilt_spread = float(np.degrees(np.arccos(np.clip(normals @ normals.T, -1, 1))).max())
    centers = np.array([value.reshape(-1, 2).mean(axis=0) / [width, height] for value in training])
    center_span = np.ptp(centers, axis=0)
    warnings = []
    if tilt_spread < 10:
        warnings.append("Training board normals span less than 10 degrees; add tilted views")
    if max(center_span) < .1:
        warnings.append("Training centers span less than 10% of image dimensions; add views across the field")
    if max(row["rms_px"] for row in records) > 1:
        warnings.append("At least one view exceeds 1 px RMS; inspect corners, blur, target flatness and lens model")
    if not 0 < K[0, 2] < width or not 0 < K[1, 2] < height:
        warnings.append("Principal point lies outside the image; inspect calibration conditioning")
    new_K, roi = cv2.getOptimalNewCameraMatrix(K, distortion, image_size, 1, image_size)
    report = {"status": "checkerboard_fit_unvalidated", "camera_model": "pinhole_brown_conrady_5", "image_width": width, "image_height": height,
              "camera_intrinsics": K.tolist(), "distortion_coefficients": distortion.ravel().tolist(), "distortion_order": ["k1", "k2", "p1", "p2", "k3"],
              "pattern_internal_corners": list(pattern), "square_size_m": square_size_m,
              "translation_units": "m" if square_size_m is not None else "board_squares_unknown_physical_size",
              "training_views": len(training), "held_out_views": holdout, "training_rms_px": float(rms), "views": records,
              "intrinsic_parameter_std": std.ravel().tolist(), "std_interpretation": "Conditional fit uncertainty, not independently validated accuracy",
              "view_diversity": {"max_normal_angle_deg": tilt_spread, "normalized_center_span_xy": center_span.tolist(), "thresholds_are_heuristics": True},
              "quality_warnings": warnings, "undistorted_intrinsics": new_K.tolist(), "undistorted_valid_roi_xywh": list(map(int, roi)),
              "R_body_camera": None, "phone_to_vehicle": None,
              "limits": ["Board poses are not camera/IMU or phone/vehicle mount calibration", "Held-out images do not fit K/D, but their six-DOF poses are fitted; this is not independent metric camera truth", "Use the same lens, focus/zoom, resolution, crop and stabilization settings; recalibrate when they change", "Unknown public board square size cannot provide metric board translations", "A small residual alone does not establish physically correct intrinsics or timing"]}
    return report, residuals
