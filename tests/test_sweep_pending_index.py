"""Message commands the sweep acts on carry their place in `GSI-SweepPending` (#502).

The generation sweep finds its commands with a filtered scan of the whole of
`stoa-main`, so the time to cover the table grows with the table. The sparse
index holds only the commands the sweep may act on: each one carries
`sweep_bucket`, and `sweep_due_at` says when the sweep may first act on it.
Every write that moves a command into such a state sets both; every write that
moves it out removes them.

These hold each transition to that, and a seeded walk over the store's writes
holds the index to exactly what the scan's filter admits, so switching the
sweep from the scan to the index loses no command.
"""

from __future__ import annotations

import random
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from fakes.ask_question import (
    CONV,
    STUDENT,
    _command_key,
    _command_row,
    _commit,
    _deliver,
)
from fakes.ask_question import model as model  # noqa: F401 - the fixture
from fakes.ask_question import table as table  # noqa: F401 - the fixture
from fakes.dynamodb import DEFAULT_INDEXES, IndexSchema
from stoa.db.repositories import attachment_repo
from stoa.services import learning_session
from stoa.services.ask_question import _store

KEY = "key-1"


def _due(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parsed(value: object) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _row(table, key: str = KEY) -> dict[str, Any]:
    return dict(_command_row(table, key))


def _indexed(table) -> dict[tuple[str, str], dict[str, Any]]:
    """What a query of the index returns, all of it, by base-table key."""
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    start: dict[str, Any] | None = None
    while True:
        request: dict[str, Any] = {
            "IndexName": _store.SWEEP_PENDING_INDEX,
            "KeyConditionExpression": "sweep_bucket=:bucket",
            "ExpressionAttributeValues": {":bucket": _store.SWEEP_PENDING_BUCKET},
        }
        if start is not None:
            request["ExclusiveStartKey"] = start
        page = table.query(**request)
        rows.update({(item["PK"], item["SK"]): item for item in page["Items"]})
        start = page.get("LastEvaluatedKey")
        if not start:
            return rows


def _admitted(table) -> set[tuple[str, str]]:
    """What the sweep's scan filter admits, over the whole table."""
    commands, last_key = _store.scan_generation_sweep_commands(table=table, max_pages=10_000)
    assert last_key is None
    return {(str(command["PK"]), str(command["SK"])) for command in commands}


def _generation(table) -> int:
    return int(_row(table)["account_fence_generation"])


def _claim(table, *, lease_owner: str = "lease-1", now: datetime | None = None) -> int:
    """Claim the command's lease for five minutes; the lease's expiry."""
    now = now or datetime.now(UTC)
    expires = int((now + timedelta(minutes=5)).timestamp())
    result = _store.claim_message_ai_lease(
        conversation_id=CONV,
        idempotency_key=KEY,
        owner_id=STUDENT,
        lease_owner=lease_owner,
        now_epoch=int(now.timestamp()),
        expires_at=expires,
        account_fence_generation=_generation(table),
    )
    assert result.disposition is _store.MessageCommandDisposition.CLAIMED, result
    return expires


def _fail(table, category: str, *, retryable: bool = False) -> str:
    row = _row(table)
    failed_at = datetime.now(UTC).isoformat()
    assert _store.fail_message_command(
        conversation_id=CONV,
        idempotency_key=KEY,
        owner_id=STUDENT,
        lease_owner=str(row["leaseOwner"]),
        lease_attempt=int(row["attempt"]),
        failure_category=category,
        retryable=retryable,
        now_iso=failed_at,
    )
    return failed_at


# ── The double carries the index ─────────────────────────────────────────────


def test_the_double_carries_the_sweep_index() -> None:
    assert DEFAULT_INDEXES[_store.SWEEP_PENDING_INDEX] == IndexSchema(
        "sweep_bucket", "sweep_due_at"
    )


# ── Into the index ───────────────────────────────────────────────────────────


def test_a_committed_question_is_due_once_its_invoke_had_time_to_arrive(table) -> None:
    _commit(KEY)

    row = _row(table)
    assert row["status"] == "message_committed"
    assert row["sweep_bucket"] == _store.SWEEP_PENDING_BUCKET
    committed = _parsed(row["message_committed_at"])
    assert row["sweep_due_at"] == _due(committed + _store.UNCLAIMED_AFTER)
    assert set(_indexed(table)) == {tuple(_command_key(CONV, KEY).values())}


def test_a_claimed_attempt_is_due_when_its_lease_runs_out(table) -> None:
    _commit(KEY)
    expires = _claim(table)

    row = _row(table)
    assert row["status"] == "ai_running"
    assert row["sweep_bucket"] == _store.SWEEP_PENDING_BUCKET
    assert row["sweep_due_at"] == _due(datetime.fromtimestamp(expires, UTC))


def test_a_renewed_lease_moves_the_due_time_with_it(table) -> None:
    _commit(KEY)
    _claim(table)
    later = datetime.now(UTC) + timedelta(minutes=3)
    renewed_to = int((later + timedelta(minutes=5)).timestamp())

    assert _store.renew_message_ai_lease(
        conversation_id=CONV,
        idempotency_key=KEY,
        owner_id=STUDENT,
        lease_owner="lease-1",
        now_epoch=int(datetime.now(UTC).timestamp()),
        expires_at=renewed_to,
        account_fence_generation=_generation(table),
    )

    assert _row(table)["sweep_due_at"] == _due(datetime.fromtimestamp(renewed_to, UTC))


@pytest.mark.parametrize("category", sorted(_store.UNSETTLED_RESERVATION_FAILURES))
def test_a_failure_holding_its_reservation_is_due_when_it_may_be_settled(
    table, category: str
) -> None:
    _commit(KEY)
    _claim(table)
    failed_at = _fail(table, category)

    row = _row(table)
    assert row["sweep_bucket"] == _store.SWEEP_PENDING_BUCKET
    assert row["sweep_due_at"] == _due(_parsed(failed_at) + _store.SETTLE_AFTER[category])


def test_a_sent_again_failure_is_waiting_again(table) -> None:
    _commit(KEY)
    _claim(table)
    _fail(table, "provider_unavailable", retryable=True)
    assert "sweep_bucket" not in _row(table)
    reopened_at = datetime.now(UTC).isoformat()

    assert _store.reopen_failed_message_command(
        conversation_id=CONV,
        idempotency_key=KEY,
        owner_id=STUDENT,
        attempt=int(_row(table)["attempt"]),
        now_iso=reopened_at,
    )

    row = _row(table)
    assert row["status"] == "message_committed"
    assert row["sweep_bucket"] == _store.SWEEP_PENDING_BUCKET
    assert row["sweep_due_at"] == _due(_parsed(reopened_at) + _store.UNCLAIMED_AFTER)


def test_a_lease_nobody_took_up_ends_due_for_settlement(table) -> None:
    _commit(KEY)
    started = datetime.now(UTC) - timedelta(hours=1)
    expires = _claim(table, now=started)
    now = datetime.now(UTC)

    assert _store.close_stale_lease(
        conversation_id=CONV,
        idempotency_key=KEY,
        owner_id=STUDENT,
        lease_owner="lease-1",
        expires_at=expires,
        now_epoch=int(now.timestamp()),
        now_iso=now.isoformat(),
    )

    row = _row(table)
    assert row["status"] == "terminal_failed"
    assert row["sweep_bucket"] == _store.SWEEP_PENDING_BUCKET
    assert row["sweep_due_at"] == _due(now + _store.SETTLE_TERMINAL_AFTER)


def test_attempts_used_up_end_due_for_settlement(table) -> None:
    _commit(KEY)
    _claim(table)
    row = _row(table)
    row["attempt"] = _store.MESSAGE_AI_MAX_ATTEMPTS
    table.seed(row)
    ended = datetime.now(UTC)

    result = _store.mark_message_command_terminal(
        conversation_id=CONV, idempotency_key=KEY, owner_id=STUDENT, now_iso=ended.isoformat()
    )

    assert result.disposition is _store.MessageCommandDisposition.TERMINAL
    row = _row(table)
    assert row["sweep_bucket"] == _store.SWEEP_PENDING_BUCKET
    assert row["sweep_due_at"] == _due(ended + _store.SETTLE_TERMINAL_AFTER)


# ── Out of the index ─────────────────────────────────────────────────────────


def test_an_answered_question_leaves(table, model) -> None:
    _commit(KEY)
    assert "sweep_bucket" in _row(table)

    _deliver(KEY)

    row = _row(table)
    assert row["status"] == "completed"
    assert "sweep_bucket" not in row and "sweep_due_at" not in row
    assert _indexed(table) == {}


def test_a_failure_the_student_may_send_again_leaves(table) -> None:
    _commit(KEY)
    _claim(table)

    _fail(table, "provider_unavailable", retryable=True)

    row = _row(table)
    assert row["status"] == "failed"
    assert "sweep_bucket" not in row and "sweep_due_at" not in row


@pytest.mark.parametrize("status", ["failed", "terminal_failed"])
def test_a_settled_reservation_leaves(table, status: str) -> None:
    _commit(KEY)
    _claim(table)
    if status == "failed":
        ended_at = _fail(table, "needs_reconciliation")
    else:
        row = _row(table)
        row["attempt"] = _store.MESSAGE_AI_MAX_ATTEMPTS
        table.seed(row)
        ended_at = datetime.now(UTC).isoformat()
        _store.mark_message_command_terminal(
            conversation_id=CONV, idempotency_key=KEY, owner_id=STUDENT, now_iso=ended_at
        )
    assert "sweep_bucket" in _row(table)

    assert _store.mark_allowance_settled(
        conversation_id=CONV,
        idempotency_key=KEY,
        owner_id=STUDENT,
        status=status,
        ended_at=ended_at,
        now_iso=datetime.now(UTC).isoformat(),
    )

    row = _row(table)
    assert "allowance_settled_at" in row
    assert "sweep_bucket" not in row and "sweep_due_at" not in row


def test_a_command_canceled_by_account_deletion_leaves(table) -> None:
    """Deletion replaces the row with its tombstone, which keeps an allowlist."""
    _commit(KEY)
    row = _row(table)
    assert "sweep_bucket" in row

    tombstone = attachment_repo._conversation_tombstone(
        row, owner_id=STUDENT, generation=2, now_iso=datetime.now(UTC).isoformat()
    )

    assert "sweep_bucket" not in tombstone and "sweep_due_at" not in tombstone


# ── The index is the scan's filter ───────────────────────────────────────────


def _walk_step(table, rng: random.Random, clock: list[datetime]) -> None:
    """One of the store's writes, with arguments read from the row as a caller would.

    Most are refused in most states; a refused write must change nothing.
    """
    clock[0] += timedelta(minutes=rng.choice([0, 1, 4, 11, 21]))
    now = clock[0]
    row = _row(table)
    identity = {"conversation_id": CONV, "idempotency_key": KEY, "owner_id": STUDENT}
    lease_owner = str(row.get("leaseOwner") or "lease-none")
    attempt = int(row.get("attempt") or 0)
    step = rng.randrange(9)
    if step == 0:
        _store.claim_message_ai_lease(
            **identity,
            lease_owner=f"lease-{rng.randrange(1000)}",
            now_epoch=int(now.timestamp()),
            expires_at=int((now + timedelta(minutes=5)).timestamp()),
            account_fence_generation=_generation(table),
        )
    elif step == 1:
        _store.renew_message_ai_lease(
            **identity,
            lease_owner=lease_owner,
            now_epoch=int(now.timestamp()),
            expires_at=int((now + timedelta(minutes=5)).timestamp()),
            account_fence_generation=_generation(table),
        )
    elif step == 2:
        _store.complete_message_command(
            **identity,
            lease_owner=lease_owner,
            assistant_message_put=learning_session.append(
                CONV,
                role="assistant",
                message_id=f"assistant-{rng.randrange(10**6)}",
                student_id=STUDENT,
                generation=_generation(table),
                content="answer",
                created_at=now.isoformat(),
                structured=None,
            ),
            result_json='{"studentMessage":{},"assistantMessage":{}}',
            completed_at=now.isoformat(),
            lease_attempt=max(attempt, 1),
            completed_epoch=int(now.timestamp()),
            account_fence_generation=_generation(table),
        )
    elif step == 3:
        category = rng.choice(
            [*sorted(_store.UNSETTLED_RESERVATION_FAILURES), "provider_unavailable"]
        )
        _store.fail_message_command(
            **identity,
            lease_owner=lease_owner,
            lease_attempt=attempt,
            failure_category=category,
            retryable=category == "provider_unavailable",
            now_iso=now.isoformat(),
        )
    elif step == 4:
        _store.reopen_failed_message_command(
            **identity, attempt=attempt, now_iso=now.isoformat()
        )
    elif step == 5:
        _store.close_stale_lease(
            **identity,
            lease_owner=lease_owner,
            expires_at=int(row.get("expiresAt") or 0),
            now_epoch=int(now.timestamp()),
            now_iso=now.isoformat(),
        )
    elif step == 6:
        _store.mark_message_command_terminal(**identity, now_iso=now.isoformat())
    elif step == 7:
        status = str(row.get("status"))
        if status in _store.SETTLEMENT_ENDED_AT:
            ended_at = str(row.get(_store.SETTLEMENT_ENDED_AT[status]) or "")
            if status == "failed":
                _store.close_failure_for_settlement(**identity, failed_at=ended_at)
            _store.mark_allowance_settled(
                **identity, status=status, ended_at=ended_at, now_iso=now.isoformat()
            )
    else:
        # The last attempt, so the terminal mark has something to end.
        if row.get("status") == "ai_running":
            row["attempt"] = _store.MESSAGE_AI_MAX_ATTEMPTS
            table.seed(row)


def test_the_index_holds_exactly_what_the_scan_admits(table) -> None:
    """After every write of a seeded walk, the index and the scan's filter agree.

    Each walk starts from the same committed question. Over all of them the
    walk has to reach every state the sweep acts on, in and out of the index,
    or agreeing would prove little.
    """
    _commit(KEY)
    committed = deepcopy(table.rows)
    seen: set[tuple[str, bool]] = set()
    for seed in range(40):
        table.rows = deepcopy(committed)
        rng = random.Random(seed)
        clock = [datetime.now(UTC)]
        for step in range(25):
            _walk_step(table, rng, clock)
            row = _row(table)
            assert set(_indexed(table)) == _admitted(table), (seed, step, row)
            assert ("sweep_bucket" in row) == ("sweep_due_at" in row), (seed, step, row)
            seen.add((str(row.get("status")), "sweep_bucket" in row))
    assert {
        ("message_committed", True),
        ("ai_running", True),
        ("failed", True),
        ("failed", False),
        ("terminal_failed", True),
        ("terminal_failed", False),
        ("completed", False),
    } <= seen, seen
