"""Connections and push devices carry their place in the indexes they are found through (#624).

Each notification is pushed to the recipient's open connections, found by a
scan of the whole of `stoa-main` that kept the site's first 500 connection
rows; a push to the recipient's devices scanned the table too, and the check
that a device is not already someone else's looked at the site's first hundred
device rows. Now a connection carries its person's bucket in GSI-SweepPending
and its role's list in GSI-Listing; a push device carries its person's bucket
and its device's list. These tests hold every write of those rows to that, so
switching the readers from the scans to the indexes loses nothing. The
backfill puts the push devices registered before in place.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from typing import Any

import pytest
from fakes.dynamodb import DEFAULT_INDEXES, FakeTable, IndexSchema

from scripts import backfill_push_token_index as backfill
from stoa import config
from stoa.config import Settings
from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo, notification_repo, websocket_repo
from stoa.services import notification_service, websocket_service

STUDENT = "student-1"
OTHER_STUDENT = "student-2"
TEACHER = "teacher-1"
PEOPLE = {STUDENT: "student", OTHER_STUDENT: "student", TEACHER: "teacher"}
GENERATION = 3
CONNECTION_FIELDS = set(websocket_repo.INDEX_FIELDS)
PUSH_FIELDS = set(notification_repo.PUSH_TOKEN_INDEX_FIELDS)


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
    config.install(Settings())
    try:
        yield double
    finally:
        db_table.install(None)
        config.install(None)


def _user(user_id: str) -> dict[str, str]:
    return {"sub": user_id, "role": PEOPLE[user_id]}


def _connection_row(table: FakeTable, connection_id: str) -> dict[str, Any]:
    return table.rows[(websocket_repo.connection_pk(connection_id), "META")]


def _connect(connection_id: str, user_id: str) -> dict[str, Any]:
    return websocket_service.register_connection(connection_id=connection_id, user=_user(user_id))


def _ids(items: list[dict[str, Any]]) -> list[str]:
    return sorted(str(item["connection_id"]) for item in items)


def _scanned_connections(table: FakeTable) -> list[dict[str, Any]]:
    return [
        row
        for row in table.rows.values()
        if row.get("entity_type") == websocket_repo.CONNECTION_ENTITY
    ]


def _assert_every_connection_is_where_the_scan_finds_it(table: FakeTable) -> None:
    scanned = _scanned_connections(table)
    for user_id, role in PEOPLE.items():
        assert _ids(websocket_repo.list_user_connections(user_id, table=table)) == _ids(
            [row for row in scanned if row.get("user_id") == user_id]
        ), user_id
        assert _ids(websocket_repo.list_role_connections(role, table=table)) == _ids(
            [row for row in scanned if row.get("role") == role]
        ), role
    for row in scanned:
        assert websocket_repo.carried_index_fields(row) == websocket_repo.index_fields(row), row


# -- The indexes are the table's ---------------------------------------------------------


def test_the_indexes_are_ones_the_table_carries() -> None:
    assert DEFAULT_INDEXES[websocket_repo.USER_INDEX] == IndexSchema(*websocket_repo.USER_INDEX_FIELDS)
    assert DEFAULT_INDEXES[websocket_repo.ROLE_INDEX] == IndexSchema(*websocket_repo.ROLE_INDEX_FIELDS)
    assert DEFAULT_INDEXES[notification_repo.PUSH_TOKEN_USER_INDEX] == IndexSchema(
        "sweep_bucket", "sweep_due_at"
    )
    assert DEFAULT_INDEXES[notification_repo.PUSH_TOKEN_DEVICE_INDEX] == IndexSchema(
        "listing", "listed_at"
    )


def test_no_bucket_or_list_is_another_kinds() -> None:
    names = {
        websocket_repo.user_bucket("teacher"),
        websocket_repo.role_listing("teacher"),
        notification_repo.push_token_user_bucket("teacher"),
        notification_repo.push_token_device_listing("teacher"),
        notification_repo.inbox_bucket(user_id="teacher"),
        notification_repo.inbox_bucket(role="teacher"),
        notification_repo.LISTING_NAME,
    }
    assert len(names) == 7
    for empty in (
        lambda: websocket_repo.user_bucket(""),
        lambda: websocket_repo.role_listing(""),
        lambda: notification_repo.push_token_user_bucket(""),
        lambda: notification_repo.push_token_device_listing(""),
    ):
        with pytest.raises(ValueError):
            empty()


# -- Connections --------------------------------------------------------------------------


def test_a_connection_is_filed_under_its_person_and_its_role(table) -> None:
    _connect("c-1", TEACHER)

    row = _connection_row(table, "c-1")
    assert row["sweep_bucket"] == websocket_repo.user_bucket(TEACHER)
    assert row["listing"] == websocket_repo.role_listing("teacher")
    assert row["sweep_due_at"] == row["listed_at"] == row["connected_at"]
    assert _ids(websocket_repo.list_user_connections(TEACHER)) == ["c-1"]
    assert _ids(websocket_repo.list_role_connections("teacher")) == ["c-1"]
    assert websocket_repo.list_user_connections(STUDENT) == []
    assert websocket_repo.list_role_connections("student") == []
    _assert_every_connection_is_where_the_scan_finds_it(table)


def test_a_persons_connections_are_found_among_more_than_500_of_the_site(table) -> None:
    """The scan kept the site's first 500 connection rows, whoever's they were."""
    for number in range(520):
        _connect(f"c-{number:04d}", OTHER_STUDENT)
    _connect("c-mine", STUDENT)

    assert _ids(websocket_repo.list_user_connections(STUDENT)) == ["c-mine"]
    assert len(websocket_repo.list_role_connections("student")) == 521


def test_refreshing_or_subscribing_leaves_a_connection_where_it_is(table) -> None:
    _connect("c-1", STUDENT)
    before = websocket_repo.carried_index_fields(_connection_row(table, "c-1"))

    websocket_service.refresh_connection("c-1", _user(STUDENT))
    websocket_service.subscribe_connection("c-1", _user(STUDENT), [f"user:{STUDENT}"])

    assert websocket_repo.carried_index_fields(_connection_row(table, "c-1")) == before
    _assert_every_connection_is_where_the_scan_finds_it(table)


def test_a_connection_written_before_the_keys_gets_them_with_its_next_refresh(table) -> None:
    _connect("c-1", STUDENT)
    row = _connection_row(table, "c-1")
    for name in CONNECTION_FIELDS:
        row.pop(name)
    assert websocket_repo.list_user_connections(STUDENT) == []

    websocket_service.refresh_connection("c-1", _user(STUDENT))

    assert _ids(websocket_repo.list_user_connections(STUDENT)) == ["c-1"]
    assert _ids(websocket_repo.list_role_connections("student")) == ["c-1"]
    _assert_every_connection_is_where_the_scan_finds_it(table)


@pytest.mark.parametrize(
    "updates",
    [
        {"user_id": OTHER_STUDENT},
        {"role": "teacher"},
        {"connected_at": "2026-11-26T10:00:00+00:00"},
        {"sweep_bucket": "pending_generation"},
        {"listing": websocket_repo.role_listing("teacher")},
    ],
)
def test_no_update_moves_a_connection_to_another_person_role_or_time(table, updates) -> None:
    _connect("c-1", STUDENT)
    before = dict(_connection_row(table, "c-1"))

    with pytest.raises(ValueError):
        websocket_repo.update_connection("c-1", updates)

    assert _connection_row(table, "c-1") == before


def test_a_closed_connection_leaves_both_indexes(table) -> None:
    _connect("c-1", STUDENT)

    websocket_service.disconnect_connection("c-1")

    assert websocket_repo.list_user_connections(STUDENT) == []
    assert websocket_repo.list_role_connections("student") == []


@pytest.mark.parametrize(
    ("fields", "carried"),
    [
        ({"entity_type": "notification_event"}, set()),
        ({"connected_at": ""}, set()),
        ({"connected_at": None}, set()),
        ({"user_id": ""}, {"listing", "listed_at"}),
        ({"role": ""}, {"sweep_bucket", "sweep_due_at"}),
    ],
)
def test_an_index_key_of_a_connection_is_never_empty(fields, carried) -> None:
    row = {
        "entity_type": websocket_repo.CONNECTION_ENTITY,
        "connection_id": "c-1",
        "user_id": STUDENT,
        "role": "student",
        "connected_at": "2026-11-25T10:00:00+00:00",
        **fields,
    }
    found = websocket_repo.index_fields(row)
    assert set(found) == carried
    assert all(isinstance(value, str) and value for value in found.values())


# -- Push devices -------------------------------------------------------------------------


def _push_row(table: FakeTable, user_id: str, token_reference: str) -> dict[str, Any]:
    return table.rows[(notification_repo.push_token_pk(user_id, token_reference), "META")]


def _register(user_id: str, **kwargs: Any) -> dict[str, Any]:
    return notification_service.register_push_token(_user(user_id), platform="ios", **kwargs)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _scanned_devices(table: FakeTable) -> list[dict[str, Any]]:
    return [
        row
        for row in table.rows.values()
        if row.get("entity_type") == notification_repo.PUSH_TOKEN_ENTITY
    ]


def _refs(items: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return sorted((str(item["user_id"]), str(item["token_reference"])) for item in items)


def _assert_every_device_is_where_the_scan_finds_it(table: FakeTable) -> None:
    scanned = _scanned_devices(table)
    for user_id in PEOPLE:
        assert _refs(notification_repo.list_user_push_tokens(user_id, table=table)) == _refs(
            [row for row in scanned if row.get("user_id") == user_id]
        ), user_id
    for row in scanned:
        assert notification_repo.carried_push_token_index_fields(
            row
        ) == notification_repo.push_token_index_fields(row), row
        if "listing" in row:
            assert row in notification_repo.list_device_push_tokens(
                {notification_repo.push_token_device_key(row)}, table=table
            )


def test_a_device_is_filed_under_its_person_and_where_the_provider_reaches_it(table) -> None:
    created = _register(STUDENT, token="device-token")

    row = _push_row(table, STUDENT, created["tokenReference"])
    assert row["sweep_bucket"] == notification_repo.push_token_user_bucket(STUDENT)
    # No provider reference: the provider is sent the token's reference.
    assert row["listing"] == notification_repo.push_token_device_listing(_sha("device-token"))
    assert row["sweep_due_at"] == row["listed_at"] == row["created_at"]
    assert _refs(notification_repo.list_user_push_tokens(STUDENT)) == [
        (STUDENT, created["tokenReference"])
    ]
    assert notification_repo.list_user_push_tokens(OTHER_STUDENT) == []
    _assert_every_device_is_where_the_scan_finds_it(table)


def test_a_device_with_a_provider_reference_is_listed_under_the_reference(table) -> None:
    created = _register(STUDENT, token="device-token", provider_token_reference="provider-ref")

    row = _push_row(table, STUDENT, created["tokenReference"])
    assert row["listing"] == notification_repo.push_token_device_listing(_sha("provider-ref"))
    # A later registration of the same reference, with or without a token, reads that list.
    for token_hash, reference in ((_sha("other-token"), "provider-ref"), (_sha("provider-ref"), None)):
        keys = notification_repo.push_token_lookup_keys(
            token_hash=token_hash, provider_token_reference=reference
        )
        assert row in notification_repo.list_device_push_tokens(keys)
    _assert_every_device_is_where_the_scan_finds_it(table)


def test_a_device_registered_by_reference_only_is_found_by_a_token_of_the_same_value(table) -> None:
    _register(STUDENT, provider_token_reference="same-value")

    keys = notification_repo.push_token_lookup_keys(
        token_hash=_sha("same-value"), provider_token_reference=None
    )

    assert _refs(notification_repo.list_device_push_tokens(keys)) == [
        (STUDENT, "push-" + _sha("same-value")[:16])
    ]


def test_a_devices_registrations_are_found_among_more_than_100_of_the_site(table) -> None:
    """The ownership check looked at the site's first hundred device rows only."""
    for number in range(120):
        _register(OTHER_STUDENT, token=f"token-{number:04d}")
    created = _register(TEACHER, token="teacher-token")

    keys = notification_repo.push_token_lookup_keys(
        token_hash=_sha("teacher-token"), provider_token_reference=None
    )

    assert _refs(notification_repo.list_device_push_tokens(keys)) == [
        (TEACHER, created["tokenReference"])
    ]
    assert len(notification_repo.list_user_push_tokens(OTHER_STUDENT)) == 120


