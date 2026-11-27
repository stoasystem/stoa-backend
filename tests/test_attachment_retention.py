"""The three ways an attachment or upload leaves: delete a file, let go of a reference, clean an upload (#653).

Each acts on one row and is safe to run again; none checks a fence, the
conditional writes on the rows keep them safe (#636). Every test runs on the
shared table double (`fakes.dynamodb.FakeTable`, installed for every test) and
the S3 double (`fakes.s3.MultipartS3`, installed with `aws.install`), so a step
a fake does not implement fails instead of being skipped.

Moved here from `test_attachment_security.py` (#254); the hand-written
repository these tests used to run on is gone (#653).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from fakes.s3 import MultipartS3, b64_sha256
from stoa import aws
from stoa.aws import Kind
from stoa.config import Settings
from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo, attachment_repo
from stoa.security.attachment_errors import AttachmentDecisionError
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.services import attachment_service, learning_session, uploads
from stoa.services.attachment_service import (
    LeaveOutcome,
    delete_attachment,
    purge_student_attachments,
    release_reference,
    release_resource_attachments,
)

OWNER = "student-1"
BUCKET = "private-bucket"
SETTINGS = Settings(s3_images_bucket=BUCKET)
NOW = datetime(2026, 11, 27, tzinfo=UTC)
DATA = b"saved attachment bytes"


class _S3(MultipartS3):
    """The S3 double; `refuse_deletes` makes every delete fail and leave the object."""

    refuse_deletes = False

    def delete_object(self, **kwargs: Any) -> dict[str, Any]:
        if self.refuse_deletes:
            raise RuntimeError("provider-private-delete-failure")
        return super().delete_object(**kwargs)

    def holds(self, key: str, version: str) -> bool:
        return (key, version) in self.objects


@pytest.fixture
def s3() -> _S3:
    double = _S3(BUCKET)
    aws.install({Kind.S3: double})
    return double


@pytest.fixture
def table() -> Any:
    table = db_table.table()
    table.seed_active_account(OWNER)
    return table


def _client() -> Any:
    return aws.client(Kind.S3)


def _put_object(s3: _S3, key: str) -> tuple[str, str]:
    stored = s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=DATA,
        ContentLength=len(DATA),
        ChecksumSHA256=b64_sha256(DATA),
        Metadata={},
    )
    return stored["VersionId"], stored["ETag"]


def _file(table: Any, s3: _S3, attachment_id: str = "attachment-1", *, ref_count: int = 0) -> dict:
    """One saved file: its object in S3, its row, and its bytes on the owner's quota."""
    key = f"objects/private/{attachment_id}.txt"
    version, etag = _put_object(s3, key)
    upload = {
        "upload_id": f"upload-{attachment_id}",
        "immutable_object_key": key,
        "immutable_version_id": version,
        "immutable_etag": etag,
        "content_sha256": "a" * 64,
        "original_filename": "notes.txt",
        "detected_type": "text/plain",
        "content_length": len(DATA),
    }
    row = {
        **attachment_repo.attachment_key(attachment_id),
        **attachment_service._attachment_from_upload(
            upload, attachment_id=attachment_id, owner_id=OWNER, now=NOW
        ),
        "ref_count": ref_count,
    }
    usage = table.rows.get(("STORAGE#" + OWNER, "USAGE"))
    used = int(usage["used_bytes"]) if usage else 0
    table.seed(row, {**attachment_repo.storage_key(OWNER), "used_bytes": used + len(DATA)})
    return row


def _reference(table: Any, attachment_id: str, conversation_id: str) -> dict:
    row = {
        **attachment_repo.association_key(
            attachment_id, "conversation", conversation_id, f"message-{conversation_id}"
        ),
        "attachment_id": attachment_id,
        "owner_id": OWNER,
        "student_id": OWNER,
        "entity_type": "attachment_association",
        "resource_type": "conversation",
        "resource_id": conversation_id,
        "message_id": f"message-{conversation_id}",
        "created_at": NOW.isoformat(),
    }
    table.seed(row)
    return row


