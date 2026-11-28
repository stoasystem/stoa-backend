"""Account deletion in three steps, every row handled as the data type catalog says (#641).

A deletion accepted now carries the catalog's hash and runs
`stoa.services.account_deletion_flow`: lock the account, handle every row of
its partitions as its catalog entry says - pass after pass until one finds
nothing - and wait for deliveries a sender still holds. These tests run the
real repositories against the shared table double, with S3 and Cognito
doubles, through the scheduled job.

Two of the rows are the shapes the production comparison (#640, 2026-11-28)
found the old branches stuck on: a teacher's mention in a notification whose
realtime delivery attempts hold a `target_count`, which the table returns as a
`Decimal`; and a moderation case whose question is already gone.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from typing import Any

import pytest

from fakes.dynamodb import FakeTable, as_stored
from fakes.s3 import MultipartS3, b64_sha256
from stoa import aws, config
from stoa.aws import Kind
from stoa.config import Settings
from stoa.db import data_catalog, owner_registry
from stoa.db import table as db_table
from stoa.db.repositories import (
    account_deletion_repo,
    account_email_claim_repo,
    attachment_repo,
    notification_repo,
)
from stoa.jobs import account_deletion as job
from stoa.services import account_deletion_flow as flow
from stoa.services import account_deletion_service as service
from stoa.services import attachment_service, owner_registry_sweep

STUDENT = "student-a6"
TEACHER = "teacher-a9"
PARENT = "parent-p1"
OTHER_STUDENT = "student-b2"
BUCKET = "private-bucket"
EMAIL = "leaving.student@stoa.test"
DATA = b"saved attachment bytes"


def _now() -> datetime:
    return datetime.now(UTC)


# -- doubles and arrangement -----------------------------------------------------------


class _Cognito:
    """The sign-in provider: records each call; a user it deleted is not found again."""

    class exceptions:
        class UserNotFoundException(Exception):
            pass

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.deleted: set[str] = set()

    def admin_user_global_sign_out(self, *, UserPoolId: str, Username: str) -> dict:  # noqa: N803
        self.calls.append(("sign_out", Username))
        if Username in self.deleted:
            raise self.exceptions.UserNotFoundException(Username)
        return {}

    def admin_delete_user(self, *, UserPoolId: str, Username: str) -> dict:  # noqa: N803
        self.calls.append(("delete", Username))
        self.deleted.add(Username)
        return {}


class _S3(MultipartS3):
    def holds(self, key: str, version: str) -> bool:
        return (key, version) in self.objects


@pytest.fixture
def s3() -> _S3:
    return _S3(BUCKET)


@pytest.fixture
def cognito() -> _Cognito:
    return _Cognito()


@pytest.fixture
def table(s3: _S3, cognito: _Cognito) -> FakeTable:
    config.install(Settings(s3_images_bucket=BUCKET, cognito_user_pool_id="pool-test"))
    aws.install({Kind.S3: s3, Kind.COGNITO: cognito})
    built = db_table.table()
    _sweep_vouches(built)
    return built


def _sweep_vouches(table: FakeTable, *, when: datetime | None = None) -> None:
    """The daily registry sweep's last result: a whole walk, nothing missing."""
    table.seed(
        {
            **owner_registry_sweep.RUN_MARKER_KEY,
            "complete": True,
            "missing_registrations": 0,
            "completed_at": (when or _now()).isoformat(),
        }
    )


def _seed(table: FakeTable, *rows: dict[str, Any]) -> None:
    """Rows as their writers leave them: each partition registered for whom the catalog says."""
    table.seed(*rows)
    for row in rows:
        for account, role in data_catalog.mentions(row).items():
            if not owner_registry.is_derived_for(row["PK"], account):
                table.seed(owner_registry.registry_item(account, row["PK"], role))


def _account(table: FakeTable, user_id: str, role: str, **profile: Any) -> None:
    _seed(
        table,
        {
            "PK": f"USER#{user_id}",
            "SK": "PROFILE",
            "user_id": user_id,
            "role": role,
            "account_status": "active",
            "created_at": "2026-09-01T00:00:00+00:00",
            "version": 1,
            **profile,
        }
    )
    table.seed(
        {
            "PK": f"USER#{user_id}", "SK": "ACCOUNT_FENCE", "entity_type": "account_fence",
            "user_id": user_id, "status": "active", "generation": 1, "version": 1,
        }
    )


def _identity(table: FakeTable, user_id: str, subject: str) -> None:
    binding_pk = f"IDENTITY#issuer-hash#{subject}"
    _seed(
        table,
        {
            "PK": binding_pk, "SK": "BINDING", "entity_type": "identity_binding",
            "issuer": "https://issuer.test", "subject": subject, "user_id": user_id,
            "status": "active", "version": 1,
        },
        {
            "PK": f"USER#{user_id}", "SK": f"IDENTITY#issuer-hash#{subject}",
            "entity_type": "user_identity_inventory", "issuer": "https://issuer.test",
            "subject": subject, "user_id": user_id, "binding_pk": binding_pk,
        },
    )


