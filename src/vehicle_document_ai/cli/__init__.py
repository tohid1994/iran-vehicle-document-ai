import argparse
import sys
from pathlib import Path

from ..core import DocumentError, Settings
from ..layout import LayoutTemplate
from ..reader import VehicleDocumentReader


def main():
    parser = argparse.ArgumentParser(prog="vehicle-document-ai")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("extract", "analyze"):
        command = sub.add_parser(name)
        command.add_argument("image", type=Path)
        command.add_argument("--output", "-o", type=Path)
        command.add_argument("--models", type=Path, default=Path("models"))
        command.add_argument("--template", type=Path)
        command.add_argument("--rectify", action="store_true")
        command.add_argument("--deskew", action="store_true")
        command.add_argument("--enhance", action="store_true")
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn

        uvicorn.run("vehicle_document_ai.api:app", host=args.host, port=args.port, access_log=False)
        return
    try:
        template = (
            LayoutTemplate.model_validate_json(args.template.read_text()) if args.template else None
        )
        reader = VehicleDocumentReader(
            template=template,
            settings=Settings(
                model_dir=args.models,
                rectify=args.rectify,
                deskew=args.deskew,
                enhance=args.enhance,
            ),
        )
        result = getattr(reader, args.command)(args.image)
        text = result.model_dump_json(indent=2)
        if args.output:
            # Explicit user-requested output is sensitive; restrict newly created files.
            import os

            fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(text + "\n")
        else:
            print(text)
    except (DocumentError, OSError, ValueError) as exc:
        print(
            str(exc) if isinstance(exc, DocumentError) else "file_operation_failed", file=sys.stderr
        )
        raise SystemExit(2) from None
