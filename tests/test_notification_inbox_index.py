"""A notification carries its place in the index it is found through (#613).

The bell finds one person's notifications with `notification_repo.list_events`:
a scan of the whole of `stoa-main` that keeps the first hundred notifications of
the whole site, whoever they are for. Every poll reads every row of the table,
a person's own notification can be missing once the site has more than a
hundred, and the scan stops answering when the table outgrows its page budget.

A notification now carries `sweep_bucket` (who it is for) and `sweep_due_at`
(when it was created), the keys of GSI-SweepPending. These hold every write of
the row to that: after each one, a person's inbox read from the index is
exactly what the scan and `_visible_to_user` find for them, so switching the
readers from the scan to the index loses no notification. The backfill puts
the rows written before in place.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fakes.dynamodb import DEFAULT_INDEXES, FakeTable, IndexSchema

from scripts import backfill_notification_inbox_index as backfill
from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo, notification_repo
from stoa.services import notification_service
from stoa.services.ask_question import _store

STUDENT = "student-1"
OTHER_STUDENT = "student-2"
TEACHER = "teacher-1"
PARENT = "parent-1"
PEOPLE = {STUDENT: "student", OTHER_STUDENT: "student", TEACHER: "teacher", PARENT: "parent"}
ROLES = ("student", "teacher", "parent", "admin")
GENERATION = 3
CREATED = "2026-11-24T10:00:00Z"
INDEX_FIELDS = set(notification_repo.INBOX_INDEX_FIELDS)


def _fence(user_id: str, *, status: str = "active") -> dict[str, Any]:
    return {
        **account_deletion_repo.account_fence_key(user_id),
        "entity_type": "account_fence",
        "status": status,
        "generation": GENERATION,
    }


@pytest.fixture
def table() -> Iterator[FakeTable]:
    double = FakeTable()
    double.seed(*(_fence(user_id) for user_id in PEOPLE))
    db_table.install(double)
    try:
        yield double
    finally:
        db_table.install(None)


def _event(
    event_id: str,
    *,
    recipient_id: str | None,
    recipient_role: str,
    owner_id: str = STUDENT,
    created_at: str = CREATED,
    **fields: Any,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "entity_type": notification_repo.NOTIFICATION_ENTITY,
        "schema_version": "notification-event.v3",
        "event_version": 1,
        "recipient_id": recipient_id,
        "recipient_role": recipient_role,
        "event_type": "teacher_help_dispatched",
        "target_type": "conversation",
        "target_id": "conv-1",
        "title": "Eine Frage wartet",
        "summary": "",
        "status": "created",
        "created_at": created_at,
        "metadata": {},
        "owner_id": owner_id,
        "account_fence_generation": GENERATION,
        "owner_classification": "private_owner",
        **fields,
    }


def _global_event(event_id: str, *, created_at: str = CREATED) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "entity_type": notification_repo.NOTIFICATION_ENTITY,
        "schema_version": "notification-event.v3",
        "event_version": 1,
        "recipient_id": None,
        "recipient_role": "admin",
        "event_type": "moderation_case_update",
        "target_type": "system_status",
        "target_id": "status-1",
        "title": "Ein Fall wartet",
        "summary": "",
        "status": "created",
        "created_at": created_at,
        "metadata": {},
        "owner_id": None,
        "account_fence_generation": None,
        "owner_classification": "global_nonprivate",
        "category": "moderation",
    }


def _row(table: FakeTable, event_id: str) -> dict[str, Any]:
    return table.rows[(notification_repo.notification_pk(event_id), "META")]


def _ids(items: list[dict[str, Any]]) -> list[str]:
    return sorted(str(item["event_id"]) for item in items)


def _legacy(event: dict[str, Any]) -> dict[str, Any]:
    """The row as a release before #613 stored it: no index keys."""
    return {**event, "PK": notification_repo.notification_pk(event["event_id"]), "SK": "META"}


