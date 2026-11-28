"""A help request carries its place in the two indexes it is found through (#608).

Finding requests by `help_requests.list_all` scans the whole of `stoa-main`, so
the sweep every five minutes and a teacher's open queue every fifteen seconds
each read every row of the table. Two sparse indexes hold what they need: a
request not yet ended carries `sweep_bucket` and `sweep_due_at`
(GSI-SweepPending, in a bucket of its own), and a request a teacher holds
carries `started_at` beside `teacher_id` (GSI-TeacherId).

These hold every write of the record to that: after each move the indexes hold
exactly what the scan finds, so switching the readers from the scan to the
indexes loses no request. The backfill puts the records written before in place.
"""

from __future__ import annotations

from typing import Any

import pytest

import deletion_helpers
from fakes.dynamodb import DEFAULT_INDEXES, FakeTable, IndexSchema

from scripts import backfill_help_request_index as backfill
from stoa.db.repositories import account_deletion_repo
from stoa.services import help_requests
from stoa.services.ask_question import _store
from test_chat_help_request_lifecycle import (
    CONV,
    OTHER_TEACHER,
    STUDENT,
    TEACHER,
    _client,
    _delete_teacher,
    _dispatch_to,
    _help,
    _set_status,
)
from test_chat_help_request_lifecycle import table as table  # noqa: F401 - the fixture

ASKED = "2026-09-28T12:00:00Z"
OPEN_FIELDS = set(help_requests.OPEN_INDEX_FIELDS)


def _ids(records: list[dict[str, Any]]) -> list[str]:
    return sorted(str(record["conversation_id"]) for record in records)


def _assert_indexes_hold_what_the_scan_finds(table: FakeTable) -> None:
    """Both indexes against the scan they replace, over the whole table."""
    scanned = help_requests.list_all(table=table)
    assert _ids(help_requests.list_unended(table=table)) == _ids(
        [record for record in scanned if help_requests.stored_status(record) in help_requests.OPEN]
    )
    for teacher in (TEACHER, OTHER_TEACHER):
        assert _ids(help_requests.list_held_by(teacher, table=table)) == _ids(
            [record for record in scanned if record.get("teacher_id") == teacher]
        ), teacher
    for record in scanned:
        carried = {name: record[name] for name in help_requests.INDEX_FIELDS if name in record}
        assert carried == help_requests.index_fields(record), record


# ── The indexes are the table's ──────────────────────────────────────────────


def test_the_indexes_are_ones_the_table_carries() -> None:
    assert DEFAULT_INDEXES[help_requests.OPEN_INDEX] == IndexSchema(*help_requests.OPEN_INDEX_FIELDS)
    assert DEFAULT_INDEXES[help_requests.HOLDER_INDEX] == IndexSchema(
        "teacher_id", help_requests.HOLDER_INDEX_FIELD
    )


def test_requests_share_the_generation_sweeps_index_but_not_its_bucket(table) -> None:
    """The generation sweep (#502) queries its own bucket and never reads a request."""
    assert help_requests.OPEN_INDEX == _store.SWEEP_PENDING_INDEX
    assert help_requests.OPEN_BUCKET != _store.SWEEP_PENDING_BUCKET
    _dispatch_to(table, TEACHER)
    assert _help(table)["sweep_bucket"] == help_requests.OPEN_BUCKET

    from datetime import UTC, datetime

    commands, complete = _store.query_generation_sweep_commands(
        now=datetime(2100, 1, 1, tzinfo=UTC), table=table
    )

    assert (commands, complete) == ([], True)


# ── Each move of a request ───────────────────────────────────────────────────


def test_an_offer_files_a_waiting_request_under_when_it_was_asked(table) -> None:
    _dispatch_to(table, TEACHER)

    record = _help(table)
    assert record["sweep_bucket"] == help_requests.OPEN_BUCKET
    assert record["sweep_due_at"] == ASKED
    # Offered is not held: only the teacher who takes it has it in their index.
    assert help_requests.HOLDER_INDEX_FIELD not in record
    assert help_requests.list_held_by(TEACHER, table=table) == []
    _assert_indexes_hold_what_the_scan_finds(table)


