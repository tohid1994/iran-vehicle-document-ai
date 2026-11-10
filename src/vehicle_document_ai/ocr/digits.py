"""Independent, synthetic-font glyph evidence. Never searches identifier checksums."""

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from ..core import DocumentError


def normalize_glyph(mask):
    ys, xs = np.where(mask > 0)
    if not len(xs):
        return None
    cropped = mask[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    return cv2.resize(cropped.astype(np.float32), (24, 32)), cropped.shape[1] / cropped.shape[0]


def segment_digits(gray, count=10):
    """Split connected printed digits geometrically, before knowing their values."""
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    _, _, stats, _ = cv2.connectedComponentsWithStats(255 - binary)
    components = sorted(
        [list(s[:4]) for s in stats[1:] if s[3] > gray.shape[0] * 0.3 and s[4] > 15]
    )
    if not components:
        return []
    median = float(np.median([s[2] for s in components]))
    parts = []
    for x, y, w, h in components:
        if w > median * 1.7:
            ink = (binary[y : y + h, x : x + w] < 128).sum(axis=0)
            a, b = int(w * 0.35), int(w * 0.65)
            cut = a + int(ink[a:b].argmin())
            parts.extend([(x, y, cut, h), (x + cut, y, w - cut, h)])
        else:
            parts.append((x, y, w, h))
    if len(parts) != count:
        return []
    return [(binary[y : y + h, x : x + w] < 128).astype(np.uint8) for x, y, w, h in parts]


class DigitTemplates:
    def __init__(self, model_dir: Path):
        path = model_dir / "persian_digit_templates.npz"
        try:
            manifest = json.loads((model_dir / "manifest.json").read_text())
            if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["files"][path.name]:
                raise ValueError()
            with np.load(path, allow_pickle=False) as model:
                self.glyphs = model["glyphs"].astype(np.float32) / 255
                self.ratios = model["ratios"]
                self.labels = model["labels"]
            if self.glyphs.shape[1:] != (32, 24) or not 10 <= len(self.labels) <= 4096:
                raise ValueError()
            if len(self.glyphs) != len(self.labels) or len(self.ratios) != len(self.labels):
                raise ValueError()
        except (OSError, ValueError, KeyError) as exc:
            raise DocumentError("digit_templates_unavailable_or_unverified") from exc

    def classify(self, glyph):
        normalized = normalize_glyph(glyph)
        if normalized is None:
            return None
        image, ratio = normalized
        distances = np.abs(self.glyphs - image).mean(axis=(1, 2))
        distances += 0.15 * np.abs(np.log(ratio / self.ratios))
        classes = sorted(
            (float(distances[self.labels == digit].min()), str(digit)) for digit in range(10)
        )
        distance, digit = classes[0]
        margin = classes[1][0] - distance
        # Visual-distance rejection thresholds, not calibrated confidence values.
        return digit if distance < 0.20 and margin > 0.05 else None

    def fuse(self, observed: str, glyphs: list) -> str | None:
        if (
            len(observed) != 10
            or len(glyphs) != 10
            or not observed.isascii()
            or not observed.isdigit()
        ):
            return None
        # Each replacement must be an independently recognized image glyph.
        # No digit is generated from a checksum, registry, expected answer or ID prefix.
        return "".join(
            self.classify(glyph) or digit for digit, glyph in zip(observed, glyphs, strict=True)
        )