def _assert_every_inbox_holds_what_the_scan_finds(table: FakeTable) -> None:
    """Each person's and each role's inbox against the scan it replaces."""
    scanned = notification_repo.list_all_events(table=table)
    for user_id, role in [*PEOPLE.items(), *(("", role) for role in ROLES)]:
        visible = [
            item
            for item in scanned
            if notification_service._visible_to_user(item, user_id=user_id, role=role)
        ]
        assert _ids(notification_repo.list_inbox(user_id=user_id, role=role, table=table)) == _ids(
            visible
        ), (user_id, role)
    for item in scanned:
        assert notification_repo.carried_index_fields(item) == notification_repo.index_fields(
            item
        ), item


# -- The index is the table's ----------------------------------------------------------


def test_the_index_is_one_the_table_carries() -> None:
    assert DEFAULT_INDEXES[notification_repo.INBOX_INDEX] == IndexSchema(
        *notification_repo.INBOX_INDEX_FIELDS
    )


def test_notifications_share_the_generation_sweeps_index_but_not_its_bucket(table) -> None:
    """The generation sweep (#502) queries its own bucket and never reads a notification."""
    assert notification_repo.INBOX_INDEX == _store.SWEEP_PENDING_INDEX
    notification_repo.put_event(_event("e1", recipient_id=TEACHER, recipient_role="teacher"))
    assert _row(table, "e1")["sweep_bucket"] != _store.SWEEP_PENDING_BUCKET

    commands, complete = _store.query_generation_sweep_commands(
        now=datetime(2100, 1, 1, tzinfo=UTC), table=table
    )

    assert (commands, complete) == ([], True)


def test_one_persons_bucket_is_never_a_roles_or_another_persons() -> None:
    buckets = {
        notification_repo.inbox_bucket(user_id="admin"),
        notification_repo.inbox_bucket(role="admin"),
        notification_repo.inbox_bucket(user_id="teacher"),
        notification_repo.inbox_bucket(role="teacher"),
    }
    assert len(buckets) == 4
    with pytest.raises(ValueError):
        notification_repo.inbox_bucket()


# -- What a row carries -----------------------------------------------------------------


def test_a_notification_for_one_person_is_filed_under_them_at_its_creation_time(table) -> None:
    notification_repo.put_event(_event("e1", recipient_id=TEACHER, recipient_role="teacher"))

    row = _row(table, "e1")
    assert row["sweep_bucket"] == notification_repo.inbox_bucket(user_id=TEACHER)
    assert row["sweep_due_at"] == CREATED
    assert _ids(notification_repo.list_inbox(user_id=TEACHER, role="teacher")) == ["e1"]
    # Not its owner's, and not every teacher's.
    assert notification_repo.list_inbox(user_id=STUDENT, role="student") == []
    assert notification_repo.list_inbox(user_id="teacher-2", role="teacher") == []
    _assert_every_inbox_holds_what_the_scan_finds(table)


@pytest.mark.parametrize("recipient_id", [None, ""])
def test_a_notification_for_a_whole_role_is_filed_under_the_role(table, recipient_id) -> None:
    event = _event("e1", recipient_id=recipient_id, recipient_role="admin")
    if recipient_id == "":
        # An empty string is no index key; the row still says who it is for.
        event.pop("recipient_id")
    notification_repo.put_event(event)

    assert _row(table, "e1")["sweep_bucket"] == notification_repo.inbox_bucket(role="admin")
    assert _ids(notification_repo.list_inbox(user_id="admin-7", role="admin")) == ["e1"]
    assert notification_repo.list_inbox(user_id=TEACHER, role="teacher") == []
    _assert_every_inbox_holds_what_the_scan_finds(table)