def _accept(user_id: str) -> str:
    return service.accept_account_deletion(
        user_id=user_id,
        initiator=service.OperatorInitiated(initiated_by="operator:test", reason="#641 test"),
        now_iso=_now().isoformat(),
    ).command_id


def _command(table: FakeTable, user_id: str, command_id: str) -> dict[str, Any]:
    return table.rows[(f"USER#{user_id}", f"DELETE_COMMAND#{command_id}")]


def _drive(table: FakeTable, user_id: str, command_id: str, *, runs: int = 10) -> int:
    """Run the scheduled job until the deletion completes; how many runs it took."""
    for run in range(1, runs + 1):
        summary = job.run_pending_deletions()
        assert summary.paused == 0
        if _command(table, user_id, command_id)["status"] == "complete":
            return run
    raise AssertionError(f"not complete after {runs} runs")


def _row(table: FakeTable, pk: str, sk: str) -> dict[str, Any] | None:
    return table.rows.get((pk, sk))


def _nothing_left(table: FakeTable, user_id: str) -> None:
    """Every row naming the account is one the catalog says needs nothing more."""
    left = [
        (row["PK"], row["SK"], row.get("entity_type"))
        for row in table.rows.values()
        if flow.action_for(row, user_id) is not None
    ]
    assert left == []


def _keeps(name: str) -> frozenset[str]:
    entry = data_catalog.CATALOG.get(name) or next(
        entry for entry in data_catalog.UNTYPED if entry.name == name
    )
    assert entry.deletion is not None
    action = entry.deletion.owner
    assert isinstance(action, data_catalog.Tombstone)
    return action.keeps


# -- the shapes production held (#640) --------------------------------------------------


def _moderation_with_question_gone(case_id: str, surface: str) -> list[dict[str, Any]]:
    """A case raised on an answer and its event, the question they point to deleted."""
    return [
        {
            "PK": f"MODERATION#{case_id}", "SK": "SUMMARY", "entity_type": "moderation_case",
            "schema_version": "moderation-case.v1", "case_id": case_id,
            "question_id": f"question-gone-{case_id}", "student_id": STUDENT,
            "privacy_generation": 1, "surface": surface, "status": "open",
            "reason": "self_harm_signal", "excerpt": "private words the student wrote",
            "listing": "moderation_case", "listed_at": "2026-11-20T10:00:00+00:00",
            "created_at": "2026-11-20T10:00:00+00:00",
        },
        {
            "PK": f"MODERATION#{case_id}", "SK": "EVENT#event-1",
            "entity_type": "moderation_event", "event_id": "event-1", "case_id": case_id,
            "question_id": f"question-gone-{case_id}", "student_id": STUDENT,
            "privacy_generation": 1, "event_type": "opened", "actor_id": "operator:agent_mcp",
            "note": "private note about the student", "created_at": "2026-11-20T10:00:00+00:00",
        },
    ]


def _teacher_mention_with_delivery_attempts(event_id: str) -> dict[str, Any]:
    """A student's notification naming the teacher, its realtime attempts recorded.

    `websocket_service._record_delivery_attempt` keeps the last five attempts in
    `metadata`, each with a `target_count`; stored as N, read back as Decimal.
    """
    return as_stored(
        {
            "PK": f"NOTIFICATION#{event_id}", "SK": "META",
            "entity_type": notification_repo.NOTIFICATION_ENTITY,
            "schema_version": "notification-event.v3", "event_version": 2,
            "event_id": event_id, "owner_id": OTHER_STUDENT, "account_fence_generation": 1,
            "recipient_id": OTHER_STUDENT, "recipient_role": "student",
            "event_type": "teacher_reply", "target_type": "conversation",
            "target_id": "conversation-b2", "actor_id": TEACHER, "actor_role": "teacher",
            "status": "accepted", "effect_state": "effect_complete",
            "accepted_at": "2026-11-21T08:00:00+00:00",
            "metadata": {
                "teacher_id": TEACHER,
                "subject": "math",
                "websocket_delivery_attempts": [
                    {
                        "delivery_id": "delivery-1",
                        "attempted_at": "2026-11-21T08:00:01+00:00",
                        "target_channels": [f"user:{OTHER_STUDENT}"],
                        "target_count": 1,
                        "results": [{"connection_id": "connection-ab12", "status": "delivered"}],
                    }
                ],
            },
        }
    )


# -- the catalog seals the deletion ---------------------------------------------------------


