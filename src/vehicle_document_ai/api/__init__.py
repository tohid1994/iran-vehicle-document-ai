"""Run via vehicle-document-ai serve. Never log OCR results or request bodies."""

import asyncio
import hmac
import json
import os
import signal
import sys
import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..layout import LayoutTemplate
from ..ocr.tesseract import TesseractAdapter
from ..schemas import Analysis, Extraction

MAX_BODY = 10 * 1024 * 1024 + 64 * 1024


class BodyLimit:
    """Bound raw request bytes before Starlette's multipart parser can spool to disk."""

    def __init__(self, app):
        self.app = app
        self.slots = asyncio.Semaphore(4)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if self.slots.locked():
            return await JSONResponse({"detail": "request_capacity_reached"}, 429)(
                scope, receive, send
            )
        async with self.slots:
            chunks, total = [], 0
            deadline = asyncio.get_running_loop().time() + 15
            while True:
                try:
                    remaining = max(0.001, deadline - asyncio.get_running_loop().time())
                    message = await asyncio.wait_for(receive(), timeout=remaining)
                except TimeoutError:
                    return await JSONResponse({"detail": "upload_timeout"}, 408)(
                        scope, receive, send
                    )
                if message["type"] == "http.disconnect":
                    return
                total += len(message.get("body", b""))
                if total > MAX_BODY:
                    return await JSONResponse({"detail": "request_size_limit"}, 413)(
                        scope, receive, send
                    )
                chunks.append(message)
                if not message.get("more_body", False):
                    break
            iterator = iter(chunks)

            async def replay():
                return next(iterator, {"type": "http.request", "body": b"", "more_body": False})

            await self.app(scope, replay, send)


def create_app() -> FastAPI:
    app = FastAPI(title="Iran Vehicle Document AI", version="0.1.0")
    app.add_middleware(BodyLimit)
    gate = asyncio.Semaphore(int(os.environ.get("IVDAI_CONCURRENCY", "1")))
    api_key = os.environ.get("IVDAI_API_KEY")
    timeout = float(os.environ.get("IVDAI_TIMEOUT", "30"))
    adapter = TesseractAdapter(Path(os.environ.get("IVDAI_MODEL_DIR", "models")))

    async def authorize(request: Request):
        supplied = request.headers.get("x-api-key", "")
        if api_key and not hmac.compare_digest(supplied.encode(), api_key.encode()):
            raise HTTPException(401, "unauthorized")

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse({"detail": "invalid_request"}, 422)

    async def execute(
        file: UploadFile,
        mode: str,
        rectify: bool,
        deskew: bool,
        enhance: bool,
        layout_template: str | None,
    ):
        if layout_template:
            try:
                if len(layout_template) > 16384:
                    raise ValueError()
                layout_template = LayoutTemplate.model_validate_json(
                    layout_template
                ).model_dump_json()
            except ValueError:
                await file.close()
                raise HTTPException(422, "invalid_layout_template") from None
        if gate.locked():
            await file.close()
            raise HTTPException(429, "processing_capacity_reached")
        async with gate:
            try:
                data = await file.read(10 * 1024 * 1024 + 1)
            finally:
                await file.close()
            if len(data) > 10 * 1024 * 1024:
                raise HTTPException(413, "image_size_limit")
            with tempfile.TemporaryDirectory(prefix="ivdai-request-") as tempdir:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "vehicle_document_ai.core.worker",
                    mode,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    start_new_session=(os.name == "posix"),
                    env={
                        **os.environ,
                        "OPENBLAS_NUM_THREADS": "1",
                        "OMP_THREAD_LIMIT": "1",
                        "TMPDIR": tempdir,
                        "IVDAI_RECTIFY": str(int(rectify)),
                        "IVDAI_DESKEW": str(int(deskew)),
                        "IVDAI_ENHANCE": str(int(enhance)),
                        "IVDAI_LAYOUT_TEMPLATE": layout_template or "",
                    },
                )
                try:
                    stdout, _ = await asyncio.wait_for(proc.communicate(data), timeout=timeout)
                except (TimeoutError, asyncio.CancelledError) as exc:
                    if proc.returncode is None:
                        if os.name == "posix":
                            os.killpg(proc.pid, signal.SIGKILL)
                        else:
                            proc.kill()
                        await proc.wait()
                    if isinstance(exc, asyncio.CancelledError):
                        raise
                    raise HTTPException(504, "processing_timeout") from None
            try:
                result = json.loads(stdout)
            except ValueError:
                raise HTTPException(503, "processing_failed") from None
            if proc.returncode:
                code = result.get("error", "processing_failed")
                status = (
                    503
                    if code
                    in {"ocr_models_unavailable_or_unverified", "ocr_failed", "processing_failed"}
                    else 422
                )
                raise HTTPException(status, code)
            return result

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok", "ocrReady": adapter.inventory()["ready"]}

    @app.get("/api/v1/models", dependencies=[Depends(authorize)])
    async def models():
        return adapter.inventory()

    @app.post(
        "/api/v1/documents/extract", response_model=Extraction, dependencies=[Depends(authorize)]
    )
    async def extract(
        file: UploadFile,
        rectify: bool = False,
        deskew: bool = False,
        enhance: bool = False,
        layout_template: str | None = Form(None),
    ):
        return await execute(file, "extract", rectify, deskew, enhance, layout_template)

    @app.post(
        "/api/v1/documents/analyze", response_model=Analysis, dependencies=[Depends(authorize)]
    )
    async def analyze(
        file: UploadFile, rectify: bool = False, deskew: bool = False, enhance: bool = False
    ):
        return await execute(file, "analyze", rectify, deskew, enhance, None)

    return app


app = create_app()
