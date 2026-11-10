import hashlib
import json

import cv2
import numpy as np
import pytest

from vehicle_document_ai.core import DocumentError
from vehicle_document_ai.ocr.digits import DigitTemplates, normalize_glyph, segment_digits


def test_checksum_never_selects_or_generates_a_digit():
    model = object.__new__(DigitTemplates)
    model.classify = lambda glyph: None
    # Synthetic invalid identifier stays invalid: there is no checksum repair search.
    observed = "1234567890"
    assert model.fuse(observed, [np.ones((10, 10))] * 10) == observed
    assert model.fuse(observed, [np.ones((10, 10))] * 9) is None


def test_visual_evidence_is_used_without_an_expected_identifier():
    model = object.__new__(DigitTemplates)
    model.classify = lambda glyph: "2" if glyph[0, 0] == 1 else None
    glyphs = [np.zeros((4, 4)) for _ in range(10)]
    glyphs[3][0, 0] = 1
    assert model.fuse("0000000000", glyphs) == "0002000000"


def test_blank_and_ambiguous_segmentation_abstains():
    assert normalize_glyph(np.zeros((30, 30))) is None
    assert segment_digits(np.full((60, 300), 255, np.uint8)) == []
    image = np.full((60, 300), 255, np.uint8)
    cv2.rectangle(image, (20, 10), (40, 45), 0, -1)
    assert segment_digits(image) == []


def test_synthetic_ten_separate_glyphs_have_ten_segments():
    image = np.full((60, 320), 255, np.uint8)
    for i in range(10):
        cv2.rectangle(image, (10 + 30 * i, 10), (25 + 30 * i, 45), 0, -1)
    assert len(segment_digits(image)) == 10


def test_template_tampering_fails_closed(tmp_path):
    target = tmp_path / "persian_digit_templates.npz"
    target.write_bytes(b"not a trusted model")
    (tmp_path / "manifest.json").write_text(json.dumps({"files": {target.name: "0" * 64}}))
    with pytest.raises(DocumentError, match="digit_templates_unavailable"):
        DigitTemplates(tmp_path)


def test_distant_visual_classes_do_not_invent_a_digit(tmp_path):
    target = tmp_path / "persian_digit_templates.npz"
    glyphs = np.zeros((10, 32, 24), dtype=np.uint8)
    np.savez_compressed(target, glyphs=glyphs, labels=np.arange(10), ratios=np.ones(10))
    (tmp_path / "manifest.json").write_text(
        json.dumps({"files": {target.name: hashlib.sha256(target.read_bytes()).hexdigest()}})
    )
    model = DigitTemplates(tmp_path)
    assert model.classify(np.ones((20, 20), np.uint8)) is None
