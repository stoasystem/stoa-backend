"""A question's attachments are bound to its message in one transaction (#254).

A student's message may carry fresh uploads (`{"uploadId": ...}`) and saved
attachments (`{"attachmentId": ...}`). Binding them spends each upload
(`uploads.consume_operation`), writes the attachment it becomes, takes a
reference on each saved one, links every attachment to the message and charges
the student's storage for the fresh bytes - all in the transaction that writes
the message and the question's command, or not at all.

These used to run against a hand-written repository that recorded the
operations it was handed, so they asserted on what the double wrote down about
itself. Here the question is sent through its own entry (`ask_question.submit`,
via the shared setup in `fakes.ask_question`), the uploads are made through the
real `uploads.start` / `sign_part` / `complete` on `fakes.s3.MultipartS3`, and
every row lives on the shared `FakeTable`. A failure is injected into the table
double - it cancels the message's transaction, refuses it, or lets another
request change a row first - never into the code under test. What is asserted is
what the table holds afterwards and the error the student got.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
import hashlib
from typing import Any

from botocore.exceptions import ClientError
import pytest

from fakes.ask_question import CONV, STUDENT, _actor, _command_row, _commit
from fakes.ask_question import _no_memory_personalisation  # noqa: F401 - the fixture
from fakes.ask_question import _parser_in_process  # noqa: F401 - the fixture
from fakes.ask_question import table as table  # noqa: F401 - the fixture
from fakes.dynamodb import FakeTable, transaction_canceled, from_wire, to_wire
from fakes.rekognition import FakeRekognition
from fakes.s3 import MultipartS3
from stoa.config import FREE_STORAGE_BYTES, Settings
from stoa.db.repositories import attachment_repo
from stoa.models.attachment import (
    UploadIntentRequest,
    UploadPartUrlRequest,
    UploadPurpose,
)
from stoa.security.attachment_errors import (
    ATTACHMENT_ERROR_REGISTRY,
    AttachmentClientAction,
    AttachmentDecisionError,
    AttachmentErrorCode,
)
from stoa.security.identity import Actor
from stoa.services import uploads
from stoa.services.uploads import _store as upload_store

BUCKET = "private-bucket-canary"
SETTINGS = Settings(s3_images_bucket=BUCKET)
NOTES = "Aufgabe 4: Berechne 1/2 + 1/4.".encode()
FOREIGN = "foreign-student-canary"


# ── Uploads, made the way the browser makes them ────────────────────────────


@pytest.fixture
def s3() -> MultipartS3:
    return MultipartS3(BUCKET)


def _issue_and_put(
    s3: MultipartS3,
    data: bytes,
    *,
    actor: Actor,
    filename: str,
    content_type: str,
) -> str:
    """An upload issued to `actor` with its one part on S3; its id."""
    intent = uploads.start(
        UploadIntentRequest(
            purpose=UploadPurpose.CONVERSATION_ATTACHMENT,
            filename=filename,
            contentType=content_type,
            sizeBytes=len(data),
        ),
        actor,
        s3=s3,
        settings=SETTINGS,
    )
    upload_id = intent["uploadId"]
    signed = uploads.sign_part(
        upload_id,
        1,
        UploadPartUrlRequest(sizeBytes=len(data), checksumSha256=hashlib.sha256(data).hexdigest()),
        actor,
        signer=s3,
        settings=SETTINGS,
    )
    assert s3.browser_put(signed["url"], signed["method"], signed["headers"], data) == 200
    return upload_id


def _upload(
    s3: MultipartS3,
    data: bytes = NOTES,
    *,
    actor: Actor | None = None,
    filename: str = "notes.txt",
    content_type: str = "text/plain",
) -> str:
    """A whole upload, issued, put and completed: validated and ready; its id."""
    actor = actor or _actor()
    upload_id = _issue_and_put(s3, data, actor=actor, filename=filename, content_type=content_type)
    completed = uploads.complete(
        upload_id, 1, actor, s3=s3, settings=SETTINGS, moderation=FakeRekognition()
    )
    assert completed["status"] == "validated", completed
    return upload_id


# ── Sending the question ─────────────────────────────────────────────────────


def _send(key: str, *references: dict[str, str]):
    """Store the student's message with `references`, leaving the answer to the worker."""
    return _commit(key, content="Kannst du mir helfen?", attachmentIds=list(references))


def _refused(key: str, *references: dict[str, str]) -> AttachmentDecisionError:
    with pytest.raises(AttachmentDecisionError) as refused:
        _send(key, *references)
    return refused.value


