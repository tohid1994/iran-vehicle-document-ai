"""Explicit online preparation only. Runtime never imports this script."""

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

REVISION = "87416418657359cb625c412a48b6e1d6d41c29bd"
REFINE_REVISION = "e12c65a915945e4c28e237a9b52bc4a8f39a0cec"
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
    refine_base = f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/{REFINE_REVISION}"
    with urllib.request.urlopen(f"{refine_base}/fas.traineddata", timeout=60) as response:
        refine = response.read(20 * 1024 * 1024 + 1)
    if len(refine) > 20 * 1024 * 1024:
        raise SystemExit("model_size_limit")
    (args.output / "fas_refine.traineddata").write_bytes(refine)
    files["fas_refine.traineddata"] = hashlib.sha256(refine).hexdigest()
    manifest = {
        "source": "tesseract-ocr/tessdata_fast",
        "revision": REVISION,
        "license": "Apache-2.0",
        "files": files,
        "refinement": {
            "source": "tesseract-ocr/tessdata_best",
            "revision": REFINE_REVISION,
            "files": ["fas_refine.traineddata"],
            "license": "Apache-2.0",
        },
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("prepare_digit_templates.py")),
            "--output",
            str(args.output),
        ],
        check=True,
    )
    print("Local models prepared; archive this directory with your offline installation.")


if __name__ == "__main__":
    main()