def test_the_catalog_hash_is_stable_and_changes_with_what_a_deletion_does(monkeypatch):
    sealed = data_catalog.catalog_sha256()
    assert sealed == data_catalog.catalog_sha256()
    assert len(sealed) == 64

    entries = list(data_catalog._ENTRIES)
    index = next(i for i, entry in enumerate(entries) if entry.name == "conversation")
    conversation = entries[index]
    assert isinstance(conversation.deletion.owner, data_catalog.Tombstone)
    keeps_more = data_catalog.Deletion(
        data_catalog.Tombstone(conversation.deletion.owner.keeps | {"content"})
    )
    entries[index] = data_catalog.replace(conversation, deletion=keeps_more)
    monkeypatch.setattr(data_catalog, "_ENTRIES", tuple(entries))
    assert data_catalog.catalog_sha256() != sealed

    # A note says why; it decides nothing, and is not sealed.
    entries[index] = data_catalog.replace(
        conversation,
        not_pointers=(data_catalog.NotPointer("created_by", "another reason"),),
    )
    monkeypatch.setattr(data_catalog, "_ENTRIES", tuple(entries))
    assert data_catalog.catalog_sha256() == sealed


def test_every_action_the_catalog_names_has_the_code_that_does_it():
    flow.check_hooks()


@pytest.mark.parametrize(
    "entry",
    [
        entry
        for entry in (*data_catalog.CATALOG.values(), *data_catalog.UNTYPED)
        if entry.deletion is not None and isinstance(entry.deletion.owner, data_catalog.Tombstone)
    ],
    ids=lambda entry: entry.name,
)
def test_a_tombstone_is_never_found_again(entry):
    """Whatever the type, its tombstone names no one, or says it is one: passes end."""
    account = "closing-account"
    row: dict[str, Any] = {"PK": "SOME#partition", "SK": "SOME#row"}
    if entry.untyped_key is None:
        row["entity_type"] = entry.name
    else:
        row["PK"] = entry.untyped_key.pk_prefix + account
        row["SK"] = entry.untyped_key.sk or (entry.untyped_key.sk_prefix or "") + "row"
    for pointer in entry.accounts:
        if pointer.role != data_catalog.OWNER:
            continue
        if isinstance(pointer, data_catalog.KeyId):
            row[pointer.key] = pointer.prefix + account
        elif isinstance(pointer, data_catalog.ScopeId):
            row["scope"] = pointer.prefixes[0] + account
        elif isinstance(pointer, data_catalog.Field):
            target = row
            *parents, last = pointer.path.split(".")
            for name in parents:
                target = target.setdefault(name, {})
            target[last] = account
    row.update(status="active", version=3, created_at="2026-01-01T00:00:00+00:00")
    assert data_catalog.owns(row, account)

    tombstone = account_deletion_repo.catalog_tombstone(
        row, keeps=entry.deletion.owner.keeps, generation=4, now_iso="2026-11-28T00:00:00+00:00"
    )

    assert set(tombstone) <= entry.deletion.owner.keeps
    assert flow.action_for(tombstone, account) is None


def test_the_profile_tombstone_its_module_writes_is_the_catalogs():
    assert account_deletion_repo.QUESTION_TOMBSTONE_ALLOWLIST == _keeps("user_profile")


# -- the whole deletion ------------------------------------------------------------------------


def _file(table: FakeTable, s3: _S3, attachment_id: str, *, ref_count: int) -> dict[str, Any]:
    key = f"objects/private/{attachment_id}.txt"
    stored = s3.put_object(
        Bucket=BUCKET, Key=key, Body=DATA, ContentLength=len(DATA),
        ChecksumSHA256=b64_sha256(DATA), Metadata={},
    )
    upload = {
        "upload_id": f"upload-{attachment_id}", "immutable_object_key": key,
        "immutable_version_id": stored["VersionId"], "immutable_etag": stored["ETag"],
        "content_sha256": "a" * 64, "original_filename": "notes.txt",
        "detected_type": "text/plain", "content_length": len(DATA),
    }
    row = {
        **attachment_repo.attachment_key(attachment_id),
        **attachment_service._attachment_from_upload(
            upload, attachment_id=attachment_id, owner_id=STUDENT, now=_now()
        ),
        "ref_count": ref_count,
    }
    usage = table.rows.get(("STORAGE#" + STUDENT, "USAGE"))
    used = int(usage["used_bytes"]) if usage else 0
    _seed(table, row)
    table.seed({**attachment_repo.storage_key(STUDENT), "used_bytes": used + len(DATA)})
    return row


