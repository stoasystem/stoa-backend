"""Upload parts go straight to S3 on a presigned URL, never through Lambda (#136).

Lambda takes at most 6 MB per request and API Gateway hands it a binary body as
base64, so a 5 MiB part sent through `PUT /files/{id}/chunks/{n}` arrived as about
7 MB and every file over 5 MiB failed. ADR-004 has the browser put the bytes on S3
itself. Here the API only signs a URL bound to one part's exact length and SHA-256,
and completion checks what S3 holds against the part the URL was signed for.

The seam is the real router and repository on the shared DynamoDB double, with S3
replaced by a double that keeps multipart state and enforces the signed headers the
way S3 does.
"""

from __future__ import annotations

import hashlib
from io import BytesIO
import random
from typing import Any
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
import pytest

from stoa.config import IMAGE_MAX_BYTES, Settings, get_settings
from stoa.db.repositories import account_deletion_repo, attachment_repo
from stoa.deps import get_actor, get_image_moderation_client, get_s3_client, get_s3_presign_client
from stoa.routers import files
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from fakes.dynamodb import FakeTable
from fakes.rekognition import FakeRekognition
from fakes.s3 import MIN_PART_BYTES, MultipartS3, b64_sha256


OWNER = "student-1"
BUCKET = "images-bucket-canary"
LAMBDA_REQUEST_LIMIT = 6 * 1024 * 1024


def _actor() -> Actor:
    return Actor(OWNER, "issuer", "subject", CanonicalRole.STUDENT, AccountStatus.ACTIVE, "student")


def _png_near_the_limit() -> bytes:
    """A real PNG just under the 10 MiB image limit: two parts, the second ~4.8 MiB."""
    edge = 1850
    noise = random.Random(136).randbytes(edge * edge * 3)
    output = BytesIO()
    Image.frombytes("RGB", (edge, edge), noise).save(output, "PNG", compress_level=0)
    data = output.getvalue()
    assert MIN_PART_BYTES < len(data) <= IMAGE_MAX_BYTES
    return data


def _S3() -> MultipartS3:
    return MultipartS3(BUCKET)


