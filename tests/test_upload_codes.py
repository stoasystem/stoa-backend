"""A one-time upload code puts a phone photo into one learning conversation (#146).

On the computer, the student's conversation shows a QR code. The phone that scans it
is not signed in: the code is its only credential. So the code is a bearer secret.
It is long and random, stored only as a hash, compared in constant time, usable once
(the claim is a conditional write), dead after ten minutes or as soon as the
student's account enters deletion, and it never reaches a log. Redeeming it hands
the phone a second secret for the rest of that one upload, so a screenshot of the
QR is worth nothing once the phone has used it. Every way a code can be wrong
answers the same way, so a caller learns nothing from the refusal.

The image goes through the same upload as any other, including #138's moderation,
and the upload it makes can be attached only to the conversation the code was made
in.

The seam is the real routes (the computer's, the phone's and the message route) on
the shared DynamoDB double, with S3 replaced by the multipart double and Rekognition
by `fakes.rekognition`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
from io import BytesIO
import logging
import random
import time
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from PIL import Image
import pytest

from stoa.config import Settings
from stoa.db.repositories import account_deletion_repo, attachment_repo, upload_code_repo
from stoa.deps import (
    get_actor,
    get_authorization_audit_sink,
    get_image_moderation_client,
    get_s3_client,
    get_s3_presign_client,
    get_settings,
)
from stoa.routers import conversations, upload_codes
from audit_helpers import MemoryAuthorizationAuditSink
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.services import attachment_service, rate_limit, upload_code_service
from fakes.dynamodb import FakeTable
from fakes.rekognition import FakeRekognition
from fakes.s3 import MultipartS3


STUDENT = "student-1"
OTHER_STUDENT = "student-2"
CONV = "conv-1"
OTHER_CONV = "conv-2"
FOREIGN_CONV = "conv-foreign"
BUCKET = "images-bucket-canary"
# Near the real time, since the message route reads the real clock for the upload's
# own expiry; on a 600 s boundary, so it starts a fresh rate window of 300 or 600 s.
START = datetime.fromtimestamp(int(time.time()) // 600 * 600, UTC)
ANSWER = {
    "steps": ["Lies die Aufgabe auf dem Bild"],
    "answer": "Das Ergebnis ist 3/4.",
    "hints": [],
}


def _png(seed: int = 146) -> bytes:
    noise = random.Random(seed).randbytes(120 * 90 * 3)
    output = BytesIO()
    Image.frombytes("RGB", (120, 90), noise).save(output, "PNG")
    return output.getvalue()


def _pdf() -> bytes:
    return b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _conversation(conversation_id: str, student_id: str) -> dict[str, Any]:
    return {
        "PK": f"CONV#{conversation_id}",
        "SK": "CONV",
        "entity_type": "conversation",
        "conversation_id": conversation_id,
        "student_id": student_id,
        "owner_id": student_id,
        "account_fence_generation": 1,
        "subject": "Mathematik",
        "grade": "Grade 6",
        "title": "Mathematik · Grade 6",
        "updated_at": "2026-10-29T08:00:00+00:00",
    }


class _Table(FakeTable):
    """The shared double, reached the way `attachment_repo.transact` calls it."""

    def transact_write_items(self, operations=None, *, TransactItems=None) -> None:
        super().transact_write_items(TransactItems if TransactItems is not None else operations)


class _Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


class _Api:
    """The student's computer (signed in) and a phone (not signed in), one backend."""

    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        table: FakeTable,
        *,
        moderation: FakeRekognition | None = None,
        settings: Settings | None = None,
    ) -> None:
        for module in (conversations, attachment_repo, upload_code_repo, rate_limit):
            monkeypatch.setattr(module, "get_table", lambda table=table: table)
        monkeypatch.setattr(account_deletion_repo, "get_table", lambda: table)
        self.clock = _Clock()
        monkeypatch.setattr(upload_code_service, "_now", self.clock)
        self.table = table
        self.s3 = MultipartS3(BUCKET)
        self.moderation = moderation or FakeRekognition()
        self.settings = settings or Settings(s3_images_bucket=BUCKET)
        monkeypatch.setattr(conversations.boto3, "client", lambda *_a, **_k: self.s3)
        self.model_calls: list[dict[str, Any]] = []

        def get_ai_answer(**kwargs: Any) -> dict[str, Any]:
            self.model_calls.append(kwargs)
            return dict(ANSWER)

        monkeypatch.setattr(conversations.ai_service, "get_ai_answer", get_ai_answer)
        monkeypatch.setattr(conversations, "_chat_limit_for_student", lambda *_: 50)
        monkeypatch.setattr(conversations, "_attachment_plan_for_student", lambda *_: "free_trial")
        monkeypatch.setattr(
            conversations.entitlement_service,
            "resolve_student_entitlement",
            lambda *_a, **_k: {"effectivePlan": "free_trial", "allowanceVersion": 1},
        )
        self.profiles = {
            student: {"user_id": student, "role": "student", "account_status": "active"}
            for student in (STUDENT, OTHER_STUDENT)
        }
        monkeypatch.setattr(
            conversations.user_repo,
            "get_user",
            lambda user_id, **_k: self.profiles.get(user_id, {}),
        )

        app = FastAPI()
        app.include_router(conversations.router, prefix="/conversations")
        app.include_router(upload_codes.conversation_router, prefix="/conversations")
        app.include_router(upload_codes.router, prefix="/upload-codes")

        def actor(request: Request) -> Actor:
            # Only the computer sends a session. The phone's requests reaching
            # this would be a phone route that asks who is signed in.
            who = request.headers.get("authorization", "")
            if not who.startswith("Bearer "):
                raise HTTPException(status_code=401, detail={"code": "unauthenticated"})
            user_id = who.removeprefix("Bearer ")
            return Actor(
                user_id, "https://identity.test", f"{user_id}-subject",
                CanonicalRole.STUDENT, AccountStatus.ACTIVE, "student",
            )

        app.dependency_overrides[get_actor] = actor
        app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
        app.dependency_overrides[get_s3_client] = lambda: self.s3
        app.dependency_overrides[get_s3_presign_client] = lambda: self.s3
        app.dependency_overrides[get_image_moderation_client] = lambda: self.moderation
        app.dependency_overrides[get_settings] = lambda: self.settings
        self.client = TestClient(app, raise_server_exceptions=False)

    # -- the computer --------------------------------------------------------------

    def issue(self, conversation_id: str = CONV, student: str = STUDENT):
        return self.client.post(
            f"/conversations/{conversation_id}/upload-codes",
            headers={"Authorization": f"Bearer {student}"},
        )

    def code(self, conversation_id: str = CONV) -> dict[str, Any]:
        issued = self.issue(conversation_id)
        assert issued.status_code == 200, issued.text
        return issued.json()

    def status(self, code_id: str, conversation_id: str = CONV, student: str = STUDENT):
        return self.client.get(
            f"/conversations/{conversation_id}/upload-codes/{code_id}",
            headers={"Authorization": f"Bearer {student}"},
        )

    def send(self, upload_id: str, conversation_id: str = CONV, key: str = "key-1"):
        return self.client.post(
            f"/conversations/{conversation_id}/messages",
            json={
                "content": "Kannst du mir bei dieser Aufgabe helfen?",
                "idempotencyKey": key,
                "attachmentIds": [{"uploadId": upload_id}],
            },
            headers={"Authorization": f"Bearer {STUDENT}", "Accept-Language": "de"},
        )

    # -- the phone -----------------------------------------------------------------

    def redeem(
        self,
        code: str,
        data: bytes | None = None,
        *,
        filename: str = "aufgabe.png",
        content_type: str = "image/png",
    ):
        data = _png() if data is None else data
        return self.client.post(
            "/upload-codes/redeem",
            json={
                "code": code,
                "filename": filename,
                "contentType": content_type,
                "sizeBytes": len(data),
            },
        )

    def put_parts(self, token: str, data: bytes, chunk_bytes: int) -> None:
        for number, start in enumerate(range(0, len(data), chunk_bytes), start=1):
            part = data[start:start + chunk_bytes]
            signed = self.sign(token, number, part)
            assert signed.status_code == 200, signed.text
            url = signed.json()
            assert self.s3.browser_put(url["url"], url["method"], url["headers"], part) == 200

    def sign(self, token: str, number: int, part: bytes):
        return self.client.post(
            f"/upload-codes/parts/{number}",
            json={
                "uploadToken": token,
                "sizeBytes": len(part),
                "checksumSha256": hashlib.sha256(part).hexdigest(),
            },
        )

    def complete(self, token: str, part_count: int = 1):
        return self.client.post(
            "/upload-codes/complete",
            json={"uploadToken": token, "partCount": part_count},
        )

    def phone_upload(self, code: str, data: bytes | None = None, **kwargs: Any):
        """Scan, put the photo on S3, finish: what the phone page does."""
        data = _png() if data is None else data
        redeemed = self.redeem(code, data, **kwargs)
        assert redeemed.status_code == 200, redeemed.text
        body = redeemed.json()
        self.put_parts(body["uploadToken"], data, body["chunkBytes"])
        return body["uploadToken"], self.complete(body["uploadToken"])

    def preview(self, code_id: str, student: str = STUDENT):
        return self.client.get(
            f"/conversations/{CONV}/upload-codes/{code_id}/content",
            headers={"Authorization": f"Bearer {student}"},
        )

    def rows(self, entity_type: str) -> list[dict[str, Any]]:
        return [row for row in self.table.rows.values() if row.get("entity_type") == entity_type]


