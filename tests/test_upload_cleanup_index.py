"""Upload rows the cleanup may act on carry their place in `GSI-SweepPending` (#611).

The upload cleanup used to find its uploads with a filtered scan of the whole
of `stoa-main` every fifteen minutes, so what it read grew with the table. It
reads the sparse index the generation sweep reads (#502), in a bucket of its
own: an upload row carries `sweep_bucket` and `sweep_due_at` while it is
refused, handed to cleanup or not yet spent, and loses them when it is spent,
protected or cleaned.

These hold each write to that, and a seeded walk over the store's writes holds
the index reader to exactly what that scan's filter admits at any moment, so
the cleanup reading the index loses no upload.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime
from typing import Any

import pytest

from fakes.dynamodb import DEFAULT_INDEXES, FakeTable, as_stored
from scripts import backfill_upload_cleanup_index as backfill
from stoa.db import table as db_table
from stoa.db.repositories import attachment_repo
from stoa.models.attachment import UploadStatus
from stoa.services.ask_question import _store as ask_store
from stoa.services.uploads import _store

OWNER = "student-1"
START = int(datetime(2026, 11, 24, 12, 0, tzinfo=UTC).timestamp())
WINDOW = 30 * 60
SHA = "a" * 64


@pytest.fixture
def table() -> FakeTable:
    table = FakeTable()
    table.seed_active_account(OWNER)
    db_table.install(table)
    return table


def _row(table: FakeTable, upload_id: str = "u1") -> dict[str, Any]:
    return dict(table.rows.get((f"UPLOAD#{upload_id}", "META"), {}))


def _issue(upload_id: str = "u1", *, now: int = START) -> None:
    _store.prepare_staging_issuance(
        {
            "entity_type": "upload_intent",
            "upload_id": upload_id,
            "owner_id": OWNER,
            "student_id": OWNER,
            "status": "issuing",
            "version": 1,
            "staging_object_key": f"staging/{upload_id}",
            "operation_kind": "staging_issuance",
            "operation_fence": "fence-0",
            "operation_lease_expires_at": now + 120,
            "operation_takeover_count": 0,
            "account_fence_generation": 1,
            "usable_until": now + WINDOW,
        }
    )


def _indexed(table: FakeTable) -> dict[str, dict[str, Any]]:
    """Everything in the cleanup's bucket of the index, by upload row key."""
    rows: dict[str, dict[str, Any]] = {}
    start: dict[str, Any] | None = None
    while True:
        request: dict[str, Any] = {
            "IndexName": _store.CLEANUP_INDEX,
            "KeyConditionExpression": "sweep_bucket=:bucket",
            "ExpressionAttributeValues": {":bucket": _store.CLEANUP_BUCKET},
        }
        if start is not None:
            request["ExclusiveStartKey"] = start
        page = table.query(**request)
        rows.update({str(item["PK"]): item for item in page["Items"]})
        start = page.get("LastEvaluatedKey")
        if not start:
            return rows


# The filter the cleanup scanned the whole table with before it read the index
# (#250), kept here as the definition of what the cleanup acts on: the reader
# has to return exactly the uploads it admits.
SCAN_FILTER: dict[str, Any] = {
    "FilterExpression": (
        "begins_with(PK,:upload) AND SK=:meta AND ("
        "#status IN (:invalid,:expired,:cleanup_pending) OR ("
        "#status IN (:pending,:validating,:validated,:issuing,:assembling,:promoting) "
        "AND (usable_until <= :now OR (attribute_not_exists(usable_until) AND expires_at <= :now))"
        " AND (attribute_not_exists(operation_lease_expires_at) OR "
        "operation_lease_expires_at <= :now)))"
    ),
    "ExpressionAttributeNames": {"#status": "status"},
    "ExpressionAttributeValues": {
        ":upload": "UPLOAD#",
        ":meta": "META",
        ":invalid": "invalid",
        ":expired": "expired",
        ":cleanup_pending": "cleanup_pending",
        ":pending": "pending_upload",
        ":validating": "validating",
        ":validated": "validated",
        ":issuing": "issuing",
        ":assembling": "assembling",
        ":promoting": "promoting",
    },
}