def _fresh(upload_id: str) -> dict[str, str]:
    return {"uploadId": upload_id}


def _saved(attachment_id: str) -> dict[str, str]:
    return {"attachmentId": attachment_id}


def _earlier_attachment(s3: MultipartS3, key: str = "earlier") -> str:
    """An attachment the student sent with an earlier message, now saved; its id."""
    accepted = _send(key, _fresh(_upload(s3, b"Meine fruehere Rechnung.", filename="saved.txt")))
    [attachment] = accepted.studentMessage.attachments
    return attachment.attachment_id


# ── What the table holds ─────────────────────────────────────────────────────


def _upload_row(table: FakeTable, upload_id: str) -> dict[str, Any]:
    return table.rows[tuple(upload_store.upload_key(upload_id).values())]


def _attachment(table: FakeTable, attachment_id: str) -> dict[str, Any] | None:
    return table.rows.get(tuple(attachment_repo.attachment_key(attachment_id).values()))


def _associations(table: FakeTable) -> list[dict[str, Any]]:
    return [row for row in table.rows.values() if row.get("entity_type") == "attachment_association"]


def _storage_used(table: FakeTable) -> int:
    return attachment_repo.get_storage_usage(STUDENT, table=table)


def _set_storage_used(table: FakeTable, used_bytes: int) -> None:
    table.seed({**attachment_repo.storage_key(STUDENT), "used_bytes": used_bytes})


def _student_message(table: FakeTable, key: str) -> dict[str, Any] | None:
    """The student message the question under `key` wrote, if it wrote one."""
    message_id = _command_row(table, key)["student_message_id"]
    return next(
        (
            row
            for (pk, _sk), row in table.rows.items()
            if pk == f"CONV#{CONV}" and row.get("message_id") == message_id
        ),
        None,
    )


def _attachment_state(table: FakeTable) -> dict[tuple[str, str], dict[str, Any]]:
    """Every row a binding writes or changes: uploads, attachments, links, storage, messages."""
    return deepcopy(
        {
            key: row
            for key, row in table.rows.items()
            if key[0].startswith(("UPLOAD#", "ATTACHMENT#", "STORAGE#"))
            or (key[0] == f"CONV#{CONV}" and row.get("role") == "student")
        }
    )


# ── Faults, injected into the table ──────────────────────────────────────────


def _binds(operations: list[dict[str, Any]]) -> bool:
    """Whether this is the transaction that binds a message's attachments."""
    return any(
        str((body.get("Key") or body.get("Item") or {}).get("PK", "")).startswith(
            ("UPLOAD#", "ATTACHMENT#")
        )
        for operation in operations
        for body in operation.values()
    )


def _on_binding(
    monkeypatch: pytest.MonkeyPatch,
    table: FakeTable,
    fault: Callable[[list[dict[str, Any]]], None],
    *,
    times: int | None = 1,
) -> None:
    """Have the table run `fault(operations)` before it judges the binding transaction.

    The fault may change rows first, as another request would, or raise as the
    table would. It runs for the first `times` binding transactions (all, if `None`).
    """
    write = table.transact_write_items
    remaining = [times]

    def faulty(*, TransactItems: list[dict[str, Any]]) -> None:  # noqa: N803
        operations = from_wire(TransactItems)
        if _binds(operations) and (remaining[0] is None or remaining[0] > 0):
            if remaining[0] is not None:
                remaining[0] -= 1
            fault(operations)
        write(TransactItems=TransactItems)

    monkeypatch.setattr(table, "transact_write_items", faulty)


def _throttled(_operations: list[dict[str, Any]]) -> None:
    raise ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "Amazon DynamoDB provider-canary"}},
        "TransactWriteItems",
    )


def _cancelled_at(picks: Callable[[str, dict[str, Any]], bool]):
    """The table cancels the transaction: the operation `picks` chooses failed its condition."""

    def fault(operations: list[dict[str, Any]]) -> None:
        reasons = [
            "ConditionalCheckFailed" if any(picks(kind, body) for kind, body in operation.items()) else "None"
            for operation in operations
        ]
        assert "ConditionalCheckFailed" in reasons
        raise transaction_canceled(reasons)

    return fault


def _references_saved(kind: str, body: dict[str, Any]) -> bool:
    return kind == "Update" and "ref_count" in str(body.get("UpdateExpression"))


# ── Before any effect: what the question may not carry ──────────────────────