def test_the_teacher_who_takes_a_request_has_it_in_their_index(table) -> None:
    _dispatch_to(table, TEACHER)
    assert _set_status(_client(), "in_progress").status_code == 200

    record = _help(table)
    assert record["sweep_bucket"] == help_requests.OPEN_BUCKET
    assert record[help_requests.HOLDER_INDEX_FIELD] == help_requests._index_time(record["accepted_at"])
    assert _ids(help_requests.list_held_by(TEACHER, table=table)) == [CONV]
    assert help_requests.list_held_by(OTHER_TEACHER, table=table) == []
    _assert_indexes_hold_what_the_scan_finds(table)


@pytest.mark.parametrize("accept_first", [True, False], ids=["accepted", "from_the_offer"])
def test_resolving_takes_a_request_out_of_the_open_index_and_leaves_it_its_teachers(
    table, accept_first
) -> None:
    _dispatch_to(table, TEACHER)
    teacher = _client()
    if accept_first:
        assert _set_status(teacher, "in_progress").status_code == 200
    assert _set_status(teacher, "resolved").status_code == 200

    record = _help(table)
    assert not OPEN_FIELDS & set(record)
    assert help_requests.list_unended(table=table) == []
    assert _ids(help_requests.list_held_by(TEACHER, table=table)) == [CONV]
    _assert_indexes_hold_what_the_scan_finds(table)


def test_withdrawing_takes_a_request_out_of_the_open_index(table) -> None:
    _dispatch_to(table, TEACHER)

    ended = help_requests.withdraw(CONV, student_id=STUDENT, table=table)

    assert ended["escalation_status"] == "withdrawn"
    assert not set(help_requests.INDEX_FIELDS) & set(_help(table))
    _assert_indexes_hold_what_the_scan_finds(table)


def test_expiring_takes_a_request_out_of_the_open_index(table) -> None:
    _dispatch_to(table, TEACHER)

    ended = help_requests.expire(CONV, asked_before="2100-01-01T00:00:00+00:00", table=table)

    assert ended is not None and ended["escalation_status"] == "expired"
    assert not set(help_requests.INDEX_FIELDS) & set(_help(table))
    _assert_indexes_hold_what_the_scan_finds(table)


def test_finding_nobody_keeps_a_waiting_request_in_the_open_index(table) -> None:
    for teacher in (TEACHER, OTHER_TEACHER):
        table.rows[(f"USER#{teacher}", "PROFILE")]["dispatch_availability"] = "paused"
    # A change the write records: the seeded record already says `not_available`.
    _help(table)["dispatch_no_candidate_reason"] = "max_active_sessions"

    written = help_requests.dispatch(dict(_help(table)), table=table)

    assert written["dispatch_status"] == "no_candidate"
    assert written["sweep_bucket"] == _help(table)["sweep_bucket"] == help_requests.OPEN_BUCKET
    _assert_indexes_hold_what_the_scan_finds(table)


# ── The readers: the sweep and a teacher's queue ─────────────────────────────


def _scans(table: FakeTable) -> list[dict[str, Any]]:
    return [call for name, call in table.requests if name == "scan"]


def test_the_sweep_finds_a_waiting_request_without_scanning_the_table(table) -> None:
    for teacher in (TEACHER, OTHER_TEACHER):
        table.rows[(f"USER#{teacher}", "PROFILE")]["dispatch_availability"] = "paused"
    table.rows[(f"USER#{TEACHER}", "PROFILE")]["dispatch_availability"] = "available"
    table.requests.clear()

    outcome = help_requests.sweep(table=table)

    assert outcome["conversationSweep"] == "completed"
    assert outcome["conversationsDispatched"] == [{"conversationId": CONV, "status": "dispatched"}]
    assert _help(table)["dispatched_teacher_id"] == TEACHER
    assert _scans(table) == []