def _scanned(now: int) -> set[str]:
    """What the old scan's filter admits at `now`, over the whole table."""
    admitted: set[str] = set()
    start: dict[str, Any] | None = None
    table = db_table.table()
    while True:
        request: dict[str, Any] = {
            **SCAN_FILTER,
            "ExpressionAttributeValues": {**SCAN_FILTER["ExpressionAttributeValues"], ":now": now},
        }
        if start is not None:
            request["ExclusiveStartKey"] = start
        page = table.scan(**request)
        admitted.update(str(item["PK"]) for item in page["Items"])
        start = page.get("LastEvaluatedKey")
        if not start:
            return admitted


def test_the_reference_filter_is_the_condition_an_upload_is_claimed_by() -> None:
    """Its window and lease conditions are the store's, so the reference cannot drift."""
    expression = str(SCAN_FILTER["FilterExpression"])
    assert f"{_store.PAST_USABLE} AND {_store.LEASE_LAPSED}" in expression
    states = {
        value
        for name, value in SCAN_FILTER["ExpressionAttributeValues"].items()
        if name not in (":upload", ":meta")
    }
    assert states == _store.CLEANUP_DUE_AT_ONCE_STATES | _store.CLEANUP_DUE_PAST_USABLE_STATES


def _queried(now: int, *, limit: int = 3) -> list[str]:
    """What the index reader returns at `now`, every page of it, in its order."""
    found: list[str] = []
    cursor: dict[str, Any] | None = None
    while True:
        page, cursor = _store.query_upload_cleanup_candidates(
            now, limit=limit, exclusive_start_key=cursor
        )
        found.extend(str(item["PK"]) for item in page)
        if cursor is None:
            return found


# ── The index itself ──────────────────────────────────────────────────────────


def test_the_cleanup_shares_the_generation_sweeps_index_in_its_own_bucket() -> None:
    assert _store.CLEANUP_INDEX == ask_store.SWEEP_PENDING_INDEX
    assert _store.CLEANUP_INDEX in DEFAULT_INDEXES
    assert _store.CLEANUP_INDEX_FIELDS == ask_store.SWEEP_INDEX_FIELDS
    assert _store.CLEANUP_BUCKET != ask_store.SWEEP_PENDING_BUCKET


def test_the_due_time_is_the_generation_sweeps_format() -> None:
    moment = datetime(2026, 11, 24, 12, 0, 7, tzinfo=UTC)
    assert _store.cleanup_due_at(int(moment.timestamp())) == ask_store.sweep_due_at(moment)
    assert _store.CLEANUP_DUE_AT_ONCE < _store.cleanup_due_at(1)


def test_every_state_is_due_at_once_due_past_its_window_or_out_of_the_index() -> None:
    """A state added to `UploadStatus` has to be placed, or the index forgets it."""
    out = {UploadStatus.CONSUMED, UploadStatus.CLEANUP_BLOCKED, UploadStatus.CLEANUP_COMPLETE}
    assert (
        _store.CLEANUP_DUE_AT_ONCE_STATES | _store.CLEANUP_DUE_PAST_USABLE_STATES | out
        == set(UploadStatus)
    )
    assert not _store.CLEANUP_DUE_AT_ONCE_STATES & _store.CLEANUP_DUE_PAST_USABLE_STATES
    for state in UploadStatus:
        fields = _store.cleanup_index_fields({"status": state.value, "usable_until": START})
        if state in out:
            assert fields == {}
        elif state in _store.CLEANUP_DUE_AT_ONCE_STATES:
            assert fields == {
                "sweep_bucket": _store.CLEANUP_BUCKET,
                "sweep_due_at": _store.CLEANUP_DUE_AT_ONCE,
            }
        else:
            assert fields == {
                "sweep_bucket": _store.CLEANUP_BUCKET,
                "sweep_due_at": _store.cleanup_due_at(START),
            }


def test_a_row_from_before_usable_until_is_due_at_its_old_window() -> None:
    """A row written before #250 keeps its window in `expires_at`."""
    assert _store.cleanup_index_fields({"status": "validated", "expires_at": START}) == {
        "sweep_bucket": _store.CLEANUP_BUCKET,
        "sweep_due_at": _store.cleanup_due_at(START),
    }


