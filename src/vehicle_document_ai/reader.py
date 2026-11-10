import time

from .core import DocumentError, Settings
from .extraction import extract_fields
from .layout import LayoutTemplate, union
from .layout.legacy import detect_grid, value_boxes
from .ocr import OCRAdapter
from .ocr.tesseract import TesseractAdapter
from .preprocessing import decode, preprocess
from .schemas import Analysis, Extraction


class VehicleDocumentReader:
    def __init__(
        self,
        adapter: OCRAdapter | None = None,
        settings: Settings | None = None,
        template: LayoutTemplate | None = None,
    ):
        self.settings = settings or Settings()
        self.adapter = adapter or TesseractAdapter(self.settings.model_dir)
        self.template = template

    def _run(self, source):
        start = time.monotonic()
        image, quality = preprocess(decode(source, self.settings), self.settings)
        remaining = self.settings.timeout - (time.monotonic() - start)
        if remaining <= 0:
            raise DocumentError("processing_timeout")
        regions = self.adapter.recognize(image, timeout=remaining)
        return start, image, quality, regions

    def analyze(self, source) -> Analysis:
        start, _, quality, regions = self._run(source)
        return Analysis(
            quality=quality,
            regions=regions,
            engine=self.adapter.name,
            processingTimeMs=int((time.monotonic() - start) * 1000),
        )

    def extract(self, source) -> Extraction:
        start, image, quality, regions = self._run(source)
        template_values = {}
        if self.template:
            # Region OCR is optional in the protocol; selecting words inside the ROI works
            # for any adapter, with a region re-read when supported.
            for field, box in self.template.boxes(quality.width, quality.height):
                remaining = self.settings.timeout - (time.monotonic() - start)
                if remaining <= 0:
                    raise DocumentError("processing_timeout")
                if hasattr(self.adapter, "recognize_region"):
                    selected = self.adapter.recognize_region(image, box, remaining)
                else:
                    selected = [
                        r
                        for r in regions
                        if box.x <= r.box.x
                        and box.y <= r.box.y
                        and r.box.x + r.box.width <= box.x + box.width
                        and r.box.y + r.box.height <= box.y + box.height
                    ]
                if selected:
                    text = " ".join(
                        r.text for r in sorted(selected, key=lambda r: r.box.x, reverse=True)
                    )
                    template_values.setdefault(field, []).append(
                        (text, union(selected), None, f"template:{self.template.name}")
                    )
        vehicle, owner, fields = extract_fields(regions, template_values)
        profile_used = False
        grid = detect_grid(image) if not self.template else None
        # Require both the repeating visual grid AND independent nearby label evidence.
        if (
            grid
            and hasattr(self.adapter, "recognize_value")
            and hasattr(self.adapter, "confirm_legacy_layout")
            and self.adapter.confirm_legacy_layout(
                image, grid, self.settings.timeout - (time.monotonic() - start)
            )
        ):
            boxes = value_boxes(grid, image)
            if boxes:
                regional = {}
                for key, box in boxes.items():
                    remaining = self.settings.timeout - (time.monotonic() - start)
                    if remaining <= 0:
                        raise DocumentError("processing_timeout")
                    candidate = self.adapter.recognize_value(image, box, key, remaining)
                    if candidate[0].strip():
                        regional[key] = [candidate]
                pv, po, pf = extract_fields([], regional)
                for key in boxes:
                    fields[key] = pf[key]
                    group, name = key.split(".")
                    setattr(
                        vehicle if group == "vehicle" else owner,
                        name,
                        getattr(pv if group == "vehicle" else po, name),
                    )
                # This printed layout has one combined owner-name field. Global OCR
                # elsewhere on the page cannot establish separate given/family names.
                owner.firstName = owner.lastName = None
                from .schemas import FieldEvidence

                fields["owner.firstName"] = FieldEvidence()
                fields["owner.lastName"] = FieldEvidence()
                profile_used = True
        found = [key for key, value in fields.items() if value.rawValue]
        recognized = len([k for k in found if k.startswith("vehicle.")]) >= 3
        warnings = [*quality.warnings, "confidence_not_calibrated", "manual_review_required"]
        required = (
            "vehicle.brand",
            "vehicle.model",
            "vehicle.year",
            "vehicle.color",
            "vehicle.fuelType",
            "vehicle.chassisNumber",
            "vehicle.engineNumber",
            "vehicle.plate",
            "vehicle.vin",
            "owner.fullName",
            "owner.nationalId",
        )
        complete = all(fields[key].normalizedValue is not None for key in required)
        # A complete transcription can still contain an invalid printed identifier.
        # Keep strict normalized VIN null; never rewrite I/O/Q into plausible digits.
        vin_evidence = fields["vehicle.vin"]
        vin_read = (
            vin_evidence.extractionMethod == "vin_grid_cells"
            and vin_evidence.rawValue is not None
            and len(vin_evidence.rawValue) == 17
        )
        transcribed = all(
            fields[key].normalizedValue is not None for key in required if key != "vehicle.vin"
        ) and (vin_read or vehicle.vin is not None)
        if vin_read and vin_evidence.validationStatus == "invalid":
            warnings.append("printed_vin_fails_standard_validation")
        if not complete:
            warnings.append("incomplete_required_fields")
        if profile_used:
            warnings.append("legacy_layout_profile_single_sample_evaluation")
        if not recognized:
            warnings.append("document_type_unverified")
        if not regions:
            warnings.append("no_text_detected")
        return Extraction(
            success=recognized and complete,
            transcriptionComplete=recognized and transcribed,
            documentType="IRAN_VEHICLE_REGISTRATION" if recognized else None,
            vehicle=vehicle,
            owner=owner,
            fields=fields,
            reviewFields=list(fields),
            warnings=warnings,
            quality=quality,
            processingTimeMs=int((time.monotonic() - start) * 1000),
        )