def test_a_teachers_queue_and_stats_are_read_without_scanning_the_table(table) -> None:
    _dispatch_to(table, TEACHER)
    teacher, other = _client(), _client(OTHER_TEACHER)
    table.requests.clear()

    # Offered: in the teacher's queue through the index of requests not yet ended.
    listed = teacher.get("/teachers/me/help-requests")
    assert listed.status_code == 200, listed.text
    assert [item["conversationId"] for item in listed.json()["items"]] == [CONV]
    assert other.get("/teachers/me/help-requests").json()["items"] == []

    # Resolved: out of that index, still theirs through the one of requests held.
    assert _set_status(teacher, "resolved").status_code == 200
    listed = teacher.get("/teachers/me/help-requests")
    assert [(item["conversationId"], item["status"]) for item in listed.json()["items"]] == [
        (CONV, "resolved")
    ]
    assert other.get("/teachers/me/help-requests").json()["items"] == []
    stats = teacher.get("/teachers/me/stats")
    assert stats.status_code == 200, stats.text
    assert stats.json()["resolvedToday"] == 1

    assert _scans(table) == []


def test_a_request_in_both_indexes_is_listed_once(table) -> None:
    _dispatch_to(table, TEACHER)
    assert _set_status(_client(), "in_progress").status_code == 200

    assert _ids(help_requests.list_for_teacher(TEACHER, table=table)) == [CONV]
    # Not this teacher's, but not yet ended: listed, and refused by the policy.
    assert _ids(help_requests.list_for_teacher(OTHER_TEACHER, table=table)) == [CONV]
    assert _client(OTHER_TEACHER).get("/teachers/me/help-requests").json()["items"] == []


# ── Account deletion ─────────────────────────────────────────────────────────


def test_deleting_the_teacher_puts_a_held_request_back_in_the_open_index_only(table) -> None:
    _dispatch_to(table, TEACHER)
    assert _set_status(_client(), "in_progress").status_code == 200

    command = _delete_teacher(table)

    assert command["status"] == "complete"
    record = _help(table)
    assert record["escalation_status"] == "pending"
    assert record["sweep_bucket"] == help_requests.OPEN_BUCKET
    assert help_requests.HOLDER_INDEX_FIELD not in record
    assert help_requests.list_held_by(TEACHER, table=table) == []
    _assert_indexes_hold_what_the_scan_finds(table)


def test_deleting_the_teacher_takes_a_resolved_request_out_of_both_indexes(table) -> None:
    _dispatch_to(table, TEACHER)
    assert _set_status(_client(), "resolved").status_code == 200

    command = _delete_teacher(table)

    assert command["status"] == "complete"
    assert not set(help_requests.INDEX_FIELDS) & set(_help(table))
    _assert_indexes_hold_what_the_scan_finds(table)


def test_the_students_deletion_leaves_a_tombstone_in_neither_index(table) -> None:
    _dispatch_to(table, TEACHER)
    assert _set_status(_client(), "in_progress").status_code == 200

    # The student's whole deletion: the catalog's tombstone for the request (#642).
    deletion_helpers.delete_account(STUDENT)

    tombstone = _help(table)
    assert account_deletion_repo.is_deletion_tombstone(tombstone)
    assert not ({*help_requests.INDEX_FIELDS, "teacher_id"} & set(tombstone))
    assert help_requests.list_unended(table=table) == []
    assert help_requests.list_held_by(TEACHER, table=table) == []


# ── What the keys are derived from ───────────────────────────────────────────


def test_the_keys_follow_the_state_alone() -> None:
    asked = {"escalated_at": "2026-09-28T14:00:00+02:00"}
    assert help_requests.index_fields({**asked, "escalation_status": "pending"}) == {
        "sweep_bucket": help_requests.OPEN_BUCKET,
        "sweep_due_at": ASKED,
    }
    # A record stored without a status is pending (`stored_status`).
    assert set(help_requests.index_fields(asked)) == OPEN_FIELDS
    assert help_requests.index_fields(
        {**asked, "escalation_status": "resolved", "teacher_id": "t", "accepted_at": "2026-09-28T12:05:00.5+00:00"}
    ) == {"started_at": "2026-09-28T12:05:00Z"}
    for ended in ("resolved", "withdrawn", "expired"):
        assert help_requests.index_fields({**asked, "escalation_status": ended}) == {}


