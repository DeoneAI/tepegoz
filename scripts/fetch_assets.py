"""Fetch explicitly versioned public research assets and verify their size and SHA-256."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request


ROOT = Path(__file__).resolve().parents[1]


def digest(file):
    hasher = hashlib.sha256()
    with file.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def fetch(asset):
    target = (ROOT / asset["path"]).resolve()
    if not target.is_relative_to(ROOT / ".tools"):
        raise ValueError("Asset destination must stay inside .tools/")
    if not asset["url"].startswith("https://"):
        raise ValueError("Asset URLs must use HTTPS")
    if target.is_file() and target.stat().st_size == asset["bytes"] and digest(target) == asset["sha256"]:
        return {"id": asset["id"], "path": str(target), "verified": True, "downloaded": False}
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    try:
        with urllib.request.urlopen(asset["url"], timeout=90) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        if temporary.stat().st_size != asset["bytes"] or digest(temporary) != asset["sha256"]:
            raise ValueError(f"Size/SHA-256 mismatch: {asset['id']}; refusing unverified asset")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return {"id": asset["id"], "path": str(target), "verified": True, "downloaded": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", choices=("vision", "roads", "road-images", "depth", "calibration", "all"), default="all")
    parser.add_argument("--id", help="fetch one named asset")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    assets = json.loads((ROOT / "configs/assets.json").read_text(encoding="utf-8"))["assets"]
    chosen = [asset for asset in assets if (args.group == "all" or asset["group"] == args.group) and (not args.id or asset["id"] == args.id)]
    if not chosen:
        parser.error("No registered assets match the request")
    try:
        for asset in chosen:
            print(json.dumps(asset if args.list else fetch(asset)), flush=True)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