def test_a_student_is_deleted_row_by_row_as_the_catalog_says(table, s3, cognito):
    _account(table, STUDENT, "student", email=EMAIL, display_name="Mia")
    table.seed(
        account_email_claim_repo.claim_item(
            email=EMAIL, role="student", account_id=STUDENT, created_at="2026-09-01T00:00:00+00:00"
        )
    )
    _identity(table, STUDENT, "subject-a6")
    _account(
        table, PARENT, "parent",
        children=[{"student_id": STUDENT, "name": "Mia"}, {"student_id": "other-child"}],
    )
    conversation = "conversation-a6"
    referenced = _file(table, s3, "attachment-in-message", ref_count=1)
    saved = _file(table, s3, "attachment-saved", ref_count=0)
    _seed(
        table,
        *_moderation_with_question_gone("case-teacher", "teacher_reply"),
        *_moderation_with_question_gone("case-ai", "ai_answer"),
        {
            "PK": f"CONV#{conversation}", "SK": "META", "entity_type": "conversation",
            "conversation_id": conversation, "owner_id": STUDENT, "student_id": STUDENT,
            "title": "private title", "status": "active", "created_at": "2026-11-01T00:00:00+00:00",
        },
        {
            "PK": f"CONV#{conversation}", "SK": "MSG#0001", "entity_type": "conversation_message",
            "conversation_id": conversation, "message_id": "message-1", "owner_id": STUDENT,
            "student_id": STUDENT, "role": "student", "content": "private question",
            "attachment_ids": [referenced["attachment_id"]],
        },
        {
            **attachment_repo.association_key(
                referenced["attachment_id"], "conversation", conversation, "message-1"
            ),
            "entity_type": "attachment_association", "attachment_id": referenced["attachment_id"],
            "owner_id": STUDENT, "student_id": STUDENT, "resource_type": "conversation",
            "resource_id": conversation, "message_id": "message-1",
        },
        # Owned only through `metadata` (#634 comment 4): its recipient is the parent.
        {
            "PK": "NOTIFICATION#about-child", "SK": "META",
            "entity_type": notification_repo.NOTIFICATION_ENTITY,
            "schema_version": "notification-event.v3", "event_version": 1,
            "event_id": "about-child", "owner_id": PARENT, "recipient_id": PARENT,
            "event_type": "learning_profile_update", "status": "accepted",
            "metadata": {"student_id": STUDENT, "summary": "private progress"},
        },
        # Owned by its key and by `owner_id` (#634 comment 5): one tombstone, the catalog's.
        {
            "PK": f"USAGE#{STUDENT}", "SK": "QUESTION#2026-11-27", "owner_id": STUDENT,
            "count": 3, "quota_period": "2026-11-27", "expires_at": 1_900_000_000,
        },
        {
            "PK": f"PARENT#{PARENT}", "SK": f"CHILD#{STUDENT}",
            "entity_type": "parent_student_link", "parent_id": PARENT, "student_id": STUDENT,
            "status": "active",
        },
    )

    command_id = _accept(STUDENT)
    runs = _drive(table, STUDENT, command_id)

    command = _command(table, STUDENT, command_id)
    assert command["status"] == "complete"
    assert command["flow"] == flow.CATALOG_FLOW
    assert command["catalog_sha256"] == data_catalog.catalog_sha256()
    assert command["receipt"]["status"] == "deleted"
    assert service.terminal_deletion_receipt(command).is_terminal
    fence = table.rows[(f"USER#{STUDENT}", "ACCOUNT_FENCE")]
    assert fence["status"] == "deleted"
    assert not [pk for (pk, _sk) in table.rows if pk == account_deletion_repo.PENDING_REGISTRY_PK]
    assert not [row for row in table.rows.values() if owner_registry.is_registry_row(row)
                and row["PK"] == f"USER#{STUDENT}"]
    assert runs == 1

    # Step 1: the profile's tombstone gave the address back; the provider user is gone.
    profile = table.rows[(f"USER#{STUDENT}", "PROFILE")]
    assert account_deletion_repo.is_deletion_tombstone(profile)
    assert "email" not in profile and "display_name" not in profile
    assert not [row for row in table.rows.values()
                if row.get("entity_type") == "account_email_claim"]
    assert ("delete", "subject-a6") in cognito.calls
    debt = table.rows[(f"USER#{STUDENT}", "PROVIDER_REVOKE#00000000000000000001")]
    assert debt["status"] == "complete"
    binding = table.rows[("IDENTITY#issuer-hash#subject-a6", "BINDING")]
    assert binding["status"] == "deleted" and "user_id" not in binding

    # Step 2: each row as its entry says.
    for case_id in ("case-teacher", "case-ai"):
        for sk in ("SUMMARY", "EVENT#event-1"):
            moderation = table.rows[(f"MODERATION#{case_id}", sk)]
            assert set(moderation) <= _keeps(moderation["entity_type"])
            assert moderation["privacy_deleted"] is True
            assert "student_id" not in moderation and "excerpt" not in moderation
    # The question was never looked for.
    assert not [request for operation, request in table.requests
                if str((request.get("Key") or {}).get("PK", "")).startswith("QUESTION#")]

    for sk in ("META", "MSG#0001"):
        row = table.rows[(f"CONV#{conversation}", sk)]
        assert set(row) <= _keeps(row["entity_type"])
        assert account_deletion_repo.is_deletion_tombstone(row)
    assert "content" not in table.rows[(f"CONV#{conversation}", "MSG#0001")]

    notification = table.rows[("NOTIFICATION#about-child", "META")]
    assert set(notification) <= _keeps("notification_event")
    assert notification["status"] == "deleted" and "metadata" not in notification

    counter = table.rows[(f"USAGE#{STUDENT}", "QUESTION#2026-11-27")]
    assert set(counter) <= _keeps("usage_counter")
    assert counter["status"] == "deleted" and counter["count"] == 3

    for attachment in (referenced, saved):
        assert _row(table, f"ATTACHMENT#{attachment['attachment_id']}", "META") is None
        assert not s3.holds(attachment["immutable_object_key"], attachment["immutable_version_id"])
    assert not [row for row in table.rows.values()
                if row.get("entity_type") == "attachment_association"]
    assert _row(table, f"STORAGE#{STUDENT}", "USAGE") is None

    assert _row(table, f"PARENT#{PARENT}", f"CHILD#{STUDENT}") is None
    parent = table.rows[(f"USER#{PARENT}", "PROFILE")]
    assert parent["children"] == [{"student_id": "other-child"}]

    _nothing_left(table, STUDENT)