def test_revoking_a_device_leaves_it_where_it_is(table) -> None:
    created = _register(STUDENT, token="device-token")
    before = notification_repo.carried_push_token_index_fields(
        _push_row(table, STUDENT, created["tokenReference"])
    )

    notification_service.revoke_push_token(_user(STUDENT), created["tokenReference"])

    row = _push_row(table, STUDENT, created["tokenReference"])
    assert notification_repo.carried_push_token_index_fields(row) == before
    assert notification_repo.list_user_push_tokens(STUDENT, status="active") == []
    assert _refs(notification_repo.list_user_push_tokens(STUDENT, status="revoked")) == [
        (STUDENT, created["tokenReference"])
    ]
    _assert_every_device_is_where_the_scan_finds_it(table)


def _legacy_device(table: FakeTable, user_id: str, token: str) -> dict[str, Any]:
    created = _register(user_id, token=token)
    row = _push_row(table, user_id, created["tokenReference"])
    for name in PUSH_FIELDS:
        row.pop(name)
    return row


def test_a_device_written_before_the_keys_gets_them_when_it_is_revoked(table) -> None:
    row = _legacy_device(table, STUDENT, "device-token")
    assert notification_repo.list_user_push_tokens(STUDENT) == []

    notification_service.revoke_push_token(_user(STUDENT), row["token_reference"])

    assert _refs(notification_repo.list_user_push_tokens(STUDENT)) == [
        (STUDENT, row["token_reference"])
    ]
    _assert_every_device_is_where_the_scan_finds_it(table)


