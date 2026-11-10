# Iran Vehicle Document AI

An independent Python package, CLI and REST service for **offline** extraction of
Iranian vehicle registration documents (برگ سبز). MIT-licensed application code.

**Version 0.1.0 is an initial, review-first implementation, not a production accuracy
claim. No real-document dataset has been evaluated.** Never automatically approve
ownership, register a vehicle or transfer money based on its output.

[راهنمای فارسی](README.fa.md) · [Offline deployment](docs/offline.md) ·
[Contract and architecture](docs/architecture.md) · [Security](SECURITY.md)

## Implemented

- JPEG, PNG and WebP decoding with byte, pixel, dimension and animation limits.
- EXIF orientation, blur/exposure/contrast diagnostics, opt-in quadrilateral
  rectification, small-angle deskew and conditional CLAHE enhancement.
- Replaceable OCR protocol; local Tesseract Persian + English adapter, TSV word
  coordinates and regional OCR, with runtime timeouts and checksum verification.
- Exact label extraction and same-line RTL geometry; optional, explicitly selected
  versioned layout templates. No hardcoded assumptions about plate/barcode position.
- `سیستم → brand`, `تیپ → model`, `مدل → year`; vehicle and owner fields.
- Persian/Arabic digit and letter normalization; VIN syntax and Iranian national
  ID checksum validation. Invalid identifiers yield null, with raw evidence retained.
- Versioned Pydantic JSON, field evidence, explicit abstention and review flags.
- FastAPI/OpenAPI, CLI and Python interfaces, Docker recipe and CI workflow.

## Install (online preparation)

Use Python 3.11+ and a compatible Tesseract 5 native runtime. On Debian/Ubuntu:

```bash
sudo apt-get update
sudo apt-get install tesseract-ocr
python -m venv .venv
. .venv/bin/activate
pip install .
python scripts/prepare_models.py
```

The preparation script explicitly downloads `fas` and `eng` from an immutable
`tessdata_fast` revision, includes their Apache-2.0 license, and writes SHA-256
checksums. Runtime **never downloads**, falls back to system models, or contacts
an external API. Protect the model directory and manifest from untrusted writers;
checksums detect changes against that manifest, not an attacker replacing both.