def _row(table: Any, attachment_id: str = "attachment-1") -> dict | None:
    return table.rows.get((f"ATTACHMENT#{attachment_id}", "META"))


def _used_bytes(table: Any) -> int:
    return int(table.rows[("STORAGE#" + OWNER, "USAGE")]["used_bytes"])


def _actor() -> Actor:
    return Actor(OWNER, "issuer", "subject", CanonicalRole.STUDENT, AccountStatus.ACTIVE, "student")


def _reuse(row: dict, conversation_id: str = "conversation-reuse") -> None:
    """Put a saved file into a new message, by the real reuse path."""
    message_id = f"message-{conversation_id}"
    attachment_service.bind_message_attachments(
        message_id=message_id,
        message_put=lambda ids, generation: learning_session.append(
            conversation_id,
            role="student",
            message_id=message_id,
            student_id=OWNER,
            generation=generation,
            content="this one again",
            created_at=NOW.isoformat(),
            attachment_ids=ids,
        ),
        conversation_id=conversation_id,
        actor=_actor(),
        prepared=[("attachment", row)],
        effective_plan="student",
        now=NOW,
    )


# -- delete one file ------------------------------------------------------------------------


def test_delete_takes_the_exact_version_the_row_and_the_quota_and_repeats_as_done(table, s3):
    row = _file(table, s3)

    assert delete_attachment(row, s3=_client(), settings=SETTINGS, now=NOW) is LeaveOutcome.DONE
    assert not s3.holds(row["immutable_object_key"], row["immutable_version_id"])
    assert _row(table) is None
    assert _used_bytes(table) == 0

    # Again, with the row as it was read: nothing left to do, nothing lowered twice.
    assert delete_attachment(row, s3=_client(), settings=SETTINGS, now=NOW) is LeaveOutcome.DONE
    assert _used_bytes(table) == 0


def test_delete_leaves_a_referenced_file_untouched(table, s3):
    row = _file(table, s3, ref_count=1)

    assert delete_attachment(row, s3=_client(), settings=SETTINGS, now=NOW) is LeaveOutcome.IN_USE
    assert _row(table)["status"] == "active"
    assert s3.holds(row["immutable_object_key"], row["immutable_version_id"])
    assert _used_bytes(table) == len(DATA)


def test_delete_that_stopped_part_way_carries_on_when_run_again(table, s3):
    row = _file(table, s3)
    s3.refuse_deletes = True

    assert (
        delete_attachment(row, s3=_client(), settings=SETTINGS, now=NOW)
        is LeaveOutcome.RETRYABLE
    )
    pending = _row(table)
    assert pending["status"] == "deletion_pending"
    assert s3.holds(row["immutable_object_key"], row["immutable_version_id"])
    assert _used_bytes(table) == len(DATA)

    s3.refuse_deletes = False
    # Either the stale active row or the pending one picks up where it stopped.
    assert delete_attachment(row, s3=_client(), settings=SETTINGS, now=NOW) is LeaveOutcome.DONE
    assert _row(table) is None
    assert not s3.holds(row["immutable_object_key"], row["immutable_version_id"])
    assert _used_bytes(table) == 0


def test_a_reuse_that_got_there_first_stops_the_delete(table, s3):
    read_before_the_reuse = _file(table, s3)
    _reuse(read_before_the_reuse)

    assert (
        delete_attachment(read_before_the_reuse, s3=_client(), settings=SETTINGS, now=NOW)
        is LeaveOutcome.IN_USE
    )
    assert _row(table)["status"] == "active"
    assert int(_row(table)["ref_count"]) == 1
    assert s3.holds(
        read_before_the_reuse["immutable_object_key"],
        read_before_the_reuse["immutable_version_id"],
    )