def test_a_global_notification_is_filed_under_its_role_and_keeps_its_seal(table) -> None:
    stored = notification_repo.put_event(_global_event("g1"))

    row = _row(table, "g1")
    assert row["sweep_bucket"] == notification_repo.inbox_bucket(role="admin")
    assert row["sweep_due_at"] == CREATED
    # The seal covers what the notification says, not where it is filed.
    assert notification_repo.validate_global_nonprivate_event(stored)
    assert row["classification_digest"] == stored["classification_digest"]
    assert stored["classification_digest"] == (
        notification_repo.seal_global_nonprivate_event(_global_event("g1"))["classification_digest"]
    )
    assert _ids(notification_repo.list_inbox(user_id="admin-7", role="admin")) == ["g1"]


@pytest.mark.parametrize(
    "fields",
    [
        {"entity_type": "notification_preference"},
        {"created_at": ""},
        {"created_at": None},
        {"recipient_id": None, "recipient_role": ""},
        {"recipient_id": 7},
    ],
)
def test_a_row_that_is_in_no_inbox_carries_neither_key(fields) -> None:
    event = {**_event("e1", recipient_id=TEACHER, recipient_role="teacher"), **fields}
    assert notification_repo.index_fields(event) == {}


def test_an_index_key_is_never_empty() -> None:
    for recipient_id in (TEACHER, None):
        fields = notification_repo.index_fields(
            _event("e1", recipient_id=recipient_id, recipient_role="teacher")
        )
        assert set(fields) == INDEX_FIELDS
        assert all(isinstance(value, str) and value for value in fields.values())


# -- Each later write of the row --------------------------------------------------------


@pytest.mark.parametrize(
    "updates",
    [
        {"status": "read", "read_at": "2026-11-24T11:00:00Z"},
        {"status": "archived", "archived_at": "2026-11-24T11:00:00Z"},
        {"metadata": {"offer_state": "taken"}, "title": "Vergeben", "summary": ""},
    ],
    ids=["read", "archived", "closed_offer"],
)
def test_reading_archiving_or_rewording_leaves_a_notification_where_it_is(table, updates) -> None:
    notification_repo.put_event(_event("e1", recipient_id=TEACHER, recipient_role="teacher"))
    before = notification_repo.carried_index_fields(_row(table, "e1"))

    notification_repo.update_event("e1", updates)

    assert notification_repo.carried_index_fields(_row(table, "e1")) == before
    # An archived notification stays in the inbox: the list can ask for those.
    assert _ids(notification_repo.list_inbox(user_id=TEACHER, role="teacher")) == ["e1"]
    _assert_every_inbox_holds_what_the_scan_finds(table)


@pytest.mark.parametrize(
    "updates",
    [
        {"recipient_id": OTHER_STUDENT},
        {"recipient_role": "admin"},
        {"created_at": "2026-11-25T10:00:00Z"},
        {"sweep_bucket": "pending_generation"},
        {"sweep_due_at": "2026-11-25T10:00:00Z"},
    ],
)
def test_no_update_moves_a_notification_to_another_inbox_or_time(table, updates) -> None:
    notification_repo.put_event(_event("e1", recipient_id=TEACHER, recipient_role="teacher"))
    before = dict(_row(table, "e1"))

    with pytest.raises(ValueError):
        notification_repo.update_event("e1", updates)

    assert _row(table, "e1") == before


def test_an_update_may_restate_who_a_notification_is_for(table) -> None:
    notification_repo.put_event(_event("e1", recipient_id=TEACHER, recipient_role="teacher"))

    notification_repo.update_event("e1", {"recipient_id": TEACHER, "status": "read"})

    assert _row(table, "e1")["status"] == "read"
    _assert_every_inbox_holds_what_the_scan_finds(table)


def test_the_owners_deletion_takes_a_notification_out_of_its_recipients_inbox(table) -> None:
    notification_repo.put_event(_event("e1", recipient_id=TEACHER, recipient_role="teacher"))
    table.seed(_fence(STUDENT, status="deletion_pending"))

    notification_repo.scrub_notification_private_row(
        _row(table, "e1"),
        owner_id=STUDENT,
        generation=GENERATION,
        now_iso="2026-11-25T00:00:00Z",
        table=table,
    )

    tombstone = _row(table, "e1")
    assert tombstone["entity_type"] == "notification_event_deletion_tombstone"
    assert not INDEX_FIELDS & set(tombstone)
    assert notification_repo.list_inbox(user_id=TEACHER, role="teacher") == []