@pytest.fixture
def table() -> FakeTable:
    table = _Table()
    table.seed_active_account(STUDENT)
    table.seed_active_account(OTHER_STUDENT)
    table.seed(
        _conversation(CONV, STUDENT),
        _conversation(OTHER_CONV, STUDENT),
        _conversation(FOREIGN_CONV, OTHER_STUDENT),
    )
    return table


@pytest.fixture(autouse=True)
def _no_memory_personalisation(stub_memory_summary) -> None:
    """The prompt enrichment reads three tables; keep it out."""


def _refusal(response) -> tuple[int, str]:
    return response.status_code, response.json()["detail"]["code"]


def _public(response) -> tuple[int, dict[str, Any]]:
    """What a caller sees, minus the per-request correlation id."""
    body = dict(response.json()["detail"])
    body.pop("correlationId", None)
    return response.status_code, body


INVALID = (404, "upload_code_invalid")


# -- the path that works -----------------------------------------------------------


def test_a_phone_with_the_code_puts_a_photo_into_that_conversation_without_signing_in(
    monkeypatch, table
) -> None:
    api = _Api(monkeypatch, table)
    data = _png()
    issued = api.code()
    assert datetime.fromisoformat(issued["expiresAt"]) == START + timedelta(minutes=10)
    assert api.status(issued["codeId"]).json()["status"] == "waiting"

    _token, completed = api.phone_upload(issued["code"], data)

    assert completed.status_code == 200, completed.text
    assert completed.json() == {"status": "validated"}
    assert [call["Image"] for call in api.moderation.calls] == [{"Bytes": data}]
    # Where #139's moderation queue reads the learning session of a blocked image.
    assert [row["conversation_id"] for row in api.rows("upload_intent")] == [CONV]
    ready = api.status(issued["codeId"]).json()
    assert ready["status"] == "ready"
    sent = api.send(ready["uploadId"])
    assert sent.status_code in {200, 202}, sent.text
    messages = [
        row for row in table.rows.values()
        if row.get("PK") == f"CONV#{CONV}" and row.get("attachment_ids")
    ]
    assert len(messages) == 1
    [attachment] = api.rows("attachment")
    assert attachment["owner_id"] == STUDENT
    assert attachment["source_upload_id"] == ready["uploadId"]


