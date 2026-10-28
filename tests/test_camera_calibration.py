import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HAS_VISION = all(importlib.util.find_spec(name) is not None for name in ("cv2", "numpy"))
if HAS_VISION:
    import cv2
    import numpy as np
    from evaluation.camera_calibration import board_points, fit_checkerboards
    from scripts.calibrate_camera import run


@unittest.skipUnless(HAS_VISION, "install scripts/requirements-vision.txt")
class CameraCalibrationTests(unittest.TestCase):
    @staticmethod
    def views():
        rng = np.random.default_rng(8)
        points = board_points(9, 6, .025)
        K = np.array([[600., 0, 320], [0, 620., 240], [0, 0, 1]])
        distortion = np.array([-.15, .02, .001, -.002, 0])
        views = []
        for index in range(14):
            rotation = np.array([-.25 + .1 * (index % 5), -.3 + .12 * (index % 6), -.12 + index * .015])
            translation = np.array([-.15 + .045 * (index % 5), -.1 + .025 * (index % 4), .65 + .04 * (index % 4)])
            projected = cv2.projectPoints(points, rotation, translation, K, distortion)[0]
            views.append((projected + rng.normal(0, .03, projected.shape)).astype(np.float32))
        return K, views

    def test_noisy_multiview_fit_recovers_projection_without_inventing_mount(self):
        K, views = self.views()
        result, _ = fit_checkerboards(views, (640, 480), (9, 6), .025)
        estimated = np.asarray(result["camera_intrinsics"])
        np.testing.assert_allclose(estimated[[0, 1], [0, 1]], K[[0, 1], [0, 1]], rtol=.02)
        self.assertLess(result["training_rms_px"], .1)
        self.assertEqual(result["translation_units"], "m")
        self.assertIsNone(result["R_body_camera"]); self.assertIsNone(result["phone_to_vehicle"])
        self.assertEqual([row["role"] for row in result["views"][-2:]], ["held_out_pose_fit"] * 2)

    def test_corrupted_holdout_changes_diagnostics_but_never_fitted_intrinsics(self):
        _, views = self.views()
        before, _ = fit_checkerboards(views, (640, 480), (9, 6), .025)
        rng = np.random.default_rng(12)
        changed = views[:-2] + [(view + rng.normal(0, 3, view.shape)).astype(np.float32) for view in views[-2:]]
        with patch("evaluation.camera_calibration.cv2.calibrateCameraExtended", wraps=cv2.calibrateCameraExtended) as fit:
            after, _ = fit_checkerboards(changed, (640, 480), (9, 6), .025)
        supplied = fit.call_args.args[1]
        self.assertEqual(len(supplied), len(views) - 2)
        for expected, actual in zip(views[:-2], supplied):
            np.testing.assert_array_equal(expected, actual)
        # Sub-millipixel agreement: native solver reduction/termination can vary.
        np.testing.assert_allclose(before["camera_intrinsics"], after["camera_intrinsics"], rtol=0, atol=1e-4)
        self.assertGreater(after["views"][-1]["rms_px"], 1)
        self.assertTrue(after["quality_warnings"])

    def test_duplicate_checkerboards_cannot_satisfy_minimum_distinct_view_count(self):
        with tempfile.TemporaryDirectory(prefix="tepegoz-checkerboard-") as folder:
            folder = Path(folder); source = folder / "images"; source.mkdir()
            image = np.full((310, 400, 3), 255, np.uint8)
            for y in range(7):
                for x in range(10):
                    if (x + y) % 2 == 0:
                        image[30 + y * 30:60 + y * 30, 30 + x * 30:60 + x * 30] = 0
            ok, jpeg = cv2.imencode(".jpg", image); self.assertTrue(ok)
            for i in range(13):
                (source / f"{i:02d}.jpg").write_bytes(jpeg.tobytes())
            with self.assertRaisesRegex(ValueError, "Only 1 distinct detected"):
                run(source, folder / "output")
            self.assertFalse((folder / "output").exists())
        with self.assertRaises(ValueError):
            board_points(9, 6, float("nan"))


if __name__ == "__main__":
    unittest.main()