@pytest.mark.parametrize("case", ["missing", "foreign", "invalid", "spent"])
def test_prepare_message_attachments_conceals_missing_foreign_and_invalid_as_no_effect(
    table, s3, case
) -> None:
    """An upload the student cannot send is refused as missing, before anything is written.

    Invalid is a completion that failed validation; spent is an upload an
    earlier message already turned into its attachment.
    """
    if case == "missing":
        upload_id = "upload-never-issued"
    elif case == "foreign":
        table.seed_active_account(FOREIGN)
        upload_id = _upload(s3, actor=_actor(user_id=FOREIGN))
    elif case == "spent":
        upload_id = _upload(s3)
        _send("key-earlier", _fresh(upload_id))
        assert _upload_row(table, upload_id)["status"] == "consumed"
    else:
        upload_id = _issue_and_put(
            s3, b"not a png", actor=_actor(), filename="work.png", content_type="image/png"
        )
        with pytest.raises(AttachmentDecisionError):
            uploads.complete(
                upload_id, 1, _actor(), s3=s3, settings=SETTINGS, moderation=FakeRekognition()
            )
        assert _upload_row(table, upload_id)["status"] == "invalid"
    before = deepcopy(table.rows)

    refused = _refused("key-concealed", _fresh(upload_id))

    assert refused.code is AttachmentErrorCode.UPLOAD_NOT_FOUND
    assert FOREIGN not in str(refused.public_body())
    # Refused before the command was claimed: nothing at all was written.
    assert table.rows == before


def test_association_rejects_legacy_key_only_records_before_effects(table, s3) -> None:
    """An upload row from before immutable promotion names a client-writable key only."""
    upload_id = _upload(s3)
    legacy = dict(_upload_row(table, upload_id))
    legacy["object_key"] = "legacy/client-writable-key"
    for field in (
        "immutable_object_key",
        "immutable_version_id",
        "immutable_etag",
        "content_sha256",
    ):
        legacy.pop(field, None)
    table.seed(legacy)
    before = deepcopy(table.rows)

    refused = _refused("key-legacy", _fresh(upload_id))

    assert refused.code is AttachmentErrorCode.UPLOAD_NOT_FOUND
    assert table.rows == before


# ── One transaction ──────────────────────────────────────────────────────────


def test_fresh_and_reused_message_attachments_share_one_atomic_transaction(
    table, s3, monkeypatch
) -> None:
    saved_id = _earlier_attachment(s3)
    upload_id = _upload(s3, b"x" * 321, filename="notes.txt")
    used_before = _storage_used(table)
    # The saved attachment's reference is refused once: the fresh upload, in
    # the same transaction, must not be spent without it.
    _on_binding(monkeypatch, table, _cancelled_at(_references_saved))
    before = _attachment_state(table)

    refused = _refused("key-refused", _fresh(upload_id), _saved(saved_id))

    assert refused.code is AttachmentErrorCode.UPLOAD_NOT_FOUND
    assert _attachment_state(table) == before
    assert _upload_row(table, upload_id)["status"] == "validated"

    accepted = _send("key-both", _fresh(upload_id), _saved(saved_id))

    message = _student_message(table, "key-both")
    assert message is not None
    fresh_id, reused_id = message["attachment_ids"]
    assert reused_id == saved_id
    consumed = _upload_row(table, upload_id)
    assert consumed["status"] == "consumed"
    assert consumed["durable_attachment_id"] == fresh_id
    fresh = _attachment(table, fresh_id)
    assert fresh is not None
    assert (fresh["owner_id"], fresh["status"], fresh["content_length"]) == (STUDENT, "active", 321)
    assert _attachment(table, saved_id)["ref_count"] == 2
    assert {
        (row["attachment_id"], row["message_id"])
        for row in _associations(table)
        if row["message_id"] == message["message_id"]
    } == {(fresh_id, message["message_id"]), (saved_id, message["message_id"])}
    # Only the fresh bytes are charged.
    assert _storage_used(table) == used_before + 321
    public = accepted.model_dump_json()
    assert [item.attachment_id for item in accepted.studentMessage.attachments] == [
        fresh_id,
        saved_id,
    ]
    assert "objects/" not in public
    assert BUCKET not in public
    assert fresh["immutable_version_id"] not in public


def _quota_race(table: FakeTable) -> None:
    """Another message charged the student's storage up to the limit first."""
    _set_storage_used(table, FREE_STORAGE_BYTES - 1)


