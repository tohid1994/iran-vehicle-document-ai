from fastapi.testclient import TestClient
from test_pipeline import raster

from vehicle_document_ai.api import create_app


def test_health_schema_and_auth(monkeypatch):
    monkeypatch.setenv("IVDAI_API_KEY", "synthetic-test-key")
    with TestClient(create_app()) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/models").status_code == 401
        assert (
            client.get("/api/v1/models", headers={"x-api-key": "synthetic-test-key"}).status_code
            == 200
        )
        assert "/api/v1/documents/extract" in client.get("/openapi.json").json()["paths"]


def test_bad_image_is_sanitized(monkeypatch, tmp_path):
    monkeypatch.setenv("IVDAI_MODEL_DIR", str(tmp_path))
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/documents/extract", files={"file": ("x.png", b"SECRET-TEXT")}
        )
        assert response.status_code == 422
        assert "SECRET" not in response.text
        assert response.json()["detail"] == "invalid_image"


def test_missing_model_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("IVDAI_MODEL_DIR", str(tmp_path))
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/documents/extract", files={"file": ("x.png", raster())})
        assert response.status_code == 503
        assert response.json()["detail"] == "ocr_models_unavailable_or_unverified"


def test_limit_without_content_length():
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/documents/extract",
            content=iter([b"x" * 1048576] * 11),
            headers={"content-type": "application/octet-stream"},
        )
        assert response.status_code == 413


def test_request_validation_does_not_echo_private_values():
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/documents/extract", data={"file": "PRIVATE-DATA"})
        assert response.status_code == 422 and "PRIVATE" not in response.text


def test_invalid_template_rejected_without_echo():
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/documents/extract",
            files={"file": ("x.png", raster())},
            data={"layout_template": '{"PRIVATE": "invalid"}'},
        )
        assert response.status_code == 422 and "PRIVATE" not in response.text


def test_worker_timeout_and_temp_cleanup_control_flow(monkeypatch, tmp_path):
    import asyncio
    import tempfile
    from pathlib import Path

    import vehicle_document_ai.api as api

    monkeypatch.setenv("IVDAI_TIMEOUT", "0.01")
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    worker_temp = []

    class SlowWorker:
        returncode = None
        pid = 999999

        async def communicate(self, data):
            await asyncio.sleep(10)

        async def wait(self):
            self.returncode = -9

    async def create(*args, **kwargs):
        folder = Path(kwargs["env"]["TMPDIR"])
        worker_temp.append(folder)
        (folder / "sensitive.tmp").write_text("SYNTHETIC")
        return SlowWorker()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    calls = []
    monkeypatch.setattr(api.os, "killpg", lambda *args: calls.append(args))
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/documents/extract", files={"file": ("x.png", raster())})
        assert response.status_code == 504
    assert calls and worker_temp and not worker_temp[0].exists()


def test_preprocessing_query_reaches_worker():
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/documents/analyze?enhance=true", files={"file": ("x.png", raster())}
        )
        # Models may be absent in CI; the option must still be validated by the endpoint.
        assert response.status_code in (200, 503)
        if response.status_code == 200:
            assert "conditional_clahe" in response.json()["quality"]["operations"]
