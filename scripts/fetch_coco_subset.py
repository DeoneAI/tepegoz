"""Fetch a small, explicitly class-balanced COCO val2017 road-user evaluation subset."""
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.fetch_euroc import RemoteZip

ANNOTATIONS = "https://s3.amazonaws.com/images.cocodataset.org/annotations/annotations_trainval2017.zip"
NAMES = ("person", "bicycle", "car", "motorcycle", "bus", "truck")


def fetch(per_class=3):
    destination = ROOT / ".tools/datasets/coco-road-val"
    destination.mkdir(parents=True, exist_ok=True)
    annotation_file = destination / "instances_val2017.json"
    if not annotation_file.exists():
        with zipfile.ZipFile(RemoteZip(ANNOTATIONS, ROOT / ".tools/datasets/coco-annotation-range-cache")) as archive:
            annotation_file.write_bytes(archive.read("annotations/instances_val2017.json"))
    source = json.loads(annotation_file.read_text(encoding="utf-8"))
    categories = [category for category in source["categories"] if category["name"] in NAMES]
    category_ids = {category["id"] for category in categories}
    by_image = defaultdict(list)
    for annotation in source["annotations"]:
        if annotation["category_id"] in category_ids:
            by_image[annotation["image_id"]].append(annotation)
    chosen = set()
    for category in categories:
        eligible = sorted(image_id for image_id, annotations in by_image.items() if not any(value["iscrowd"] for value in annotations) and any(value["category_id"] == category["id"] and value["area"] >= 32 * 32 for value in annotations))
        chosen.update(eligible[:per_class])
    images = [image for image in source["images"] if image["id"] in chosen]
    hashes = {}
    (destination / "images").mkdir(exist_ok=True)
    for image in images:
        file = destination / "images" / image["file_name"]
        url = "https://s3.amazonaws.com/images.cocodataset.org/val2017/" + image["file_name"]
        if not file.exists():
            urllib.request.urlretrieve(url, file)
        hashes[file.name] = hashlib.sha256(file.read_bytes()).hexdigest()
        print("COCO image", file.name, flush=True)
    annotations = [annotation for image_id in sorted(chosen) for annotation in by_image[image_id]]
    subset = {"images": images, "annotations": annotations, "categories": categories, "licenses": source["licenses"],
              "sampling": f"First {per_class} sorted eligible val images per target class with at least one >=32px-area-scale target and no target crowd annotations; retain every target-class annotation in selected images. Nonrandom class-balanced subset, not the full COCO benchmark."}
    (destination / "subset.json").write_text(json.dumps(subset, indent=2), encoding="utf-8")
    manifest = {"source": "https://cocodataset.org/", "annotation_archive": ANNOTATIONS, "annotation_sha256": hashlib.sha256(annotation_file.read_bytes()).hexdigest(), "image_sha256": hashes,
                "images": len(images), "annotations": len(annotations), "categories": categories, "license": "COCO annotations CC BY 4.0; image licenses/Flickr attribution are preserved from source metadata", "sampling": subset["sampling"]}
    (destination / "provenance.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"output": str(destination), "images": len(images), "annotations": len(annotations)}


if __name__ == "__main__":
    try:
        print(json.dumps(fetch()))
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        raise SystemExit(str(error))