def _spent_elsewhere(table: FakeTable, upload_id: str) -> None:
    """Another message spent the upload first."""
    table.seed({**_upload_row(table, upload_id), "status": "consumed"})


def _deleted_elsewhere(table: FakeTable, attachment_id: str) -> None:
    """The student deleted the saved attachment from another device first."""
    table.seed({**(_attachment(table, attachment_id) or {}), "status": "deletion_pending"})


@pytest.mark.parametrize(
    "path,race,code,action,status",
    [
        (
            "message_fresh",
            "quota",
            AttachmentErrorCode.STORAGE_QUOTA_EXCEEDED,
            AttachmentClientAction.DELETE_OR_UPGRADE,
            409,
        ),
        (
            "message_fresh",
            "dependency",
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE,
            AttachmentClientAction.RETRY_LATER,
            503,
        ),
        (
            "message_fresh",
            "conflict",
            AttachmentErrorCode.UPLOAD_NOT_FOUND,
            AttachmentClientAction.SELECT_FILE,
            404,
        ),
        (
            "message_reuse",
            "dependency",
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE,
            AttachmentClientAction.RETRY_LATER,
            503,
        ),
        (
            "message_reuse",
            "conflict",
            AttachmentErrorCode.UPLOAD_NOT_FOUND,
            AttachmentClientAction.SELECT_FILE,
            404,
        ),
    ],
)
def test_transaction_quota_race_dependency_cancellation_is_zero_effect_and_stable_error(
    table, s3, monkeypatch, path, race, code, action, status
) -> None:
    """Whatever refuses the message's transaction, nothing of it lands.

    Each refusal is the table's own answer: a quota race is another message
    charging the student's storage between the check and the write; a
    conflict is the upload spent, or the saved attachment deleted, by another
    request first; a dependency is the table refusing the request. Reusing a
    saved attachment charges no storage, so a reuse has no quota race.
    """
    fresh = path == "message_fresh"
    if fresh:
        upload_id = _upload(s3, b"y" * 1234, filename="race.txt")
        reference = _fresh(upload_id)
    else:
        saved_id = _earlier_attachment(s3)
        reference = _saved(saved_id)
    _set_storage_used(table, 1234)
    raced: list[dict[tuple[str, str], dict[str, Any]]] = []

    def refuse(operations: list[dict[str, Any]]) -> None:
        if race == "quota":
            _quota_race(table)
        elif race == "conflict" and fresh:
            _spent_elsewhere(table, upload_id)
        elif race == "conflict":
            _deleted_elsewhere(table, saved_id)
        raced.append(_attachment_state(table))
        if race == "dependency":
            _throttled(operations)

    _on_binding(monkeypatch, table, refuse, times=None)

    refused = _refused("key-zero-effect", reference)

    assert refused.code is code
    contract = ATTACHMENT_ERROR_REGISTRY[code]
    assert contract.http_status == status
    assert contract.client_action is action
    # What the other request changed stands; nothing of this message moved.
    [state] = raced
    assert _attachment_state(table) == state
    assert _student_message(table, "key-zero-effect") is None
    public = refused.public_body()
    assert set(public) == {"code", "message", "correlationId"}
    assert public["code"] == code.value
    for canary in (STUDENT, "objects/", "immutable-version", BUCKET, "Amazon", "provider-canary"):
        assert canary not in str(public)


def test_saved_attachment_reuse_does_not_mutate_storage_usage(table, s3) -> None:
    saved_id = _earlier_attachment(s3)
    # The student is at the limit: a reuse adds no bytes, so it still goes through.
    _set_storage_used(table, FREE_STORAGE_BYTES)

    _send("key-reuse", _saved(saved_id))

    assert _storage_used(table) == FREE_STORAGE_BYTES
    assert _student_message(table, "key-reuse")["attachment_ids"] == [saved_id]
    assert _attachment(table, saved_id)["ref_count"] == 2


# ── The attachment ids a question decides for its fresh uploads ─────────────


