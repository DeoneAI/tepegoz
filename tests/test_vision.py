import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest

HAS_VISION = all(importlib.util.find_spec(name) is not None for name in ("numpy", "cv2", "scipy"))
if HAS_VISION:
    import cv2
    import numpy as np
    from localization.filters import ScalarKalmanFilter, ConstantVelocity2D, heading_motion_and_jacobian
    from perception.lanes import ClassicalLaneDetector, fit_lane_mask
    from perception.depth import box_depth, normalize_relative
    from perception.models import decode_yolox
    from perception.sequence import FrameSequence
    from perception.tracking import BoxTracker, iou_matrix
    from perception.camera_motion import rotation_homography, warp_box
    from localization.orientation import integrate_gyro, blend_rotation, find_initial_quiet_window
    from scipy.spatial.transform import Rotation
    from evaluation.detection import evaluate_detections
    from perception.motion_input import SessionRotationCompensation
    from localization.vo import EssentialVisualOdometry


@unittest.skipUnless(HAS_VISION, "install scripts/requirements-vision.txt")
class EstimationTests(unittest.TestCase):
    def test_scalar_hand_examples_and_joseph_covariance(self):
        for variance, expected in ((9, 11.428571428571429), (1, 13.333333333333334), (100, 10.19047619047619)):
            kf = ScalarKalmanFilter(); kf.step(14, measurement_variance=variance)
            self.assertAlmostEqual(kf.x[0], expected)
            self.assertAlmostEqual(kf.P[0, 0], 5 * variance / (5 + variance))

    def test_variable_dt_and_missing_measurements_preserve_physical_motion_model(self):
        kf = ConstantVelocity2D(position=(1, 2), velocity=(3, -1), acceleration_variance=.1)
        for dt in (.05, .2, .75):
            kf.advance(dt)
        np.testing.assert_allclose(kf.x, [4, 1, 3, -1], atol=1e-10)
        before = kf.x.copy(); result = kf.update([10000, -10000], kf.H, kf.R, gate=9.21)
        self.assertFalse(result["accepted"]); np.testing.assert_array_equal(before, kf.x)

    def test_covariance_remains_symmetric_positive_semidefinite_under_repeated_updates(self):
        kf = ConstantVelocity2D()
        for i in range(100):
            kf.advance(.01 + i % 3 * .02, [i / 10, -i / 5], gate=None)
            np.testing.assert_allclose(kf.P, kf.P.T, atol=1e-12)
            self.assertGreaterEqual(np.linalg.eigvalsh(kf.P).min(), -1e-12)

    def test_heading_jacobian_agrees_with_numerical_derivative(self):
        state = np.array([2., 3., .4, 5.]); predicted, F = heading_motion_and_jacobian(state, .2)
        for column in (2, 3):
            shifted = state.copy(); shifted[column] += 1e-6
            other, _ = heading_motion_and_jacobian(shifted, .2)
            np.testing.assert_allclose((other[:2] - predicted[:2]) / 1e-6, F[:2, column], atol=1e-6)
        self.assertAlmostEqual(F[0, 2], -math.sin(.4))
        self.assertAlmostEqual(F[1, 2], math.cos(.4))

    def test_gyro_bias_exercise_uses_integer_timestamps_and_quaternion_composition(self):
        base = 1403715273262142976
        samples = [{"timestamp_ns": str(base + i * 10000000), "angular_velocity": [0, 0, .11], "acceleration": [0, 0, 9.81]} for i in range(1001)]
        corrected = integrate_gyro(samples, [0, 0, .01])
        raw = integrate_gyro(samples)
        self.assertAlmostEqual(corrected[-1]["rotation"].as_rotvec()[2], 1, places=10)
        self.assertAlmostEqual(raw[-1]["rotation"].as_rotvec()[2], 1.1, places=10)
        self.assertTrue(corrected[-1]["continuous"])
        samples[-1]["timestamp_ns"] = str(base + 12000000000)
        gap = integrate_gyro(samples)
        self.assertFalse(gap[-1]["continuous"]); self.assertEqual(gap[-1]["gaps_seen"], 1)

    def test_visual_rotation_blending_gates_disagreement(self):
        gyro = Rotation.identity(); visual = Rotation.from_euler("z", 2, degrees=True)
        blended, detail = blend_rotation(gyro, visual, gain=.5)
        self.assertTrue(detail["visual_used"]); self.assertAlmostEqual(blended.as_euler("xyz", degrees=True)[2], 1)
        rejected, detail = blend_rotation(gyro, Rotation.from_euler("z", 30, degrees=True))
        self.assertFalse(detail["visual_used"]); self.assertAlmostEqual(rejected.magnitude(), 0)

    def test_quiet_window_search_does_not_calibrate_initial_motion_as_bias(self):
        samples = []
        for i in range(500):
            samples.append({"timestamp_ns": str(i * 10000000), "angular_velocity": [0, 0, .7 if i < 100 else .02], "acceleration": [0, 0, 9.81]})
        result = find_initial_quiet_window(samples)
        self.assertTrue(result["accepted"]); self.assertGreaterEqual(result["start_offset_s"], 1)
        self.assertAlmostEqual(result["gyro_bias_rad_s"][2], .02)

    def test_calibrated_phone_rotation_compensation_uses_same_clock_and_correct_inverse(self):
        with tempfile.TemporaryDirectory(prefix="tepegoz-motion-") as folder:
            folder = Path(folder)
            calibration = {"camera_intrinsics": [400, 400, 320, 240], "R_body_camera": np.eye(3).tolist(), "image_width": 640, "image_height": 480, "gyro_bias_rad_s": [0, 0, 0]}
            file = folder / "calibration.json"; file.write_text(json.dumps(calibration))
            samples = [{"sensor_type": "gyroscope", "timestamp_ns": str(i * 10000000), "units": "rad_s", "frame_axes": "phone_portrait_x_right_y_up_z_out", "values": {"x": 0, "y": .2, "z": 0}} for i in range(21)]
            (folder / "telemetry.jsonl").write_text("".join(json.dumps(sample) + "\n" for sample in samples))
            adapter = SessionRotationCompensation(folder, file)
            H, status = adapter.for_frame("0", (480, 640, 3)); self.assertIsNone(H)
            H, status = adapter.for_frame("100000000", (480, 640, 3))
            K = np.array([[400, 0, 320], [0, 400, 240], [0, 0, 1]])
            np.testing.assert_allclose(H, rotation_homography(K, Rotation.from_rotvec([0, -.02, 0]).as_matrix()), atol=1e-10)
            self.assertTrue(status["used"])
            H, status = adapter.for_frame("1000000000", (480, 640, 3)); self.assertIsNone(H); self.assertFalse(status["used"])
            with self.assertRaisesRegex(ValueError, "Frame size differs"):
                adapter.for_frame("100000000", (240, 320, 3))

    def test_lower_rate_dataset_gyro_requires_explicit_axes_and_gap_limits(self):
        with tempfile.TemporaryDirectory(prefix="tepegoz-public-motion-") as folder:
            folder = Path(folder)
            calibration = {"camera_intrinsics": [400, 400, 320, 240], "R_body_camera": np.eye(3).tolist(), "image_width": 640, "image_height": 480,
                           "imu_frame_axes": "dataset_native", "gyro_max_gap_s": .25, "gyro_match_tolerance_ms": 50}
            file = folder / "calibration.json"; file.write_text(json.dumps(calibration))
            samples = [{"sensor_type": "gyroscope", "timestamp_ns": str(i * 101000000), "units": "rad_s", "frame_axes": "dataset_native", "values": {"x": 0, "y": .2, "z": 0}} for i in range(3)]
            (folder / "telemetry.jsonl").write_text("".join(json.dumps(sample) + "\n" for sample in samples))
            adapter = SessionRotationCompensation(folder, file)
            adapter.for_frame("0", (480, 640, 3))
            H, status = adapter.for_frame("100000000", (480, 640, 3))
            self.assertIsNotNone(H); self.assertTrue(status["used"])
            self.assertAlmostEqual(status["alignment_delta_ms"], 1)
            calibration.pop("imu_frame_axes"); file.write_text(json.dumps(calibration))
            with self.assertRaisesRegex(ValueError, "matching axes"):
                SessionRotationCompensation(folder, file)


