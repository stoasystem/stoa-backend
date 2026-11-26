"""A reviewed draft is written the way the table accepts it (#543).

Accepting a draft without a note sends `review_note: None`. The table gateway
leaves every `None` out of `ExpressionAttributeValues`, so an update that still
named `:review_note` in its `SET` was refused by DynamoDB as a whole, and the
accept answered a bare 500 in production. The tests of the review route replace
the repository with a dict, so none of them sent the write; these send it to
the in-memory table, which refuses the same request DynamoDB refused.
"""

from __future__ import annotations

from typing import Any

import pytest

from stoa.db import table as db_table
from stoa.db.repositories import ai_teacher_tools_repo

from fakes.dynamodb import FakeTable

DRAFT_ID = "aitool-review"
STUDENT = "student-1"


@pytest.fixture
def table() -> Any:
    fake = FakeTable()
    fake.seed_active_account(STUDENT)
    db_table.install(fake)
    yield fake
    db_table.install(None)


def _draft(table: FakeTable, **fields: Any) -> dict[str, Any]:
    item = {
        "PK": ai_teacher_tools_repo.draft_pk(DRAFT_ID),
        "SK": "META",
        "entity_type": ai_teacher_tools_repo.DRAFT_ENTITY,
        "draft_id": DRAFT_ID,
        "draft_type": "practice_exercise",
        "student_id": STUDENT,
        "owner_id": STUDENT,
        "account_fence_generation": 1,
        "status": "draft",
        **fields,
    }
    table.seed(item)
    return item


def _stored(table: FakeTable) -> dict[str, Any]:
    return table.rows[(ai_teacher_tools_repo.draft_pk(DRAFT_ID), "META")]


def _review(status: str, note: str | None) -> dict[str, Any]:
    return {
        "status": status,
        "updated_at": "2026-11-20T21:00:00+00:00",
        "reviewed_by": "teacher-1",
        "reviewed_at": "2026-11-20T21:00:00+00:00",
        "review_note": note,
    }


def test_a_draft_accepted_without_a_note_is_stored(table: FakeTable) -> None:
    existing = _draft(table)

    updated = ai_teacher_tools_repo.update_draft(
        DRAFT_ID, _review("accepted", None), existing=existing
    )

    stored = _stored(table)
    assert stored["status"] == "accepted"
    assert stored["reviewed_by"] == "teacher-1"
    assert "review_note" not in stored
    assert updated is not None and updated["status"] == "accepted"


def test_a_draft_archived_with_a_note_keeps_it(table: FakeTable) -> None:
    existing = _draft(table)

    ai_teacher_tools_repo.update_draft(
        DRAFT_ID, _review("archived", "smoke item 13"), existing=existing
    )

    assert _stored(table)["status"] == "archived"
    assert _stored(table)["review_note"] == "smoke item 13"


def test_a_note_set_to_none_is_taken_off_the_draft(table: FakeTable) -> None:
    existing = _draft(table, review_note="an earlier note")

    ai_teacher_tools_repo.update_draft(DRAFT_ID, _review("accepted", None), existing=existing)

    assert "review_note" not in _stored(table)


def test_the_update_names_no_value_it_does_not_send() -> None:
    """Every `:value` the update expression names is one the request carries
    once the gateway has left the `None` members out."""
    [operation] = ai_teacher_tools_repo.build_ai_draft_write_transaction(
        item={"PK": "AI_TEACHER_DRAFT#x", "SK": "META"},
        owner_id=STUDENT,
        generation=1,
        mode="update",
        updates=_review("accepted", None),
    )
    update = operation["Update"]
    sent = {key for key, value in update["ExpressionAttributeValues"].items() if value is not None}

    assert ":review_note" not in update["UpdateExpression"]
    assert "REMOVE #review_note" in update["UpdateExpression"]
    for token in ("status", "updated_at", "reviewed_by", "reviewed_at", "owner", "generation"):
        assert f":{token}" in sent


def test_a_students_drafts_are_read_from_their_index_not_a_scan(
    table: FakeTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Card 135: the learning memory's draft lookup reads GSI-StudentId.

    Every draft was written with `student_id` and `created_at`, so the index
    holds each one the scan found for this student.
    """
    def refuse(**_kwargs: Any) -> Any:
        raise AssertionError("list_drafts scanned the table")

    monkeypatch.setattr(table, "scan", refuse)
    table.page_item_cap = 1
    for index, (student, draft_type, status) in enumerate(
        [
            (STUDENT, "practice_exercise", "accepted"),
            (STUDENT, "practice_exercise", "draft"),
            (STUDENT, "teacher_summary", "accepted"),
            ("student-2", "practice_exercise", "accepted"),
            (STUDENT, "practice_exercise", "accepted"),
        ]
    ):
        table.seed(
            {
                "PK": ai_teacher_tools_repo.draft_pk(f"aitool-{index}"),
                "SK": "META",
                "entity_type": ai_teacher_tools_repo.DRAFT_ENTITY,
                "draft_id": f"aitool-{index}",
                "draft_type": draft_type,
                "status": status,
                "student_id": student,
                "created_at": f"2026-11-1{index}T09:00:00+00:00",
            }
        )
    # Another kind of row on the same index.
    table.seed(
        {
            "PK": "CONV#c-1",
            "SK": "HELP",
            "entity_type": "help_request",
            "student_id": STUDENT,
            "status": "accepted",
            "created_at": "2026-11-19T09:00:00+00:00",
        }
    )

    drafts = ai_teacher_tools_repo.list_drafts(
        student_id=STUDENT, status="accepted", draft_type="practice_exercise", limit=None
    )

    assert [draft["draft_id"] for draft in drafts] == ["aitool-4", "aitool-0"]
    assert table.calls["query"] > 1
