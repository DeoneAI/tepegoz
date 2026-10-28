import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


HAS_VISION = all(importlib.util.find_spec(name) is not None for name in ("numpy", "cv2", "scipy"))


@unittest.skipUnless(HAS_VISION, "install scripts/requirements-vision.txt")
class PerceptionCliTests(unittest.TestCase):
    def test_classical_video_run_preserves_indices_writes_independent_logs_and_refuses_overwrite(self):
        import cv2
        import numpy as np
        script = Path(__file__).resolve().parents[1] / "scripts/run_perception.py"
        with tempfile.TemporaryDirectory(prefix="tepegoz-cli-") as directory:
            root = Path(directory); video = root / "fixture.avi"; output = root / "run"
            writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 20, (320, 180))
            self.assertTrue(writer.isOpened())
            for _ in range(6):
                frame = np.zeros((180, 320, 3), np.uint8)
                cv2.line(frame, (50, 175), (145, 105), (255, 255, 255), 4)
                cv2.line(frame, (270, 175), (175, 105), (255, 255, 255), 4)
                writer.write(frame)
            writer.release()
            original = video.read_bytes()
            command = [sys.executable, str(script), str(video), "--output", str(output), "--mode", "lanes", "--lanes", "classical", "--stride", "2", "--max-frames", "3"]
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            run = json.loads((output / "run.json").read_text())
            self.assertEqual(run["frames"], 3); self.assertEqual(run["last_frame_index"], 4)
            self.assertFalse(run["code_changed_during_run"]); self.assertTrue(run["code_sha256"])
            self.assertEqual(run["models"], {}); self.assertEqual(run["time_basis"], "video_media_estimate_no_phone_imu")
            for file in ("lanes_classical.jsonl", "detections.jsonl", "tracks.jsonl", "camera_motion.jsonl"):
                rows = [json.loads(line) for line in (output / file).read_text().splitlines()]
                self.assertEqual([row["frame_index"] for row in rows], [0, 2, 4])
                self.assertEqual([row["timestamp_ns"] for row in rows], ["0", "100000000", "200000000"])
            self.assertEqual(video.read_bytes(), original)
            self.assertTrue((output / "overlay.mp4").is_file())
            second = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=60)
            self.assertNotEqual(second.returncode, 0); self.assertIn("must be empty", second.stderr)


if __name__ == "__main__":
    unittest.main()
