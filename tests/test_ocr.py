import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from vehicle_document_ai.core import DocumentError
from vehicle_document_ai.ocr.tesseract import TesseractAdapter


def test_model_tampering_fails_closed(tmp_path):
    (tmp_path / "eng.traineddata").write_bytes(b"changed")
    (tmp_path / "manifest.json").write_text(json.dumps({"files": {"eng.traineddata": "0" * 64}}))
    adapter = TesseractAdapter(tmp_path, "eng")
    assert not adapter.inventory()["ready"]
    with pytest.raises(DocumentError):
        adapter.recognize(np.zeros((50, 50, 3), dtype=np.uint8))


def test_real_tesseract_on_synthetic_image(tmp_path):
    source = Path("/usr/share/tesseract-ocr/5/tessdata/eng.traineddata")
    if not shutil.which("tesseract") or not source.exists():
        pytest.skip("System English OCR runtime not installed")
    shutil.copy(source, tmp_path / source.name)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    (tmp_path / "manifest.json").write_text(json.dumps({"files": {source.name: digest}}))
    image = Image.new("RGB", (900, 180), "white")
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    if not Path(font_path).is_file():
        pytest.skip("Test font not installed")
    ImageDraw.Draw(image).text(
        (30, 40), "TEST VEHICLE 1402", fill="black", font=ImageFont.truetype(font_path, 48)
    )
    adapter = TesseractAdapter(tmp_path, "eng")
    regions = adapter.recognize(np.array(image))
    assert "1402" in " ".join(r.text for r in regions)
    assert all(r.box.width > 0 for r in regions)
