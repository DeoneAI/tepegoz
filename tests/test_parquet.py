import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("export_parquet", Path(__file__).resolve().parents[1] / "scripts/export_parquet.py")
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)
HAS_ARROW = importlib.util.find_spec("pyarrow") is not None


@unittest.skipUnless(HAS_ARROW, "optional PyArrow dependency is not installed")
class ParquetExportTests(unittest.TestCase):
    def test_typed_roundtrip_preserves_ns_null_gnss_and_original_jsonl(self):
        import pyarrow.parquet as pq
        with tempfile.TemporaryDirectory(prefix="sensorlink-parquet-") as directory:
            root = Path(directory)
            (root / "manifest.json").write_text('{"status":"completed"}', encoding="utf-8")
            records = [
                {"session_id":"abc", "sensor_type":"gyroscope", "timestamp_ns":"999999999999999999", "sequence_id":0, "values":{"x":0,"y":1,"z":2}, "units":"rad_s"},
                {"session_id":"abc", "sensor_type":"gnss", "timestamp_ns":"999999999999999998", "sequence_id":0, "values":{"latitude":40.4,"longitude":49.8,"altitude":None}, "accuracy_m":12},
            ]
            source = "\n".join(map(json.dumps, records)) + "\n"
            (root / "telemetry.jsonl").write_text(source, encoding="utf-8")
            result = exporter.export_session(root, batch_size=1)
            rows = pq.read_table(result["path"]).to_pylist()
            self.assertEqual(result["rows"], 2)
            self.assertEqual(rows[0]["timestamp_ns"], 999999999999999999)
            self.assertIsNone(rows[0]["latitude"])
            self.assertEqual(rows[1]["accuracy_m"], 12)
            self.assertIsNone(rows[1]["altitude"])
            self.assertEqual((root / "telemetry.jsonl").read_text(encoding="utf-8"), source)

    def test_active_session_refused_and_empty_finalized_file_is_readable(self):
        import pyarrow.parquet as pq
        with tempfile.TemporaryDirectory(prefix="sensorlink-parquet-") as directory:
            root = Path(directory)
            manifest = root / "manifest.json"
            manifest.write_text('{"status":"recording"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Stop & save"):
                exporter.export_session(root)
            manifest.write_text('{"status":"completed"}', encoding="utf-8")
            (root / "telemetry.jsonl").write_text("", encoding="utf-8")
            result = exporter.export_session(root)
            self.assertEqual(pq.ParquetFile(result["path"]).metadata.num_rows, 0)


if __name__ == "__main__":
    unittest.main()