def test_the_computer_learns_the_upload_only_once_it_has_passed(monkeypatch, table) -> None:
    api = _Api(monkeypatch, table)
    data = _png()
    issued = api.code()
    assert api.status(issued["codeId"]).json()["redeemedAt"] is None
    api.clock.now = START + timedelta(minutes=2)
    redeemed = api.redeem(issued["code"], data).json()

    uploading = api.status(issued["codeId"]).json()
    assert (uploading["status"], uploading.get("uploadId")) == ("uploading", None)
    assert datetime.fromisoformat(uploading["redeemedAt"]) == START + timedelta(minutes=2)
    assert api.preview(issued["codeId"]).status_code == 404

    api.put_parts(redeemed["uploadToken"], data, redeemed["chunkBytes"])
    assert api.complete(redeemed["uploadToken"]).status_code == 200
    assert api.status(issued["codeId"]).json()["status"] == "ready"


def test_the_student_sees_the_phones_photo_before_sending_it(monkeypatch, table) -> None:
    """Whoever scans first holds the code, so the computer shows what arrived."""
    api = _Api(monkeypatch, table)
    data = _png()
    issued = api.code()
    _token, completed = api.phone_upload(issued["code"], data)
    assert completed.status_code == 200

    preview = api.preview(issued["codeId"])

    assert preview.status_code == 200
    assert preview.content == data
    assert preview.headers["content-type"] == "image/png"
    assert api.preview(issued["codeId"], OTHER_STUDENT).status_code in {403, 404}


