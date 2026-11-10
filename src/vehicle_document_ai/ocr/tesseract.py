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
        if languages not in {"fas+eng", "eng", "fas", "fas_refine"}:
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
            "regionalRefinementReady": self._refinement_ready(manifest),
        }

    def _refinement_ready(self, manifest):
        assets = ("fas_refine.traineddata", "persian_digit_templates.npz")
        for name in assets:
            path = self.model_dir / name
            expected = manifest.get("files", {}).get(name)
            if not expected or not path.is_file():
                return False
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                return False
        return True

    def recognize(
        self, image: np.ndarray, timeout: float = 30, *, psm: int = 11, whitelist: str | None = None
    ) -> list[TextRegion]:
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
                        str(psm),
                        "-c",
                        "tessedit_create_tsv=1",
                        *(["-c", f"tessedit_char_whitelist={whitelist}"] if whitelist else []),
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
        for row in csv.DictReader(
            io.StringIO(run.stdout.decode("utf-8")), delimiter="\t", quoting=csv.QUOTE_NONE
        ):
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

    def recognize_value(self, image: np.ndarray, box: Box, field: str, timeout: float):
        """A local value-only pass, with an explicit script and segmentation mode.

        Return actual OCR text; no edit-distance correction, catalog completion or
        identifier substitutions. Boxes describe the original processed-image ROI.
        """
        import cv2

        if field in {"vehicle.model", "vehicle.vin", "vehicle.plate"}:
            from .registration import RegionalReader

            return getattr(RegionalReader(self, timeout), field.split(".")[1])(image, box)
        if field == "vehicle.color":
            return self._recognize_color(image, box, timeout)
        if field == "owner.nationalId":
            return self._recognize_national_id(image, box, timeout)
        crop = image[box.y : box.y + box.height, box.x : box.x + box.width]
        gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
        gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        gray = cv2.copyMakeBorder(gray, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255)
        latin = field in {"vehicle.engineNumber", "vehicle.chassisNumber", "vehicle.vin"}
        numeric = field in {"vehicle.year", "owner.nationalId"}
        language = "eng" if latin else "fas"
        psm = (
            7 if field in {"vehicle.brand", "vehicle.engineNumber", "vehicle.chassisNumber"} else 13
        )
        whitelist = "0123456789۰۱۲۳۴۵۶۷۸۹" if numeric else None
        if latin:
            whitelist = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        adapter = TesseractAdapter(self.model_dir, language)
        regions = adapter.recognize(
            cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB), timeout, psm=psm, whitelist=whitelist
        )
        ordered = sorted(regions, key=lambda r: r.box.x, reverse=not (latin or numeric))
        text = " ".join(r.text for r in ordered)
        scores = [r.engineScore for r in ordered if r.engineScore is not None]
        return text, box, min(scores) if scores else None, "legacy_grid_regional_ocr"

    def _recognize_color(self, image, box, timeout):
        import cv2

        refine = TesseractAdapter(self.model_dir, "fas_refine")
        # No implicit download or fallback to a different unverified model.
        if not refine.inventory()["ready"]:
            raise DocumentError("ocr_models_unavailable_or_unverified")
        crop = image[box.y : box.y + box.height, box.x : box.x + box.width]
        gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
        gray = cv2.copyMakeBorder(gray, 15, 15, 15, 15, cv2.BORDER_CONSTANT, value=255)
        regions = refine.recognize(cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB), timeout, psm=7)
        ordered = sorted(regions, key=lambda r: r.box.x, reverse=True)
        scores = [r.engineScore for r in ordered if r.engineScore is not None]
        return (
            " ".join(r.text for r in ordered),
            box,
            min(scores) if scores else None,
            "legacy_grid_regional_ocr",
        )

    def _recognize_national_id(self, image, box, timeout):
        import re
        import time

        import cv2

        from ..schemas import Box
        from ..validation import normalize
        from .digits import DigitTemplates, segment_digits

        start = time.monotonic()
        h, w = image.shape[:2]
        # Include the adjacent field title as context; no expected digits are supplied.
        left = max(0, box.x - round(box.width * 0.075))
        top = max(0, box.y - round(box.height * 0.85))
        right = min(w, box.x + 2 * box.width)
        bottom = min(h, box.y + round(box.height * 1.44))
        context = image[top:bottom, left:right]
        refine = TesseractAdapter(self.model_dir, "fas_refine")
        regions = refine.recognize(context, timeout, psm=6)
        numbers = [r for r in regions if re.fullmatch(r"[0-9]{10}", normalize(r.text))]
        if len(numbers) != 1:
            return "", box, None, "legacy_grid_regional_ocr"
        # The number must actually lie in the target value window, not a neighboring field.
        region = numbers[0]
        cx, cy = (
            left + region.box.x + region.box.width / 2,
            top + region.box.y + region.box.height / 2,
        )
        if not (box.x <= cx <= box.x + box.width and box.y <= cy <= box.y + box.height):
            return "", box, None, "legacy_grid_regional_ocr"
        observed = normalize(region.text)
        gray = cv2.cvtColor(
            image[box.y : box.y + box.height, box.x : box.x + box.width], cv2.COLOR_RGB2GRAY
        )
        if time.monotonic() - start >= timeout:
            raise DocumentError("ocr_timeout")
        model = DigitTemplates(self.model_dir)
        fused = model.fuse(observed, segment_digits(gray))
        return (
            fused or "",
            Box(x=box.x, y=box.y, width=box.width, height=box.height),
            None,
            "legacy_grid_regional_ocr:independent_digit_fusion",
            {"sourceReadings": [region.text, fused or ""]},
        )

    def confirm_legacy_layout(self, image, grid, timeout):
        import cv2

        from ..validation import normalize
        from .registration import RegionalReader

        scale = grid.width / 923
        x1, x2 = round(grid.x + (890 - 491) * scale), round(grid.x + (1050 - 491) * scale)
        y1, y2 = round(grid.y + (640 - 694) * scale), round(grid.y + (699 - 694) * scale)
        crop = cv2.cvtColor(image[max(0, y1) : y2, max(0, x1) : x2], cv2.COLOR_RGB2GRAY)
        crop = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        regions, _ = RegionalReader(self, timeout).read(crop, "fas", 7)
        text = normalize(
            " ".join(r.text for r in sorted(regions, key=lambda r: r.box.x, reverse=True))
        )
        return "شماره" in text and "شاسی" in text