def test_the_owners_deletion_takes_a_device_out_of_both_indexes(table) -> None:
    created = _register(STUDENT, token="device-token")
    row = dict(_push_row(table, STUDENT, created["tokenReference"]))
    table.seed(_fence(STUDENT, status="deletion_pending"))

    notification_repo.scrub_notification_private_row(
        row,
        owner_id=STUDENT,
        generation=GENERATION,
        now_iso="2026-11-25T00:00:00Z",
        table=table,
    )

    tombstone = table.rows[(row["PK"], row["SK"])]
    assert not PUSH_FIELDS & set(tombstone)
    assert notification_repo.push_token_index_fields(tombstone) == {}
    assert notification_repo.list_user_push_tokens(STUDENT) == []
    assert notification_repo.list_device_push_tokens({_sha("device-token")}) == []


@pytest.mark.parametrize(
    ("fields", "carried"),
    [
        ({"entity_type": "notification_preference"}, set()),
        ({"created_at": ""}, set()),
        ({"user_id": ""}, {"listing", "listed_at"}),
        ({"token_hash": "", "provider_token_reference": None}, {"sweep_bucket", "sweep_due_at"}),
    ],
)
def test_an_index_key_of_a_device_is_never_empty(fields, carried) -> None:
    row = {
        "entity_type": notification_repo.PUSH_TOKEN_ENTITY,
        "user_id": STUDENT,
        "token_reference": "push-1",
        "token_hash": _sha("device-token"),
        "provider_token_reference": None,
        "created_at": "2026-11-25T10:00:00+00:00",
        **fields,
    }
    found = notification_repo.push_token_index_fields(row)
    assert set(found) == carried
    assert all(isinstance(value, str) and value for value in found.values())