def test_a_code_spent_on_a_failed_start_shows_failed(monkeypatch, table) -> None:
    api = _Api(monkeypatch, table)
    issued = api.code()

    def unavailable(**_kwargs: Any):
        raise RuntimeError("s3 down")

    monkeypatch.setattr(api.s3, "create_multipart_upload", unavailable)

    assert _refusal(api.redeem(issued["code"])) == (503, "upload_service_unavailable")
    assert api.status(issued["codeId"]).json()["status"] == "failed"


# -- single use --------------------------------------------------------------------


def test_the_code_works_once(monkeypatch, table) -> None:
    api = _Api(monkeypatch, table)
    issued = api.code()
    first = api.redeem(issued["code"])
    assert first.status_code == 200, first.text

    assert _refusal(api.redeem(issued["code"])) == INVALID
    assert len(api.rows("upload_intent")) == 1


def test_a_used_code_does_not_open_the_upload_it_started(monkeypatch, table) -> None:
    """A screenshot of the QR, taken after the phone scanned it, signs nothing."""
    api = _Api(monkeypatch, table)
    data = _png()
    issued = api.code()
    assert api.redeem(issued["code"], data).status_code == 200

    assert _refusal(api.sign(issued["code"], 1, data)) == INVALID
    assert _refusal(api.complete(issued["code"])) == INVALID
    assert api.s3.signed == {}


def test_two_phones_racing_on_one_code_produce_one_upload(monkeypatch, table) -> None:
    """The claim is a conditional write: a rival that wins between read and claim wins."""
    api = _Api(monkeypatch, table)
    issued = api.code()
    real_update = table.update_item

    def rival_wins_first(**kwargs: Any):
        if kwargs.get("Key", {}).get("PK", "").startswith("UPLOADCODE#"):
            row = table.rows[(kwargs["Key"]["PK"], kwargs["Key"]["SK"])]
            row["status"] = "redeemed"
        return real_update(**kwargs)

    monkeypatch.setattr(table, "update_item", rival_wins_first)

    assert _refusal(api.redeem(issued["code"])) == INVALID
    assert api.rows("upload_intent") == []
    assert api.s3.uploads == {}


# -- ten minutes -------------------------------------------------------------------


def test_the_code_is_refused_from_ten_minutes_on(monkeypatch, table) -> None:
    api = _Api(monkeypatch, table)
    almost, exactly = api.code(), api.code()

    api.clock.now = START + timedelta(minutes=10) - timedelta(seconds=1)
    assert api.redeem(almost["code"]).status_code == 200
    api.clock.now = START + timedelta(minutes=10)
    assert _refusal(api.redeem(exactly["code"])) == INVALID
    assert api.status(exactly["codeId"]).json()["status"] == "expired"


def test_the_upload_a_code_started_must_finish_within_ten_minutes(monkeypatch, table) -> None:
    api = _Api(monkeypatch, table)
    data = _png()
    issued = api.code()
    redeemed = api.redeem(issued["code"], data).json()
    api.put_parts(redeemed["uploadToken"], data, redeemed["chunkBytes"])

    api.clock.now = START + timedelta(minutes=10)

    assert _refusal(api.complete(redeemed["uploadToken"])) == INVALID
    assert api.moderation.calls == []


# -- one conversation --------------------------------------------------------------


def test_the_photo_cannot_be_sent_into_another_conversation(monkeypatch, table) -> None:
    api = _Api(monkeypatch, table)
    issued = api.code(CONV)
    _token, completed = api.phone_upload(issued["code"])
    assert completed.status_code == 200
    upload_id = api.status(issued["codeId"]).json()["uploadId"]

    refused = api.send(upload_id, OTHER_CONV)

    assert _refusal(refused) == (404, "upload_not_found")
    assert api.model_calls == []
    assert api.rows("attachment") == []
    assert api.send(upload_id, CONV, key="key-2").status_code in {200, 202}


