# Architecture and contract

`preprocessing.decode → preprocess → OCRAdapter.recognize → layout.candidates →
extraction.extract_fields → validation.validate → schemas.Extraction`.

`reader` coordinates the package. The CLI calls it directly. The API uses an
isolated worker invoking the same reader. OCR uses only a bounded local raster
and local model directory. No inference client, cloud credential or remote OCR
provider is included. Each processing call has its own private temporary space.

The normalized value is copied into `vehicle`/`owner`. Evidence remains in
`fields` keyed by `vehicle.brand` etc. Evidence includes raw text, normalized text,
engine score, null calibrated confidence, box, extraction method, validation and
review state. `valid` means a syntax/checksum rule passed, not semantic certainty.
`unverified` means no semantic validator exists. Multiple distinct candidates are
`ambiguous` and abstain. Missing values are `missing`.

The stable v1 contract uses camelCase JSON property names. `schemaVersion` is
literal `1.0`. Breaking removals/type or semantics changes require a new version
and API namespace. A null value never means an empty string or an invented value.
`origin` is separate from `vehicleType` (category) to avoid conflating them.

## Layout extension

`LayoutTemplate` has `name`, `version`, and explicit normalized regions with
`field`, `x`, `y`, `width`, `height` (fractions 0..1). Bounds and known field names
are validated. Provide a template to `VehicleDocumentReader(template=...)` only
when a caller knows its layout and document alignment. No example template is
claimed to match a real document. Template regions are re-read with regional OCR
if supported; otherwise enclosed OCR words are selected. Conflicts with label
candidates abstain. Template selection is available in Python, CLI `--template template.json` and the
REST extract multipart field `layout_template` (JSON, at most 16 KiB / 32 regions).
REST query flags `rectify`, `deskew`, `enhance` expose optional preprocessing on
both document endpoints; they default to false. Templates must be explicitly
selected by a caller who has validated the layout.

More advanced adapters should return word/line boxes and actual engine scores.
Implement regional OCR optionally with `recognize_region`. Calibrated confidence
requires labeled real-world evaluation stratified by field and document layout;
never convert raw OCR scores into correctness probabilities by dividing by 100.
