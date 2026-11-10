"""Disposable worker for API hard timeout and process memory isolation (Linux)."""

import json
import os
import sys
from pathlib import Path

from . import DocumentError, Settings


def main():
    # Optional POSIX address-space limit. Container memory limit remains recommended.
    if os.name == "posix":
        import resource

        limit = int(os.environ.get("IVDAI_WORKER_MEMORY_MB", "2048")) * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    settings = Settings(
        model_dir=Path(os.environ.get("IVDAI_MODEL_DIR", "models")),
        timeout=float(os.environ.get("IVDAI_TIMEOUT", "30")),
        rectify=os.environ.get("IVDAI_RECTIFY") == "1",
        deskew=os.environ.get("IVDAI_DESKEW") == "1",
        enhance=os.environ.get("IVDAI_ENHANCE") == "1",
    )
    try:
        from ..layout import LayoutTemplate
        from ..reader import VehicleDocumentReader

        template_json = os.environ.get("IVDAI_LAYOUT_TEMPLATE")
        template = LayoutTemplate.model_validate_json(template_json) if template_json else None
        reader = VehicleDocumentReader(settings=settings, template=template)
        source = sys.stdin.buffer.read(settings.max_bytes + 1)
        result = getattr(reader, sys.argv[1])(source)
        print(result.model_dump_json())
    except DocumentError as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
    except Exception:
        print(json.dumps({"error": "processing_failed"}))
        sys.exit(3)


if __name__ == "__main__":
    main()
