"""Every uploaded image is machine-moderated before it counts as uploaded (#138).

When an upload completes, a JPEG or PNG is shown to Amazon Rekognition
DetectModerationLabels in Frankfurt (ADR-010: only the image goes there). A label in
a blocked category at or above the configured confidence refuses the upload with a
stable code the frontend turns into its own four-language copy; the image is never
promoted. If moderation cannot answer, the upload fails as retryable and stays
unpromoted until a later completion gets an answer.

The seam is the real files router and repository on the shared DynamoDB double, S3
replaced by the multipart double and Rekognition by `fakes.rekognition`, which
answers the way the service does (it drops labels under `MinConfidence`).
"""

from __future__ import annotations

import hashlib
from io import BytesIO
import random
from typing import Any

from botocore.exceptions import ClientError, EndpointConnectionError, ReadTimeoutError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
import pytest

from stoa.config import Settings
from stoa.db.repositories import account_deletion_repo, attachment_repo
from stoa.deps import (
    get_actor,
    get_image_moderation_client,
    get_s3_client,
    get_s3_presign_client,
    get_settings,
)
from stoa.routers import files
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from fakes.dynamodb import FakeTable
from fakes.rekognition import FakeRekognition
from fakes.s3 import MultipartS3


STUDENT = "student-1"
TEACHER = "teacher-1"
BUCKET = "images-bucket-canary"
REKOGNITION_MAX_BYTES = 5 * 1024 * 1024
REKOGNITION_MIN_EDGE = 80
REKOGNITION_MAX_EDGE = 10_000


def _actor(user_id: str, role: CanonicalRole) -> Actor:
    return Actor(user_id, "issuer", "subject", role, AccountStatus.ACTIVE, role.value)


def _png(width: int = 200, height: int = 200, *, seed: int = 138) -> bytes:
    noise = random.Random(seed).randbytes(width * height * 3)
    output = BytesIO()
    Image.frombytes("RGB", (width, height), noise).save(output, "PNG", compress_level=0)
    return output.getvalue()


def _label(name: str, confidence: float, parent: str = "", level: int = 1) -> dict[str, Any]:
    return {"Name": name, "Confidence": confidence, "ParentName": parent, "TaxonomyLevel": level}


def _lineage(confidence: float, *names: str) -> list[dict[str, Any]]:
    """An L1 label and its descendants, the way Rekognition returns a detection."""
    return [
        _label(name, confidence, names[index - 1] if index else "", index + 1)
        for index, name in enumerate(names)
    ]


def _client_error(code: str, status: int) -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": "canary"}, "ResponseMetadata": {"HTTPStatusCode": status}},
        "DetectModerationLabels",
    )