# ── Each write ────────────────────────────────────────────────────────────────


def test_an_issued_upload_is_due_when_its_window_ends(table) -> None:
    _issue()

    row = _row(table)
    assert row["sweep_bucket"] == _store.CLEANUP_BUCKET
    assert row["sweep_due_at"] == _store.cleanup_due_at(START + WINDOW)
    assert _queried(START + WINDOW - 1) == []
    assert _queried(START + WINDOW) == ["UPLOAD#u1"]


def test_a_state_change_inside_the_window_keeps_the_due_time(table) -> None:
    _issue()
    due = _row(table)["sweep_due_at"]

    assert _store.record_staging_multipart(
        "u1", OWNER, 1, operation_fence="fence-0", multipart_upload_id="mp-1"
    )
    assert _store.claim_staging_assembly(
        "u1", OWNER, 2, START + 60, operation_fence="fence-1",
        multipart_upload_id="mp-1", ordered_part_count=1, part_ledger_digest=SHA,
    )
    assert _store.recover_staging_completion(
        "u1", OWNER, 3, operation_fence="fence-1", staging_version_id="v1", staging_etag="e1"
    )

    row = _row(table)
    assert row["status"] == "validating"
    assert (row["sweep_bucket"], row["sweep_due_at"]) == (_store.CLEANUP_BUCKET, due)


def test_a_live_lease_past_the_window_holds_the_upload_back(table) -> None:
    """The lease is not in the key: the reader's filter keeps the scan's condition on it."""
    _issue()
    _store.record_staging_multipart(
        "u1", OWNER, 1, operation_fence="fence-0", multipart_upload_id="mp-1"
    )
    claimed_at = START + WINDOW - 10
    assert _store.claim_staging_assembly(
        "u1", OWNER, 2, claimed_at, operation_fence="fence-1",
        multipart_upload_id="mp-1", ordered_part_count=1, part_ledger_digest=SHA,
    )

    assert _queried(START + WINDOW) == [] and _scanned(START + WINDOW) == set()
    # Taken over once the lease ran out: held back for the new lease too.
    taken_at = claimed_at + 120
    assert _store.claim_stale_upload_operation(
        "u1", OWNER, 3, "staging_assembly", "fence-1", "fence-2", taken_at
    )
    assert _queried(taken_at + 119) == [] and _scanned(taken_at + 119) == set()
    assert _queried(taken_at + 120) == ["UPLOAD#u1"]
    assert _scanned(taken_at + 120) == {"UPLOAD#u1"}


def test_a_refused_upload_is_due_at_once(table) -> None:
    _issue()
    table.rows[("UPLOAD#u1", "META")]["status"] = "validating"

    assert _store.mark_invalid("u1", OWNER, 1, "unsupported_type")

    assert _row(table)["sweep_due_at"] == _store.CLEANUP_DUE_AT_ONCE
    assert _queried(START) == ["UPLOAD#u1"]


def test_a_failed_issuance_is_due_at_once(table) -> None:
    _issue()

    assert _store.mark_upload_issuance_failed("u1", OWNER, 1)

    row = _row(table)
    assert row["status"] == "cleanup_pending"
    assert row["sweep_due_at"] == _store.CLEANUP_DUE_AT_ONCE
    assert _queried(START) == ["UPLOAD#u1"]


def test_a_claimed_upload_stays_in_the_index_until_it_is_cleaned(table) -> None:
    _issue()
    now = START + WINDOW + 200

    assert _store.claim_upload_cleanup("u1", 1, now, "abandoned")
    assert _row(table)["sweep_due_at"] == _store.CLEANUP_DUE_AT_ONCE
    assert _store.mark_cleanup_multipart_aborted("u1", 2)
    assert _store.mark_cleanup_staging_deleted("u1", 3)
    assert _store.mark_cleanup_immutable_deleted("u1", 4)
    assert _store.mark_cleanup_parts_absent("u1", 5)
    assert "UPLOAD#u1" in _indexed(table)

    assert _store.complete_upload_cleanup("u1", 6, "2026-11-24T13:00:00+00:00", now_epoch=now)

    row = _row(table)
    assert row["status"] == "cleanup_complete"
    assert "sweep_bucket" not in row and "sweep_due_at" not in row
    assert _indexed(table) == {}


