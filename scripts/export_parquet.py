"""Convert a finalized Sensorlink session to typed Parquet, without changing raw logs."""
import argparse
import json
from pathlib import Path


def export_session(directory, batch_size=10000):
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("Install the optional exporter: python -m pip install -r scripts/requirements-parquet.txt") from exc
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") not in {"completed", "interrupted"}:
        raise ValueError("Stop & save the session before exporting Parquet.")
    schema = pa.schema([
        ("session_id", pa.string()), ("sensor_type", pa.string()),
        ("timestamp_ns", pa.int64()), ("sequence_id", pa.int64()),
        ("frame_axes", pa.string()), ("units", pa.string()), ("quality", pa.string()),
        ("x", pa.float64()), ("y", pa.float64()), ("z", pa.float64()),
        ("latitude", pa.float64()), ("longitude", pa.float64()),
        ("altitude", pa.float64()), ("speed", pa.float64()), ("heading", pa.float64()),
        ("accuracy_m", pa.float64()), ("altitude_accuracy_m", pa.float64()),
        ("timestamp_source", pa.string()), ("server_receive_ns", pa.int64()),
    ])
    output = directory / "telemetry.parquet"
    temporary = directory / "telemetry.parquet.tmp"
    count = 0
    try:
        with pq.ParquetWriter(temporary, schema, compression="zstd") as writer:
            batch = []
            with (directory / "telemetry.jsonl").open(encoding="utf-8") as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    sample = json.loads(line)
                    row = {key: sample.get(key) for key in schema.names}
                    row.update({key: sample["values"].get(key) for key in ("x", "y", "z", "latitude", "longitude", "altitude", "speed", "heading")})
                    for key in ("timestamp_ns", "server_receive_ns"):
                        row[key] = int(row[key]) if row[key] is not None else None
                    batch.append(row)
                    if len(batch) >= batch_size:
                        writer.write_table(pa.Table.from_pylist(batch, schema=schema))
                        count += len(batch)
                        batch.clear()
                if batch:
                    writer.write_table(pa.Table.from_pylist(batch, schema=schema))
                    count += len(batch)
        if pq.ParquetFile(temporary).metadata.num_rows != count:
            raise RuntimeError("Parquet row-count verification failed.")
        temporary.replace(output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {"path": str(output), "rows": count}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(export_session(args.session_dir)))
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, f"{error}\n")