def test_deterministic_fresh_attachment_ids_preserve_exact_order_and_keys(table, s3) -> None:
    saved_id = _earlier_attachment(s3)
    first = _upload(s3, b"erste Seite", filename="one.txt")
    second = _upload(s3, b"zweite Seite", filename="two.txt")

    accepted = _send("key-deterministic", _fresh(first), _saved(saved_id), _fresh(second))

    command = _command_row(table, "key-deterministic")
    expected = command["deterministic_attachment_ids"]
    assert len(expected) == 2
    message = _student_message(table, "key-deterministic")
    assert message["attachment_ids"] == [expected[0], saved_id, expected[1]]
    assert [item.attachment_id for item in accepted.studentMessage.attachments] == message[
        "attachment_ids"
    ]
    assert _upload_row(table, first)["durable_attachment_id"] == expected[0]
    assert _upload_row(table, second)["durable_attachment_id"] == expected[1]
    assert all(_attachment(table, value) is not None for value in expected)
    assert {
        (row["PK"], row["SK"])
        for row in _associations(table)
        if row["message_id"] == command["student_message_id"]
    } == {
        tuple(
            attachment_repo.association_key(
                value, "conversation", CONV, command["student_message_id"]
            ).values()
        )
        for value in message["attachment_ids"]
    }


@pytest.mark.parametrize(
    "supplied",
    [[], ["one", "two"], [""], ["   "], [None]],
)
def test_deterministic_fresh_attachment_id_cardinality_fails_before_effects(
    table, s3, monkeypatch, supplied: list[str | None]
) -> None:
    """A stored command whose fresh ids do not fit its uploads is not bound.

    The first attempt is refused by the table and leaves the command claimed;
    the stored command is then damaged, and the resumed attempt must stop
    before it writes anything with ids that are not one per upload.
    """
    upload_id = _upload(s3)
    _on_binding(monkeypatch, table, _throttled)
    assert _refused("key-cardinality", _fresh(upload_id)).code is (
        AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
    )
    command = dict(_command_row(table, "key-cardinality"))
    assert command["status"] == "claimed"
    command["deterministic_attachment_ids"] = list(supplied)
    table.seed(command)
    before = deepcopy(table.rows)

    refused = _refused("key-cardinality", _fresh(upload_id))

    assert refused.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
    assert table.rows == before
    assert _upload_row(table, upload_id)["status"] == "validated"


def test_saved_reuse_consumes_no_deterministic_fresh_id(table, s3) -> None:
    saved_id = _earlier_attachment(s3)
    upload_id = _upload(s3)

    _send("key-saved-first", _saved(saved_id), _fresh(upload_id))

    [only_fresh_id] = _command_row(table, "key-saved-first")["deterministic_attachment_ids"]
    assert _student_message(table, "key-saved-first")["attachment_ids"] == [
        saved_id,
        only_fresh_id,
    ]
    assert _upload_row(table, upload_id)["durable_attachment_id"] == only_fresh_id


@pytest.mark.parametrize("applied", [False, True], ids=["refused", "applied-response-lost"])
def test_lost_transaction_retry_rebuilds_identical_attachment_and_association_keys(
    table, s3, monkeypatch, applied: bool
) -> None:
    """A retry of a lost transaction writes the same attachment and link, never a second.

    Refused, nothing landed and the retry must land it under the ids the first
    attempt chose. Applied with its response lost, the retry must find the
    message already written and add nothing.
    """
    upload_id = _upload(s3, b"z" * 77, filename="lost.txt")
    used_before = _storage_used(table)
    write = table.transact_write_items

    def lose(operations: list[dict[str, Any]]) -> None:
        if applied:
            write(TransactItems=to_wire(operations))
        _throttled(operations)

    _on_binding(monkeypatch, table, lose)

    if applied:
        # The request reads its own command back, finds the message written
        # and goes on from there; the student is not told of the lost response.
        _send("key-lost", _fresh(upload_id))
    else:
        assert _refused("key-lost", _fresh(upload_id)).code is (
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
        )
        assert _student_message(table, "key-lost") is None
    [chosen] = _command_row(table, "key-lost")["deterministic_attachment_ids"]
    # The student sends it again, with the same key.
    accepted = _send("key-lost", _fresh(upload_id))

    message = _student_message(table, "key-lost")
    assert message["attachment_ids"] == [chosen]
    assert [item.attachment_id for item in accepted.studentMessage.attachments] == [chosen]
    assert _upload_row(table, upload_id)["durable_attachment_id"] == chosen
    attachments = [
        key for key, row in table.rows.items() if row.get("entity_type") == "attachment"
    ]
    assert attachments == [tuple(attachment_repo.attachment_key(chosen).values())]
    assert [(row["PK"], row["SK"]) for row in _associations(table)] == [
        tuple(
            attachment_repo.association_key(
                chosen, "conversation", CONV, message["message_id"]
            ).values()
        )
    ]
    assert _storage_used(table) == used_before + 77