def test_a_delete_that_got_there_first_refuses_the_reuse(table, s3):
    row = _file(table, s3)
    s3.refuse_deletes = True
    assert (
        delete_attachment(row, s3=_client(), settings=SETTINGS, now=NOW)
        is LeaveOutcome.RETRYABLE
    )

    with pytest.raises(AttachmentDecisionError):
        _reuse(row)
    assert _row(table)["status"] == "deletion_pending"
    assert int(_row(table)["ref_count"]) == 0


def test_the_owner_route_answers_in_use_and_deleted(table, s3):
    referenced = _file(table, s3, "attachment-held", ref_count=1)
    with pytest.raises(AttachmentDecisionError) as refused:
        attachment_service.delete_saved_attachment(referenced, s3=_client(), settings=SETTINGS)
    assert refused.value.code.value == "attachment_in_use"

    free = _file(table, s3, "attachment-free")
    result = attachment_service.delete_saved_attachment(free, s3=_client(), settings=SETTINGS)
    assert result.status.value == "deleted"


# -- let go of one reference ----------------------------------------------------------------


def test_releasing_keeps_a_file_another_reference_holds_and_deletes_it_with_the_last(table, s3):
    row = _file(table, s3, ref_count=2)
    first = _reference(table, "attachment-1", "conversation-1")
    second = _reference(table, "attachment-1", "conversation-2")

    assert release_reference(first, s3=_client(), settings=SETTINGS, now=NOW) is LeaveOutcome.DONE
    assert int(_row(table)["ref_count"]) == 1
    assert s3.holds(row["immutable_object_key"], row["immutable_version_id"])

    # The same reference again lowers nothing a second time.
    assert release_reference(first, s3=_client(), settings=SETTINGS, now=NOW) is LeaveOutcome.DONE
    assert int(_row(table)["ref_count"]) == 1

    assert release_reference(second, s3=_client(), settings=SETTINGS, now=NOW) is LeaveOutcome.DONE
    assert _row(table) is None
    assert not s3.holds(row["immutable_object_key"], row["immutable_version_id"])
    assert _used_bytes(table) == 0
    assert release_reference(second, s3=_client(), settings=SETTINGS, now=NOW) is LeaveOutcome.DONE


def test_a_last_release_that_stopped_part_way_is_finished_by_either_row(table, s3):
    row = _file(table, s3, ref_count=1)
    reference = _reference(table, "attachment-1", "conversation-1")
    s3.refuse_deletes = True

    assert (
        release_reference(reference, s3=_client(), settings=SETTINGS, now=NOW)
        is LeaveOutcome.RETRYABLE
    )
    assert table.rows.get((reference["PK"], reference["SK"])) is None
    assert _row(table)["status"] == "deletion_pending"

    s3.refuse_deletes = False
    assert release_reference(reference, s3=_client(), settings=SETTINGS, now=NOW) is LeaveOutcome.DONE
    assert _row(table) is None
    assert not s3.holds(row["immutable_object_key"], row["immutable_version_id"])
    assert _used_bytes(table) == 0


def test_a_reuse_between_the_read_and_the_release_keeps_the_file(table, s3, monkeypatch):
    row = _file(table, s3, ref_count=1)
    reference = _reference(table, "attachment-1", "conversation-1")
    read = attachment_repo.get_attachment
    raced: list[bool] = []

    def read_then_reuse(attachment_id: str, **kwargs: Any) -> Any:
        current = read(attachment_id, **kwargs)
        if not raced:
            raced.append(True)
            _reuse(dict(current))
        return current

    monkeypatch.setattr(attachment_repo, "get_attachment", read_then_reuse)
    # It read one reference, so it would have been the last; the count moved.
    assert (
        release_reference(reference, s3=_client(), settings=SETTINGS, now=NOW)
        is LeaveOutcome.RETRYABLE
    )
    monkeypatch.setattr(attachment_repo, "get_attachment", read)
    assert _row(table)["status"] == "active"
    assert int(_row(table)["ref_count"]) == 2
    assert table.rows.get((reference["PK"], reference["SK"])) is not None

    assert release_reference(reference, s3=_client(), settings=SETTINGS, now=NOW) is LeaveOutcome.DONE
    assert _row(table)["status"] == "active"
    assert int(_row(table)["ref_count"]) == 1
    assert s3.holds(row["immutable_object_key"], row["immutable_version_id"])