def test_a_protected_upload_leaves_the_index(table) -> None:
    _issue()
    now = START + WINDOW + 200
    assert _store.claim_upload_cleanup("u1", 1, now, "abandoned")

    assert _store.block_upload_cleanup("u1", 2, now_epoch=now)

    row = _row(table)
    assert row["status"] == "cleanup_blocked"
    assert "sweep_bucket" not in row and "sweep_due_at" not in row


def _validate(table: FakeTable, upload_id: str = "u1") -> None:
    table.rows[(f"UPLOAD#{upload_id}", "META")].update(
        as_stored({"status": "validated", "expected_kind": "question_image"})
    )
    for field in ("operation_kind", "operation_fence", "operation_lease_expires_at"):
        table.rows[(f"UPLOAD#{upload_id}", "META")].pop(field, None)


def test_a_spent_upload_leaves_the_index(table) -> None:
    _issue()
    _validate(table)

    attachment_repo.transact(
        [
            _store.consume_operation(
                _row(table), attachment_id="a1", now_epoch=START + 60, owner_id=OWNER
            )
        ]
    )

    row = _row(table)
    assert row["status"] == "consumed"
    assert "sweep_bucket" not in row and "sweep_due_at" not in row


def test_a_promoted_upload_that_forgets_its_staging_copy_keeps_its_place(table) -> None:
    _issue()
    _validate(table)
    due = _row(table)["sweep_due_at"]

    assert _store.clear_staging_coordinates("u1", OWNER, 1)

    assert _row(table)["sweep_due_at"] == due


def test_an_upload_claimed_for_account_deletion_is_due_at_once(table) -> None:
    _issue()
    _validate(table)
    table.rows[(f"USER#{OWNER}", "ACCOUNT_FENCE")]["status"] = "deletion_pending"

    claimed = _store.claim_account_upload_cleanup(
        _row(table), owner_id=OWNER, account_fence_generation=1
    )

    assert claimed is not None and claimed["status"] == "cleanup_pending"
    assert claimed["sweep_due_at"] == _store.CLEANUP_DUE_AT_ONCE


# ── The reader ────────────────────────────────────────────────────────────────


def test_the_reader_pages_through_the_index_earliest_due_first(table) -> None:
    for number in range(5):
        _issue(f"u{number}", now=START + number)
    _store.mark_upload_issuance_failed("u3", OWNER, 1)

    now = START + WINDOW + 500
    assert _queried(now, limit=2) == [
        "UPLOAD#u3", "UPLOAD#u0", "UPLOAD#u1", "UPLOAD#u2", "UPLOAD#u4",
    ]


def test_the_reader_reads_the_index_and_never_scans(table) -> None:
    _issue()
    before = table.calls["scan"]

    _queried(START + WINDOW + 500)

    assert table.calls["scan"] == before


def test_a_generation_sweep_command_is_not_an_upload_candidate(table) -> None:
    table.seed(
        {
            "PK": "CONV#c1",
            "SK": "MESSAGE_COMMAND#k1",
            "status": "message_committed",
            "sweep_bucket": ask_store.SWEEP_PENDING_BUCKET,
            "sweep_due_at": _store.CLEANUP_DUE_AT_ONCE,
        }
    )

    assert _queried(START) == []


def test_the_reader_answers_a_table_failure_as_a_dependency_failure() -> None:
    class _Down(FakeTable):
        def query(self, **_request: Any) -> dict[str, Any]:
            return {"Items": "not a page"}

    with pytest.raises(attachment_repo.AttachmentRepositoryConflict):
        _store.query_upload_cleanup_candidates(START, limit=5, table=_Down())


# ── The index holds what the scan admits ──────────────────────────────────────

UPLOADS = ("u1", "u2", "u3")
# The walk's step that moves an upload on from each state, as `_walk_step` numbers them.
_NEXT = {
    "issuing": (1,),
    "pending_upload": (3,),
    "assembling": (4,),
    "validating": (6,),
    "promoting": (7,),
    "validated": (8, 10),
    "cleanup_pending": (12, 13, 15),
}