class _Api:
    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        table: FakeTable,
        moderation: FakeRekognition | None,
        settings: Settings | None = None,
    ) -> None:
        monkeypatch.setattr(attachment_repo, "get_table", lambda: table)
        monkeypatch.setattr(account_deletion_repo, "get_table", lambda: table)
        self.table = table
        self.s3 = MultipartS3(BUCKET)
        self.actor = _actor(STUDENT, CanonicalRole.STUDENT)
        app = FastAPI()
        app.include_router(files.router, prefix="/files")
        app.dependency_overrides[get_actor] = lambda: self.actor
        app.dependency_overrides[get_s3_client] = lambda: self.s3
        app.dependency_overrides[get_s3_presign_client] = lambda: self.s3
        app.dependency_overrides[get_image_moderation_client] = lambda: moderation
        app.dependency_overrides[get_settings] = lambda: settings or Settings(s3_images_bucket=BUCKET)
        self.client = TestClient(app)

    def upload(
        self,
        data: bytes,
        filename: str = "work.png",
        content_type: str = "image/png",
        purpose: str = "conversation_attachment",
    ) -> str:
        """Every step but completion: an intent, then each part put on its signed URL."""
        intent = self.client.post(
            "/files/intents",
            json={
                "purpose": purpose,
                "filename": filename,
                "contentType": content_type,
                "sizeBytes": len(data),
            },
        )
        assert intent.status_code == 200, intent.text
        body = intent.json()
        size = body["chunkBytes"]
        for number, start in enumerate(range(0, len(data), size), start=1):
            part = data[start:start + size]
            signed = self.client.post(
                f"/files/{body['uploadId']}/parts/{number}",
                json={"sizeBytes": len(part), "checksumSha256": hashlib.sha256(part).hexdigest()},
            )
            assert signed.status_code == 200, signed.text
            url = signed.json()
            assert self.s3.browser_put(url["url"], url["method"], url["headers"], part) == 200
        return body["uploadId"]

    def complete(self, upload_id: str, data: bytes):
        part_count = -(-len(data) // (5 * 1024 * 1024))
        return self.client.post(f"/files/{upload_id}/complete", json={"partCount": part_count})

    def promoted(self) -> list[bytes]:
        return [stored["data"] for (key, _v), stored in self.s3.objects.items() if key.startswith("objects/")]


@pytest.fixture
def table() -> FakeTable:
    table = FakeTable()
    table.seed_active_account(STUDENT)
    return table


def _code(response) -> str:
    return response.json()["detail"]["code"]


def test_a_clean_image_is_moderated_in_full_and_then_counts_as_uploaded(monkeypatch, table) -> None:
    moderation = FakeRekognition()
    api = _Api(monkeypatch, table, moderation)
    data = _png()

    completed = api.complete(api.upload(data), data)

    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "validated"
    assert api.promoted() == [data]
    assert len(moderation.calls) == 1
    assert moderation.calls[0]["Image"] == {"Bytes": data}


@pytest.mark.parametrize(
    ("confidence", "blocked"),
    [(79.0, False), (79.99, False), (80.0, True), (80.01, True)],
)
def test_the_threshold_is_eighty_percent(monkeypatch, table, confidence, blocked) -> None:
    moderation = FakeRekognition(_lineage(confidence, "Explicit", "Explicit Nudity"))
    api = _Api(monkeypatch, table, moderation)
    data = _png()

    completed = api.complete(api.upload(data), data)

    if blocked:
        assert (completed.status_code, _code(completed)) == (422, "upload_content_blocked")
        assert api.promoted() == []
    else:
        assert completed.status_code == 200, completed.text
        assert api.promoted() == [data]


BLOCKED = {
    "explicit": _lineage(97.0, "Explicit", "Explicit Nudity", "Exposed Female Nipple"),
    "nudity": _lineage(
        97.0, "Non-Explicit Nudity of Intimate parts and Kissing", "Non-Explicit Nudity", "Implied Nudity"
    ),
    "violence and gore": _lineage(97.0, "Violence", "Graphic Violence", "Blood & Gore"),
    "visually disturbing": _lineage(97.0, "Visually Disturbing", "Death and Emaciation", "Corpses"),
    "hate symbols": _lineage(97.0, "Hate Symbols", "Nazi Party"),
    "rude gestures": _lineage(97.0, "Rude Gestures", "Middle Finger"),
}

NOT_BLOCKED = {
    "alcohol": _lineage(99.0, "Alcohol", "Alcohol Use", "Drinking"),
    "tobacco": _lineage(99.0, "Drugs & Tobacco", "Drugs & Tobacco Paraphernalia & Use", "Smoking"),
    "drugs": _lineage(99.0, "Drugs & Tobacco", "Products", "Pills"),
    "gambling": _lineage(99.0, "Gambling"),
}


@pytest.mark.parametrize("category", sorted(BLOCKED))
def test_each_blocked_category_refuses_the_image(monkeypatch, table, category) -> None:
    api = _Api(monkeypatch, table, FakeRekognition(BLOCKED[category]))
    data = _png()
    upload_id = api.upload(data)

    refused = api.complete(upload_id, data)

    assert (refused.status_code, _code(refused)) == (422, "upload_content_blocked")
    # Neither the image nor its staging copy is kept, and completing again
    # cannot turn the refused upload into an attachment.
    assert api.s3.objects == {}
    again = api.complete(upload_id, data)
    assert again.status_code != 200 and api.promoted() == []


@pytest.mark.parametrize("category", sorted(NOT_BLOCKED))
def test_alcohol_tobacco_drugs_and_gambling_are_not_blocked(monkeypatch, table, category) -> None:
    api = _Api(monkeypatch, table, FakeRekognition(NOT_BLOCKED[category]))
    data = _png()

    completed = api.complete(api.upload(data), data)

    assert completed.status_code == 200, completed.text
    assert api.promoted() == [data]


@pytest.mark.parametrize(
    "label",
    [
        _label("Blood & Gore", 95.0, "Graphic Violence", 3),
        _label("Corpses", 95.0, "Death and Emaciation", 3),
        _label("Exposed Male Genitalia", 95.0, "Explicit Nudity", 3),
    ],
    ids=["gore", "corpses", "explicit nudity"],
)
def test_a_label_returned_without_its_ancestors_is_judged_by_its_category(
    monkeypatch, table, label
) -> None:
    api = _Api(monkeypatch, table, FakeRekognition([label]))
    data = _png()

    refused = api.complete(api.upload(data), data)

    assert (refused.status_code, _code(refused)) == (422, "upload_content_blocked")


def test_categories_and_threshold_come_from_configuration(monkeypatch, table) -> None:
    settings = Settings(
        s3_images_bucket=BUCKET,
        image_moderation_blocked_labels=["Alcohol"],
        image_moderation_min_confidence=90.0,
    )
    moderation = FakeRekognition(_lineage(95.0, "Alcohol", "Alcoholic Beverages"))
    api = _Api(monkeypatch, table, moderation, settings)
    data = _png()

    refused = api.complete(api.upload(data), data)
    moderation.labels = _lineage(89.0, "Alcohol") + _lineage(99.0, "Explicit")
    other = _png(seed=139)
    passed = api.complete(api.upload(other), other)

    assert (refused.status_code, _code(refused)) == (422, "upload_content_blocked")
    assert passed.status_code == 200, passed.text


def test_moderation_outside_the_eu_is_refused_by_configuration() -> None:
    with pytest.raises(ValueError):
        Settings(image_moderation_region="us-east-1")


@pytest.mark.parametrize(
    "error",
    [
        _client_error("ThrottlingException", 400),
        _client_error("ProvisionedThroughputExceededException", 400),
        _client_error("InternalServerError", 500),
        _client_error("AccessDeniedException", 400),
        EndpointConnectionError(endpoint_url="https://rekognition.eu-central-1.amazonaws.com"),
        ReadTimeoutError(endpoint_url="https://rekognition.eu-central-1.amazonaws.com"),
    ],
    ids=["throttled", "over-quota", "server-error", "access-denied", "unreachable", "timeout"],
)
def test_without_an_answer_the_upload_fails_retryably_and_is_not_let_through(
    monkeypatch, table, error
) -> None:
    moderation = FakeRekognition()
    moderation.error = error
    api = _Api(monkeypatch, table, moderation)
    data = _png()
    upload_id = api.upload(data)

    failed = api.complete(upload_id, data)

    assert (failed.status_code, _code(failed)) == (503, "upload_service_unavailable")
    assert failed.headers["Retry-After"] == "30"
    assert api.promoted() == []
    # The same upload completes once moderation answers.
    moderation.error = None
    retried = api.complete(upload_id, data)
    assert retried.status_code == 200, retried.text
    assert api.promoted() == [data]


def test_without_a_moderation_client_no_image_is_let_through(monkeypatch, table) -> None:
    api = _Api(monkeypatch, table, None)
    data = _png()

    failed = api.complete(api.upload(data), data)

    assert (failed.status_code, _code(failed)) == (503, "upload_service_unavailable")
    assert api.promoted() == []


def test_an_image_rekognition_cannot_read_is_refused_not_let_through(monkeypatch, table) -> None:
    moderation = FakeRekognition()
    moderation.error = _client_error("InvalidImageFormatException", 400)
    api = _Api(monkeypatch, table, moderation)
    data = _png()

    refused = api.complete(api.upload(data), data)

    assert (refused.status_code, _code(refused)) == (422, "upload_invalid")
    assert api.promoted() == []


def test_an_image_over_rekognitions_byte_limit_is_moderated_as_a_smaller_copy(
    monkeypatch, table
) -> None:
    moderation = FakeRekognition()
    api = _Api(monkeypatch, table, moderation)
    data = _png(1850, 1850)
    assert len(data) > REKOGNITION_MAX_BYTES

    completed = api.complete(api.upload(data), data)

    assert completed.status_code == 200, completed.text
    sent = moderation.calls[0]["Image"]["Bytes"]
    assert len(sent) <= REKOGNITION_MAX_BYTES
    with Image.open(BytesIO(sent)) as shown:
        assert shown.format in {"JPEG", "PNG"}
        assert max(shown.size) >= 1024
    # What is stored is the upload itself, not the copy shown to moderation.
    assert api.promoted() == [data]


def test_an_image_narrower_than_rekognitions_minimum_is_moderated_enlarged(
    monkeypatch, table
) -> None:
    """A one-line formula cropped from a screenshot can be under 80 px tall."""
    moderation = FakeRekognition()
    api = _Api(monkeypatch, table, moderation)
    data = _png(600, 40)

    completed = api.complete(api.upload(data), data)

    assert completed.status_code == 200, completed.text
    with Image.open(BytesIO(moderation.calls[0]["Image"]["Bytes"])) as shown:
        assert REKOGNITION_MIN_EDGE <= min(shown.size)
        assert max(shown.size) <= REKOGNITION_MAX_EDGE
        # Enlarged, not stretched: moderation sees the image's own proportions.
        assert shown.size[0] / shown.size[1] == pytest.approx(600 / 40, rel=0.02)
    assert api.promoted() == [data]


def test_a_document_is_not_sent_to_image_moderation(monkeypatch, table) -> None:
    moderation = FakeRekognition(_lineage(99.0, "Explicit"))
    api = _Api(monkeypatch, table, moderation)
    data = b"x^2 + 1 = 0\n"

    completed = api.complete(api.upload(data, "notes.txt", "text/plain"), data)

    assert completed.status_code == 200, completed.text
    assert moderation.calls == []


def test_a_teachers_image_is_moderated_the_same_way(monkeypatch, table) -> None:
    """A teacher's image for a reply to a help request (#145): the same completion."""
    table.seed_active_account(TEACHER)
    moderation = FakeRekognition(BLOCKED["rude gestures"])
    api = _Api(monkeypatch, table, moderation)
    api.actor = _actor(TEACHER, CanonicalRole.TEACHER)
    blocked, clean = _png(), _png(seed=139)
    blocked_id = api.upload(blocked, purpose="help_reply_image")
    clean_id = api.upload(clean, purpose="help_reply_image")

    refused = api.complete(blocked_id, blocked)
    moderation.labels = []
    passed = api.complete(clean_id, clean)

    assert (refused.status_code, _code(refused)) == (422, "upload_content_blocked")
    assert passed.status_code == 200, passed.text
    assert [call["Image"]["Bytes"] for call in moderation.calls] == [blocked, clean]
    assert api.promoted() == [clean]


def test_the_production_client_calls_rekognition_in_frankfurt(monkeypatch) -> None:
    for name in ("AWS_PROFILE", "AWS_SHARED_CREDENTIALS_FILE", "AWS_CONFIG_FILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIDEXAMPLE")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "not-a-secret")
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", "/nonexistent")
    monkeypatch.setenv("AWS_CONFIG_FILE", "/nonexistent")
    get_image_moderation_client.cache_clear()
    client = get_image_moderation_client()
    get_image_moderation_client.cache_clear()

    assert client.meta.service_model.service_name == "rekognition"
    assert client.meta.region_name == "eu-central-1"
    assert client.meta.endpoint_url == "https://rekognition.eu-central-1.amazonaws.com"
    # Throttling is retried a little inside the request, then reported as retryable.
    assert client.meta.config.retries["mode"] == "standard"