def test_a_code_dies_with_its_conversation(monkeypatch, table) -> None:
    api = _Api(monkeypatch, table)
    issued = api.code()

    table.rows[(f"CONV#{CONV}", "CONV")]["status"] = "deleted"

    assert _refusal(api.redeem(issued["code"])) == INVALID
    assert api.issue().status_code == 404


def test_a_code_is_made_only_in_the_students_own_conversation(monkeypatch, table) -> None:
    api = _Api(monkeypatch, table)

    assert api.issue(FOREIGN_CONV).status_code in {403, 404}
    assert api.issue("conv-missing").status_code == 404
    assert api.rows("upload_code") == []


def test_the_computer_reads_a_code_only_through_its_conversation(monkeypatch, table) -> None:
    api = _Api(monkeypatch, table)
    issued = api.code(CONV)

    assert api.status(issued["codeId"], OTHER_CONV).status_code == 404
    assert api.status(issued["codeId"], FOREIGN_CONV, OTHER_STUDENT).status_code == 404
    assert api.status("0" * 32).status_code == 404


# -- images only -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [("aufgabe.pdf", "application/pdf"), ("notes.txt", "text/plain"), ("scan.docx",
     "application/vnd.openxmlformats-officedocument.wordprocessingml.document")],
)
def test_only_an_image_can_be_started_and_the_code_survives_a_wrong_pick(
    monkeypatch, table, filename, content_type
) -> None:
    api = _Api(monkeypatch, table)
    issued = api.code()

    refused = api.redeem(issued["code"], _pdf(), filename=filename, content_type=content_type)

    assert _refusal(refused) == (422, "upload_type_not_supported")
    assert api.rows("upload_intent") == []
    assert api.redeem(issued["code"]).status_code == 200


def test_bytes_that_are_not_an_image_are_refused_at_completion(monkeypatch, table) -> None:
    api = _Api(monkeypatch, table)
    issued = api.code()

    _token, completed = api.phone_upload(issued["code"], _pdf())

    assert completed.status_code == 422
    assert api.status(issued["codeId"]).json()["status"] == "failed"
    assert [key for key, _version in api.s3.objects if key.startswith("objects/")] == []


def test_a_blocked_photo_never_reaches_the_conversation(monkeypatch, table) -> None:
    moderation = FakeRekognition(
        [{"Name": "Explicit", "Confidence": 99.0, "ParentName": "", "TaxonomyLevel": 1}]
    )
    api = _Api(monkeypatch, table, moderation=moderation)
    issued = api.code()

    _token, completed = api.phone_upload(issued["code"])

    assert _refusal(completed) == (422, "upload_content_blocked")
    status = api.status(issued["codeId"]).json()
    assert (status["status"], status.get("uploadId")) == ("failed", None)


def test_when_moderation_cannot_answer_the_phone_may_finish_later(monkeypatch, table) -> None:
    api = _Api(monkeypatch, table)
    data = _png()
    issued = api.code()
    redeemed = api.redeem(issued["code"], data).json()
    api.put_parts(redeemed["uploadToken"], data, redeemed["chunkBytes"])
    api.moderation.error = RuntimeError("rekognition down")

    assert api.complete(redeemed["uploadToken"]).status_code == 503
    assert api.status(issued["codeId"]).json()["status"] == "uploading"
    api.moderation.error = None
    assert api.complete(redeemed["uploadToken"]).status_code == 200


# -- the account fence -------------------------------------------------------------


def _enter_deletion(table: FakeTable, student: str = STUDENT) -> None:
    """What account deletion's first transaction writes on the fence."""
    fence = table.rows[(f"USER#{student}", "ACCOUNT_FENCE")]
    fence["status"] = "deletion_pending"


def test_a_code_dies_when_the_account_enters_deletion(monkeypatch, table) -> None:
    api = _Api(monkeypatch, table)
    issued = api.code()

    _enter_deletion(table)

    assert _refusal(api.redeem(issued["code"])) == INVALID
    assert api.rows("upload_intent") == []


