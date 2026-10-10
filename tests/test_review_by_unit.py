"""A review session for one knowledge point (#70).

The star map offers "review N questions" on a unit; opening it has to hand back
that unit's cards and no others. The selection therefore happens before the
page is cut, and `dueCount` is the size of the selected set rather than the
length of the page -- otherwise a unit whose cards sort behind a fuller one
comes back empty while its badge says there is work.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fakes.dynamodb import FakeTable

from stoa.db.repositories import review_repo
from stoa.models.practice import DEFAULT_CHALLENGE_TYPE
from stoa.services import (
    curriculum_service,
    knowledge_map_service,
    practice_projection_service,
    review_service,
)
from stoa.services.review_scheduler import CardState

NOW = datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc)
STUDENT = "student-1"

LESSONS = [
    {"id": "lesson-a", "unitId": "unit-a", "subjectId": "math", "topicId": "t1"},
    {"id": "lesson-b", "unitId": "unit-b", "subjectId": "math", "topicId": "t1"},
    {"id": "lesson-c", "unitId": "unit-c", "subjectId": "math", "topicId": "t1"},
]

CATALOG = {"subjects": [], "topics": [], "units": [], "lessons": LESSONS}


def use_table(monkeypatch) -> FakeTable:
    table = FakeTable()
    table.seed_active_account(STUDENT)
    monkeypatch.setattr(review_repo, "get_table", lambda: table)
    monkeypatch.setattr(review_repo, "_write_generation", lambda *a, **k: 1)
    monkeypatch.setattr(curriculum_service, "list_catalog", lambda **kwargs: CATALOG)
    return table


def use_challenges(monkeypatch, challenges: dict[str, dict[str, Any]]) -> None:
    monkeypatch.setattr(
        review_service.practice_repo,
        "get_challenge",
        lambda challenge_id: challenges.get(challenge_id),
    )


def challenge(challenge_id: str, lesson_id: str) -> dict[str, Any]:
    return {
        "challenge_id": challenge_id,
        "lesson_id": lesson_id,
        "subject_id": "math",
        "topic_id": "t1",
        "prompt": f"Frage {challenge_id}",
        "options": ["1", "2"],
        "type": "multiple_choice",
    }


def put_card(challenge_id: str, *, due_at: datetime, lesson_id: str = "") -> None:
    review_repo.save_card(
        STUDENT,
        challenge_id,
        CardState(
            stability=1.0,
            difficulty=5.0,
            due_at=due_at,
            last_reviewed_at=due_at - timedelta(days=1),
            reps=1,
            lapses=0,
        ),
        lesson_id=lesson_id,
        subject_id="math",
        topic_id="t1",
    )


def seed_a_and_b(monkeypatch) -> None:
    """Twenty cards on unit A sorting ahead of the single card on unit B."""
    challenges: dict[str, dict[str, Any]] = {}
    for index in range(20):
        card_id = f"a-{index:02d}"
        put_card(card_id, due_at=NOW - timedelta(hours=20 - index), lesson_id="lesson-a")
        challenges[card_id] = challenge(card_id, "lesson-a")
    put_card("b-0", due_at=NOW - timedelta(minutes=1), lesson_id="lesson-b")
    challenges["b-0"] = challenge("b-0", "lesson-b")
    use_challenges(monkeypatch, challenges)


def test_a_unit_behind_a_fuller_one_still_hands_back_its_own_card(monkeypatch) -> None:
    """The acceptance example: A fills the page, B must not come back empty."""
    use_table(monkeypatch)
    seed_a_and_b(monkeypatch)

    result = review_service.due_review(student_id=STUDENT, now=NOW, unit_id="unit-b")

    assert [item["challengeId"] for item in result["items"]] == ["b-0"]
    assert result["dueCount"] == 1


def test_the_due_count_is_the_whole_set_not_the_page(monkeypatch) -> None:
    use_table(monkeypatch)
    challenges: dict[str, dict[str, Any]] = {}
    for index in range(25):
        card_id = f"c-{index:02d}"
        put_card(card_id, due_at=NOW - timedelta(hours=25 - index), lesson_id="lesson-c")
        challenges[card_id] = challenge(card_id, "lesson-c")
    use_challenges(monkeypatch, challenges)

    result = review_service.due_review(student_id=STUDENT, now=NOW, unit_id="unit-c")

    assert result["dueCount"] == 25
    assert len(result["items"]) == 20
    assert [item["challengeId"] for item in result["items"]] == [
        f"c-{index:02d}" for index in range(20)
    ]


def test_the_unit_count_agrees_with_the_star_map_badge(monkeypatch) -> None:
    """`dueCount` and the map's `reviewDue` must be one number, not two.

    The cards here are attributed through `lesson_id`. The `challenge_id`
    fallback is pinned on its own below, and joins this comparison once the
    read model carries it too (#57).
    """
    use_table(monkeypatch)
    seed_a_and_b(monkeypatch)

    badges = knowledge_map_service._review_due_by_unit(STUDENT, LESSONS)

    for unit_id in ("unit-a", "unit-b", "unit-c"):
        counted = review_service.due_review(
            student_id=STUDENT, now=NOW, unit_id=unit_id
        )["dueCount"]
        assert counted == badges.get(unit_id, 0), unit_id


def test_a_card_is_placed_by_its_lesson_before_its_challenge(monkeypatch) -> None:
    """`lesson_id` first, `challenge_id` only when the card carries no lesson."""
    use_table(monkeypatch)
    put_card("orphan", due_at=NOW - timedelta(hours=1), lesson_id="lesson-b")
    use_challenges(monkeypatch, {})

    result = review_service.due_review(student_id=STUDENT, now=NOW, unit_id="unit-b")

    # The question itself is gone, so there is nothing to attempt...
    assert result["items"] == []
    # ...but the card is still due, and the badge counts it.
    assert result["dueCount"] == 1


def test_a_card_without_a_lesson_is_placed_by_its_challenge(monkeypatch) -> None:
    use_table(monkeypatch)
    put_card("loose", due_at=NOW - timedelta(hours=1))
    use_challenges(monkeypatch, {"loose": challenge("loose", "lesson-b")})

    result = review_service.due_review(student_id=STUDENT, now=NOW, unit_id="unit-b")

    assert [item["challengeId"] for item in result["items"]] == ["loose"]
    assert result["dueCount"] == 1


def test_a_card_outside_the_active_curriculum_belongs_to_no_unit(monkeypatch) -> None:
    use_table(monkeypatch)
    put_card("retired", due_at=NOW - timedelta(hours=1), lesson_id="lesson-withdrawn")
    use_challenges(monkeypatch, {"retired": challenge("retired", "lesson-withdrawn")})

    for unit_id in ("unit-a", "unit-b", "unit-c"):
        result = review_service.due_review(
            student_id=STUDENT, now=NOW, unit_id=unit_id
        )
        assert result["items"] == []
        assert result["dueCount"] == 0


def test_without_a_unit_the_answer_is_what_it_always_was(monkeypatch) -> None:
    use_table(monkeypatch)
    seed_a_and_b(monkeypatch)

    result = review_service.due_review(student_id=STUDENT, now=NOW)

    # The old page: the first twenty due cards, soonest first, counted by page.
    assert [item["challengeId"] for item in result["items"]] == [
        f"a-{index:02d}" for index in range(20)
    ]
    assert result["dueCount"] == 20
    assert result["generatedAt"] == NOW.isoformat()


# ── a question with no stored type is the same kind on both pages (#124) ──


def _typeless(challenge_id: str, lesson_id: str) -> dict[str, Any]:
    """A curriculum row exactly as 60 of the 120 in production stand: no `type`.

    No `options` either, which is why a `multiple_choice` default made it
    unanswerable: a choice question with nothing to choose from.
    """
    return {
        "challenge_id": challenge_id,
        "lesson_id": lesson_id,
        "subject_id": "math",
        "topic_id": "t1",
        "unit_id": "unit-a",
        "grade_level": "Sek1",
        "prompt": f"Frage {challenge_id}",
    }


def _review_types(monkeypatch, challenges: dict[str, dict[str, Any]]) -> dict[str, str]:
    use_table(monkeypatch)
    use_challenges(monkeypatch, challenges)
    for challenge_id, raw in challenges.items():
        put_card(challenge_id, due_at=NOW - timedelta(hours=1), lesson_id=raw["lesson_id"])
    due = review_service.due_review(student_id=STUDENT, now=NOW)
    return {item["challengeId"]: item["type"] for item in due["items"]}


def _lesson_types(challenges: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {
        challenge_id: practice_projection_service.build_challenge_preview(raw)["type"]
        for challenge_id, raw in challenges.items()
    }


def test_a_question_is_the_same_kind_on_the_review_page_as_in_its_lesson(monkeypatch) -> None:
    """The two paths compared with each other, not with a literal.

    Asserting either side equals `"text_input"` leaves the other free to drift,
    which is the state this found: the lesson stage said `text_input` and the
    review page said `multiple_choice` for the same row.
    """
    challenges = {
        "c-none": _typeless("c-none", "lesson-a"),
        "c-text": {**_typeless("c-text", "lesson-a"), "type": "text_input"},
        "c-choice": {
            **_typeless("c-choice", "lesson-a"),
            "type": "multiple_choice",
            "options": ["1", "2"],
        },
        "c-blank": {**_typeless("c-blank", "lesson-a"), "type": ""},
    }

    assert _review_types(monkeypatch, challenges) == _lesson_types(challenges)


def test_the_two_paths_are_not_agreeing_by_saying_nothing(monkeypatch) -> None:
    """The negative control.

    Two implementations that both returned `""` - or both dropped the field -
    would satisfy the comparison above. The kinds actually produced have to be
    the kinds the rows asked for, and a row with no type has to come out as
    the shared default rather than as a choice question.
    """
    challenges = {
        "c-none": _typeless("c-none", "lesson-a"),
        "c-choice": {
            **_typeless("c-choice", "lesson-a"),
            "type": "multiple_choice",
            "options": ["1", "2"],
        },
    }

    produced = _review_types(monkeypatch, challenges)

    assert produced == {
        "c-none": DEFAULT_CHALLENGE_TYPE,
        "c-choice": "multiple_choice",
    }
    assert DEFAULT_CHALLENGE_TYPE != "multiple_choice"


def test_a_question_with_no_type_is_never_sent_as_a_choice_with_no_choices(monkeypatch) -> None:
    """What the student actually hits: nothing to choose from and no way to answer."""
    challenges = {"c-none": _typeless("c-none", "lesson-a")}

    use_table(monkeypatch)
    use_challenges(monkeypatch, challenges)
    put_card("c-none", due_at=NOW - timedelta(hours=1), lesson_id="lesson-a")
    item = review_service.due_review(student_id=STUDENT, now=NOW)["items"][0]

    assert item["options"] == []
    assert item["type"] != "multiple_choice"
