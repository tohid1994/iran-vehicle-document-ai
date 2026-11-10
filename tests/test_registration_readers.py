import numpy as np
from test_regional_layout import fake_grid

from vehicle_document_ai.extraction import extract_fields
from vehicle_document_ai.layout.legacy import detect_grid, value_boxes
from vehicle_document_ai.ocr.registration import RegionalReader
from vehicle_document_ai.schemas import Box, TextRegion
from vehicle_document_ai.validation import validate


def word(text, x=0, score=90):
    return TextRegion(text=text, box=Box(x=x, y=20, width=20, height=20), engineScore=score)


def test_vin_cell_reader_abstains_instead_of_inventing_missing_character():
    image = fake_grid()
    box = value_boxes(detect_grid(image), image)["vehicle.vin"]
    reader = RegionalReader(None, 10)
    reader.read = lambda *a, **k: ([], np.zeros((60, 100), np.uint8))
    assert reader.vin(image, box)[0] == ""


def test_vin_cell_reader_preserves_observed_forbidden_letter():
    image = fake_grid()
    box = value_boxes(detect_grid(image), image)["vehicle.vin"]
    reader = RegionalReader(None, 10)
    characters = iter("IABCDEFGHJKLMNPRS")
    reader.read = lambda *a, **k: ([word(next(characters))], np.zeros((60, 100), np.uint8))
    result = reader.vin(image, box)
    assert result[0] == "IABCDEFGHJKLMNPRS"
    assert validate("vin", result[0]) == (None, "invalid")
    vehicle, _, fields = extract_fields([], {"vehicle.vin": [result]})
    assert vehicle.vin is None
    assert fields["vehicle.vin"].rawValue == result[0]
    assert fields["vehicle.vin"].sourceReadings[0] == "I"


def test_word_reader_uses_actual_reread_and_not_dictionary_completion():
    reader = RegionalReader(None, 10)
    calls = iter(
        [
            ([word("جی", 100), word("نامفهوم", 50, 0)], np.zeros((80, 180), np.uint8)),
            ([word("ایکس", 70), word("آی", 20)], np.zeros((60, 100), np.uint8)),
        ]
    )
    reader.read = lambda *a, **k: next(calls)
    result = reader.model(np.zeros((100, 200, 3), np.uint8), Box(x=0, y=0, width=180, height=80))
    assert result[0] == "جی ایکس آی"
    assert "نامفهوم" in result[4]["sourceReadings"]


def test_unknown_model_is_not_replaced_with_a_known_trim():
    reader = RegionalReader(None, 10)
    reader.read = lambda *a, **k: ([word("مدل ساختگی", 50, 0)], np.zeros((80, 180), np.uint8))
    result = reader.model(np.zeros((100, 200, 3), np.uint8), Box(x=0, y=0, width=180, height=80))
    vehicle, _, fields = extract_fields([], {"vehicle.model": [result]})
    assert vehicle.model is None and fields["vehicle.model"].rawValue == "مدل ساختگی"


def test_empty_plate_cannot_produce_fabricated_components():
    reader = RegionalReader(None, 10)
    box = Box(x=0, y=0, width=300, height=70)
    assert reader.plate(np.full((70, 300, 3), 255, np.uint8), box)[0] == ""