def test_an_upload_in_flight_dies_when_the_account_enters_deletion(monkeypatch, table) -> None:
    api = _Api(monkeypatch, table)
    data = _png()
    issued = api.code()
    redeemed = api.redeem(issued["code"], data).json()
    api.put_parts(redeemed["uploadToken"], data, redeemed["chunkBytes"])

    _enter_deletion(table)

    assert _refusal(api.sign(redeemed["uploadToken"], 1, data)) == INVALID
    assert _refusal(api.complete(redeemed["uploadToken"])) == INVALID
    assert api.moderation.calls == []


def test_a_code_dies_when_the_account_is_suspended(monkeypatch, table) -> None:
    """Suspension leaves the fence alone and refuses sessions; the phone has none."""
    api = _Api(monkeypatch, table)
    data = _png()
    waiting = api.code()
    redeemed = api.redeem(api.code()["code"], data).json()
    api.put_parts(redeemed["uploadToken"], data, redeemed["chunkBytes"])

    api.profiles[STUDENT]["account_status"] = "suspended"

    assert _refusal(api.redeem(waiting["code"])) == INVALID
    assert _refusal(api.complete(redeemed["uploadToken"])) == INVALID
    assert api.moderation.calls == []


def test_a_code_minted_while_deletion_begins_is_taken_back(monkeypatch, table) -> None:
    """Deletion's sweep can run between the fence read and the write of the code."""
    api = _Api(monkeypatch, table)
    real_put = table.put_item

    def deletion_begins_meanwhile(**kwargs: Any):
        result = real_put(**kwargs)
        if kwargs["Item"]["PK"].startswith("UPLOADCODE#"):
            _enter_deletion(table)
        return result

    monkeypatch.setattr(table, "put_item", deletion_begins_meanwhile)

    assert api.issue().status_code == 404
    assert api.rows("upload_code") == []


def test_a_code_from_an_earlier_account_generation_is_dead(monkeypatch, table) -> None:
    api = _Api(monkeypatch, table)
    issued = api.code()

    table.rows[(f"USER#{STUDENT}", "ACCOUNT_FENCE")]["generation"] = 2

    assert _refusal(api.redeem(issued["code"])) == INVALID


def test_account_deletion_sweeps_the_students_codes(monkeypatch, table) -> None:
    api = _Api(monkeypatch, table)
    api.code()
    api.redeem(api.code()["code"])
    foreign = api.issue(FOREIGN_CONV, OTHER_STUDENT)
    assert foreign.status_code == 200
    _enter_deletion(table)

    attachment_service.purge_student_attachments(
        STUDENT, account_fence_generation=1, s3=api.s3, settings=api.settings
    )

    assert [row["student_id"] for row in api.rows("upload_code")] == [OTHER_STUDENT]


# -- the code as a secret ----------------------------------------------------------


def test_every_way_a_code_can_be_wrong_looks_the_same(monkeypatch, table) -> None:
    api = _Api(monkeypatch, table)
    used = api.code()
    api.redeem(used["code"])
    expired = api.code()
    live = api.code()
    code_id, secret = live["code"].split(".")
    flipped = secret[:-1] + ("A" if secret[-1] != "A" else "B")

    answers = {
        "used": api.redeem(used["code"]),
        "wrong secret": api.redeem(f"{code_id}.{flipped}"),
        "unknown id": api.redeem(f"{'f' * 32}.{secret}"),
        "no separator": api.redeem(secret),
        "garbage": api.redeem("x"),
        "empty": api.redeem(""),
        "trailing newline": api.redeem(live["code"] + "\n"),
    }
    api.clock.now = START + timedelta(minutes=11)
    answers["expired"] = api.redeem(expired["code"])
    api.clock.now = START
    _enter_deletion(table)
    answers["account in deletion"] = api.redeem(live["code"])

    seen = {name: _public(response) for name, response in answers.items()}
    assert set(map(repr, seen.values())) == {repr(seen["used"])}, seen
    assert seen["used"][0] == 404


