"""Registering a push device again keeps one row and leaves it active.

A person whose app registers the same token twice (every launch does) reaches
the row they already have. That row was rewritten with every field the new
registration carries, `None` ones too; the gateway leaves a `None` value out of
the request but kept the `SET` that names it, so the table refused every second
registration. A field with no value now leaves the row, which is also how a
revoked device comes back: `status` active, `revoked_at` gone.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fakes.dynamodb import FakeTable

from stoa import config
from stoa.config import Settings
from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo, notification_repo
from stoa.services import notifications

STUDENT = "student-1"
GENERATION = 3


@pytest.fixture
def table() -> Iterator[FakeTable]:
    double = FakeTable()
    double.seed(
        {
            **account_deletion_repo.account_fence_key(STUDENT),
            "entity_type": "account_fence",
            "status": "active",
            "generation": GENERATION,
        }
    )
    db_table.install(double)
    config.install(Settings())
    try:
        yield double
    finally:
        db_table.install(None)
        config.install(None)


def _user() -> dict[str, str]:
    return {"sub": STUDENT, "role": "student"}


def _register(**kwargs: Any) -> dict[str, Any]:
    return notifications.register_push_token(_user(), platform="ios", **kwargs)


def _devices(table: FakeTable) -> list[dict[str, Any]]:
    return [
        row
        for row in table.rows.values()
        if row.get("entity_type") == notification_repo.PUSH_TOKEN_ENTITY
    ]


def test_registering_the_same_device_twice_keeps_one_active_row(table) -> None:
    first = _register(token="device-token")

    again = _register(token="device-token")

    assert again["tokenReference"] == first["tokenReference"]
    (row,) = _devices(table)
    assert row["status"] == "active"
    # A field with no value is not on the row, the first time or the second.
    assert "revoked_at" not in row
    assert "provider_token_reference" not in row
    assert "device_id_hash" not in row


def test_registering_a_revoked_device_again_makes_it_active(table) -> None:
    created = _register(token="device-token")
    notifications.revoke_authorized_push_token(
        {"user_id": _user()["sub"], "token_reference": created["tokenReference"]}
    )
    (revoked,) = _devices(table)
    assert revoked["status"] == "revoked"
    assert revoked["revoked_at"]

    _register(token="device-token")

    (row,) = _devices(table)
    assert row["status"] == "active"
    assert "revoked_at" not in row


def test_a_value_the_new_registration_drops_leaves_the_row(table) -> None:
    _register(token="device-token", provider_token_reference="provider-ref", device_id="phone")
    (before,) = _devices(table)
    assert before["provider_token_reference"] == "provider-ref"
    assert before["device_id_hash"]

    _register(token="device-token")

    (row,) = _devices(table)
    assert "provider_token_reference" not in row
    assert "device_id_hash" not in row
    # Its place in the device list follows what the provider is now sent.
    assert row["listing"] == notification_repo.push_token_device_listing(row["token_hash"])


def test_an_update_of_only_missing_values_removes_them() -> None:
    (operation,) = notification_repo.build_notification_write_transaction(
        item={"PK": "PUSH#x", "SK": "META"},
        owner_id=STUDENT,
        generation=GENERATION,
        mode="update",
        updates={"revoked_at": None},
    )

    update = operation["Update"]
    assert update["UpdateExpression"] == "REMOVE #revoked_at"
    assert update["ExpressionAttributeNames"] == {"#revoked_at": "revoked_at"}
    assert update["ExpressionAttributeValues"] == {":owner": STUDENT}
