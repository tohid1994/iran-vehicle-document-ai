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
        raw, box, score, method = values[0]
        group, field = key.split(".")
        value, status = validate(field, raw)
        evidence[key] = FieldEvidence(
            rawValue=raw,
            normalizedValue=value,
            engineScore=score,
            boundingBox=box,
            extractionMethod=method,
            validationStatus=status,
        )
        setattr(vehicle if group == "vehicle" else owner, field, value)
    return vehicle, owner, evidence
