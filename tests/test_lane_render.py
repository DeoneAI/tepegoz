import copy
import importlib.util
import unittest
from unittest.mock import patch

HAS_VISION = all(importlib.util.find_spec(name) is not None for name in ("numpy", "cv2"))
if HAS_VISION:
    import cv2
    import numpy as np
    from perception.lanes import fit_lane_mask, LANE_GEOMETRY_CONFIDENCE, LANE_DEPARTURE_CONFIDENCE
    from perception.render import render_overlay


@unittest.skipUnless(HAS_VISION, "install scripts/requirements-vision.txt")
class LaneRenderTests(unittest.TestCase):
    def setUp(self):
        self.image = np.zeros((360, 640, 3), np.uint8)
        self.lane = {"left": [[150, 210], [100, 340]], "right": [[490, 210], [540, 340]],
                     "centerline": [[320, 210], [320, 340]],
                     "corridor": [[150, 210], [100, 340], [540, 340], [490, 210]],
                     "confidence": .9, "image_departure_indicator": "centered"}

    def texts(self, lane):
        with patch("perception.render.cv2.putText", wraps=cv2.putText) as draw:
            rendered = render_overlay(self.image, lane)
        return rendered, [call.args[1] for call in draw.call_args_list]

    def test_sparse_real_fitter_output_does_not_render_low_confidence_geometry(self):
        mask = np.zeros((360, 640), np.uint8)
        mask[212:240, 168:173] = 255
        mask[212:240, 468:473] = 255
        lane = fit_lane_mask(mask)
        self.assertIsNotNone(lane["centerline"])
        self.assertLess(lane["confidence"], LANE_GEOMETRY_CONFIDENCE)
        original = copy.deepcopy(lane)
        rendered, text = self.texts(lane)
        self.assertFalse(rendered[100:].any(), "low-confidence geometry must not be drawn")
        self.assertFalse(any("Lane offset" in value for value in text))
        self.assertEqual(lane, original, "keep raw estimates intact for independent logging")
        self.assertFalse(self.image.any(), "rendering must not mutate source pixels")

    def test_geometry_threshold_is_inclusive_and_departure_has_its_own_gate(self):
        for confidence, visible in [(LANE_GEOMETRY_CONFIDENCE - .001, False), (LANE_GEOMETRY_CONFIDENCE, True), (.599, True)]:
            with self.subTest(confidence=confidence):
                self.lane["confidence"] = confidence
                rendered, text = self.texts(self.lane)
                self.assertEqual(bool(rendered[100:].any()), visible)
                self.assertFalse(any("Lane offset" in value for value in text))

    def test_departure_directions_are_visible_and_explicitly_image_space_uncalibrated(self):
        for direction in ("left", "right", "centered"):
            with self.subTest(direction=direction):
                self.lane["confidence"] = LANE_DEPARTURE_CONFIDENCE
                self.lane["image_departure_indicator"] = direction
                rendered, text = self.texts(self.lane)
                self.assertIn(f"Lane offset (image): {direction.upper()} | UNCALIBRATED", text)
                missing = {**self.lane, "image_departure_indicator": None}
                self.assertFalse(np.array_equal(rendered, render_overlay(self.image, missing)))

    def test_missing_invalid_or_incomplete_geometry_never_displays_departure(self):
        for lane in (None, {**self.lane, "image_departure_indicator": None},
                     {**self.lane, "image_departure_indicator": "unknown"},
                     {**self.lane, "centerline": None}, {**self.lane, "corridor": None},
                     {**self.lane, "confidence": float("nan")}):
            with self.subTest(lane=lane):
                _, text = self.texts(lane)
                self.assertFalse(any("Lane offset" in value for value in text))


if __name__ == "__main__":
    unittest.main()