Tesseract is selected because official Persian (`fas`) and English models can be
loaded locally and it supplies word geometry. It is a replaceable baseline;
PaddleOCR and learned layout recognition are not implemented. Upstream references:
[Tesseract models](https://tesseract-ocr.github.io/tessdoc/Data-Files),
[TSV output](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html).

## Python

```python
from vehicle_document_ai import VehicleDocumentReader
from vehicle_document_ai.core import Settings
from pathlib import Path

reader = VehicleDocumentReader(settings=Settings(model_dir=Path("models")))
result = reader.extract("vehicle.jpg")
private_data = result.model_dump()
```

`reader.analyze(...)` returns diagnostics and text boxes. Paths and in-memory
bytes are accepted. Package/CLI preprocessing options are explicit and default
off except EXIF orientation. A custom OCR adapter implements
`name` and `recognize(image: RGB ndarray, timeout: float) -> list[TextRegion]`.
It must obey the timeout and offline/no-retention policy.

## CLI

```bash
vehicle-document-ai extract vehicle.jpg --models models --output result.json
vehicle-document-ai analyze vehicle.jpg --models models --output analysis.json
vehicle-document-ai extract vehicle.jpg --rectify --deskew --enhance
vehicle-document-ai serve --host 127.0.0.1 --port 8000
```

JSON output contains personal data: keep it private. `--output` creates files
with owner-only permissions on POSIX; existing file permissions are preserved.

## REST API

Set `IVDAI_MODEL_DIR` to your models directory and optionally `IVDAI_API_KEY`.
Local development binds to loopback by default. API execution uses disposable
workers; default concurrency 1 and hard timeout 30 seconds. Raw upload limit is
10 MiB plus 64 KiB multipart overhead; image limit 10 MiB / 16 MP / 8000 pixels
per dimension. Four bounded HTTP requests and 15-second upload deadlines limit
buffering. Responses are private and should never be cached or logged.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/extract \
  -H "x-api-key: $IVDAI_API_KEY" -F 'file=@vehicle.jpg'
```

| Method | Endpoint | Result |
| --- | --- | --- |
| POST | `/api/v1/documents/extract` | Versioned extraction JSON |
| POST | `/api/v1/documents/analyze` | Quality, OCR text regions and engine |
| GET | `/api/v1/health` | Liveness plus OCR readiness flag |
| GET | `/api/v1/models` | Local model hashes and readiness |
| GET | `/docs` | Swagger UI (standard UI assets require internet) |
| GET | `/openapi.json` | API contract, usable completely offline |

`success` means at least three distinct vehicle labels produced candidates; it
is a processing heuristic, **not** proof that the image is a genuine registration
or that all required fields were read. HTTP 200 can contain `success: false`.
`health.status=ok` is liveness; check `ocrReady` before routing work. Expected
errors are sanitized: 401 auth, 413 byte limits, 422 invalid image/request,
429 capacity, 503 models/runtime failure, 504 overall timeout.

## JSON semantics

The response contains `schemaVersion: "1.0"`, `vehicle`, `owner`, `fields`,
`quality`, `warnings`, `reviewFields`, `requiresReview`, `processingTimeMs`.
A full synthetic response is generated in `examples/synthetic-result.json`.
`fields["vehicle.vin"]` illustrates the per-field contract:

```json
{
  "rawValue": "1HGCM82633A004352",
  "normalizedValue": "1HGCM82633A004352",
  "confidence": null,
  "engineScore": 92.4,
  "boundingBox": {"x": 10, "y": 20, "width": 300, "height": 35},
  "extractionMethod": "label_inline",
  "validationStatus": "valid",
  "requiresReview": true
}
```

This example's engine score is illustrative. Runtime only returns actual OCR
scores. **All calibrated confidence values remain null** until a separately
labeled evaluation supports calibration; all fields require review. OCR scores
are not probabilities. Missing/invalid/conflicting values remain null. `rawValue`
is sensitive and appears only in the response, never logs. Boxes use processed
image pixels; `quality.originalToProcessed` maps EXIF-oriented pixels to that
space. File-native coordinates before EXIF rotation are not represented.

## Docker / offline

Prepare models first, then build on a connected machine:

```bash
python scripts/prepare_models.py
docker build -t iran-vehicle-document-ai:0.1.0 .
docker save iran-vehicle-document-ai:0.1.0 -o vehicle-ai-image.tar
# Transfer to the offline server:
docker load -i vehicle-ai-image.tar
# Set your own IVDAI_API_KEY outside the source tree before using compose.
docker compose up
```

Compose applies non-root execution, loopback binding, read-only root filesystem,
tmpfs, PID/CPU/RAM limits and dropped capabilities. For a fully disconnected
smoke check, run the saved image with `--network none` and inspect local models
or use CLI; a network-disabled container cannot expose HTTP to a client.
The Docker build is preparation-time online; image execution is offline.
[Native offline install and CPU constraints](docs/offline.md).

## Node.js / NestJS

Run this as an independent local service and use standard HTTP multipart from
your backend. `node examples/extract.mjs /private/vehicle.jpg` demonstrates
Node 20+ `fetch`/`FormData`, auth and a client timeout. It does not couple to any
application, database, Nuxt frontend or NestJS module. Never expose an API key in
client-side code. Require explicit user review before saving extracted values.

## Known limitations

- No real-document accuracy assessment, calibration, benchmark or production certification.
- Label and geometry heuristics may miss layouts, merged OCR words, vertical/rotated
  documents, glare, holograms, complex tables and unlabeled plates beside barcodes.
- No trained document detector, learned layout engine, automatic template selection,
  arbitrary orientation detection, denoising or lighting-field correction.
- Full owner name is never split automatically. Other unmodeled owner details are
  visible only through `analyze` text regions, not assigned to guessed fields.
- Domestic/foreign origin stays null: no vetted origin catalog is bundled. Brand
  alone cannot prove where a specific vehicle was manufactured or assembled.
- VIN validation is syntax only (17 permitted characters), not a universal checksum,
  manufacturer lookup, registry check or authenticity verification. Year is four
  digits with no guessed calendar conversion. Plates remain unverified text.
- CPU-only supported in architecture; no guarantee for AVX2-less hardware until a
  compatible native Tesseract/OpenCV/NumPy build is exercised on that machine.
- Docker recipes are supplied; see `docs/verification.md` for what was actually run.

## Development and contribution

```bash
pip install '.[dev]'
ruff check .
ruff format --check .
pytest -q
python -m build
```

See [CONTRIBUTING.md](CONTRIBUTING.md). Tests use synthetic images and generated
identifiers; do not submit real registration documents, secrets or identities.
Code is MIT; redistributed OCR models retain their separate Apache-2.0 license.

Optional preprocessing is available via REST query flags, for example
`/api/v1/documents/extract?rectify=true&deskew=true&enhance=true`.
A vetted layout template can be supplied as the multipart text field
`layout_template` (JSON). In the CLI use `--template template.json`.