class _Api:
    """The real files router; it records the size of every request it is sent."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, table: FakeTable, s3: MultipartS3) -> None:
        monkeypatch.setattr(attachment_repo, "get_table", lambda: table)
        monkeypatch.setattr(account_deletion_repo, "get_table", lambda: table)
        app = FastAPI()
        app.include_router(files.router, prefix="/files")
        app.dependency_overrides[get_actor] = _actor
        app.dependency_overrides[get_s3_client] = lambda: s3
        app.dependency_overrides[get_s3_presign_client] = lambda: s3
        app.dependency_overrides[get_image_moderation_client] = lambda: FakeRekognition()
        app.dependency_overrides[get_settings] = lambda: Settings(s3_images_bucket=BUCKET)
        self.client = TestClient(app)
        self.request_sizes: list[int] = []
        self.client.event_hooks["request"].append(
            lambda request: self.request_sizes.append(len(request.read()))
        )

    def post(self, path: str, body: dict[str, Any]):
        return self.client.post(path, json=body)


@pytest.fixture
def table() -> FakeTable:
    table = FakeTable()
    table.seed_active_account(OWNER)
    return table


def _intent(api: _Api, data: bytes) -> dict[str, Any]:
    response = api.post(
        "/files/intents",
        {"purpose": "question_image", "filename": "work.png", "contentType": "image/png", "sizeBytes": len(data)},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _parts(data: bytes, chunk_bytes: int) -> list[bytes]:
    return [data[start:start + chunk_bytes] for start in range(0, len(data), chunk_bytes)]


def _sign(api: _Api, upload_id: str, number: int, part: bytes):
    return api.post(
        f"/files/{upload_id}/parts/{number}",
        {"sizeBytes": len(part), "checksumSha256": hashlib.sha256(part).hexdigest()},
    )


def test_a_file_near_the_image_limit_uploads_without_its_bytes_reaching_the_api(
    monkeypatch, table
) -> None:
    data = _png_near_the_limit()
    s3 = _S3()
    api = _Api(monkeypatch, table, s3)

    intent = _intent(api, data)
    parts = _parts(data, intent["chunkBytes"])
    assert len(parts) == 2 and len(parts[1]) * 4 / 3 > LAMBDA_REQUEST_LIMIT * 0.75
    for number, part in enumerate(parts, start=1):
        signed = _sign(api, intent["uploadId"], number, part)
        assert signed.status_code == 200, signed.text
        body = signed.json()
        assert s3.browser_put(body["url"], body["method"], body["headers"], part) == 200

    completed = api.post(f"/files/{intent['uploadId']}/complete", {"partCount": len(parts)})

    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "validated"
    promoted = [stored for (key, _v), stored in s3.objects.items() if key.startswith("objects/")]
    assert [stored["data"] for stored in promoted] == [data]
    assert s3.server_side_part_writes == 0
    assert max(api.request_sizes) < 1024


def test_a_url_is_signed_for_one_part_exactly(monkeypatch, table) -> None:
    data = _png_near_the_limit()
    s3 = _S3()
    api = _Api(monkeypatch, table, s3)
    intent = _intent(api, data)
    first, _second = _parts(data, intent["chunkBytes"])

    signed = _sign(api, intent["uploadId"], 1, first).json()

    assert signed["uploadId"] == intent["uploadId"] and signed["partNumber"] == 1
    assert signed["headers"] == {"x-amz-checksum-sha256": b64_sha256(first)}
    # Other bytes, or the same bytes cut short, are refused by S3 on that URL.
    assert s3.browser_put(signed["url"], "PUT", signed["headers"], bytes(reversed(first))) == 400
    assert s3.browser_put(signed["url"], "PUT", signed["headers"], first[:-1]) == 403


def test_a_part_of_the_wrong_size_gets_no_url(monkeypatch, table) -> None:
    data = _png_near_the_limit()
    api = _Api(monkeypatch, table, _S3())
    intent = _intent(api, data)
    first, second = _parts(data, intent["chunkBytes"])

    short = _sign(api, intent["uploadId"], 1, first[:-1])
    long = _sign(api, intent["uploadId"], 2, second + b"x")
    missing = _sign(api, intent["uploadId"], 3, second)

    assert (short.status_code, short.json()["detail"]["code"]) == (422, "upload_invalid")
    assert (long.status_code, long.json()["detail"]["code"]) == (422, "upload_too_large")
    assert (missing.status_code, missing.json()["detail"]["code"]) == (422, "upload_invalid")


def test_a_part_signed_for_other_bytes_is_a_conflict(monkeypatch, table) -> None:
    data = _png_near_the_limit()
    api = _Api(monkeypatch, table, _S3())
    intent = _intent(api, data)
    first, _second = _parts(data, intent["chunkBytes"])

    assert _sign(api, intent["uploadId"], 1, first).status_code == 200
    assert _sign(api, intent["uploadId"], 1, first).status_code == 200
    changed = _sign(api, intent["uploadId"], 1, bytes(reversed(first)))

    assert (changed.status_code, changed.json()["detail"]["code"]) == (409, "upload_chunk_conflict")


def test_completion_waits_for_every_part_to_reach_s3(monkeypatch, table) -> None:
    data = _png_near_the_limit()
    s3 = _S3()
    api = _Api(monkeypatch, table, s3)
    intent = _intent(api, data)
    parts = _parts(data, intent["chunkBytes"])
    signed = [_sign(api, intent["uploadId"], number, part).json() for number, part in enumerate(parts, 1)]
    s3.browser_put(signed[0]["url"], "PUT", signed[0]["headers"], parts[0])

    early = api.post(f"/files/{intent['uploadId']}/complete", {"partCount": 2})

    assert (early.status_code, early.json()["detail"]["code"]) == (422, "upload_invalid")
    s3.browser_put(signed[1]["url"], "PUT", signed[1]["headers"], parts[1])
    completed = api.post(f"/files/{intent['uploadId']}/complete", {"partCount": 2})
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "validated"


def test_the_production_signer_uses_the_regional_endpoint_and_signs_the_part(monkeypatch) -> None:
    """Without the regional host the browser is redirected away from a Zurich bucket."""
    for name in ("AWS_PROFILE", "AWS_SHARED_CREDENTIALS_FILE", "AWS_CONFIG_FILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIDEXAMPLE")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "not-a-secret")
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", "/nonexistent")
    monkeypatch.setenv("AWS_CONFIG_FILE", "/nonexistent")
    # The client is cached and holds the credentials it was built with.
    get_s3_presign_client.cache_clear()
    signer = get_s3_presign_client()
    get_s3_presign_client.cache_clear()
    region = get_settings().aws_region

    url = signer.generate_presigned_url(
        ClientMethod="upload_part",
        Params={
            "Bucket": "stoa-images-123456789012",
            "Key": "staging/abc/upload.png",
            "UploadId": "mp-1",
            "PartNumber": 1,
            "ContentLength": 3,
            "ChecksumSHA256": b64_sha256(b"abc"),
        },
        ExpiresIn=300,
        HttpMethod="PUT",
    )

    parsed = urlparse(url)
    assert parsed.netloc == f"stoa-images-123456789012.s3.{region}.amazonaws.com"
    signed_headers = parse_qs(parsed.query)["X-Amz-SignedHeaders"][0].split(";")
    # Exactly these: a header signed here that the browser does not send, after a
    # botocore upgrade say, is a SignatureDoesNotMatch on every upload.
    assert set(signed_headers) == {"content-length", "host", "x-amz-checksum-sha256"}


class _RaceLostTable(FakeTable):
    """A second completion records each part just before this one tries to.

    Two `complete` calls for the same upload both find the part uploading on S3;
    the one whose ledger write lands second has its condition refused.
    """

    def __init__(self, *, winner_etag: str | None = None) -> None:
        super().__init__()
        self.winner_etag = winner_etag

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        recording_part = str(kwargs["Key"]["SK"]).startswith("PART#") and "provider_etag" in str(
            kwargs["UpdateExpression"]
        )
        if recording_part:
            winner = {**kwargs, "ExpressionAttributeValues": dict(kwargs["ExpressionAttributeValues"])}
            if self.winner_etag is not None:
                winner["ExpressionAttributeValues"][":etag"] = self.winner_etag
            super().update_item(**winner)
        return super().update_item(**kwargs)


def _complete_after_losing_the_race(monkeypatch, table: _RaceLostTable):
    table.seed_active_account(OWNER)
    data = _png_near_the_limit()
    s3 = _S3()
    api = _Api(monkeypatch, table, s3)
    intent = _intent(api, data)
    for number, part in enumerate(_parts(data, intent["chunkBytes"]), 1):
        signed = _sign(api, intent["uploadId"], number, part).json()
        assert s3.browser_put(signed["url"], "PUT", signed["headers"], part) == 200
    return api.post(f"/files/{intent['uploadId']}/complete", {"partCount": 2}), s3


def test_a_completion_that_loses_the_race_to_record_a_part_still_completes(monkeypatch) -> None:
    completed, _s3 = _complete_after_losing_the_race(monkeypatch, _RaceLostTable())

    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "validated"


def test_a_part_recorded_with_another_etag_is_not_taken_on_trust(monkeypatch) -> None:
    completed, s3 = _complete_after_losing_the_race(
        monkeypatch, _RaceLostTable(winner_etag='"another-etag"')
    )

    assert (completed.status_code, completed.json()["detail"]["code"]) == (
        503,
        "upload_service_unavailable",
    )
    # Refused before assembly, not left for S3 to catch.
    assert s3.completions_sent == 0
