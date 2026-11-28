"""#534: what account deletion does to a student's weekly allowance rows.

A student's weekly AI token allowance (`ALLOWANCE#<student>`: the week's
counter, each question's reservation, the provider's usage evidence) and
teacher-help allowance (each admission under `TEACHER_SUPPORT_CASE#<digest>`,
the weekly figure an administrator set beside the profile) are the student's.
They name the student as `beneficiary_id` (the assigned figure as
`student_id`), and the deletion removes them as the catalog says, run whole as
`test_voice_question_consent_deletion` runs it until the command completes.

- Deleting the student removes all five kinds, and leaves another student's.
- Deleting the paying parent the admission names as `parent_id` leaves it.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

import deletion_helpers
import test_chat_help_request_lifecycle as lifecycle
import test_voice_question_consent_deletion as consent_deletion
from stoa.db.repositories import allowance_repo, weekly_counter
from stoa.services import teacher_support_allowance_service

STUDENT = lifecycle.STUDENT
OTHER_STUDENT = "student-other-534"
PARENT = "parent-534"
KINDS = (
    "allowance_counter",
    "allowance_effect",
    "provider_usage_evidence",
    "teacher_support_admission",
    "teacher_support_assigned_allowance",
)


def _allowance_rows(student_id: str, digest: str) -> list[dict]:
    return [
        {
            **allowance_repo._effect_key(student_id, digest),
            "entity_type": "allowance_effect",
            "beneficiary_id": student_id,
            "plan_id": "plan-534",
            "state": "settled",
            "reservation_input_tokens": 1200,
        },
        {
            **allowance_repo._evidence_key(student_id, digest),
            "entity_type": "provider_usage_evidence",
            "beneficiary_id": student_id,
            "effect_id": digest,
            "provider_input_tokens": 1100,
        },
        {
            "PK": f"{weekly_counter.TOKENS.namespace}#{student_id}",
            "SK": "WEEK#2026-W47",
            "entity_type": weekly_counter.TOKENS.entity_type,
            weekly_counter.TOKENS.scope_field: student_id,
            "finalized_input_tokens": 1100,
        },
        {
            "PK": f"TEACHER_SUPPORT_CASE#{digest}",
            "SK": "ADMISSION",
            "entity_type": "teacher_support_admission",
            "beneficiary_id": student_id,
            "parent_id": PARENT,
            "support_case_id": f"conv-{student_id}",
            "case_kind": "conversation",
        },
    ]


def _rows_of(table, student_id: str) -> dict[tuple[str, str], str]:
    return {
        key: row["entity_type"]
        for key, row in table.rows.items()
        if row.get("entity_type") in KINDS
        and student_id in {row.get("beneficiary_id"), row.get("student_id")}
    }


@pytest.fixture
def table(monkeypatch):
    table = lifecycle.build_table(monkeypatch)
    lifecycle.keep_waiting(monkeypatch)
    allowance = [*_allowance_rows(STUDENT, "a" * 64), *_allowance_rows(OTHER_STUDENT, "b" * 64)]
    table.seed(*consent_deletion._parent_rows(PARENT), *allowance)
    # As their writers would have filed them: the deletion reads only the
    # account's own and registered partitions.
    deletion_helpers.register(table, *allowance)
    for student in (STUDENT, OTHER_STUDENT):
        table.seed_active_account(student)
        written = teacher_support_allowance_service.set_assigned_weekly_cases(
            student, 3, actor_id="admin-1", now=datetime(2026, 11, 18, tzinfo=UTC)
        )
        assert written.state_version == 1, written
        assert sorted(_rows_of(table, student).values()) == sorted(KINDS)
    return table


def test_deleting_the_student_removes_every_allowance_row(table) -> None:
    assert consent_deletion._delete(table, STUDENT)
    assert _rows_of(table, STUDENT) == {}
    assert sorted(_rows_of(table, OTHER_STUDENT).values()) == sorted(KINDS)


def test_deleting_the_paying_parent_leaves_the_childs_allowance(table) -> None:
    before = {key: dict(table.rows[key]) for key in _rows_of(table, STUDENT)}

    assert consent_deletion._delete(table, PARENT)
    assert {key: table.rows[key] for key in _rows_of(table, STUDENT)} == before