def test_a_reference_whose_file_is_gone_is_simply_deleted(table, s3):
    reference = _reference(table, "attachment-gone", "conversation-1")

    assert release_reference(reference, s3=_client(), settings=SETTINGS, now=NOW) is LeaveOutcome.DONE
    assert table.rows.get((reference["PK"], reference["SK"])) is None


# -- the old per-resource release and account purge, now made of the actions ---------------


def test_resource_release_and_purge_run_on_the_actions(table, s3):
    row = _file(table, s3, ref_count=2)
    _reference(table, "attachment-1", "conversation-1")
    _reference(table, "attachment-1", "conversation-2")

    first = release_resource_attachments(
        OWNER, "conversation", "conversation-1", s3=_client(), settings=SETTINGS
    )
    assert first == {"released": 1, "deleted": 0}
    assert first.disposition.value == "complete"
    second = release_resource_attachments(
        OWNER, "conversation", "conversation-2", s3=_client(), settings=SETTINGS
    )
    assert second == {"released": 1, "deleted": 1}
    assert not s3.holds(row["immutable_object_key"], row["immutable_version_id"])
    assert purge_student_attachments(OWNER, s3=_client(), settings=SETTINGS) == {
        "released": 0,
        "deleted": 0,
    }


def test_the_account_purge_deletes_every_file_and_upload_and_is_safe_to_repeat(table, s3):
    held = _file(table, s3, "attachment-held", ref_count=1)
    _reference(table, "attachment-held", "conversation-1")
    free = _file(table, s3, "attachment-free")
    upload = _consumed_upload(table, held)
    table.seed({**account_deletion_repo.account_fence_key(OWNER), "status": "deletion_pending",
                "generation": 1})

    result = purge_student_attachments(
        OWNER, account_fence_generation=1, s3=_client(), settings=SETTINGS
    )
    assert result.status.value == "complete", result.debt_counts
    assert result == {"released": 1, "deleted": 2}
    for gone in (held, free):
        assert _row(table, gone["attachment_id"]) is None
    assert table.rows.get((upload["PK"], upload["SK"])) is None
    assert s3.objects == {}
    assert ("STORAGE#" + OWNER, "USAGE") not in table.rows

    again = purge_student_attachments(
        OWNER, account_fence_generation=1, s3=_client(), settings=SETTINGS
    )
    assert again.status.value == "complete"
    assert again == {"released": 0, "deleted": 0}


# -- clean one upload -----------------------------------------------------------------------


def _consumed_upload(table: Any, attachment: dict, **extra: Any) -> dict:
    """The upload `attachment` was made from, as spending it left it."""
    row = {
        "PK": f"UPLOAD#{attachment['source_upload_id']}",
        "SK": "META",
        "entity_type": "upload_intent",
        "upload_id": attachment["source_upload_id"],
        "owner_id": OWNER,
        "student_id": OWNER,
        "status": "consumed",
        "version": 6,
        "expected_kind": "conversation_attachment",
        "immutable_object_key": attachment["immutable_object_key"],
        "immutable_version_id": attachment["immutable_version_id"],
        "immutable_etag": attachment["immutable_etag"],
        "content_sha256": attachment["content_sha256"],
        "content_length": attachment["content_length"],
        "durable_attachment_id": attachment["attachment_id"],
        "created_at": NOW.isoformat(),
        **extra,
    }
    table.seed(row)
    return row


def _closing(table: Any, generation: int = 3) -> int:
    table.seed({**account_deletion_repo.account_fence_key(OWNER), "status": "deletion_pending",
                "generation": generation})
    return generation


