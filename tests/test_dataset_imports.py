import importlib.util
from pathlib import Path
import tempfile
import unittest

HAS_NUMPY = importlib.util.find_spec("numpy") is not None
if HAS_NUMPY:
    import numpy as np
    from evaluation.kitti import timestamp_ns, color_imu_calibration


@unittest.skipUnless(HAS_NUMPY, "install scripts/requirements-vision.txt")
class DatasetTimeAndCalibrationTests(unittest.TestCase):
    def test_calendar_subtraction_preserves_single_nanoseconds_across_seconds(self):
        first = timestamp_ns("2011-09-30 12:34:59.999999999")
        second = timestamp_ns("2011-09-30 12:35:00.000000000")
        self.assertEqual(second - first, 1)
        with self.assertRaisesRegex(ValueError, "nanosecond timestamp"):
            timestamp_ns("2011-09-30 12:34:59.123")

    def test_rectified_color_calibration_uses_common_rectification_not_raw_camera_axes(self):
        with tempfile.TemporaryDirectory(prefix="tepegoz-kitti-calibration-") as folder:
            folder = Path(folder)
            rect = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]])
            velo = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]])
            write = lambda file, data: (folder / file).write_text("\n".join(key + ": " + " ".join(map(str, np.asarray(value).ravel())) for key, value in data.items()))
            write("calib_cam_to_cam.txt", {"R_rect_00": rect, "P_rect_02": [[400, 0, 320, 25], [0, 410, 240, 0], [0, 0, 1, 0]]})
            write("calib_velo_to_cam.txt", {"R": velo})
            write("calib_imu_to_velo.txt", {"R": np.eye(3)})
            K, R_BC = color_imu_calibration(folder)
            np.testing.assert_array_equal(K, [[400, 0, 320], [0, 410, 240], [0, 0, 1]])
            np.testing.assert_array_equal(R_BC, (rect @ velo).T)


if __name__ == "__main__":
    unittest.main()
