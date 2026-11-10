"""Field-specific readers; no expected document values or identifier repairs."""

import re
import time

import cv2
import numpy as np

from ..core import DocumentError
from ..validation import normalize

LETTER_NAMES = set(
    (
        "ای بی سی دی ایی اف جی اچ آی جیی کی ال ام ان او پی کیو آر اس تی یو وی دبلیو ایکس وای زد زی"
    ).split()
)


class RegionalReader:
    def __init__(self, adapter, timeout):
        self.adapter = adapter
        self.deadline = time.monotonic() + timeout

    def read(self, gray, lang, psm, whitelist=None):
        from .tesseract import TesseractAdapter

        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise DocumentError("ocr_timeout")
        gray = cv2.copyMakeBorder(gray, 15, 15, 15, 15, cv2.BORDER_CONSTANT, value=255)
        regions = TesseractAdapter(self.adapter.model_dir, lang).recognize(
            cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB), remaining, psm=psm, whitelist=whitelist
        )
        return regions, gray

    def model(self, image, box):
        gray = cv2.cvtColor(
            image[box.y : box.y + box.height, box.x : box.x + box.width], cv2.COLOR_RGB2GRAY
        )
        regions, padded = self.read(gray, "fas_refine", 7)
        words, scores, sources = [], [], []
        for region in sorted(regions, key=lambda r: r.box.x, reverse=True):
            word = normalize(region.text).strip(".,،:؛")
            sources.append(region.text)
            if word in LETTER_NAMES:
                words.append(word)
                if region.engineScore is not None:
                    scores.append(region.engineScore)
                continue
            b = region.box
            crop = padded[max(0, b.y - 3) : b.y + b.height + 3, max(0, b.x - 3) : b.x + b.width + 3]
            reread, _ = self.read(crop, "fas", 7)
            tokens = [
                normalize(r.text).strip(".,،:؛")
                for r in sorted(reread, key=lambda r: r.box.x, reverse=True)
            ]
            if not tokens or not all(token in LETTER_NAMES for token in tokens):
                original = sorted(regions, key=lambda r: r.box.x, reverse=True)
                actual_scores = [r.engineScore for r in original if r.engineScore is not None]
                return (
                    " ".join(r.text for r in original),
                    box,
                    min(actual_scores) if actual_scores else None,
                    "legacy_grid_regional_ocr",
                    {"sourceReadings": [r.text for r in original]},
                )
            words.extend(tokens)
            scores.extend(r.engineScore for r in reread if r.engineScore is not None)
            sources.extend(r.text for r in reread)
        return (
            " ".join(words),
            box,
            min(scores) if scores else None,
            "model_word_reread",
            {"sourceReadings": sources},
        )

    def vin(self, image, box):
        from ..layout.legacy import detect_grid

        grid = detect_grid(image)
        if grid is None:
            return "", box, None, "vin_grid_cells"
        rgb = image[grid.y : grid.y + grid.height, grid.x : grid.x + grid.width].astype(np.int16)
        copper = ((rgb[:, :, 0] - rgb[:, :, 1] > 12) & (rgb[:, :, 0] - rgb[:, :, 2] > 18)).astype(
            np.uint8
        )
        copper = cv2.morphologyEx(copper, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        peaks = np.flatnonzero(copper.sum(0) > grid.height * 0.65)
        groups = np.split(peaks, np.flatnonzero(np.diff(peaks) > 2) + 1)
        centers = [int(round(g.mean())) + grid.x for g in groups if len(g)]
        if len(centers) != 17:
            return "", box, None, "vin_grid_cells"
        step = int(round(np.median(np.diff(centers))))
        bounds = [centers[0] - step] + centers
        characters, sources = [], []
        for left, right in zip(bounds, bounds[1:], strict=False):
            # This legacy form prints glyphs on the left edges of cells, not their centers.
            shift = round(step * 0.21)
            top = grid.y + round(grid.height * 0.12)
            bottom = grid.y + grid.height - round(grid.height * 0.15)
            crop = image[top:bottom, left - shift : right - shift]
            gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
            gray = cv2.threshold(gray, 70, 255, cv2.THRESH_BINARY)[1]
            observed = ""
            for mode in (10, 13):
                regions, _ = self.read(gray, "eng", mode, "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
                text = "".join(r.text for r in regions).strip()
                sources.append(text)
                if re.fullmatch(r"[A-Z0-9]", text):
                    observed = text
                    break
            if not observed:
                return "", box, None, "vin_grid_cells", {"sourceReadings": sources}
            characters.append(observed)
        return ("".join(characters), box, None, "vin_grid_cells", {"sourceReadings": sources})

    def plate(self, image, box):
        gray = cv2.cvtColor(
            image[box.y : box.y + box.height, box.x : box.x + box.width], cv2.COLOR_RGB2GRAY
        )
        contours, _ = cv2.findContours(
            (gray < 110).astype(np.uint8) * 255, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        contours = [c for c in contours if cv2.boundingRect(c)[2] > box.width * 0.7]
        if not contours:
            return "", box, None, "plate_components"
        points = cv2.boxPoints(cv2.minAreaRect(max(contours, key=cv2.contourArea)))
        sums, diffs = points.sum(1), np.diff(points, axis=1).ravel()
        points = points[[sums.argmin(), diffs.argmin(), sums.argmax(), diffs.argmax()]]
        width = int(
            max(np.linalg.norm(points[1] - points[0]), np.linalg.norm(points[2] - points[3]))
        )
        height = int(
            max(np.linalg.norm(points[3] - points[0]), np.linalg.norm(points[2] - points[1]))
        )
        if width < 80 or height < 20 or len(np.unique(points, axis=0)) != 4:
            return "", box, None, "plate_components"
        target = np.float32([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]])
        warp = cv2.getPerspectiveTransform(points.astype(np.float32), target)
        plate = cv2.warpPerspective(gray, warp, (width, height))[5:-5, 5:-5]
        ink = plate < 110
        xs = np.flatnonzero(ink.sum(0) > plate.shape[0] * 0.7)
        xs = xs[(xs > plate.shape[1] * 0.5) & (xs < plate.shape[1] * 0.85)]
        if not len(xs):
            return "", box, None, "plate_components"
        separator = int(np.median(xs))
        windows = [
            (5, round(separator * 0.29)),
            (round(separator * 0.53), round(separator * 0.94)),
            (
                separator + round((plate.shape[1] - separator) * 0.185),
                plate.shape[1] - round((plate.shape[1] - separator) * 0.1),
            ),
        ]
        numbers, sources = [], []
        for index, ((left, right), count) in enumerate(zip(windows, (2, 3, 2), strict=True)):
            crop = plate[5:-2, left:right]
            if index == 1:
                crop = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
            regions, _ = self.read(crop, "fas", 7)
            text = normalize("".join(r.text for r in regions)).replace(" ", "")
            sources.append(text)
            if not re.fullmatch(rf"[0-9]{{{count}}}", text):
                return "", box, None, "plate_components", {"sourceReadings": sources}
            numbers.append(text)
        binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        regions, _ = self.read(binary, "fas", 7)
        text = normalize(" ".join(r.text for r in regions))
        sources.append(text)
        letters = re.findall(r"[آ-ی]", text)
        if len(letters) != 1:
            return "", box, None, "plate_components", {"sourceReadings": sources}
        return (
            f"{numbers[0]} {letters[0]} {numbers[1]} {numbers[2]}",
            box,
            None,
            "plate_components",
            {"sourceReadings": sources},
        )