# -- The backfill -------------------------------------------------------------------------


def test_the_backfill_counts_writes_and_verifies_the_devices_registered_before(table, capsys) -> None:
    for number in range(3):
        _legacy_device(table, STUDENT, f"token-{number}")
    _legacy_device(table, TEACHER, "teacher-token")
    _register(OTHER_STUDENT, token="already-in-place")

    assert backfill.run(table, apply_writes=False, verify_index=False) == 0
    assert "push devices: 5 | active: 5 | in no index: 0 | in place: 1 | to write: 4" in capsys.readouterr().out
    assert backfill.run(table, apply_writes=False, verify_index=True) == 1
    assert notification_repo.list_user_push_tokens(STUDENT) == []

    assert backfill.run(table, apply_writes=True, verify_index=False) == 0
    assert "in place: 1 | written: 4" in capsys.readouterr().out

    assert backfill.run(table, apply_writes=False, verify_index=True) == 0
    assert "Index problems: 0" in capsys.readouterr().out
    _assert_every_device_is_where_the_scan_finds_it(table)
    # A second run has nothing left to write.
    assert backfill.apply(table, notification_repo.list_all_push_tokens(table=table)) == {
        "in place": 5
    }


def test_the_backfill_skips_a_device_whose_owner_is_being_deleted(table) -> None:
    row = _legacy_device(table, STUDENT, "device-token")
    table.seed(_fence(STUDENT, status="deletion_pending"))

    outcome = backfill.apply(table, [dict(row)])

    assert outcome == {"account closing or changed meanwhile, skipped": 1}
    assert not PUSH_FIELDS & set(_push_row(table, STUDENT, row["token_reference"]))


def test_the_backfill_names_no_person_or_device(table, capsys) -> None:
    _legacy_device(table, STUDENT, "device-token")
    row = _push_row(table, STUDENT, "push-" + _sha("device-token")[:16])
    row["listing"] = notification_repo.push_token_device_listing("somewhere-else")

    backfill.run(table, apply_writes=False, verify_index=True)

    out = capsys.readouterr().out
    assert "problems: 0" not in out
    assert STUDENT not in out
    assert _sha("device-token") not in out
