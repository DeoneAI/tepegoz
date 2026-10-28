import csv
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/analyze_session.py"
spec = importlib.util.spec_from_file_location("analyze_session", SCRIPT)
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)
HAS_MATPLOTLIB = importlib.util.find_spec("matplotlib") is not None
BASE = 900000000000000000


def frame(index, time):
    return {"frame_index": index, "timestamp_ns": str(time), "timestamp_source": "callback_estimate"}


def sample(sensor, sequence, time):
    unit = {"accelerometer": "m_s2", "gyroscope": "rad_s"}[sensor]
    return {"sensor_type": sensor, "sequence_id": sequence, "timestamp_ns": str(time), "values": {"x": .1, "y": 9.81, "z": 0}, "units": unit}


class SessionAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="tepegoz-analysis-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def session(self, frames=(), samples=(), status="completed", **metadata):
        manifest = {"id": "synthetic-test", "name": "SYNTHETIC QA - not physical evidence", "status": status, "calibration": {"intrinsics": None}, **metadata}
        (self.root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        for name, records in (("frames.jsonl", frames), ("telemetry.jsonl", samples)):
            (self.root / name).write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        (self.root / "frames").mkdir(exist_ok=True)
        for value in frames:
            (self.root / "frames" / f"{value['frame_index']:08d}.jpg").write_bytes(b"\xff\xd8\xff\xd9")

    def test_exact_nanoseconds_ties_and_inclusive_window_with_unsorted_logs(self):
        frames = [frame(2, BASE + 200000001), frame(0, BASE + 50000000), frame(1, BASE + 200000000)]
        samples = [sample("gyroscope", 1, BASE + 100000000), sample("gyroscope", 0, BASE)]
        self.session(frames, samples)
        report, ordered, groups, aligned = analysis.analyze_session(self.root)
        self.assertEqual([value["frame_index"] for value in ordered], [0, 1, 2])
        self.assertEqual(aligned[0]["sensors"]["gyroscope"]["sequence_id"], 0, "earlier timestamp wins exact tie")
        self.assertEqual(aligned[0]["sensors"]["gyroscope"]["delta_ms"], -50)
        self.assertEqual(aligned[1]["sensors"]["gyroscope"]["delta_ms"], -100)
        self.assertIsNone(aligned[2]["sensors"]["gyroscope"], "one nanosecond beyond window is missing")
        self.assertEqual(report["alignment"]["gyroscope"]["missing_frames"], 1)
        self.assertEqual(report["sensors"]["gyroscope"]["timestamp_regressions"], 1)

    def test_export_preserves_raw_logs_and_missing_sensor_fields(self):
        self.session([frame(0, BASE)], [sample("accelerometer", 0, BASE + 1)])
        originals = {file: file.read_bytes() for file in self.root.rglob("*") if file.is_file()}
        result = analysis.export_analysis(self.root, make_plot=False)
        with (Path(result["output"]) / "alignment.csv").open(newline="", encoding="utf-8") as stream:
            row = next(csv.DictReader(stream))
        self.assertEqual(row["frame_timestamp_ns"], str(BASE))
        self.assertEqual(row["accelerometer_timestamp_ns"], str(BASE + 1))
        self.assertEqual(float(row["accelerometer_delta_ms"]), .000001)
        self.assertEqual(row["gyroscope_timestamp_ns"], "")
        report = json.loads((Path(result["output"]) / "analysis.json").read_text(encoding="utf-8"))
        self.assertFalse(report["checks"]["required_streams_present"])
        self.assertIsNone(report["sensors"]["gyroscope"]["observed_hz"])
        self.assertIn("No gyroscope samples recorded.", report["warnings"])
        self.assertEqual(report["calibration"]["intrinsics"], None)
        for file, contents in originals.items():
            self.assertEqual(file.read_bytes(), contents)

    def test_two_minute_timestamp_overlap_never_automatically_passes_physical_acceptance(self):
        end = BASE + 120000000000
        self.session([frame(0, BASE), frame(1, end)], [sample(sensor, i, time) for sensor in analysis.REQUIRED for i, time in enumerate((BASE, end))])
        report, *_ = analysis.analyze_session(self.root)
        self.assertEqual(report["common_camera_accel_gyro_overlap_s"], 120)
        self.assertTrue(all(report["checks"].values()))
        self.assertEqual(report["acceptance_status"], "requires_physical_validation", "sparse endpoints do not demonstrate sustained hardware performance")

    def test_sequence_and_jpeg_integrity_find_corrupted_or_incomplete_recordings(self):
        self.session([frame(0, BASE)], [sample("gyroscope", 1, BASE + 100), sample("gyroscope", 1, BASE), sample("gyroscope", 3, BASE + 200)])
        (self.root / "frames/00000000.jpg").unlink()
        (self.root / "frames/00000009.jpg").write_bytes(b"orphan")
        report, *_ = analysis.analyze_session(self.root)
        self.assertEqual(report["missing_jpeg_files"], ["00000000.jpg"])
        self.assertEqual(report["orphan_jpeg_files"], ["00000009.jpg"])
        self.assertEqual(report["sensors"]["gyroscope"]["sequence_gaps"], 2)
        self.assertEqual(report["sensors"]["gyroscope"]["duplicate_ids"], 1)
        self.assertFalse(report["checks"]["sequence_integrity"])
        self.assertFalse(report["checks"]["frame_files_consistent"])

    def test_active_and_storage_error_sessions_are_refused_before_output_is_written(self):
        self.session(status="recording")
        with self.assertRaisesRegex(ValueError, "Stop & save"):
            analysis.export_analysis(self.root, make_plot=False)
        self.assertFalse((self.root / "analysis").exists())
        self.session(status="interrupted", storage_error="Rollback failed")
        with self.assertRaisesRegex(ValueError, "storage error"):
            analysis.analyze_session(self.root)

    def test_empty_interrupted_session_stays_explicitly_incomplete(self):
        self.session(status="interrupted")
        report, frames, groups, aligned = analysis.analyze_session(self.root)
        self.assertEqual(report["frames"]["count"], 0)
        self.assertEqual(report["origin_timestamp_ns"], "0")
        self.assertFalse(report["checks"]["completed_session"])
        self.assertFalse(report["checks"]["all_frames_have_required_imu_match"])
        self.assertEqual(aligned, [])
        self.assertTrue(any("Interrupted" in warning for warning in report["warnings"]))

    def test_invalid_records_include_file_and_line_and_bad_windows_are_rejected(self):
        self.session(samples=[{**sample("gyroscope", 0, BASE), "values": {"x": None, "y": 0, "z": 0}}])
        with self.assertRaisesRegex(ValueError, "telemetry.jsonl:1: inertial"):
            analysis.analyze_session(self.root)
        (self.root / "telemetry.jsonl").write_text('{"timestamp_ns": 123}\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "telemetry.jsonl:1: timestamp_ns"):
            analysis.analyze_session(self.root)
        for value in (0, -1, float("nan"), float("inf")):
            with self.assertRaisesRegex(ValueError, "finite and positive"):
                analysis.analyze_session(self.root, value)
        self.session(samples=[{**sample("gyroscope", 0, BASE), "units": "deg_s"}])
        with self.assertRaisesRegex(ValueError, "units must be rad_s"):
            analysis.analyze_session(self.root)
        self.session(samples=[{**sample("gyroscope", 0, BASE), "session_id": "another-session"}])
        with self.assertRaisesRegex(ValueError, "conflicting session IDs"):
            analysis.analyze_session(self.root)

    @unittest.skipUnless(HAS_MATPLOTLIB, "optional Matplotlib dependency is not installed")
    def test_cli_exports_real_plot_artifacts_and_json_csv(self):
        self.session([frame(0, BASE), frame(1, BASE + 50000000)], [sample("accelerometer", 0, BASE), sample("accelerometer", 1, BASE + 50000000)])
        result = subprocess.run([sys.executable, str(SCRIPT), str(self.root)], capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = Path(json.loads(result.stdout)["output"])
        self.assertEqual((output / "timeline.png").read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        svg = output / "timeline.svg"
        self.assertEqual(ET.parse(svg).getroot().tag, "{http://www.w3.org/2000/svg}svg")
        self.assertIn("No gyroscope samples recorded", svg.read_text(encoding="utf-8"))
        self.assertTrue((output / "analysis.json").is_file())
        self.assertTrue((output / "alignment.csv").is_file())


if __name__ == "__main__":
    unittest.main()
