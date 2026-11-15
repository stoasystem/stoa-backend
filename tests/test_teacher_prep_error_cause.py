"""The teacher's prep for a help request names the student's commonest recent 错因 (#452).

The cause may have been authored on a distractor (#452) or inferred from a
typed answer by a rule (#453).

Read from the student's answer receipts as they are stored: the cause each
wrong answer recorded when it was given. Nothing is asked of a model.
"""

from __future__ import annotations

from typing import Any

import pytest
from fakes.dynamodb import FakeTable

from stoa.services import error_causes, student_evidence
from test_chat_help_request_lifecycle import STUDENT, REQUEST, TEACHER, _client, _dispatch_to
from test_chat_help_request_lifecycle import table as table  # noqa: F401 - the fixture
from test_error_causes import ADDS_DENOMINATORS, DENOMINATORS, SIGN

SIGN_CAUSE = {"category": "deviation", "misconception": SIGN}


def _attempt(table: FakeTable, n: int, cause: dict[str, Any] | None, **fields: Any) -> None:
    row = {
        "PK": f"ATTEMPTS#{STUDENT}",
        "SK": f"ATTEMPT#a{n:02d}",
        "attempt_id": f"a{n:02d}",
        "student_id": STUDENT,
        "challenge_id": f"c{n}",
        "correct": False,
        "created_at": f"2026-11-{n:02d}T10:00:00+00:00",
        **fields,
    }
    if cause is not None:
        row["error_cause"] = cause
    table.seed(row)


def _detail() -> dict[str, Any]:
    response = _client(TEACHER).get(f"/teachers/me/help-requests/{REQUEST}")
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("locale", ["de", "en", "fr", "it"])
def test_the_prep_names_the_commonest_recent_cause_in_the_teacher_s_language(
    table: FakeTable, locale: str
) -> None:
    _dispatch_to(table, TEACHER)
    table.rows[(f"USER#{TEACHER}", "PROFILE")]["preferred_locale"] = locale
    _attempt(table, 1, SIGN_CAUSE)
    _attempt(table, 2, ADDS_DENOMINATORS)
    _attempt(table, 3, ADDS_DENOMINATORS)
    _attempt(table, 4, {"category": "unclassified"})
    _attempt(table, 5, None)

    assert _detail()["commonErrorCause"] == {
        "category": "structural",
        "misconception": DENOMINATORS[locale],
        "count": 2,
        "recentMistakes": 5,
    }


def test_without_a_known_cause_the_prep_names_none(table: FakeTable) -> None:
    _dispatch_to(table, TEACHER)
    _attempt(table, 1, {"category": "unclassified"})
    _attempt(table, 2, None)
    _attempt(table, 3, SIGN_CAUSE, correct=True)

    assert _detail()["commonErrorCause"] is None


def test_the_request_opens_when_the_answers_cannot_be_read(
    table: FakeTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    _dispatch_to(table, TEACHER)

    def unavailable(self: student_evidence.StudentEvidence) -> Any:
        raise RuntimeError("table unavailable")

    monkeypatch.setattr(
        student_evidence.StudentEvidence, "most_common_error_cause", property(unavailable)
    )

    assert _detail()["commonErrorCause"] is None


def test_a_cause_inferred_from_a_typed_answer_reaches_the_prep(table: FakeTable) -> None:
    """A rule's cause (#453) is stored like an authored one and read the same way."""
    inferred = error_causes.rule_cause(error_causes.RULE_SIGN)
    _dispatch_to(table, TEACHER)
    table.rows[(f"USER#{TEACHER}", "PROFILE")]["preferred_locale"] = "fr"
    _attempt(table, 1, ADDS_DENOMINATORS)
    _attempt(table, 2, inferred)
    _attempt(table, 3, inferred)

    assert _detail()["commonErrorCause"] == {
        "category": "deviation",
        "misconception": inferred["misconception"]["fr"],
        "count": 2,
        "recentMistakes": 3,
    }