def _walk_step(table: FakeTable, rng: random.Random, clock: list[int]) -> None:
    """One store write on one upload, as the lifecycle makes it; refusals are part of the walk."""
    upload_id = rng.choice(UPLOADS)
    row = _row(table, upload_id)
    now = clock[0]
    if not row:
        _issue(upload_id, now=now)
        return
    version = int(row["version"])
    fence = str(row.get("operation_fence") or "fence-x")
    step = rng.randrange(16)
    if rng.random() < 0.5:
        # Half the time the write the lifecycle makes next, or the walk rarely gets far.
        step = rng.choice(_NEXT.get(str(row["status"]), (step,)))
    if step == 0:
        clock[0] += rng.choice([30, 119, 121, 600, 1500, 1800])
    elif step == 1:
        _store.record_staging_multipart(
            upload_id, OWNER, version, operation_fence=fence, multipart_upload_id="mp-1"
        )
    elif step == 2:
        _store.mark_upload_issuance_failed(upload_id, OWNER, version)
    elif step == 3:
        _store.claim_staging_assembly(
            upload_id, OWNER, version, now, operation_fence=f"fence-{version}",
            multipart_upload_id="mp-1", ordered_part_count=1, part_ledger_digest=SHA,
        )
    elif step == 4:
        _store.recover_staging_completion(
            upload_id, OWNER, version, operation_fence=fence,
            staging_version_id="v1", staging_etag="e1",
        )
    elif step == 5:
        _store.claim_stale_upload_operation(
            upload_id, OWNER, version, str(row.get("operation_kind") or "none"),
            fence, f"fence-{version}", now,
        )
    elif step == 6:
        _store.begin_immutable_promotion(
            upload_id, OWNER, version, now, operation_fence=f"fence-{version}",
            immutable_object_key=f"immutable/{upload_id}", content_sha256=SHA,
            content_length=10, detected_type="image/png", image_width=1, image_height=1,
        )
    elif step == 7:
        _store.record_immutable_version(
            upload_id, OWNER, version, operation_fence=fence, immutable_version_id="iv1",
            immutable_etag="ie1", validated_at="2026-11-24T12:00:00+00:00",
        )
    elif step == 8:
        _store.clear_staging_coordinates(upload_id, OWNER, version)
    elif step == 9:
        _store.mark_invalid(upload_id, OWNER, version, "unsupported_type")
    elif step == 10:
        try:
            attachment_repo.transact(
                [
                    _store.consume_operation(
                        row, attachment_id="a1", now_epoch=now, owner_id=OWNER
                    )
                ]
            )
        except attachment_repo.AttachmentRepositoryConflict:
            pass
    elif step == 11:
        _store.claim_upload_cleanup(upload_id, version, now, "abandoned")
    elif step == 12:
        _store.block_upload_cleanup(upload_id, version, now_epoch=now)
    elif step == 13:
        rng.choice(
            [
                _store.mark_cleanup_multipart_aborted,
                _store.mark_cleanup_staging_deleted,
                _store.mark_cleanup_immutable_deleted,
                _store.mark_cleanup_parts_absent,
            ]
        )(upload_id, version)
    elif step == 14:
        _store.advance_upload_cleanup_reference_scan(
            upload_id, version, {"PK": "ATTACHMENT#a", "SK": "META"}
        )
    else:
        table.rows[(f"UPLOAD#{upload_id}", "META")].update(
            as_stored(
                {
                    "cleanup_multipart_aborted": True,
                    "cleanup_staging_deleted": True,
                    "cleanup_immutable_deleted": True,
                    "cleanup_parts_absent": True,
                }
            )
        )
        _store.complete_upload_cleanup(
            upload_id, version, "2026-11-24T13:00:00+00:00", now_epoch=now
        )


