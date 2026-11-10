from ..layout import LABELS, candidates
from ..schemas import FieldEvidence, Owner, TextRegion, Vehicle
from ..validation import normalize, validate


def extract_fields(regions: list[TextRegion], template_candidates: dict | None = None):
    matches = candidates(regions)
    # Caller must explicitly select a template; no unverified built-in coordinates.
    for key, values in (template_candidates or {}).items():
        matches.setdefault(key, []).extend(values)
    evidence = {}
    vehicle, owner = Vehicle(), Owner()
    for key in [*LABELS, "vehicle.origin"]:
        values = matches.get(key, [])
        distinct = {normalize(v[0]) for v in values}
        if len(distinct) > 1:
            evidence[key] = FieldEvidence(
                validationStatus="ambiguous", extractionMethod="conflicting_candidates"
            )
            continue
        if not values:
            evidence[key] = FieldEvidence()
            continue
        raw, box, score, method, *details = values[0]
        group, field = key.split(".")
        value, status = validate(field, raw)
        # This is a conservative engine-quality rejection, NOT a calibrated probability.
        # Keep the actual read text as evidence, but do not populate obvious low-score OCR.
        minimum_score = 20 if field == "year" and status == "valid" else 40
        if (
            method in {"legacy_grid_regional_ocr", "model_word_reread"}
            and score is not None
            and score < minimum_score
        ):
            value = None
            if status != "invalid":
                status = "unverified"
            method += ":low_engine_score"
        evidence[key] = FieldEvidence(
            rawValue=raw,
            sourceReadings=details[0].get("sourceReadings", []) if details else [],
            normalizedValue=value,
            engineScore=score,
            boundingBox=box,
            extractionMethod=method,
            validationStatus=status,
        )
        setattr(vehicle if group == "vehicle" else owner, field, value)
    return vehicle, owner, evidence