def test_a_teacher_is_scrubbed_from_a_notification_whose_metadata_holds_numbers(table):
    _account(table, TEACHER, "teacher")
    _account(table, OTHER_STUDENT, "student")
    mention = _teacher_mention_with_delivery_attempts("teacher-reply-1")
    # What the table hands back, and what `json.dumps` alone refuses (#640).
    attempt = mention["metadata"]["websocket_delivery_attempts"][0]
    assert isinstance(attempt["target_count"], Decimal)
    with pytest.raises(TypeError):
        json.dumps(mention["metadata"])
    _seed(
        table,
        mention,
        _teacher_mention_with_delivery_attempts("teacher-reply-2"),
        # The teacher's own dispatch notice: theirs, so tombstoned.
        as_stored({
            "PK": "NOTIFICATION#dispatched-1", "SK": "META",
            "entity_type": notification_repo.NOTIFICATION_ENTITY,
            "schema_version": "notification-event.v3", "event_version": 1,
            "event_id": "dispatched-1", "owner_id": TEACHER, "recipient_id": TEACHER,
            "event_type": "teacher_help_dispatched", "status": "accepted",
            "metadata": {"student_id": OTHER_STUDENT, "websocket_delivery_attempts": [
                {"delivery_id": "d", "target_count": 2, "results": []}]},
        }),
    )

    command_id = _accept(TEACHER)
    _drive(table, TEACHER, command_id)

    for event_id in ("teacher-reply-1", "teacher-reply-2"):
        scrubbed = table.rows[(f"NOTIFICATION#{event_id}", "META")]
        assert "actor_id" not in scrubbed
        assert "teacher_id" not in scrubbed["metadata"]
        assert scrubbed["owner_id"] == OTHER_STUDENT
        assert scrubbed["metadata"]["websocket_delivery_attempts"][0]["target_count"] == 1
        assert scrubbed["event_version"] == 3
    own = table.rows[("NOTIFICATION#dispatched-1", "META")]
    assert own["status"] == "deleted" and "metadata" not in own
    _nothing_left(table, TEACHER)


# -- interrupted, and written to, while it runs ---------------------------------------------------


def _study_days(count: int) -> list[dict[str, Any]]:
    return [
        {
            "PK": f"ACTIVITY#{STUDENT}", "SK": f"DAY#{index:04d}", "entity_type": "study_day",
            "student_id": STUDENT, "minutes": index, "created_at": "2026-11-01T00:00:00+00:00",
        }
        for index in range(count)
    ]


def _claim(table: FakeTable, user_id: str, command_id: str) -> Any:
    now = _now()
    claim = account_deletion_repo.claim_deletion_command(
        _command(table, user_id, command_id),
        lease_owner="worker-test",
        now_epoch=int(now.timestamp()),
        lease_expires_at=int(now.timestamp()) + 120,
        now_iso=now.isoformat(),
    )
    assert claim is not None
    return claim


