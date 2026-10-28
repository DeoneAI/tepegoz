"""Fetch a bounded real RGB/GPS-IMU road sequence from KITTI's public S3 distribution.

Only selected color frames, OXTS packets, timestamps and calibration are read from the
large archive. Verified byte-range requests prevent downloading the whole archive.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.fetch_euroc import RemoteZip

URL = "https://s3.eu-central-1.amazonaws.com/avg-kitti/raw_data/2011_09_30_drive_0028/2011_09_30_drive_0028_sync.zip"
CALIBRATION_URL = "https://s3.eu-central-1.amazonaws.com/avg-kitti/raw_data/2011_09_30_calib.zip"


def fetch(frames=1205):
    if not 1 <= frames <= 1500:
        raise ValueError("Choose a bounded 1..1500-frame subset")
    destination = (ROOT / ".tools/datasets/kitti-0028").resolve()
    if not destination.is_relative_to(ROOT / ".tools"):
        raise ValueError("Dataset destination escaped workspace tools")
    hashes = {}
    with zipfile.ZipFile(RemoteZip(URL, ROOT / ".tools/datasets/kitti-0028-range-cache")) as archive:
        names = set(archive.namelist())
        first = next(name for name in names if name.endswith("/image_02/data/0000000000.png"))
        prefix = first[:-len("image_02/data/0000000000.png")]
        camera_times = archive.read(prefix + "image_02/timestamps.txt").decode().splitlines()
        imu_times = archive.read(prefix + "oxts/timestamps.txt").decode().splitlines()
        if min(len(camera_times), len(imu_times)) < frames:
            raise ValueError("Requested subset exceeds synchronized stream length")
        files = ["image_02/timestamps.txt", "oxts/timestamps.txt"]
        files += [f"image_02/data/{index:010d}.png" for index in range(frames)]
        imu_count = min(frames + 1, len(imu_times))
        files += [f"oxts/data/{index:010d}.txt" for index in range(imu_count)]
        for index, relative in enumerate(files):
            file = (destination / relative).resolve()
            if not file.is_relative_to(destination):
                raise ValueError("Unsafe archive member path")
            data = archive.read(prefix + relative)
            file.parent.mkdir(parents=True, exist_ok=True); file.write_bytes(data)
            hashes[relative] = hashlib.sha256(data).hexdigest()
            if index % 100 == 0:
                print(f"KITTI members {index}/{len(files)}", flush=True)
    with urllib.request.urlopen(CALIBRATION_URL, timeout=60) as response:
        calibration_zip = response.read(2_000_001)
    if len(calibration_zip) > 2_000_000:
        raise ValueError("Unexpectedly large calibration archive")
    with zipfile.ZipFile(io.BytesIO(calibration_zip)) as archive:
        for name in ("calib_cam_to_cam.txt", "calib_velo_to_cam.txt", "calib_imu_to_velo.txt"):
            member = next(value for value in archive.namelist() if value.endswith("/" + name))
            data = archive.read(member); (destination / name).write_bytes(data); hashes[name] = hashlib.sha256(data).hexdigest()
    selection = {"camera_frames": frames, "imu_packets": imu_count, "camera": camera_times[:frames], "imu": imu_times[:imu_count]}
    (destination / "selection.json").write_text(json.dumps(selection, indent=2), encoding="utf-8")
    provenance = {"dataset": "KITTI raw 2011_09_30_drive_0028 synced/rectified color camera 02 + OXTS", "official_source": "https://www.cvlibs.net/datasets/kitti/raw_data.php", "archive_url": URL, "calibration_url": CALIBRATION_URL,
                  "camera_frames": frames, "selected_file_sha256": hashes, "verification": "ZIP CRC and per-file SHA-256; full large-archive SHA-256 not independently verified", "license": "Retain KITTI attribution and original dataset terms; this is research data, not a phone acceptance recording"}
    (destination / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    return {"output": str(destination), "camera_frames": frames, "imu_packets": imu_count}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__); cli.add_argument("--frames", type=int, default=1205)
    try:
        print(json.dumps(fetch(cli.parse_args().frames)))
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        cli.exit(1, f"{error}\n")