def test_scrubbing_a_mentioned_account_leaves_a_notification_in_its_inbox(table) -> None:
    notification_repo.put_event(
        _event("e1", recipient_id=STUDENT, recipient_role="student", metadata={"parent_id": PARENT})
    )
    table.seed(_fence(PARENT, status="deletion_pending"))

    notification_repo.scrub_notification_private_row(
        _row(table, "e1"),
        owner_id=PARENT,
        generation=GENERATION,
        now_iso="2026-11-25T00:00:00Z",
        table=table,
    )

    assert _row(table, "e1")["metadata"] == {}
    assert _ids(notification_repo.list_inbox(user_id=STUDENT, role="student")) == ["e1"]
    _assert_every_inbox_holds_what_the_scan_finds(table)


# -- Reading an inbox -------------------------------------------------------------------


def test_everyone_finds_all_of_their_own_among_more_than_a_hundred_site_wide() -> None:
    """The scan keeps the site's first hundred; an inbox is cut off by nothing."""
    double = FakeTable(page_item_cap=7)
    double.seed(*(_fence(user_id) for user_id in PEOPLE))
    db_table.install(double)
    try:
        expected: dict[str, list[str]] = {user_id: [] for user_id in PEOPLE}
        for number in range(240):
            user_id = list(PEOPLE)[number % len(PEOPLE)]
            event_id = f"e{number:03d}"
            notification_repo.put_event(
                _event(
                    event_id,
                    recipient_id=user_id,
                    recipient_role=PEOPLE[user_id],
                    created_at=f"2026-11-24T10:{number // 60:02d}:{number % 60:02d}Z",
                )
            )
            expected[user_id].append(event_id)
        notification_repo.put_event(_event("for-admins", recipient_id=None, recipient_role="admin"))

        for user_id, role in PEOPLE.items():
            found = notification_repo.list_inbox(user_id=user_id, role=role)
            assert _ids(found) == expected[user_id]
            assert len(found) == 60
        assert _ids(notification_repo.list_inbox(user_id="admin-7", role="admin")) == ["for-admins"]
        _assert_every_inbox_holds_what_the_scan_finds(double)
    finally:
        db_table.install(None)


def test_an_inbox_is_read_by_queries_of_the_index_and_never_a_scan(table) -> None:
    notification_repo.put_event(_event("e1", recipient_id=TEACHER, recipient_role="teacher"))
    scans, queries = table.calls["scan"], table.calls["query"]

    notification_repo.list_inbox(user_id=TEACHER, role="teacher")

    assert table.calls["scan"] == scans
    assert table.calls["query"] == queries + 2
    requests = [request for operation, request in table.requests if operation == "query"][-2:]
    assert {request["IndexName"] for request in requests} == {notification_repo.INBOX_INDEX}


def test_a_row_of_another_kind_in_the_bucket_is_not_a_notification(table) -> None:
    table.seed(
        {
            "PK": "OTHER#1",
            "SK": "META",
            "entity_type": "something_else",
            "sweep_bucket": notification_repo.inbox_bucket(user_id=TEACHER),
            "sweep_due_at": CREATED,
        }
    )

    assert notification_repo.list_inbox(user_id=TEACHER, role="teacher") == []


def test_with_no_one_to_read_for_nothing_is_read(table) -> None:
    queries = table.calls["query"]

    assert notification_repo.list_inbox() == []
    assert table.calls["query"] == queries


# -- The backfill -----------------------------------------------------------------------


def _seed_legacy(table: FakeTable) -> None:
    table.seed(
        _legacy(_event("old-teacher", recipient_id=TEACHER, recipient_role="teacher")),
        _legacy(_event("old-student", recipient_id=STUDENT, recipient_role="student")),
        _legacy(_event("old-admins", recipient_id=None, recipient_role="admin")),
        _legacy(notification_repo.seal_global_nonprivate_event(_global_event("old-global"))),
    )
    notification_repo.put_event(_event("new", recipient_id=PARENT, recipient_role="parent"))


