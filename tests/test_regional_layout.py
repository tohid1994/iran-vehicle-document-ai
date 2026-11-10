"""Synthetic geometry only: never embed the supplied registration or its values."""

import csv
import io
from types import SimpleNamespace

import cv2
import numpy as np

from vehicle_document_ai.extraction import extract_fields
from vehicle_document_ai.layout.legacy import detect_grid, value_boxes
from vehicle_document_ai.ocr.tesseract import TesseractAdapter
from vehicle_document_ai.schemas import Box, TextRegion
from vehicle_document_ai.validation import validate


def fake_grid(scale=1):
    image = np.full((1100 * scale, 1800 * scale, 3), 240, np.uint8)
    for i in range(17):
        x = (500 + i * 50) * scale
        cv2.line(image, (x, 400 * scale), (x, 450 * scale), (165, 100, 65), 2 * scale)
    for y in (400, 450):
        cv2.line(
            image, (500 * scale, y * scale), (1300 * scale, y * scale), (165, 100, 65), 2 * scale
        )
    return image


def test_grid_is_detected_and_scales_without_sample_pixels():
    small, large = fake_grid(), fake_grid(2)
    a, b = detect_grid(small), detect_grid(large)
    assert a and b
    assert abs(b.x - 2 * a.x) <= 2 and abs(b.width - 2 * a.width) <= 3
    assert set(value_boxes(a, small)) == set(value_boxes(b, large))
    assert "owner.fullName" in value_boxes(a, small)


def test_no_profile_from_a_rule_or_blank_image():
    image = np.full((1100, 1800, 3), 240, np.uint8)
    assert detect_grid(image) is None
    cv2.rectangle(image, (500, 400), (1300, 450), (165, 100, 65), 2)
    assert detect_grid(image) is None


def test_profile_does_not_apply_to_truncated_photo():
    assert (
        value_boxes(Box(x=10, y=10, width=500, height=30), np.zeros((200, 800, 3), np.uint8)) == {}
    )


def test_garbled_fuel_and_plate_are_not_returned_as_values():
    assert validate("fuelType", "متن تعداد چرخ") == (None, "invalid")
    assert validate("plate", "۱۲ م [۳۴۵ نامفهوم") == (None, "invalid")
    assert validate("fuelType", "بنزین") == ("بنزین", "valid")
    assert validate("plate", "۱۲ م ۳۴۵ ۶۷") == ("12 م 345 67", "valid")


def test_low_engine_score_retains_raw_without_populating_field():
    box = Box(x=1, y=1, width=80, height=30)
    vehicle, _, fields = extract_fields(
        [], {"vehicle.color": [("متن ساختگی", box, 0.0, "legacy_grid_regional_ocr")]}
    )
    assert vehicle.color is None
    assert fields["vehicle.color"].rawValue == "متن ساختگی"
    assert fields["vehicle.color"].confidence is None


def test_administrative_plate_alias_is_recognized():
    box = Box(x=1, y=1, width=200, height=30)
    vehicle, _, _ = extract_fields([TextRegion(text="شماره انتظامی: ۱۲ م ۳۴۵ ۶۷", box=box)])
    assert vehicle.plate == "12 م 345 67"


def test_tsv_quotes_cannot_swallow_following_rows(monkeypatch, tmp_path):
    text = (
        "level\tleft\ttop\twidth\theight\tconf\ttext\n"
        '5\t1\t1\t20\t20\t90\t"\n'
        "5\t30\t1\t20\t20\t95\tTEST\n"
    )
    monkeypatch.setattr(TesseractAdapter, "inventory", lambda self: {"ready": True})
    monkeypatch.setattr(
        "subprocess.run", lambda *a, **k: SimpleNamespace(stdout=text.encode(), returncode=0)
    )
    result = TesseractAdapter(tmp_path, "eng").recognize(np.zeros((50, 100, 3), np.uint8))
    assert [r.text for r in result] == ['"', "TEST"]
    assert len(list(csv.DictReader(io.StringIO(text), delimiter="\t", quoting=csv.QUOTE_NONE))) == 2


def test_success_requires_complete_core_fields_not_three_labels():
    from test_pipeline import raster, region

    from vehicle_document_ai import VehicleDocumentReader

    class CompleteSynthetic:
        name = "synthetic"

        def recognize(self, image, timeout):
            values = [
                "سیستم: برند ساختگی",
                "تیپ: تیپ آزمایشی",
                "مدل: ۱۴۰۲",
                "رنگ: سفید",
                "نوع سوخت: بنزین",
                "شماره شاسی: TEST123456",
                "شماره موتور: TEST987654",
                "VIN: 1HGCM82633A004352",
                "شماره انتظامی: ۱۲ م ۳۴۵ ۶۷",
                "نام و نام خانوادگی: مالک ساختگی",
                "شماره ملی: 1234567891",
            ]
            return [region(value, y=10 + i * 40) for i, value in enumerate(values)]

    result = VehicleDocumentReader(adapter=CompleteSynthetic()).extract(raster())
    assert result.success
    assert result.requiresReview and result.confidence is None
