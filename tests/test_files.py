from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.config import Settings, get_settings
from stoa.deps import get_current_user, get_s3_client
from stoa.routers import files


class RecordingS3Client:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def generate_presigned_url(self, operation: str, *, Params: dict, ExpiresIn: int) -> str:
        self.calls.append({"operation": operation, "Params": Params, "ExpiresIn": ExpiresIn})
        return "https://uploads.example.test/presigned"


def _settings() -> Settings:
    return Settings(
        cognito_user_pool_id="pool",
        s3_images_bucket="images-bucket",
        s3_presign_expiry_seconds=120,
    )


def _client(s3: RecordingS3Client | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(files.router, prefix="/files")
    app.dependency_overrides[get_settings] = _settings
    app.dependency_overrides[get_current_user] = lambda: {"sub": "teacher-1", "role": "teacher"}
    app.dependency_overrides[get_s3_client] = lambda: s3 or RecordingS3Client()
    return TestClient(app)


def test_presign_allows_teacher_certificate_pdf_upload() -> None:
    s3 = RecordingS3Client()

    response = _client(s3).post(
        "/files/presign",
        json={"filename": "diploma.pdf", "content_type": "application/pdf"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["upload_url"] == "https://uploads.example.test/presigned"
    assert body["s3_key"].startswith("uploads/teacher-1/")
    assert body["s3_key"].endswith(".pdf")
    assert body["expires_in"] == 120
    assert s3.calls[0]["operation"] == "put_object"
    assert s3.calls[0]["Params"]["Bucket"] == "images-bucket"
    assert s3.calls[0]["Params"]["ContentType"] == "application/pdf"


def test_presign_still_allows_image_uploads() -> None:
    s3 = RecordingS3Client()

    response = _client(s3).post(
        "/files/presign",
        json={"filename": "work.jpeg", "content_type": "image/jpeg"},
    )

    assert response.status_code == 200
    assert response.json()["s3_key"].endswith(".jpeg")
    assert s3.calls[0]["Params"]["ContentType"] == "image/jpeg"


def test_presign_rejects_extension_content_type_mismatch() -> None:
    response = _client().post(
        "/files/presign",
        json={"filename": "diploma.pdf", "content_type": "image/png"},
    )

    assert response.status_code == 422
    assert "application/pdf" in str(response.json())
