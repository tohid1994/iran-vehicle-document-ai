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


## Guarded legacy form profile

A copper-colored, regularly spaced VIN grid is detected from the actual image.
A profile is used only when chassis and engine label candidates also exist above
that grid. Its value windows translate and scale with the detected grid. The
profile never stores vehicle/owner values and does not split full names.
This is a single-sample layout, not a learned universal detector. Text-only and
Latin/numeric regions use different OCR settings; raw-line segmentation avoids
Tesseract's observed empty single-line results on isolated Persian words.

When the profile is selected, its scoped ROI reads replace wide same-line
candidates for those fields, preventing text from a neighboring column being
used as a value. Low engine scores yield null normalized values, with raw evidence
retained and review required. Fuel values must match an explicit vocabulary after
punctuation cleanup; unparseable plates are null. Unknown plate categories need a
future parser. No dictionary edit-distance substitutions or ID digit repairs occur.

`success` requires every core field listed in reader.py's `required` tuple to
have a normalized value. Recognition of several labels alone is insufficient.
A `success` value never replaces the per-field manual-review policy.


VIN cell reads preserve I/O/Q literally. Validation may reject the printed string
while transcription is complete. Only a complete 17-character cell read enables
that distinction; an absent or undecodable cell is never supplied from a VIN rule.
Plate frame rectification and the detected internal separator determine numeric
group regions, and the letter must occur in actual OCR. The reader's success flag
requires valid normalized core values; transcriptionComplete permits a fully read
but invalid printed VIN, whose text remains in rawValue with validationStatus invalid.
