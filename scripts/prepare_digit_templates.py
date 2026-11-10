"""Generate a local digit model only from freely licensed synthetic font glyphs."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from vehicle_document_ai.ocr.digits import normalize_glyph  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fonts", type=Path, default=Path("/usr/share/fonts/truetype"))
    parser.add_argument("--font-license", type=Path, action="append")
    parser.add_argument("--output", type=Path, default=Path("models"))
    args = parser.parse_args()
    names = ("NotoNaskhArabic", "NotoSansArabic", "NotoKufiArabic", "DejaVuSans")
    fonts = sorted(p for p in args.fonts.rglob("*.ttf") if p.name.startswith(names))
    if not fonts:
        raise SystemExit("Install fonts-noto-core and fonts-dejavu-core, or pass --fonts")
    licenses = args.font_license or [
        Path("/usr/share/doc/fonts-noto-core/copyright"),
        Path("/usr/share/doc/fonts-dejavu-core/copyright"),
    ]
    if not all(p.is_file() for p in licenses):
        raise SystemExit("Supply --font-license for the fonts used to generate templates")
    glyphs, ratios, labels = [], [], []
    for path in fonts:
        font = ImageFont.truetype(str(path), 70)
        for digit, character in enumerate("۰۱۲۳۴۵۶۷۸۹"):
            canvas = Image.new("L", (150, 150), 0)
            ImageDraw.Draw(canvas).text((20, 0), character, font=font, fill=255)
            mask = (np.array(canvas) > 128).astype(np.uint8)
            for stroke in (-1, 0, 1):
                mat = (
                    cv2.erode(mask, np.ones((2, 2), np.uint8))
                    if stroke == -1
                    else (cv2.dilate(mask, np.ones((2, 2), np.uint8)) if stroke == 1 else mask)
                )
                normalized = normalize_glyph(mat)
                if normalized is None:
                    continue
                image, ratio = normalized
                glyphs.append(np.round(image * 255).astype(np.uint8))
                ratios.append(ratio)
                labels.append(digit)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "digit-font-LICENSES.txt").write_text(
        "\n\n".join(p.read_text() for p in licenses)
    )
    target = args.output / "persian_digit_templates.npz"
    np.savez_compressed(
        target, glyphs=np.array(glyphs), ratios=np.array(ratios), labels=np.array(labels)
    )
    manifest_path = args.output / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"][target.name] = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest["digitTemplates"] = {
        "version": "1",
        "training": "synthetic-font-glyphs-only",
        "fonts": [
            {"name": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in fonts
        ],
        "licenses": "DejaVu font license and SIL Open Font License (Noto)",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print("Prepared synthetic digit templates; no document or identity data used.")


if __name__ == "__main__":
    main()
