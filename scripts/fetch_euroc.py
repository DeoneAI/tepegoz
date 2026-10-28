"""Fetch a bounded EuRoC V1_01_easy camera/IMU subset using validated HTTP byte ranges.

ETH's original download moved to a rate-limited repository. This uses a pinned public mirror,
retains the original dataset attribution, verifies ZIP CRCs and records SHA-256 for every file.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile
import requests


ROOT = Path(__file__).resolve().parents[1]
URL = "https://huggingface.co/datasets/pepijn223/euroc-mirror/resolve/d05bd6a92a5f456562153f83d65805fea27cb57d/V1_01_easy.zip"


class RemoteZip(io.RawIOBase):
    def __init__(self, url, cache):
        self.url, self.cache = url, Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.position, self.block_size = 0, 4 * 1024 * 1024
        with requests.get(url, headers={"Range": "bytes=0-0"}, stream=True, timeout=60) as response:
            response.raise_for_status()
            content_range = response.headers.get("Content-Range", "")
            if response.status_code != 206 or not content_range.startswith("bytes 0-0/"):
                raise ValueError("Server does not provide verified byte ranges; refusing a full archive download")
            self.size = int(content_range.split("/")[1])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        position = offset if whence == 0 else self.position + offset if whence == 1 else self.size + offset
        if position < 0 or position > self.size:
            raise ValueError("ZIP seek outside archive")
        self.position = position
        return position

    def read(self, size=-1):
        size = min(self.size - self.position, self.size - self.position if size < 0 else size)
        chunks = []
        while size > 0:
            index = self.position // self.block_size
            start = index * self.block_size; end = min(self.size - 1, start + self.block_size - 1)
            block = self.cache / f"{index:06d}.bin"
            if not block.exists() or block.stat().st_size != end - start + 1:
                # The unique query prevents intermediary caches from serving a different range.
                with requests.get(self.url + f"?download=true&chunk={index}", headers={"Range": f"bytes={start}-{end}"}, stream=True, timeout=90) as response:
                    response.raise_for_status()
                    if response.status_code != 206 or response.headers.get("Content-Range") != f"bytes {start}-{end}/{self.size}":
                        raise ValueError("Server returned the wrong byte range")
                    expected = end - start + 1
                    data = bytearray()
                    # Check status/range before consuming a body, and bound bytes even if
                    # a faulty server sends more than its declared range.
                    for chunk in response.iter_content(65536):
                        if len(data) + len(chunk) > expected:
                            raise ValueError("Archive block exceeds its declared byte range")
                        data.extend(chunk)
                    if len(data) != expected:
                        raise ValueError("Truncated archive block")
                    temporary = block.with_suffix(".part"); temporary.write_bytes(data); temporary.replace(block)
            offset = self.position - start; count = min(size, end - self.position + 1)
            with block.open("rb") as stream:
                stream.seek(offset); chunks.append(stream.read(count))
            self.position += count; size -= count
        return b"".join(chunks)


def fetch_subset(frames=600):
    if not 1 <= frames <= 2000:
        raise ValueError("Choose 1..2000 camera frames")
    destination = (ROOT / ".tools/datasets/euroc-v101").resolve()
    if not destination.is_relative_to(ROOT / ".tools"):
        raise ValueError("Dataset destination escaped the workspace tools directory")
    cache = ROOT / ".tools/datasets/euroc-v101-range-cache"
    hashes = {}
    with zipfile.ZipFile(RemoteZip(URL, cache)) as archive:
        names = archive.namelist()
        camera_csv = next(name for name in names if name.endswith("mav0/cam0/data.csv"))
        prefix = camera_csv[:-len("mav0/cam0/data.csv")]
        selected = [row for row in csv.reader(io.StringIO(archive.read(camera_csv).decode())) if row and not row[0].startswith("#")][:frames]
        required = ["mav0/cam0/data.csv", "mav0/cam0/sensor.yaml", "mav0/imu0/data.csv", "mav0/imu0/sensor.yaml", "mav0/state_groundtruth_estimate0/data.csv", "mav0/state_groundtruth_estimate0/sensor.yaml"]
        required += ["mav0/cam0/data/" + row[1].strip() for row in selected]
        for index, relative in enumerate(required):
            file = (destination / relative).resolve()
            if not file.is_relative_to(destination):
                raise ValueError("Unsafe ZIP member path")
            data = archive.read(prefix + relative)  # ZipFile checks member CRC, including decompression.
            file.parent.mkdir(parents=True, exist_ok=True); file.write_bytes(data)
            hashes[relative] = hashlib.sha256(data).hexdigest()
            if index % 50 == 0:
                print(f"Extracted {index}/{len(required)} members", flush=True)
    with (destination / "camera_selection.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream); writer.writerow(["timestamp_ns", "filename"]); writer.writerows(selected)
    manifest = {"dataset": "EuRoC MAV V1_01_easy", "original_source": "https://projects.asl.ethz.ch/datasets/euroc-mav/", "doi": "10.3929/ethz-b-000690084",
                "mirror_url": URL, "mirror_revision": "d05bd6a92a5f456562153f83d65805fea27cb57d", "camera_frames": len(selected), "first_camera_timestamp_ns": selected[0][0], "last_camera_timestamp_ns": selected[-1][0],
                "selected_member_sha256": hashes, "verification": "ZIP member CRC and per-file SHA-256; full archive SHA-256 not independently verified", "license": "Retain ETH EuRoC dataset attribution and source terms; mirror is a transport source"}
    (destination / "subset.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"output": str(destination), "camera_frames": len(selected), "members": len(hashes)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--frames", type=int, default=600)
    try:
        print(json.dumps(fetch_subset(parser.parse_args().frames)))
    except (OSError, ValueError, requests.RequestException, zipfile.BadZipFile, KeyError) as error:
        parser.exit(1, f"{error}\n")
