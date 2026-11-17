"""Lit stars the student answered right mostly after asking AI (#451).

The rule is `knowledge_mastery_service.lit_mostly_with_ai`: a star is named
when it is lit and more than half of its exercises answered right were answered
right only after asking Ask about them (#449). The teacher's prep for a help
request lists those stars, and nothing when there are none.
"""

from __future__ import annotations

from typing import Any

import pytest
from fakes import student_evidence as fake_evidence
from fakes.dynamodb import FakeTable

from stoa.services import knowledge_mastery_service
from stoa.services.student_evidence import RightAnswers
from test_chat_help_request_lifecycle import STUDENT, REQUEST, TEACHER, _client, _dispatch_to
from test_chat_help_request_lifecycle import table as table  # noqa: F401 - the fixture

CATALOG: dict[str, Any] = {
    "subjects": [{"id": "math", "name": "Mathematik", "order": 0}],
    "topics": [{"id": "t1", "subjectId": "math", "title": "Brüche", "order": 0}],
    "units": [
        {"id": f"u{n}", "subjectId": "math", "topicId": "t1", "title": title, "order": n}
        for n, title in enumerate(["Kürzen", "Erweitern", "Teilen", "Addieren"], start=1)
    ],
    "lessons": [
        {"id": f"l{n}", "unitId": f"u{n}", "subjectId": "math", "topicId": "t1", "order": 0}
        for n in range(1, 5)
    ],
}
EXERCISES = {
    "l1": ["l1-c1", "l1-c2", "l1-c3"],
    "l2": ["l2-c1", "l2-c2"],
    "l3": ["l3-c1", "l3-c2"],
    "l4": ["l4-c1", "l4-c2"],
}


def _right(challenge: str, *, asked_ai: bool = False) -> dict[str, Any]:
    unit = "u" + challenge[1]
    return {
        "challenge_id": challenge,
        "unit_id": unit,
        "correct": True,
        "created_at": fake_evidence.DEFAULT_MOMENT,
        **({"asked_ai": True} if asked_ai else {}),
    }


def _evidence(**facts: Any):
    return fake_evidence.evidence(STUDENT, catalog=CATALOG, exercises=EXERCISES, **facts)


# u1: lit, two of three right after asking AI - named.
# u2: lit, one of two after asking - exactly half, not named.
# u3: lit by its quiz, its one right answer after asking - named.
# u4: every right answer after asking, but not lit - not named.
MIXED = {
    "completed": ["l1", "l2", "l4"],
    "star_quiz_passed": ["u3"],
    "attempts": [
        _right("l1-c1", asked_ai=True),
        _right("l1-c2", asked_ai=True),
        _right("l1-c3"),
        _right("l2-c1", asked_ai=True),
        _right("l2-c2"),
        _right("l3-c1", asked_ai=True),
        _right("l4-c1", asked_ai=True),
    ],
}


# ── the rule ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("independent", "asked_ai", "mostly"),
    [
        (0, 0, False),  # nothing answered right
        (1, 0, False),
        (1, 1, False),  # exactly half is not more than half
        (2, 2, False),
        (1, 2, True),
        (0, 1, True),
        (3, 4, True),
        (4, 3, False),
    ],
)
def test_mostly_means_more_than_half_after_asking_ai(
    independent: int, asked_ai: int, mostly: bool
) -> None:
    right = RightAnswers(independent=independent, asked_ai=asked_ai)

    assert knowledge_mastery_service.mostly_with_ai(right) is mostly


def test_only_lit_stars_answered_right_mostly_after_asking_are_named_in_catalog_order() -> None:
    evidence = _evidence(**MIXED)

    assert knowledge_mastery_service.lit_mostly_with_ai(evidence) == ("u1", "u3")


def test_an_exercise_also_answered_right_alone_counts_as_independent() -> None:
    """As #449 counts it: right once without asking is shown independently."""
    evidence = _evidence(
        completed=["l2"],
        attempts=[
            _right("l2-c1", asked_ai=True),
            _right("l2-c1"),
            _right("l2-c2", asked_ai=True),
        ],
    )

    assert knowledge_mastery_service.lit_mostly_with_ai(evidence) == ()


def test_a_student_who_answered_everything_alone_has_no_such_star() -> None:
    evidence = _evidence(
        completed=["l1"], attempts=[_right("l1-c1"), _right("l1-c2"), _right("l1-c3")]
    )

    assert knowledge_mastery_service.lit_mostly_with_ai(evidence) == ()


def test_naming_the_stars_does_not_change_which_are_lit() -> None:
    evidence = _evidence(**MIXED)
    before = {unit: item.state for unit, item in knowledge_mastery_service.unit_states(evidence).items()}

    knowledge_mastery_service.lit_mostly_with_ai(evidence)

    after = knowledge_mastery_service.unit_states(evidence)
    assert {unit: item.state for unit, item in after.items()} == before
    assert knowledge_mastery_service.lit_unit_ids(after.values()) == {"u1", "u2", "u3"}


# ── the teacher's prep ──────────────────────────────────────────────────────


def _detail() -> dict[str, Any]:
    response = _client(TEACHER).get(f"/teachers/me/help-requests/{REQUEST}")
    assert response.status_code == 200, response.text
    return response.json()


def test_the_prep_lists_the_lit_stars_mostly_answered_after_asking_ai(
    table: FakeTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    _dispatch_to(table, TEACHER)
    evidence = _evidence(**MIXED)
    asked = fake_evidence.install(monkeypatch, evidence)

    assert _detail()["aiHelpedStars"] == [
        {"unitId": "u1", "title": "Kürzen", "independent": 1, "askedAi": 2},
        {"unitId": "u3", "title": "Teilen", "independent": 0, "askedAi": 1},
    ]
    # One evidence for the whole prep, and the answers read once for it.
    assert asked == [STUDENT]
    assert evidence.source.reads.count("attempts") == 1


def test_without_such_stars_the_prep_lists_none(
    table: FakeTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    _dispatch_to(table, TEACHER)
    fake_evidence.install(
        monkeypatch,
        _evidence(completed=["l1"], attempts=[_right("l1-c1"), _right("l1-c2"), _right("l1-c3")]),
    )

    assert _detail()["aiHelpedStars"] == []


def test_the_request_opens_when_the_answers_cannot_be_read(
    table: FakeTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    _dispatch_to(table, TEACHER)
    fake_evidence.install(monkeypatch, _evidence(**MIXED, failing=["attempts"]))

    detail = _detail()

    assert detail["aiHelpedStars"] == []
    assert detail["commonErrorCause"] is None
