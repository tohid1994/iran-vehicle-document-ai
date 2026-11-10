"""Conservative syntax checks; validity does not prove identity or ownership."""

import re
import unicodedata

DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩يك", "01234567890123456789یک")


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).translate(DIGITS)
    value = "".join(c for c in value if unicodedata.category(c) != "Cf")
    return " ".join(value.split()).strip(" :：؛")


def national_id_valid(value: str) -> bool:
    if not re.fullmatch(r"[0-9]{10}", value) or len(set(value)) == 1:
        return False
    remainder = sum(int(value[i]) * (10 - i) for i in range(9)) % 11
    return int(value[9]) == (remainder if remainder < 2 else 11 - remainder)


def validate(field: str, value: str) -> tuple[str | None, str]:
    value = normalize(value)
    if field in {"vin", "chassisNumber", "engineNumber"}:
        value = value.upper().replace(" ", "")
    if field == "nationalId":
        value = value.replace(" ", "")
        return (value, "valid") if national_id_valid(value) else (None, "invalid")
    if field == "vin":
        return (
            (value, "valid") if re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", value) else (None, "invalid")
        )
    if field == "year":
        return (value, "valid") if re.fullmatch(r"[0-9]{4}", value) else (None, "invalid")
    # Plate formats vary by vehicle category. Preserve read text without inventing components.
    return (value, "unverified") if value else (None, "missing")