def test_the_dry_run_counts_and_writes_nothing(table, capsys) -> None:
    _seed_legacy(table)
    before = {key: dict(row) for key, row in table.rows.items()}

    assert backfill.run(table, apply_writes=False, verify_index=False) == 0

    assert table.rows == before
    printed = capsys.readouterr().out
    assert (
        "notifications: 5 | for one person: 3 | for a role: 2 | in no inbox: 0 | "
        "in place: 1 | to write: 4"
    ) in printed
    assert "[DRY RUN]" in printed


def test_before_the_backfill_the_check_fails_and_names_events_not_people(table, capsys) -> None:
    _seed_legacy(table)

    assert backfill.run(table, apply_writes=False, verify_index=True) == 1

    printed = capsys.readouterr().out
    assert "missing from its inbox: old-teacher" in printed
    assert not any(user_id in printed for user_id in PEOPLE)


def test_the_backfill_puts_every_old_notification_in_its_inbox(table, capsys) -> None:
    _seed_legacy(table)

    assert backfill.run(table, apply_writes=True, verify_index=False) == 0
    assert "in place: 1 | written: 4" in capsys.readouterr().out

    assert backfill.run(table, apply_writes=False, verify_index=True) == 0
    assert "Index problems: 0" in capsys.readouterr().out
    _assert_every_inbox_holds_what_the_scan_finds(table)
    sealed = notification_repo.seal_global_nonprivate_event(_global_event("old-global"))
    assert _row(table, "old-global")["classification_digest"] == sealed["classification_digest"]
    # Nothing but the two keys was added.
    old = _legacy(_event("old-teacher", recipient_id=TEACHER, recipient_role="teacher"))
    assert {k: v for k, v in _row(table, "old-teacher").items() if k not in INDEX_FIELDS} == old


def test_running_the_backfill_again_writes_nothing(table, capsys) -> None:
    _seed_legacy(table)
    backfill.run(table, apply_writes=True, verify_index=False)
    capsys.readouterr()
    before = {key: dict(row) for key, row in table.rows.items()}

    assert backfill.run(table, apply_writes=True, verify_index=False) == 0

    assert table.rows == before
    assert "in place: 5" in capsys.readouterr().out


def test_the_backfill_skips_a_notification_whose_owner_is_being_deleted(table, capsys) -> None:
    _seed_legacy(table)
    table.seed(_fence(STUDENT, status="deletion_pending"))

    assert backfill.run(table, apply_writes=True, verify_index=False) == 0

    assert "account closing or changed meanwhile, skipped: 3" in capsys.readouterr().out
    assert not INDEX_FIELDS & set(_row(table, "old-teacher"))
    assert INDEX_FIELDS <= set(_row(table, "old-global"))


def test_reindexing_a_row_already_replaced_by_a_tombstone_is_refused(table) -> None:
    read = _legacy(_event("old-teacher", recipient_id=TEACHER, recipient_role="teacher"))
    table.seed(
        {
            "PK": read["PK"],
            "SK": "META",
            "entity_type": "notification_event_deletion_tombstone",
            "status": "deleted",
        }
    )

    with pytest.raises(account_deletion_repo.AccountDeletionConflict):
        notification_repo.reindex_event(read, table=table)

    assert not INDEX_FIELDS & set(_row(table, "old-teacher"))


def test_a_global_notification_that_changed_is_not_reindexed(table) -> None:
    read = _legacy(notification_repo.seal_global_nonprivate_event(_global_event("old-global")))
    table.seed({**read, "created_at": "2026-11-25T00:00:00Z"})

    with pytest.raises(account_deletion_repo.AccountDeletionConflict):
        notification_repo.reindex_event(read, table=table)

    assert not INDEX_FIELDS & set(_row(table, "old-global"))