def test_the_index_reader_returns_exactly_what_the_scan_admits(table) -> None:
    """After every write of a seeded walk, at several moments, reader and scan agree.

    Over all the walks every state has to be reached, in and out of the index
    and on both sides of the scan's filter, or agreeing would prove little.
    """
    indexed_states = _store.CLEANUP_DUE_AT_ONCE_STATES | _store.CLEANUP_DUE_PAST_USABLE_STATES
    seen: set[tuple[str, bool]] = set()
    for seed in range(60):
        table.rows = {
            key: row for key, row in table.rows.items() if not key[0].startswith("UPLOAD#")
        }
        rng = random.Random(seed)
        clock = [START]
        for step in range(60):
            _walk_step(table, rng, clock)
            in_index = _indexed(table)
            for upload_id in UPLOADS:
                row = _row(table, upload_id)
                if not row:
                    continue
                where = (seed, step, row)
                assert ("sweep_bucket" in row) == ("sweep_due_at" in row), where
                assert (row["PK"] in in_index) == (row["status"] in indexed_states), where
                assert {
                    name: row[name] for name in _store.CLEANUP_INDEX_FIELDS if name in row
                } == _store.cleanup_index_fields(row), where
            for moment in (clock[0], clock[0] + 119, clock[0] + 121, clock[0] + WINDOW + 121):
                admitted = _scanned(moment)
                found = _queried(moment)
                assert len(found) == len(set(found)), (seed, step, moment)
                assert set(found) == admitted, (seed, step, moment)
                for upload_id in UPLOADS:
                    row = _row(table, upload_id)
                    if row:
                        seen.add((str(row["status"]), row["PK"] in admitted))
    assert {
        ("issuing", True), ("issuing", False),
        ("pending_upload", True), ("pending_upload", False),
        ("assembling", True), ("assembling", False),
        ("validating", True), ("validating", False),
        ("promoting", True), ("promoting", False),
        ("validated", True), ("validated", False),
        ("invalid", True),
        ("cleanup_pending", True),
        ("consumed", False),
        ("cleanup_blocked", False),
        ("cleanup_complete", False),
    } <= seen, seen


# ── The backfill ──────────────────────────────────────────────────────────────


def _before_the_writers(table: FakeTable) -> None:
    for key, row in table.rows.items():
        if key[0].startswith("UPLOAD#"):
            for name in _store.CLEANUP_INDEX_FIELDS:
                row.pop(name, None)


@pytest.fixture
def old_rows(table) -> FakeTable:
    """Uploads as the table holds them before the writers: live, refused, spent, and one from before #250."""
    for number in range(4):
        _issue(f"u{number}", now=START + number)
    _store.mark_upload_issuance_failed("u1", OWNER, 1)
    _validate(table, "u2")
    attachment_repo.transact(
        [_store.consume_operation(_row(table, "u2"), attachment_id="a", now_epoch=START, owner_id=OWNER)]
    )
    legacy = table.rows[("UPLOAD#u3", "META")]
    legacy["expires_at"] = legacy.pop("usable_until")
    _before_the_writers(table)
    return table


def test_a_dry_run_counts_and_writes_nothing(old_rows, capsys) -> None:
    before = {key: dict(row) for key, row in old_rows.rows.items()}

    assert backfill.run(old_rows, apply_writes=False, verify_index=False) == 0

    assert old_rows.rows == before
    out = capsys.readouterr().out
    assert "issuing: rows 2 | in place 0 | to write 2 | not indexed 0 | unreadable 0" in out
    assert "cleanup_pending: rows 1 | in place 0 | to write 1 | not indexed 0 | unreadable 0" in out
    assert "consumed: rows 1 | in place 0 | to write 0 | not indexed 1 | unreadable 0" in out
    assert "Rows to write: 3" in out
    assert "[DRY RUN]" in out


def test_apply_puts_every_upload_where_its_writer_would(old_rows) -> None:
    assert backfill.run(old_rows, apply_writes=True, verify_index=False) == 0

    for number in range(4):
        row = _row(old_rows, f"u{number}")
        assert {
            name: row[name] for name in _store.CLEANUP_INDEX_FIELDS if name in row
        } == _store.cleanup_index_fields(row)
    assert set(_indexed(old_rows)) == {"UPLOAD#u0", "UPLOAD#u1", "UPLOAD#u3"}
    assert _row(old_rows, "u3")["sweep_due_at"] == _store.cleanup_due_at(START + 3 + WINDOW)
    later = START + WINDOW + 500
    assert set(_queried(later)) == _scanned(later) == {"UPLOAD#u0", "UPLOAD#u1", "UPLOAD#u3"}
    # A second run has nothing left to write.
    assert backfill.plan(backfill.upload_rows(old_rows)).writes == []


