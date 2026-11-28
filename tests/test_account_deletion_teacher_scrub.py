"""Plan 475-27 teacher identity deletion proof, run through the catalog flow since #642."""

from __future__ import annotations

from copy import deepcopy

import pytest

import deletion_helpers
from stoa.db import data_catalog, owner_registry
from stoa.db import table as db_table


TEACHER_ID = "teacher-deleting"
STUDENT_ID = "student-retained"
OTHER_TEACHER_ID = "teacher-retained"
GENERATION = 12


def _question(
    question_id: str,
    *,
    version: int,
    status: str = "teacher_active",
    direct: bool = True,
) -> dict[str, object]:
    item: dict[str, object] = {
        "PK": f"QUESTION#{question_id}",
        "SK": "META",
        "entity_type": "question",
        "schema_version": "question.v1",
        "question_id": question_id,
        "student_id": STUDENT_ID,
        "status": status,
        "version": version,
        "subject": "Algebra",
        "content": "Retain the student's exact question",
        "original_content": "Retain the original bytes",
        "attachment_id": f"attachment-{question_id}",
        "attachment_ids": [f"attachment-{question_id}", "attachment-shared"],
        "attachment_source_identity": f"opaque-{question_id}",
        "ai_response": {"answer": "Retain the AI result"},
        "student_feedback": "retain",
        "previous_dispatch_teacher_ids": [OTHER_TEACHER_ID, TEACHER_ID],
    }
    if direct:
        item.update(
            teacher_id=TEACHER_ID,
            teacher_takeover_claim_id=f"claim-{question_id}",
            session_id=f"session-{question_id}",
            teacher_started_at="2026-07-22T08:00:00+00:00",
            teacher_taken_over_at="2026-07-22T08:01:00+00:00",
            teacher_first_replied_at="2026-07-22T08:02:00+00:00",
            teacher_first_reply_seconds=60,
            teacher_first_reply_sla_bucket="within_target",
            dispatched_teacher_id=TEACHER_ID,
            dispatch_status="accepted",
            dispatch_accepted_at="2026-07-22T08:01:00+00:00",
        )
    return item


def _session(question_id: str, *, question_version: int) -> dict[str, object]:
    session_id = f"session-{question_id}"
    return {
        "PK": f"SESSION#{session_id}",
        "SK": "META",
        "entity_type": "teacher_session",
        "session_id": session_id,
        "teacher_takeover_claim_id": f"claim-{question_id}",
        "question_id": question_id,
        "teacher_id": TEACHER_ID,
        "student_id": STUDENT_ID,
        "started_at": "2026-07-22T08:01:00+00:00",
        "resolved_at": None,
        "question_version": question_version,
        "account_fence_generation": 4,
        "notes": "private teacher-session material",
    }


def _retained_question_snapshot(item: dict[str, object]) -> dict[str, object]:
    return {
        field: deepcopy(item[field])
        for field in (
            "student_id",
            "subject",
            "content",
            "original_content",
            "attachment_id",
            "attachment_ids",
            "attachment_source_identity",
            "ai_response",
            "student_feedback",
        )
    }


def test_teacher_identity_scrub_preserves_student_question_and_retries_a_moved_question(
    fake_table, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The teacher's whole deletion, as production runs it (#642).

    The student's questions keep everything that is the student's; only the
    teacher's name goes. A question that moves between the read and the write
    is refused by its version and scrubbed again by a later pass, keeping what
    changed. The teacher's session becomes the catalog's tombstone.
    """
    direct = _question("direct", version=7)
    session = _session("direct", question_version=7)
    history = _question("history", version=3, status="ai_answered", direct=False)
    fake_table.seed(direct, session, history)
    deletion_helpers.register(fake_table, direct, session, history)
    deletion_helpers.active_fence(fake_table, TEACHER_ID, generation=GENERATION)
    retained = {
        key: _retained_question_snapshot(row)
        for key, row in fake_table.rows.items()
        if row.get("entity_type") == "question"
    }

    real_transact = db_table.transact
    raced: list[bool] = []

    def transact(operations, *, table=None):
        touches_direct = any(
            (op.get("Update") or {}).get("Key") == {"PK": "QUESTION#direct", "SK": "META"}
            for op in operations
        )
        if touches_direct and not raced:
            raced.append(True)
            row = fake_table.rows[("QUESTION#direct", "META")]
            row.update(status="resolved", version=8, concurrent_student_note="must survive")
        return real_transact(operations, table=table)

    monkeypatch.setattr(db_table, "transact", transact)

    command = deletion_helpers.delete_account(TEACHER_ID)

    assert raced
    assert command["status"] == "complete"

    direct = fake_table.rows[("QUESTION#direct", "META")]
    assert direct["status"] == "resolved"
    assert direct["version"] == 9
    assert direct["concurrent_student_note"] == "must survive"
    assert _retained_question_snapshot(direct) == retained[("QUESTION#direct", "META")]

    history = fake_table.rows[("QUESTION#history", "META")]
    assert history["status"] == "ai_answered"
    assert history["version"] == 4
    assert history["previous_dispatch_teacher_ids"] == [OTHER_TEACHER_ID]
    assert _retained_question_snapshot(history) == retained[("QUESTION#history", "META")]

    for item in fake_table.rows.values():
        if owner_registry.is_registry_row(item):
            continue
        assert item.get("teacher_id") != TEACHER_ID
        assert item.get("dispatched_teacher_id") != TEACHER_ID
        assert TEACHER_ID not in item.get("previous_dispatch_teacher_ids", [])
        assert item.get("teacher_takeover_claim_id") != "claim-direct"
        if item.get("entity_type") == "question":
            assert item.get("session_id") != "session-direct"

    session = fake_table.rows[("SESSION#session-direct", "META")]
    assert set(session) <= data_catalog.DELETIONS["teacher_session"].owner.keeps
    assert session["status"] == "deleted"
    assert TEACHER_ID not in repr(session)