def test_a_run_that_stops_is_carried_on_from_the_cursor_on_the_command(table):
    _account(table, STUDENT, "student")
    _seed(table, *_study_days(250))
    command_id = _accept(STUDENT)

    cursors = []
    for _ in range(20):
        worker = flow.CatalogDeletion(page_rows=100, max_pages=1)
        outcome = worker.continue_command(_claim(table, STUDENT, command_id))
        command = _command(table, STUDENT, command_id)
        if outcome.status == "complete":
            break
        progress = command["deletion_progress"]
        assert progress["open"] is False  # it said where it stopped
        cursors.append(progress["cursor"])
        assert command["lease_expires_at"] < _now().timestamp()  # the lease given back
    assert command["status"] == "complete"
    # Resumed page by page, never from the top.
    assert any(cursor is not None for cursor in cursors)
    for row in _study_days(250):
        assert account_deletion_repo.is_deletion_tombstone(table.rows[(row["PK"], row["SK"])])
    _nothing_left(table, STUDENT)


class _Died(BaseException):
    """The Lambda timed out, or the process went: nothing after this line ran."""


def test_a_run_that_dies_before_it_records_a_page_does_not_count_that_pass_as_clean(
    table, monkeypatch
):
    """The run handles every row of the page and dies before writing that it did.

    The next run finds the page already settled. Counted as found nothing, that
    pass would end the deletion though the rows it changed were never counted;
    it is the run's own `open` mark that sends it round once more.
    """
    _account(table, STUDENT, "student")
    _seed(table, *_study_days(30))
    command_id = _accept(STUDENT)
    real = account_deletion_repo.persist_deletion_progress
    calls = {"count": 0}

    def dies_on_the_second_record(*args: Any, **kwargs: Any) -> Any:
        calls["count"] += 1
        if calls["count"] == 2:  # the first is step 1's, the second the page's
            raise _Died()
        return real(*args, **kwargs)

    monkeypatch.setattr(account_deletion_repo, "persist_deletion_progress", dies_on_the_second_record)
    with pytest.raises(_Died):
        flow.CatalogDeletion().continue_command(_claim(table, STUDENT, command_id))
    monkeypatch.setattr(account_deletion_repo, "persist_deletion_progress", real)
    progress = _command(table, STUDENT, command_id)["deletion_progress"]
    assert progress["open"] is True and progress["found"] == 0
    for row in _study_days(30):  # every row was handled before it died
        assert account_deletion_repo.is_deletion_tombstone(table.rows[(row["PK"], row["SK"])])

    outcome = flow.CatalogDeletion().continue_command(_claim(table, STUDENT, command_id))

    assert outcome.status == "complete"
    assert outcome.passes == 2  # the uncounted pass, then a clean one
    _nothing_left(table, STUDENT)


def test_a_row_written_while_the_deletion_runs_is_found_by_a_later_pass(table):
    _account(table, STUDENT, "student")
    _seed(table, *_study_days(150))
    command_id = _accept(STUDENT)
    flow.CatalogDeletion(page_rows=100, max_pages=1).continue_command(
        _claim(table, STUDENT, command_id)
    )
    cursor = _command(table, STUDENT, command_id)["deletion_progress"]["cursor"]
    assert cursor["PK"] == f"ACTIVITY#{STUDENT}"
    # Written behind the cursor, where this pass has already read.
    late = {
        "PK": f"ACTIVITY#{STUDENT}", "SK": "DAY#0000-late", "entity_type": "study_day",
        "student_id": STUDENT, "minutes": 99,
    }
    assert late["SK"] < cursor["SK"]
    table.seed(late)

    _drive(table, STUDENT, command_id)

    assert account_deletion_repo.is_deletion_tombstone(table.rows[(late["PK"], late["SK"])])
    assert _command(table, STUDENT, command_id)["status"] == "complete"
    _nothing_left(table, STUDENT)


# -- step 3: deliveries ----------------------------------------------------------------------------


def _delivery(status: str, *, lease_expires_at: int | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "PK": notification_repo.delivery_intent_pk(STUDENT),
        "SK": notification_repo.delivery_intent_sk("operation-1"),
        "entity_type": notification_repo.DELIVERY_INTENT_ENTITY,
        "schema_version": "notification-delivery-intent.v2", "operation_id": "operation-1",
        "owner_id": STUDENT, "account_fence_generation": 1, "channel": "push",
        "event_ids": ["event-1"], "payload_digest": "f" * 64, "status": status,
        "effect_state": status, "created_at": "2026-11-28T00:00:00+00:00",
    }
    if lease_expires_at is not None:
        row["lease_expires_at"] = lease_expires_at
        row["lease_owner"] = "sender-1"
    return row