def test_apply_removes_fields_a_row_should_not_carry(old_rows) -> None:
    old_rows.rows[("UPLOAD#u2", "META")].update(
        {"sweep_bucket": _store.CLEANUP_BUCKET, "sweep_due_at": _store.CLEANUP_DUE_AT_ONCE}
    )

    assert backfill.run(old_rows, apply_writes=True, verify_index=False) == 0

    assert "sweep_bucket" not in _row(old_rows, "u2")
    assert "UPLOAD#u2" not in _indexed(old_rows)


def test_a_row_the_application_moved_on_meanwhile_is_left_alone(old_rows, capsys) -> None:
    planned = backfill.plan(backfill.upload_rows(old_rows))
    assert _store.record_staging_multipart(
        "u0", OWNER, 1, operation_fence="fence-0", multipart_upload_id="mp-1"
    )

    outcome = backfill.apply(old_rows, planned)

    assert outcome == {"written": 2, "changed meanwhile, skipped": 1}
    assert "sweep_bucket" not in _row(old_rows, "u0")


def test_a_row_whose_window_cannot_be_read_is_counted_and_not_written(old_rows, capsys) -> None:
    old_rows.rows[("UPLOAD#u0", "META")]["usable_until"] = "soon"

    planned = backfill.plan(backfill.upload_rows(old_rows))

    assert planned.counts[("issuing", "unreadable")] == 1
    assert all(row["PK"] != "UPLOAD#u0" for row, _expected in planned.writes)


def test_verify_reports_what_the_index_lacks_and_then_nothing(old_rows, capsys) -> None:
    assert backfill.run(old_rows, apply_writes=False, verify_index=True) == 1
    out = capsys.readouterr().out
    assert "Uploads expected in the index: 3" in out
    assert "missing: UPLOAD#u0" in out

    backfill.run(old_rows, apply_writes=True, verify_index=False)
    capsys.readouterr()

    assert backfill.run(old_rows, apply_writes=False, verify_index=True) == 0
    assert "Differences from GSI-SweepPending (upload_cleanup): 0" in capsys.readouterr().out


def test_verify_reports_an_entry_that_should_not_be_there(old_rows, capsys) -> None:
    backfill.run(old_rows, apply_writes=True, verify_index=False)
    old_rows.rows[("UPLOAD#u2", "META")].update(
        {"sweep_bucket": _store.CLEANUP_BUCKET, "sweep_due_at": _store.CLEANUP_DUE_AT_ONCE}
    )
    old_rows.rows[("UPLOAD#u0", "META")]["sweep_due_at"] = _store.CLEANUP_DUE_AT_ONCE
    capsys.readouterr()

    assert backfill.run(old_rows, apply_writes=False, verify_index=True) == 1

    out = capsys.readouterr().out
    assert "not expected: UPLOAD#u2" in out
    assert f"due {_store.CLEANUP_DUE_AT_ONCE}, expected" in out


# ── The job reads the index ───────────────────────────────────────────────────


def test_the_job_finds_its_uploads_in_the_index_and_never_scans(table, monkeypatch) -> None:
    """The scheduled job, on the real reader: due uploads only, in order, by continuation."""
    from stoa.config import Settings
    from stoa.jobs import upload_cleanup
    from stoa.services import uploads

    for number in range(4):
        _issue(f"u{number}", now=START + number)
    _store.mark_upload_issuance_failed("u2", OWNER, 1)
    _issue("later", now=START + 3600)
    visited: list[str] = []

    def observed(candidate: dict[str, Any], **_kwargs: Any) -> str:
        visited.append(str(candidate["upload_id"]))
        return "deferred"

    monkeypatch.setattr(uploads, "cleanup", observed)
    scans = table.calls["scan"]
    token = None
    for _ in range(2):
        summary = upload_cleanup.cleanup_expired_uploads(
            s3=object(),
            settings_obj=Settings(s3_images_bucket="bucket"),
            now=datetime.fromtimestamp(START + WINDOW + 60, UTC),
            batch_limit=2,
            page_limit=2,
            continuation_token=token,
        )
        token = summary.continuation_token
        assert summary.invalid_continuation == 0

    assert visited == ["u2", "u0", "u1", "u3"]
    assert table.calls["scan"] == scans
