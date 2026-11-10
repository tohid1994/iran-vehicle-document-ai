import pytest

from vehicle_document_ai.validation import national_id_valid, normalize, validate


def test_digits_and_persian_letters():
    assert normalize("  مدل: ۱۴۰۲ يك ") == "مدل: 1402 یک"


def test_synthetic_national_id_checksum():
    # Generated test sequence, not an asserted real person's identity.
    base = "123456789"
    remainder = sum(int(base[i]) * (10 - i) for i in range(9)) % 11
    check = remainder if remainder < 2 else 11 - remainder
    value = base + str(check)
    assert national_id_valid(value)
    assert not national_id_valid(base + str((check + 1) % 10))


@pytest.mark.parametrize("value", ["0000000000", "1111111111", "123", "abcdefghij"])
def test_reject_invalid_ids(value):
    assert validate("nationalId", value) == (None, "invalid")


def test_vin_structure_no_autocorrection():
    assert validate("vin", "1HGCM82633A004352") == ("1HGCM82633A004352", "valid")
    assert validate("vin", "1HGCM82633I004352") == (None, "invalid")
