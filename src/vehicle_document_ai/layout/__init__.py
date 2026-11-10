"""Label/value matching with explicit, opt-in normalized layout templates."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..schemas import Box, TextRegion
from ..validation import normalize

LABELS = {
    "vehicle.brand": ("سیستم",),
    "vehicle.model": ("تیپ",),
    "vehicle.year": ("مدل",),
    "vehicle.color": ("رنگ",),
    "vehicle.fuelType": ("نوع سوخت",),
    "vehicle.vehicleType": ("نوع خودرو", "نوع وسیله نقلیه", "نوع"),
    "vehicle.vin": ("شناسه وسیله نقلیه", "VIN"),
    "vehicle.chassisNumber": ("شماره شاسی",),
    "vehicle.engineNumber": ("شماره موتور",),
    "vehicle.plate": ("شماره انتظامی", "شماره پلاک", "پلاک"),
    "owner.fullName": ("نام و نام خانوادگی", "نام و نام خانوادکی"),
    "owner.firstName": ("نام",),
    "owner.lastName": ("نام خانوادگی",),
    "owner.nationalId": ("شماره ملی", "کد ملی"),
}


class TemplateRegion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    x: float = Field(ge=0, lt=1)
    y: float = Field(ge=0, lt=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def bounds(self):
        if self.field not in LABELS or self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("invalid_template_region")
        return self


class LayoutTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    version: str
    regions: list[TemplateRegion] = Field(max_length=32)

    def boxes(self, width: int, height: int):
        return [
            (
                r.field,
                Box(
                    x=int(r.x * width),
                    y=int(r.y * height),
                    width=max(1, int(r.width * width)),
                    height=max(1, int(r.height * height)),
                ),
            )
            for r in self.regions
        ]


def union(regions: list[TextRegion]) -> Box:
    left = min(r.box.x for r in regions)
    top = min(r.box.y for r in regions)
    right = max(r.box.x + r.box.width for r in regions)
    bottom = max(r.box.y + r.box.height for r in regions)
    return Box(x=left, y=top, width=right - left, height=bottom - top)


def lines(regions: list[TextRegion]) -> list[list[TextRegion]]:
    groups: list[list[TextRegion]] = []
    for r in sorted(regions, key=lambda t: t.box.y + t.box.height / 2):
        cy = r.box.y + r.box.height / 2
        for group in groups:
            anchor = group[0].box
            if abs(cy - (anchor.y + anchor.height / 2)) < min(anchor.height, r.box.height) * 0.55:
                group.append(r)
                break
        else:
            groups.append([r])
    return groups


def candidates(regions: list[TextRegion]) -> dict[str, list[tuple[str, Box, float | None, str]]]:
    """Prefer exact colon labels. Otherwise match contiguous label words, then nearby RTL value.

    Conservative: only same-line relationships; never pick arbitrary text below a label.
    Multiple candidates remain ambiguous rather than taking the highest score.
    """
    result = {}
    labels = sorted(
        ((normalize(label), field) for field, aliases in LABELS.items() for label in aliases),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for line in lines(regions):
        # Useful for adapters that return a whole line, and explicit colon-delimited text.
        for r in line:
            text = normalize(r.text)
            for label, field in labels:
                if text.startswith(label + ":") or text.startswith(label + " :"):
                    value = text[len(label) :].lstrip(" :")
                    if value:
                        result.setdefault(field, []).append(
                            (value, r.box, r.engineScore, "label_inline")
                        )
                    break
        tokens = sorted(line, key=lambda r: r.box.x, reverse=True)
        consumed = set()
        matches = []
        for label, field in labels:
            for i in range(len(tokens)):
                if i in consumed:
                    continue
                for size in range(1, min(6, len(tokens) - i) + 1):
                    inds = set(range(i, i + size))
                    if consumed & inds:
                        continue
                    text = normalize(" ".join(t.text for t in tokens[i : i + size]))
                    if text == label:
                        matches.append((field, i, i + size))
                        consumed.update(inds)
                        break
        for field, _start, end in matches:
            value_tokens = []
            previous = tokens[end - 1].box
            for i in range(end, len(tokens)):
                if i in consumed:
                    break
                token = tokens[i]
                if previous.x - (token.box.x + token.box.width) > previous.height * 8:
                    break
                value_tokens.append(token)
                previous = token.box
            value_tokens = [r for r in value_tokens if normalize(r.text)]
            if value_tokens:
                value = " ".join(r.text for r in value_tokens).strip(" :")
                scores = [r.engineScore for r in value_tokens if r.engineScore is not None]
                result.setdefault(field, []).append(
                    (value, union(value_tokens), min(scores) if scores else None, "label_spatial")
                )
    return result