@unittest.skipUnless(HAS_VISION, "install scripts/requirements-vision.txt")
class PerceptionTests(unittest.TestCase):
    @staticmethod
    def detection(x, score=.9, class_id=2):
        return {"xyxy": [x, 20, x + 30, 60], "class_id": class_id, "class_name": "car", "score": score}

    def test_iou_geometry_and_empty_association(self):
        np.testing.assert_allclose(iou_matrix([[0, 0, 10, 10]], [[0, 0, 10, 10], [5, 0, 15, 10], [10, 10, 20, 20]]), [[1, 1 / 3, 0]])
        self.assertEqual(iou_matrix([], []).shape, (0, 0))

    def test_tracker_recovers_low_confidence_detection_and_keeps_class_identity(self):
        tracker = BoxTracker()
        first = tracker.update([self.detection(10)], 0)
        second = tracker.update([self.detection(13, .2)], .1)
        self.assertEqual(first[0]["track_id"], second[0]["track_id"])
        self.assertTrue(second[0]["confirmed"])
        self.assertTrue(second[0]["observed"])
        third = tracker.update([self.detection(13, .9, class_id=7)], .2)
        self.assertEqual(len(third), 2, "overlapping different classes must not be associated")

    def test_low_confidence_does_not_create_track_and_stale_tracks_expire(self):
        tracker = BoxTracker(max_age_s=.5)
        self.assertEqual(tracker.update([self.detection(10, .2)], 0), [])
        tracker.update([self.detection(10)], .1)
        stale = tracker.update([], .3)
        self.assertFalse(stale[0]["observed"]); self.assertAlmostEqual(stale[0]["stale_age_s"], .2)
        self.assertEqual(tracker.update([], .7), [])
        with self.assertRaisesRegex(ValueError, "increase"):
            tracker.update([], .7)

    def test_motion_prediction_bridges_short_occlusion_without_creating_measured_boxes(self):
        tracker = BoxTracker(max_age_s=1)
        for i in range(6):
            result = tracker.update([self.detection(i * 5)], i * .1)
        identifier = result[0]["track_id"]
        stale = tracker.update([], .7)[0]
        self.assertGreater(stale["xyxy"][0], result[0]["xyxy"][0] + 2)
        self.assertFalse(stale["observed"])
        recovered = tracker.update([self.detection(40)], .8)
        self.assertEqual(recovered[0]["track_id"], identifier)

    def test_rotation_assisted_tracking_keeps_id_through_large_known_camera_shift(self):
        baseline, assisted = BoxTracker(), BoxTracker()
        detection = self.detection(100)
        baseline.update([detection], 0); assisted.update([detection], 0)
        K = np.array([[400., 0, 320], [0, 400., 240], [0, 0, 1]])
        H = rotation_homography(K, Rotation.from_euler("y", 8, degrees=True).as_matrix())
        moved = {**detection, "xyxy": warp_box(detection["xyxy"], H)}
        rgb = baseline.update([moved], .1)
        motion = assisted.update([moved], .1, H)
        self.assertEqual([value["track_id"] for value in motion if value["observed"]], [1])
        self.assertEqual([value["track_id"] for value in rgb if value["observed"]], [2])
        self.assertGreaterEqual(np.linalg.eigvalsh(assisted.tracks[0].filter.P).min(), -1e-8)

    def test_detection_metrics_require_ground_truth_and_count_duplicate_false_positive(self):
        box = {"xyxy": [0, 0, 10, 10], "class_id": 2}
        predictions = {1: [{**box, "score": .9}, {**box, "score": .8}]}
        result = evaluate_detections(predictions, {1: [box]}, {2: "car", 7: "truck"})
        self.assertEqual(result["classes"]["car"]["tp"], 1); self.assertEqual(result["classes"]["car"]["fp"], 1)
        self.assertEqual(result["classes"]["car"]["precision_at_score"], .5)
        self.assertEqual(result["classes"]["car"]["recall_at_score"], 1)
        self.assertEqual(result["classes"]["car"]["ap50"], 1)
        self.assertIsNone(result["classes"]["truck"]["ap50"])

    def test_essential_vo_recovers_rotation_from_controlled_static_3d_scene(self):
        cv2.setRNGSeed(42)
        rng = np.random.default_rng(42)
        points = np.c_[rng.uniform(-2, 2, 500), rng.uniform(-1.5, 1.5, 500), rng.uniform(4, 12, 500)]
        K = np.array([[500., 0, 320], [0, 500., 240], [0, 0, 1.]])
        R = Rotation.from_euler("y", .05).as_matrix()
        images = []
        for cloud in (points, (R @ points.T).T + [.25, 0, 0]):
            image = np.zeros((480, 640), np.uint8)
            projected = (K @ cloud.T).T; projected = projected[:, :2] / projected[:, 2:]
            for i, (x, y) in enumerate(projected):
                if 5 <= x < 635 and 5 <= y < 475:
                    cv2.circle(image, (round(x), round(y)), 2, 100 + i % 155, -1, cv2.LINE_AA)
            images.append(image)
        model = EssentialVisualOdometry(K)
        self.assertFalse(model.update(images[0])["valid"])
        result = model.update(images[1])
        self.assertTrue(result["valid"], result["reason"])
        error = (Rotation.from_matrix(R) * result["rotation_delta"]).magnitude() * 180 / np.pi
        self.assertLess(error, 1.5)

    def test_yolox_raw_grid_decode_and_coco_class_mapping(self):
        output = np.zeros((1, 21, 85), dtype=np.float32)
        output[0, 5, :4] = [0, 0, math.log(2), math.log(2)]
        output[0, 5, 4] = .9; output[0, 5, 7] = .8
        detections = decode_yolox(output, 32, threshold=.3)
        self.assertEqual(len(detections), 1); self.assertEqual(detections[0]["class_name"], "car")
        self.assertAlmostEqual(detections[0]["score"], .72, places=6)
        np.testing.assert_allclose(detections[0]["xyxy"], [0, 0, 16, 16], atol=1e-6)
        with self.assertRaisesRegex(ValueError, "shape"):
            decode_yolox(np.zeros((1, 2, 85)), 32)

    def test_lane_corridor_is_pixel_geometry_and_empty_scene_stays_missing(self):
        mask = np.zeros((360, 640), dtype=np.uint8)
        for y in range(200, 345):
            left = round(130 + (340 - y) * .5); right = 640 - left
            mask[y, left - 2:left + 3] = 255; mask[y, right - 2:right + 3] = 255
        lane = fit_lane_mask(mask)
        self.assertGreater(lane["confidence"], .6); self.assertIsNotNone(lane["centerline"])
        self.assertAlmostEqual(lane["image_center_offset_lane_widths"], 0, places=2)
        self.assertFalse(lane["calibrated"]); self.assertEqual(lane["units"], "pixels")
        empty, _ = ClassicalLaneDetector()(np.zeros((360, 640, 3), np.uint8))
        self.assertIsNone(empty["left"]); self.assertIsNone(empty["image_departure_indicator"])

    def test_perspective_convergence_near_horizon_does_not_invalidate_lane(self):
        mask = np.zeros((360, 640), dtype=np.uint8)
        for y in range(208, 340):
            left = round(315 - (y - 208) * 1.65); right = 640 - left
            mask[y, left - 2:left + 3] = 255; mask[y, right - 2:right + 3] = 255
        lane = fit_lane_mask(mask)
        self.assertIsNotNone(lane["corridor"])
        self.assertGreater(lane["confidence"], .5)

    def test_robust_interior_depth_rejects_background_and_off_image_boxes(self):
        depth = np.full((100, 100), 100., np.float32)
        depth[35:65, 35:65] = 5
        depth[40, 40] = 1000
        result = box_depth(depth, [20, 20, 80, 80], "arbitrary_inverse_depth")
        self.assertEqual(result["median"], 5)
        self.assertFalse(result["validated_metric"])
        self.assertEqual(result["units"], "arbitrary_inverse_depth")
        self.assertTrue(result["background_leakage_possible"])
        self.assertIsNone(box_depth(depth, [-50, -50, -10, -10], "model_m_unvalidated"))
        self.assertIsNone(box_depth(depth, [2, 2, 3, 3], "model_m_unvalidated"))
        normalized, limits = normalize_relative(np.ones((10, 10), np.float32))
        self.assertTrue(np.isfinite(normalized).all()); self.assertEqual(normalized.max(), 0)

    def test_recorded_video_stride_preserves_source_indices_and_media_timestamps(self):
        with tempfile.TemporaryDirectory(prefix="tepegoz-sequence-") as folder:
            path = Path(folder) / "fixture.avi"
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 20, (64, 48))
            self.assertTrue(writer.isOpened())
            for i in range(8):
                writer.write(np.full((48, 64, 3), i * 20, np.uint8))
            writer.release()
            sequence = FrameSequence(path, stride=3, max_frames=2)
            frames = list(sequence)
            self.assertEqual([frame.index for frame in frames], [0, 3])
            self.assertEqual(frames[1].timestamp_ns, "150000000")
            self.assertEqual(sequence.time_basis, "video_media_estimate_no_phone_imu")


if __name__ == "__main__":
    unittest.main()
