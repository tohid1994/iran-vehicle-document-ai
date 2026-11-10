import time

from .core import DocumentError, Settings
from .extraction import extract_fields
from .layout import LayoutTemplate, union
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
        # Conservative document recognition requires multiple distinct vehicle labels.
        found = [key for key, value in fields.items() if value.rawValue]
        recognized = len([k for k in found if k.startswith("vehicle.")]) >= 3
        warnings = [*quality.warnings, "confidence_not_calibrated", "manual_review_required"]
        if not recognized:
            warnings.append("document_type_unverified")
        if not regions:
            warnings.append("no_text_detected")
        return Extraction(
            success=recognized and bool(found),
            documentType="IRAN_VEHICLE_REGISTRATION" if recognized else None,
            vehicle=vehicle,
            owner=owner,
            fields=fields,
            reviewFields=list(fields),
            warnings=warnings,
            quality=quality,
            processingTimeMs=int((time.monotonic() - start) * 1000),
        )