def test_a_delivery_a_sender_holds_is_waited_for_then_counted(table):
    _account(table, STUDENT, "student")
    sending = _delivery("claimed_pre_effect", lease_expires_at=int(_now().timestamp()) + 600)
    _seed(table, sending)
    command_id = _accept(STUDENT)

    for _ in range(3):
        job.run_pending_deletions()
    command = _command(table, STUDENT, command_id)
    assert command["status"] == "running"
    assert command["deletion_progress"]["step"] == "deliveries"
    held = table.rows[(sending["PK"], sending["SK"])]
    assert held["status"] == "claimed_pre_effect" and held["owner_id"] == STUDENT

    # The sender finishes: the provider accepted it.
    table.seed({**held, "status": "accepted", "effect_state": "accepted"})
    _drive(table, STUDENT, command_id)

    command = _command(table, STUDENT, command_id)
    assert command["external_receipts"] == [
        {"channel": "provider", "status": "accepted", "count": 1,
         "claim": "outside_backend_purge_authority"}
    ]
    receipt = table.rows[(sending["PK"], sending["SK"])]
    assert receipt["status"] == "accepted" and "owner_id" not in receipt


def test_a_delivery_whose_sender_let_its_lease_run_out_counts_as_unknown(table):
    _account(table, STUDENT, "student")
    _seed(table, _delivery("claimed_pre_effect", lease_expires_at=int(_now().timestamp()) - 5))
    command_id = _accept(STUDENT)

    _drive(table, STUDENT, command_id)

    assert _command(table, STUDENT, command_id)["external_receipts"] == [
        {"channel": "provider", "status": "provider_acceptance_unknown", "count": 1,
         "claim": "outside_backend_purge_authority"}
    ]


# -- the seal ---------------------------------------------------------------------------------------


def test_a_changed_catalog_pauses_the_deletion_and_pages(table, monkeypatch, caplog):
    _account(table, STUDENT, "student", email=EMAIL)
    command_id = _accept(STUDENT)
    monkeypatch.setattr(flow, "current_catalog_sha256", lambda: "0" * 64)
    before = {key: dict(row) for key, row in table.rows.items()}

    summary = job.run_pending_deletions()

    assert summary.paused == 1 and summary.continued == 0
    command = _command(table, STUDENT, command_id)
    assert command["status"] == "running" and "deletion_progress" not in command
    assert table.rows[(f"USER#{STUDENT}", "PROFILE")] == before[(f"USER#{STUDENT}", "PROFILE")]
    assert "account_deletion_paused reason=catalog_changed" in caplog.text
    with pytest.raises(job.DeletionsPaused):
        job.handler({}, None)


def test_a_command_from_before_the_catalog_flow_is_refused_and_pages(table, caplog):
    _account(table, STUDENT, "student")
    table.seed(
        {
            "PK": f"USER#{STUDENT}", "SK": "DELETE_COMMAND#legacy",
            "entity_type": "account_deletion_command", "command_id": "legacy",
            "user_id": STUDENT, "generation": 1, "status": "pending", "version": 1,
            "inventory_sha256": "8b40" + "0" * 60,
        },
        {
            **account_deletion_repo.pending_registry_key(STUDENT, "legacy"),
            "entity_type": "account_deletion_pending", "deletion_user_id": STUDENT,
            "deletion_command_id": "legacy",
        },
    )

    summary = job.run_pending_deletions()

    assert summary.paused == 1 and summary.claimed == 0
    assert _command(table, STUDENT, "legacy")["status"] == "pending"
    assert "account_deletion_paused reason=legacy_command" in caplog.text
    with pytest.raises(job.DeletionsPaused):
        job.handler({}, None)


# -- acceptance ---------------------------------------------------------------------------------------


def test_a_new_deletion_waits_for_a_sweep_that_vouches_for_the_registry(table):
    _account(table, STUDENT, "student")
    _sweep_vouches(table, when=_now() - timedelta(hours=40))

    with pytest.raises(service.DeletionNotReady):
        _accept(STUDENT)
    assert table.rows[(f"USER#{STUDENT}", "ACCOUNT_FENCE")]["status"] == "active"

    _sweep_vouches(table)
    command_id = _accept(STUDENT)
    # A replay is the same command, whatever the sweep says by then.
    _sweep_vouches(table, when=_now() - timedelta(hours=40))
    assert _accept(STUDENT) == command_id


def test_the_request_side_only_tombstones_the_profile(table, cognito):
    _account(table, STUDENT, "student", email=EMAIL)
    _identity(table, STUDENT, "subject-a6")
    command_id = _accept(STUDENT)

    worker = flow.CatalogDeletion()
    worker.run_request_side(_claim(table, STUDENT, command_id))

    assert account_deletion_repo.is_deletion_tombstone(table.rows[(f"USER#{STUDENT}", "PROFILE")])
    assert cognito.calls == []
    command = _command(table, STUDENT, command_id)
    assert command["status"] == "running" and "deletion_progress" not in command