def test_a_record_whose_times_cannot_be_read_is_filed_first_not_left_out() -> None:
    fields = help_requests.index_fields({"escalated_at": "soon", "teacher_id": "t"})

    assert fields["sweep_due_at"] == fields["started_at"] == "1970-01-01T00:00:00Z"
    assert all(fields.values())


# ── The backfill ─────────────────────────────────────────────────────────────


def _before_608(table: FakeTable) -> None:
    for name in help_requests.INDEX_FIELDS:
        _help(table).pop(name, None)


def test_a_record_written_before_is_indexed_once_and_its_version_does_not_move(table) -> None:
    _before_608(table)
    version = _help(table)["version"]
    assert not set(help_requests.INDEX_FIELDS) & set(_help(table))
    assert help_requests.list_unended(table=table) == []

    assert help_requests.reindex(dict(_help(table)), table=table) is True

    assert _ids(help_requests.list_unended(table=table)) == [CONV]
    assert _help(table)["version"] == version
    assert help_requests.reindex(dict(_help(table)), table=table) is False
    _assert_indexes_hold_what_the_scan_finds(table)


def test_reindexing_removes_keys_a_record_should_no_longer_carry(table) -> None:
    _dispatch_to(table, TEACHER)
    assert _set_status(_client(), "resolved").status_code == 200
    _help(table).update(sweep_bucket=help_requests.OPEN_BUCKET, sweep_due_at=ASKED)

    assert help_requests.reindex(dict(_help(table)), table=table) is True

    assert not OPEN_FIELDS & set(_help(table))
    _assert_indexes_hold_what_the_scan_finds(table)


def test_a_record_that_moved_since_it_was_read_is_not_reindexed(table) -> None:
    _before_608(table)
    read = dict(_help(table))
    _dispatch_to(table, TEACHER)
    after = dict(_help(table))

    with pytest.raises(help_requests.HelpRequestConflict):
        help_requests.reindex(read, table=table)

    assert _help(table) == after


def test_the_backfill_dry_run_counts_and_writes_nothing(table, capsys) -> None:
    _before_608(table)
    before = {key: dict(row) for key, row in table.rows.items()}

    assert backfill.run(table, apply_writes=False, verify_index=False) == 0

    assert table.rows == before
    out = capsys.readouterr().out
    assert "requests: 1 | not ended: 1 | held by a teacher: 0 | in place: 0 | to write: 1" in out
    assert "[DRY RUN]" in out


def test_the_backfill_writes_each_record_once_and_verifies(table, capsys) -> None:
    _dispatch_to(table, TEACHER)
    assert _set_status(_client(), "in_progress").status_code == 200
    _before_608(table)
    assert backfill.run(table, apply_writes=False, verify_index=True) == 1

    assert backfill.run(table, apply_writes=True, verify_index=False) == 0

    assert "written: 1" in capsys.readouterr().out
    _assert_indexes_hold_what_the_scan_finds(table)
    assert backfill.run(table, apply_writes=False, verify_index=True) == 0
    assert backfill.run(table, apply_writes=True, verify_index=False) == 0
    assert "in place: 1" in capsys.readouterr().out.splitlines()[-1]


def test_the_backfill_skips_a_record_that_moves_meanwhile(table, monkeypatch) -> None:
    _before_608(table)
    read = [dict(_help(table))]
    _dispatch_to(table, TEACHER)

    outcome = backfill.apply(table, read)

    assert outcome == {"changed meanwhile, skipped": 1}


def test_verify_names_a_request_missing_from_an_index_without_naming_its_teacher(table) -> None:
    _dispatch_to(table, TEACHER)
    assert _set_status(_client(), "in_progress").status_code == 200
    _before_608(table)

    problems = backfill.verify(table, help_requests.list_all(table=table))

    assert problems == [
        f"not ended, missing from the index: {CONV}",
        f"held, missing from its teacher's index: {CONV}",
    ]
    assert TEACHER not in " ".join(problems)
