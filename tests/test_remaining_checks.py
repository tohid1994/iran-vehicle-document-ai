import asyncio
import io
import struct
import zlib

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from vehicle_document_ai.api import BodyLimit, create_app
from vehicle_document_ai.core import DocumentError, Settings
from vehicle_document_ai.extraction import extract_fields
from vehicle_document_ai.ocr.tesseract import TesseractAdapter
from vehicle_document_ai.preprocessing import decode
from vehicle_document_ai.schemas import Box
from vehicle_document_ai.validation import national_id_valid, validate


def test_valid_leading_zero_national_id_is_preserved():
    base = "001234567"
    remainder = sum(int(base[i]) * (10 - i) for i in range(9)) % 11
    value = base + str(remainder if remainder < 2 else 11 - remainder)
    assert national_id_valid(value)
    assert validate("nationalId", value) == (value, "valid")


@pytest.mark.parametrize(
    "field,value", [("engineNumber", "00012345"), ("chassisNumber", "000ABC123")]
)
def test_identifier_leading_zeroes_are_preserved(field, value):
    assert validate(field, value)[0] == value


def test_plate_digit_group_order_and_zeroes():
    assert validate("plate", "۰۱ ب ۰۰۲ ۰۳") == ("01 ب 002 03", "valid")


@pytest.mark.parametrize("letter", ["I", "O", "Q"])
def test_forbidden_vin_letters_are_never_repaired(letter):
    raw = letter + "1234567890123456"
    _, _, fields = extract_fields(
        [], {"vehicle.vin": [(raw, Box(x=1, y=1, width=300, height=30), None, "vin_grid_cells")]}
    )
    assert fields["vehicle.vin"].rawValue == raw
    assert fields["vehicle.vin"].normalizedValue is None


def test_exif_orientation_is_applied_before_ocr():
    image = Image.new("RGB", (80, 40), "white")
    image.paste((255, 0, 0), (0, 0, 30, 20))
    exif = Image.Exif()
    exif[274] = 6
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", exif=exif)
    decoded = decode(buffer.getvalue(), Settings())
    assert np.array_equal(decoded, np.rot90(np.array(image), 3))


def test_oversized_png_header_is_rejected_before_decode():
    stream = io.BytesIO()
    Image.new("RGB", (40, 40)).save(stream, format="PNG")
    data = bytearray(stream.getvalue())
    data[16:24] = struct.pack(">II", 50000, 50000)
    data[29:33] = struct.pack(">I", zlib.crc32(data[12:29]) & 0xFFFFFFFF)
    with pytest.raises(DocumentError):
        decode(bytes(data), Settings())


def test_health_reports_incomplete_model_installation(monkeypatch):
    monkeypatch.setattr(
        TesseractAdapter,
        "inventory",
        lambda self: {"ready": True, "regionalRefinementReady": False},
    )
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health")
        assert response.json()["ocrReady"] is False
        assert response.headers["cache-control"] == "no-store"


def test_request_slots_are_bounded_before_body_buffering():
    async def run():
        async def app(scope, receive, send):
            raise AssertionError("over-capacity request must not reach app")

        limiter = BodyLimit(app)
        for _ in range(4):
            await limiter.slots.acquire()
        messages = []

        async def receive():
            raise AssertionError("must not read a rejected upload")

        async def send(message):
            messages.append(message)

        await limiter({"type": "http"}, receive, send)
        assert messages[0]["status"] == 429

    asyncio.run(run())


def test_stalled_upload_times_out_without_processing(monkeypatch):
    async def run():
        async def app(scope, receive, send):
            raise AssertionError("must not process stalled upload")

        async def receive():
            return {"type": "http.request", "body": b""}

        messages = []

        async def send(message):
            messages.append(message)

        async def timeout(awaitable, **kwargs):
            awaitable.close()
            raise TimeoutError()

        monkeypatch.setattr(asyncio, "wait_for", timeout)
        await BodyLimit(app)({"type": "http"}, receive, send)
        assert messages[0]["status"] == 408

    asyncio.run(run())


def test_low_score_model_reread_is_not_accepted():
    vehicle, _, fields = extract_fields(
        [],
        {
            "vehicle.model": [
                ("تیپ ساختگی", Box(x=1, y=1, width=100, height=30), 0, "model_word_reread")
            ]
        },
    )
    assert vehicle.model is None and fields["vehicle.model"].rawValue == "تیپ ساختگی"


def test_configurable_two_worker_capacity(monkeypatch):

    import httpx
    from test_pipeline import raster

    from vehicle_document_ai import VehicleDocumentReader

    class Empty:
        name = "synthetic"

        def recognize(self, image, timeout):
            return []

    output = VehicleDocumentReader(adapter=Empty()).analyze(raster()).model_dump_json().encode()
    monkeypatch.setenv("IVDAI_CONCURRENCY", "2")

    async def run():
        release = asyncio.Event()
        two_started = asyncio.Event()
        count = 0

        class Worker:
            returncode = 0

            async def communicate(self, data):
                await release.wait()
                return output, b""

        async def spawn(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                two_started.set()
            return Worker()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
        ) as client:
            jobs = [
                asyncio.create_task(
                    client.post(
                        "/api/v1/documents/analyze", files={"file": ("synthetic.png", raster())}
                    )
                )
                for _ in range(2)
            ]
            await two_started.wait()
            third = await client.post(
                "/api/v1/documents/analyze", files={"file": ("synthetic.png", raster())}
            )
            assert third.status_code == 429 and count == 2
            release.set()
            assert [r.status_code for r in await asyncio.gather(*jobs)] == [200, 200]

    asyncio.run(run())


@pytest.mark.parametrize("turns", [0, 1, 2, 3])
def test_legacy_alignment_coordinate_transform_matches_rotation(turns):
    import cv2

    from vehicle_document_ai.layout.legacy import align_legacy, detect_grid

    image = np.full((2644, 1844, 3), 240, np.uint8)
    for i in range(17):
        cv2.line(image, (500 + i * 50, 400), (500 + i * 50, 450), (165, 100, 65), 2)
    for y in (400, 450):
        cv2.line(image, (500, y), (1300, y), (165, 100, 65), 2)
    grid = detect_grid(image)
    assert grid
    x, y = grid.x, grid.y
    rotations = [(x, y), (y, 1844 - 1 - x), (1844 - 1 - x, 2644 - 1 - y), (2644 - 1 - y, x)]
    aligned, matrix, operations = align_legacy(np.rot90(image, turns).copy())
    point = matrix @ np.array([*rotations[turns], 1.0])
    assert np.allclose(point[:2] / point[2], (491, 694), atol=2)
    assert aligned.shape == (2644, 1844, 3) and operations