# API Gateway and the Lambda both stop at 29 s; completion also reads and writes
# S3 around the moderation call. Past the gateway's limit the student gets a bare
# 504 instead of our retryable 503 with Retry-After.
GATEWAY_LIMIT_SECONDS = 29
MODERATION_BUDGET_SECONDS = 17
# Standard mode backs off at most 2 ** (attempt - 1) seconds before each retry.
STANDARD_BACKOFF_CAP_SECONDS = 20


def test_the_production_client_gives_up_well_inside_the_gateway_limit(monkeypatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIDEXAMPLE")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "not-a-secret")
    get_image_moderation_client.cache_clear()
    config = get_image_moderation_client().meta.config
    get_image_moderation_client.cache_clear()

    attempts = config.retries["total_max_attempts"]
    backoff = sum(min(2 ** retry, STANDARD_BACKOFF_CAP_SECONDS) for retry in range(attempts - 1))
    worst = attempts * (config.connect_timeout + config.read_timeout) + backoff

    assert (config.connect_timeout, config.read_timeout, attempts) == (2, 5, 2)
    assert worst <= MODERATION_BUDGET_SECONDS < GATEWAY_LIMIT_SECONDS


def _animated_png(frames: list[Image.Image]) -> bytes:
    output = BytesIO()
    frames[0].save(output, "PNG", save_all=True, append_images=frames[1:], default_image=True)
    return output.getvalue()


def test_an_animated_png_is_refused_before_moderation(monkeypatch, table) -> None:
    """Moderation sees only an APNG's default image; a browser plays every frame."""
    moderation = FakeRekognition()
    api = _Api(monkeypatch, table, moderation)
    harmless = Image.new("RGB", (200, 200), (255, 255, 255))
    hidden = Image.frombytes("RGB", (200, 200), random.Random(138).randbytes(200 * 200 * 3))
    data = _animated_png([harmless, hidden, hidden])
    with Image.open(BytesIO(data)) as decoded:
        assert decoded.format == "PNG" and decoded.n_frames == 3

    refused = api.complete(api.upload(data), data)

    assert (refused.status_code, _code(refused)) == (422, "upload_invalid")
    assert api.promoted() == []
    assert moderation.calls == []


def test_another_moderation_model_is_logged_for_review(monkeypatch, table, caplog) -> None:
    """A renamed category would stop matching without a word; this says so."""
    moderation = FakeRekognition()
    moderation.model_version = "8.0"
    api = _Api(monkeypatch, table, moderation)
    data = _png()

    with caplog.at_level("WARNING", logger="stoa.services.image_moderation_service"):
        completed = api.complete(api.upload(data), data)

    assert completed.status_code == 200, completed.text
    warnings = [r.getMessage() for r in caplog.records if "model_version" in r.getMessage()]
    assert warnings == ["image_moderation_model_version_unexpected version=8.0 expected=7.0"]


def test_the_expected_moderation_model_logs_nothing(monkeypatch, table, caplog) -> None:
    api = _Api(monkeypatch, table, FakeRekognition())
    data = _png()

    with caplog.at_level("WARNING", logger="stoa.services.image_moderation_service"):
        completed = api.complete(api.upload(data), data)

    assert completed.status_code == 200, completed.text
    assert not [r for r in caplog.records if "model_version" in r.getMessage()]
