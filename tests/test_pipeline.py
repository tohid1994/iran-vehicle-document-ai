import io

import numpy as np
import pytest
from PIL import Image

from vehicle_document_ai import VehicleDocumentReader
from vehicle_document_ai.core import DocumentError, Settings
from vehicle_document_ai.extraction import extract_fields
from vehicle_document_ai.layout import LayoutTemplate
from vehicle_document_ai.preprocessing import decode, preprocess
from vehicle_document_ai.schemas import Box, TextRegion


def raster(fmt="PNG", size=(500, 500)):
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format=fmt)
    return buffer.getvalue()


def region(text, x=10, y=10, width=200):
    return TextRegion(text=text, box=Box(x=x, y=y, width=width, height=25), engineScore=98)


class SyntheticAdapter:
    name = "synthetic-test-adapter"

    def recognize(self, image, timeout):
        return [
            region("سیستم: برند ساختگی", y=10),
            region("تیپ: تیپ آزمایشی", y=60),
            region("مدل: ۱۴۰۲", y=110),
            region("نام و نام خانوادگی: مالک ساختگی", y=160),
            region("VIN: 1HGCM82633I004352", y=210),
        ]


def test_extraction_contract_and_no_guesses():
    result = VehicleDocumentReader(adapter=SyntheticAdapter()).extract(raster())
    assert not result.success
    assert "incomplete_required_fields" in result.warnings
    assert result.vehicle.brand == "برند ساختگی"
    assert result.vehicle.model == "تیپ آزمایشی"
    assert result.vehicle.year == "1402"
    assert result.vehicle.vin is None
    assert result.owner.fullName == "مالک ساختگی"
    assert result.owner.firstName is None and result.owner.lastName is None
    assert result.vehicle.origin is None
    assert result.confidence is None and result.requiresReview
    assert result.fields["vehicle.brand"].confidence is None
    assert result.fields["vehicle.brand"].engineScore == 98
    assert result.fields["vehicle.vin"].validationStatus == "invalid"


def test_conflicting_values_abstain():
    vehicle, _, fields = extract_fields([region("سیستم: الف"), region("سیستم: ب", y=80)])
    assert vehicle.brand is None
    assert fields["vehicle.brand"].validationStatus == "ambiguous"


def test_rtl_multiword_label_with_geometry():
    _, owner, _ = extract_fields(
        [
            region("شماره", x=400, width=55),
            region("ملی", x=340, width=50),
            region("1234567891", x=190, width=140),
        ]
    )
    assert owner.nationalId == "1234567891"


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_supported_rasters(fmt):
    assert decode(raster(fmt), Settings()).shape == (500, 500, 3)


def test_reject_disguised_and_oversized():
    with pytest.raises(DocumentError, match="invalid_image"):
        decode(b"<html>not a raster</html>", Settings())
    with pytest.raises(DocumentError, match="image_size_limit"):
        decode(raster(), Settings(max_bytes=100))
    with pytest.raises(DocumentError, match="image_pixel_limit"):
        decode(raster(), Settings(max_pixels=1000))
    with pytest.raises(DocumentError, match="unsupported_image"):
        decode(raster("GIF"), Settings())


def test_no_unconditional_enhancement():
    image = np.full((80, 100, 3), 240, dtype=np.uint8)
    processed, quality = preprocess(image, Settings())
    assert np.array_equal(image, processed)
    assert quality.operations == []
    assert quality.originalToProcessed == np.eye(3).tolist()


def test_template_explicit_and_bounded():
    with pytest.raises(ValueError):
        LayoutTemplate.model_validate(
            {
                "name": "bad",
                "version": "1",
                "regions": [
                    {"field": "vehicle.brand", "x": 0.9, "y": 0, "width": 0.3, "height": 0.1}
                ],
            }
        )


def test_blank_does_not_claim_success():
    class Empty:
        name = "empty"

        def recognize(self, image, timeout):
            return []

    result = VehicleDocumentReader(adapter=Empty()).extract(raster())
    assert not result.success and result.documentType is None


def test_perspective_and_conditional_enhancement():
    import cv2

    image = np.zeros((600, 800, 3), dtype=np.uint8)
    cv2.fillConvexPoly(
        image, np.array([[100, 80], [700, 120], [650, 520], [120, 500]]), (240, 240, 240)
    )
    _, quality = preprocess(image, Settings(rectify=True))
    assert "perspective_rectification" in quality.operations
    assert quality.originalToProcessed != np.eye(3).tolist()
    _, quality = preprocess(np.full((100, 100, 3), 100, dtype=np.uint8), Settings(enhance=True))
    assert "conditional_clahe" in quality.operations
