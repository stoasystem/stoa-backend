"""Plan 475-27 teacher identity deletion proof."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from typing import Any

import pytest

from stoa.db.repositories import account_deletion_repo
from stoa.services import account_deletion_service


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


class _TeacherDeletionTable:
    def __init__(self) -> None:
        direct = _question("direct", version=7)
        session = _session("direct", question_version=7)
        history = _question("history", version=3, status="ai_answered", direct=False)
        self.rows: dict[tuple[str, str], dict[str, object]] = {
            (str(direct["PK"]), str(direct["SK"])): direct,
            (str(session["PK"]), str(session["SK"])): session,
            (str(history["PK"]), str(history["SK"])): history,
            (f"USER#{TEACHER_ID}", "ACCOUNT_FENCE"): {
                "PK": f"USER#{TEACHER_ID}",
                "SK": "ACCOUNT_FENCE",
                "status": "deletion_pending",
                "generation": GENERATION,
            },
        }
        self.scan_count = 0
        self.cas_raced = False
        self.transactions: list[list[dict[str, Any]]] = []

    def scan(self, **kwargs: object) -> dict[str, object]:
        assert kwargs.get("ConsistentRead") is True
        assert "IndexName" not in kwargs
        self.scan_count += 1
        if self.scan_count == 3:
            late = _question("late", version=2)
            self.rows[(str(late["PK"]), str(late["SK"]))] = late
        return {"Items": [deepcopy(row) for row in self.rows.values()]}

    def transact_account_deletion(self, operations: list[dict[str, Any]]) -> None:
        self.transactions.append(deepcopy(operations))
        assert len(operations) == 2
        fence = operations[0]["ConditionCheck"]
        assert fence["Key"] == {
            "PK": f"USER#{TEACHER_ID}",
            "SK": "ACCOUNT_FENCE",
        }
        assert fence["ExpressionAttributeValues"] == {
            ":pending": "deletion_pending",
            ":generation": GENERATION,
        }
        if "Update" in operations[1]:
            self._apply_question_scrub(operations[1]["Update"])
        else:
            self._apply_session_tombstone(operations[1]["Put"])

    def _apply_question_scrub(self, update: dict[str, Any]) -> None:
        key = update["Key"]
        current = self.rows[(key["PK"], key["SK"])]
        values = update["ExpressionAttributeValues"]
        condition = update["ConditionExpression"]
        assert all(
            fragment in condition
            for fragment in (
                "PK=:pk",
                "SK=:sk",
                "entity_type=:entity",
                "schema_version=:schema",
                "student_id=:student",
                "#status=:status",
                "#version=:version",
                "teacher_id=:teacher",
                "dispatched_teacher_id=:teacher",
                "contains(previous_dispatch_teacher_ids,:teacher)",
            )
        )
        if key == {"PK": "QUESTION#direct", "SK": "META"} and not self.cas_raced:
            self.cas_raced = True
            current["status"] = "resolved"
            current["version"] = 8
            current["concurrent_student_note"] = "must survive"
            raise account_deletion_repo.AccountDeletionConflict(
                "conditional teacher-question cleanup conflict"
            )
        assert current["PK"] == values[":pk"]
        assert current["SK"] == values[":sk"]
        assert current["entity_type"] == values[":entity"]
        assert current["schema_version"] == values[":schema"]
        assert current["student_id"] == values[":student"]
        assert current["status"] == values[":status"]
        assert current["version"] == values[":version"]
        assert (
            current.get("teacher_id") == values[":teacher"]
            or current.get("dispatched_teacher_id") == values[":teacher"]
            or values[":teacher"]
            in current.get("previous_dispatch_teacher_ids", [])
        )
        expression = update["UpdateExpression"]
        current["version"] = values[":next_version"]
        if ":next_status" in values:
            current["status"] = values[":next_status"]
        if ":next_history" in values:
            current["previous_dispatch_teacher_ids"] = deepcopy(
                values[":next_history"]
            )
        for field in (
            "teacher_id",
            "teacher_takeover_claim_id",
            "session_id",
            "teacher_started_at",
            "teacher_taken_over_at",
            "teacher_first_replied_at",
            "teacher_first_reply_seconds",
            "teacher_first_reply_sla_bucket",
            "dispatched_teacher_id",
            "dispatch_accepted_at",
            "dispatch_deadline_at",
        ):
            if f"#{field}" in expression:
                current.pop(field, None)
        if ":closed_dispatch" in values:
            current["dispatch_status"] = values[":closed_dispatch"]

    def _apply_session_tombstone(self, put: dict[str, Any]) -> None:
        tombstone = put["Item"]
        key = (str(tombstone["PK"]), str(tombstone["SK"]))
        current = self.rows[key]
        values = put["ExpressionAttributeValues"]
        condition = put["ConditionExpression"]
        assert all(
            fragment in condition
            for fragment in (
                "PK=:pk",
                "SK=:sk",
                "entity_type=:entity",
                "session_id=:session_id",
                "question_id=:question_id",
                "student_id=:student",
                "teacher_id=:teacher",
                "teacher_takeover_claim_id=:claim",
                "question_version=:question_version",
            )
        )
        assert current["PK"] == values[":pk"]
        assert current["SK"] == values[":sk"]
        assert current["entity_type"] == values[":entity"]
        assert current["session_id"] == values[":session_id"]
        assert current["question_id"] == values[":question_id"]
        assert current["student_id"] == values[":student"]
        assert current["teacher_id"] == values[":teacher"]
        assert current["teacher_takeover_claim_id"] == values[":claim"]
        assert current["question_version"] == values[":question_version"]
        assert set(tombstone) <= account_deletion_repo.SESSION_TOMBSTONE_ALLOWLIST
        self.rows[key] = deepcopy(tombstone)


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


def test_teacher_identity_scrub_preserves_student_question_and_requires_two_clean_epochs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = _TeacherDeletionTable()
    retained = {
        key: _retained_question_snapshot(row)
        for key, row in table.rows.items()
        if row.get("entity_type") == "question"
    }
    monkeypatch.setattr(account_deletion_repo, "get_table", lambda: table)

    branch = account_deletion_service.BRANCH_HANDLERS["question_ocr_session"]
    command = {"user_id": TEACHER_ID, "generation": GENERATION}
    results = []
    previous: dict[str, object] = {}
    for _ in range(5):
        result = branch(command=command, previous=previous)
        results.append(result)
        previous = asdict(result)

    assert table.cas_raced is True
    assert [(result.status, result.epoch) for result in results] == [
        ("retryable", 0),
        ("retryable", 0),
        ("retryable", 0),
        ("retryable", 1),
        ("complete", 2),
    ]
    assert results[-1].quiescent is True

    direct = table.rows[("QUESTION#direct", "META")]
    assert direct["status"] == "resolved"
    assert direct["version"] == 9
    assert direct["concurrent_student_note"] == "must survive"
    assert _retained_question_snapshot(direct) == retained[("QUESTION#direct", "META")]

    history = table.rows[("QUESTION#history", "META")]
    assert history["status"] == "ai_answered"
    assert history["version"] == 4
    assert history["previous_dispatch_teacher_ids"] == [OTHER_TEACHER_ID]
    assert _retained_question_snapshot(history) == retained[("QUESTION#history", "META")]

    late = table.rows[("QUESTION#late", "META")]
    assert late["status"] == "resolved"
    assert late["version"] == 3

    for item in table.rows.values():
        assert item.get("teacher_id") != TEACHER_ID
        assert item.get("dispatched_teacher_id") != TEACHER_ID
        assert TEACHER_ID not in item.get("previous_dispatch_teacher_ids", [])
        assert item.get("teacher_takeover_claim_id") not in {
            "claim-direct",
            "claim-late",
        }
        if item.get("entity_type") == "question":
            assert item.get("session_id") not in {"session-direct", "session-late"}

    session = table.rows[("SESSION#session-direct", "META")]
    assert set(session) <= account_deletion_repo.SESSION_TOMBSTONE_ALLOWLIST
    assert session["entity_type"] == "teacher_session_deletion_tombstone"
    assert session["status"] == "deleted"
    assert TEACHER_ID not in repr(session)