def test_an_upload_whose_attachment_is_there_is_left_for_the_attachment(table, s3):
    attachment = _file(table, s3)
    upload = _consumed_upload(table, attachment)
    generation = _closing(table)

    outcome = uploads.cleanup(
        upload, s3=_client(), settings=SETTINGS, now=NOW, account_fence_generation=generation
    )
    assert outcome == "protected"
    assert table.rows[(upload["PK"], "META")]["status"] == "consumed"
    assert table.rows[(upload["PK"], "META")]["durable_attachment_id"] == "attachment-1"
    assert s3.holds(attachment["immutable_object_key"], attachment["immutable_version_id"])


def test_an_upload_whose_attachment_is_gone_is_cleaned_with_its_staging_debt(table, s3):
    attachment = _file(table, s3)
    staging_version, staging_etag = _put_object(s3, "staging/upload-attachment-1")
    upload = _consumed_upload(
        table,
        attachment,
        staging_object_key="staging/upload-attachment-1",
        staging_version_id=staging_version,
        staging_etag=staging_etag,
        staging_cleanup_status="pending",
    )
    generation = _closing(table)
    assert delete_attachment(attachment, s3=_client(), settings=SETTINGS, now=NOW) is LeaveOutcome.DONE

    s3.refuse_deletes = True
    first = uploads.cleanup(
        upload, s3=_client(), settings=SETTINGS, now=NOW, account_fence_generation=generation
    )
    assert first == "retryable"
    assert s3.holds("staging/upload-attachment-1", staging_version)

    s3.refuse_deletes = False
    current = table.rows[(upload["PK"], "META")]
    assert uploads.cleanup(
        current, s3=_client(), settings=SETTINGS, now=NOW, account_fence_generation=generation
    ) == "deleted"
    cleaned = table.rows[(upload["PK"], "META")]
    assert cleaned["status"] == "cleanup_complete"
    assert "staging_cleanup_status" not in cleaned
    assert s3.objects == {}
    assert uploads.cleanup(
        cleaned, s3=_client(), settings=SETTINGS, now=NOW, account_fence_generation=generation
    ) == "deleted"


def test_the_sweep_cleans_an_upload_whose_attachment_is_gone(table, s3):
    """A pointer to an attachment no longer there no longer blocks the sweep."""
    attachment = _file(table, s3)
    upload = _consumed_upload(table, attachment, status="invalid")
    assert delete_attachment(attachment, s3=_client(), settings=SETTINGS, now=NOW) is LeaveOutcome.DONE

    assert uploads.cleanup(upload, s3=_client(), settings=SETTINGS, now=NOW) == "deleted"
    assert table.rows[(upload["PK"], "META")]["status"] == "cleanup_complete"


def test_the_sweep_still_blocks_an_upload_whose_attachment_is_there(table, s3):
    attachment = _file(table, s3)
    upload = _consumed_upload(table, attachment, status="invalid")

    assert uploads.cleanup(upload, s3=_client(), settings=SETTINGS, now=NOW) == "protected"
    assert table.rows[(upload["PK"], "META")]["status"] == "cleanup_blocked"
    assert s3.holds(attachment["immutable_object_key"], attachment["immutable_version_id"])


def test_settling_staging_debt_no_longer_fails_on_a_missing_argument(table, s3):
    """`settle_staging_debts` called `_reconcile_staging_cleanup_debt` without `repository=`."""
    staging_version, staging_etag = _put_object(s3, "staging/upload-validated")
    table.seed(
        {
            "PK": "UPLOAD#upload-validated",
            "SK": "META",
            "entity_type": "upload_intent",
            "upload_id": "upload-validated",
            "owner_id": OWNER,
            "student_id": OWNER,
            "status": "validated",
            "version": 4,
            "staging_object_key": "staging/upload-validated",
            "staging_version_id": staging_version,
            "staging_etag": staging_etag,
            "staging_cleanup_status": "pending",
            "created_at": NOW.isoformat(),
        }
    )

    assert uploads.settle_staging_debts(OWNER, s3=_client(), settings=SETTINGS)
    assert not s3.holds("staging/upload-validated", staging_version)
    assert "staging_cleanup_status" not in table.rows[("UPLOAD#upload-validated", "META")]
