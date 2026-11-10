import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from ..core import DocumentError
from ..schemas import Box, TextRegion


class TesseractAdapter:
    name = "tesseract-fas-eng"

    def __init__(self, model_dir: str | Path = "models", languages: str = "fas+eng"):
        if languages not in {"fas+eng", "eng", "fas"}:
            raise ValueError("unsupported_languages")
        self.model_dir = Path(model_dir).resolve()
        self.languages = languages

    def inventory(self) -> dict:
        executable = shutil.which("tesseract")
        models = []
        try:
            manifest = json.loads((self.model_dir / "manifest.json").read_text())
        except (OSError, ValueError):
            manifest = {}
        for lang in self.languages.split("+"):
            path = self.model_dir / f"{lang}.traineddata"
            expected = manifest.get("files", {}).get(path.name)
            digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
            models.append(
                {
                    "language": lang,
                    "present": digest is not None,
                    "sha256": digest,
                    "verified": bool(expected and expected == digest),
                }
            )
        return {
            "engine": self.name,
            "runtimeAvailable": bool(executable),
            "models": models,
            "ready": bool(executable) and all(m["verified"] for m in models),
        }

    def recognize(self, image: np.ndarray, timeout: float = 30) -> list[TextRegion]:
        if not self.inventory()["ready"]:
            raise DocumentError("ocr_models_unavailable_or_unverified")
        # Private directory, fixed filenames, no shell, cleanup on success AND errors.
        with tempfile.TemporaryDirectory(prefix="ivdai-") as directory:
            source = Path(directory) / "input.png"
            Image.fromarray(image).save(source)
            env = {**os.environ, "OMP_THREAD_LIMIT": "1"}
            try:
                run = subprocess.run(
                    [
                        "tesseract",
                        str(source),
                        "stdout",
                        "--tessdata-dir",
                        str(self.model_dir),
                        "-l",
                        self.languages,
                        "--oem",
                        "1",
                        "--psm",
                        "11",
                        "-c",
                        "tessedit_create_tsv=1",
                    ],
                    capture_output=True,
                    timeout=timeout,
                    check=False,
                    env=env,
                )
            except subprocess.TimeoutExpired as exc:
                raise DocumentError("ocr_timeout") from exc
            if run.returncode:
                raise DocumentError("ocr_failed")
        regions = []
        for row in csv.DictReader(io.StringIO(run.stdout.decode("utf-8")), delimiter="\t"):
            text = row.get("text", "").strip()
            if not text or row.get("level") != "5":
                continue
            x, y, w, h = (int(row[k]) for k in ("left", "top", "width", "height"))
            if w <= 0 or h <= 0:
                continue
            score = float(row["conf"])
            regions.append(
                TextRegion(
                    text=text,
                    box=Box(x=x, y=y, width=w, height=h),
                    engineScore=score if 0 <= score <= 100 else None,
                )
            )
        return regions

    def recognize_region(self, image: np.ndarray, box: Box, timeout: float = 30):
        h, w = image.shape[:2]
        if box.x + box.width > w or box.y + box.height > h:
            raise DocumentError("region_out_of_bounds")
        regions = self.recognize(
            image[box.y : box.y + box.height, box.x : box.x + box.width], timeout
        )
        for region in regions:
            region.box.x += box.x
            region.box.y += box.y
        return regions
