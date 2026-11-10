"""Explicit online preparation only. Runtime never imports this script."""

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

REVISION = "87416418657359cb625c412a48b6e1d6d41c29bd"
BASE = f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{REVISION}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("models"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    files = {}
    for filename in ["fas.traineddata", "eng.traineddata", "LICENSE"]:
        with urllib.request.urlopen(f"{BASE}/{filename}", timeout=60) as response:
            data = response.read(20 * 1024 * 1024 + 1)
        if len(data) > 20 * 1024 * 1024:
            raise SystemExit("model_size_limit")
        (args.output / filename).write_bytes(data)
        if filename.endswith(".traineddata"):
            files[filename] = hashlib.sha256(data).hexdigest()
    manifest = {
        "source": "tesseract-ocr/tessdata_fast",
        "revision": REVISION,
        "license": "Apache-2.0",
        "files": files,
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("Local models prepared; archive this directory with your offline installation.")


if __name__ == "__main__":
    main()