# -- every outside action can run again --------------------------------------------------------------


def _visit() -> Any:
    now = _now()
    return flow._Visit(STUDENT, 1, now.isoformat(), int(now.timestamp()))


def _pending_deletion(table: FakeTable) -> None:
    _account(table, STUDENT, "student")
    fence = table.rows[(f"USER#{STUDENT}", "ACCOUNT_FENCE")]
    table.seed({**fence, "status": "deletion_pending", "command_id": "command-1"})


def test_revoking_the_provider_user_twice_revokes_it_once(table, cognito):
    _pending_deletion(table)
    binding = {"PK": "IDENTITY#h#subject-a6", "SK": "BINDING", "subject": "subject-a6"}
    kind = data_catalog.CATALOG["identity_binding"]

    assert flow.EFFECTS["revoke_provider_identity"](binding, kind, _visit()) == flow.READY
    # A second identity row, or the same one read again: the debt says it is done.
    assert flow.EFFECTS["revoke_provider_identity"](binding, kind, _visit()) == flow.READY
    assert cognito.calls == [("sign_out", "subject-a6"), ("delete", "subject-a6")]
    # Even with the debt not yet recorded as done, a repeat is harmless.
    flow.revoke_provider(STUDENT, 1, "subject-a6", now_iso=_now().isoformat())
    debt = table.rows[(f"USER#{STUDENT}", "PROVIDER_REVOKE#00000000000000000001")]
    assert debt["status"] == "complete"


def test_letting_go_of_a_reference_and_deleting_a_file_twice_change_nothing_twice(table, s3):
    _pending_deletion(table)
    file = _file(table, s3, "attachment-twice", ref_count=1)
    reference = {
        **attachment_repo.association_key(file["attachment_id"], "conversation", "c", "m"),
        "entity_type": "attachment_association", "attachment_id": file["attachment_id"],
        "owner_id": STUDENT, "student_id": STUDENT, "resource_type": "conversation",
        "resource_id": "c", "message_id": "m",
    }
    table.seed(reference)
    kind = data_catalog.CATALOG["attachment_association"]

    assert flow.EFFECTS["release_attachments"](reference, kind, _visit()) == flow.DONE
    assert flow.EFFECTS["release_attachments"](reference, kind, _visit()) == flow.DONE
    # The last reference took the file with it.
    assert _row(table, f"ATTACHMENT#{file['attachment_id']}", "META") is None

    saved = _file(table, s3, "attachment-saved-twice", ref_count=0)
    assert flow.STORED_OBJECTS["attachment"](saved, _visit()) == flow.DONE
    assert flow.STORED_OBJECTS["attachment"](saved, _visit()) == flow.DONE
    assert int(table.rows[(f"STORAGE#{STUDENT}", "USAGE")]["used_bytes"]) == 0


def test_a_case_image_deleted_twice_and_a_delivery_counted_twice_agree(table, s3):
    _pending_deletion(table)
    stored = s3.put_object(
        Bucket=BUCKET, Key="moderation/case.png", Body=DATA, ContentLength=len(DATA),
        ChecksumSHA256=b64_sha256(DATA), Metadata={},
    )
    case = {
        "PK": "MODERATION#image", "SK": "SUMMARY", "entity_type": "moderation_case",
        "student_id": STUDENT, "surface": "image_upload",
        "image_context": {"image_status": "stored"},
        "image_object_key": "moderation/case.png", "image_version_id": stored["VersionId"],
    }
    kind = data_catalog.CATALOG["moderation_case"]
    for _ in range(2):
        assert flow.EFFECTS["delete_stored_object"](case, kind, _visit()) == flow.READY
    assert not s3.holds("moderation/case.png", stored["VersionId"])

    accepted = _delivery("accepted")
    delivery = data_catalog.CATALOG["notification_delivery_intent"]
    for _ in range(2):
        visit = _visit()
        assert flow.EFFECTS["count_external_delivery"](accepted, delivery, visit) == flow.READY
        assert visit.receipt == "accepted" and visit.keep_status


def test_a_row_already_settled_asks_nothing_of_a_later_pass(table):
    _pending_deletion(table)
    row = {"PK": f"ACTIVITY#{STUDENT}", "SK": "DAY#1", "entity_type": "study_day",
           "student_id": STUDENT, "minutes": 3}
    table.seed(row)
    visit = _visit()

    assert flow.handle_row(row, visit) == flow.DONE
    settled = table.rows[(row["PK"], row["SK"])]
    assert flow.handle_row(settled, visit) is None
    # Even the row as first read: its tombstone is written again, the same.
    assert flow.handle_row(row, visit) == flow.DONE
    assert table.rows[(row["PK"], row["SK"])] == {**settled, "deleted_at": visit.now_iso}