def test_the_code_and_the_upload_token_are_long_random_and_never_stored(
    monkeypatch, table
) -> None:
    api = _Api(monkeypatch, table)
    data = _png()
    issued = [api.code() for _ in range(5)]
    redeemed = api.redeem(issued[0]["code"], data).json()
    api.put_parts(redeemed["uploadToken"], data, redeemed["chunkBytes"])
    api.complete(redeemed["uploadToken"])

    secrets = [item["code"].split(".", 1)[1] for item in issued]
    secrets.append(redeemed["uploadToken"].split(".", 1)[1])
    assert len(set(secrets)) == len(secrets)
    assert all(len(secret) >= 43 for secret in secrets)  # 32 random bytes, base64url
    stored = repr(list(table.rows.values()))
    for value in (*secrets, *(item["code"] for item in issued), redeemed["uploadToken"]):
        assert value not in stored
    [row] = [r for r in api.rows("upload_code") if r["code_id"] == issued[0]["codeId"]]
    assert row["secret_sha256"] == hashlib.sha256(secrets[0].encode()).hexdigest()


def test_the_secrets_never_reach_a_log(monkeypatch, table, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    api = _Api(monkeypatch, table)
    data = _png()
    issued = api.code()
    redeemed = api.redeem(issued["code"], data).json()
    api.redeem(issued["code"])  # used
    api.sign(issued["code"], 1, data)  # a code where a token belongs
    api.put_parts(redeemed["uploadToken"], data, redeemed["chunkBytes"])
    api.moderation.error = RuntimeError("rekognition down")
    api.complete(redeemed["uploadToken"])
    api.moderation.error = None
    api.complete(redeemed["uploadToken"])
    api.clock.now = START + timedelta(hours=1)
    api.complete(redeemed["uploadToken"])  # expired

    logged = "\n".join(
        f"{record.getMessage()} {record.exc_text or ''} {record.__dict__}"
        for record in caplog.records
    )
    assert caplog.records, "the refusals above are expected to log something"
    for secret in (issued["code"].split(".", 1)[1], redeemed["uploadToken"].split(".", 1)[1]):
        assert secret not in logged


def test_refused_codes_are_limited_per_source(monkeypatch, table) -> None:
    # A window shorter than a code's life, so the next window is reachable.
    settings = Settings(
        s3_images_bucket=BUCKET,
        upload_code_refusals_max_per_window=3,
        upload_code_window_seconds=300,
    )
    api = _Api(monkeypatch, table, settings=settings)
    guess = f"{'f' * 32}.{'a' * 43}"

    for _ in range(3):
        assert _refusal(api.redeem(guess)) == INVALID
    limited = api.redeem(guess)

    assert _refusal(limited) == (429, "upload_code_rate_limited")
    assert int(limited.headers["Retry-After"]) > 0
    api.clock.now = START + timedelta(seconds=settings.upload_code_window_seconds)
    assert _refusal(api.redeem(guess)) == INVALID


def test_refused_tokens_count_against_the_same_source(monkeypatch, table) -> None:
    settings = Settings(s3_images_bucket=BUCKET, upload_code_refusals_max_per_window=2)
    api = _Api(monkeypatch, table, settings=settings)
    guess = f"{'f' * 32}.{'a' * 43}"

    assert _refusal(api.sign(guess, 1, b"x")) == INVALID
    assert _refusal(api.complete(guess)) == INVALID

    assert _refusal(api.redeem(guess)) == (429, "upload_code_rate_limited")


def test_a_flood_of_bad_codes_does_not_lock_out_a_real_phone_on_the_same_address(
    monkeypatch, table
) -> None:
    """One script behind a school's NAT must not stop every phone there."""
    settings = Settings(s3_images_bucket=BUCKET, upload_code_refusals_max_per_window=3)
    api = _Api(monkeypatch, table, settings=settings)
    data = _png()
    issued = api.code()
    for _ in range(10):
        api.redeem(f"{'f' * 32}.{'a' * 43}")

    _token, completed = api.phone_upload(issued["code"], data)

    assert completed.status_code == 200, completed.text
    assert api.status(issued["codeId"]).json()["status"] == "ready"


def test_a_student_cannot_mint_codes_without_limit(monkeypatch, table) -> None:
    settings = Settings(s3_images_bucket=BUCKET, upload_code_issue_max_per_window=2)
    api = _Api(monkeypatch, table, settings=settings)

    assert [api.issue().status_code for _ in range(3)] == [200, 200, 429]
    assert len(api.rows("upload_code")) == 2
