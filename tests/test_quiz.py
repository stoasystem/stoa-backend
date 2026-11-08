"""The quiz module: the lesson quiz and the star quiz as two kinds of one paper (#213).

Four parts:

* the pure rules (`quiz.rules`): what a paper asks, and where it stands;
* the interface, table-driven over both kinds: the answer ladder (replay, out
  of order, expired, finished, gone, a race), and what passing and losing do;
* what only one kind does (hearts and the credential; who may take a star,
  the cooldown, the map);
* the routes: one call each, every refusal mapped to its kind's error code,
  and a lesson-quiz answer that must name its exercise.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fakes.dynamodb import FakeTable
from rule_violation_helpers import assert_violation

from stoa.db.repositories import practice_repo, review_repo, usage_ledger_repo
from stoa.deps import get_actor
from stoa.routers import practice
from stoa.security.authorization import AuthorizationFacts
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.security.route_authorization import get_authorization_fact_repository
from stoa.services import (
    answer_recording,
    knowledge_map_service,
    knowledge_mastery_service,
    quiz,
    student_evidence,
    usage_ledger_service,
)
from stoa.services.quiz import rules

STUDENT = "student-1"
LIT = knowledge_mastery_service.LearningState.LIT

#: The lesson a lesson quiz is drawn from: three exercises.
LESSON = {
    "lesson_id": "lesson-1",
    "subject_id": "math",
    "topic_id": "brueche",
    "unit_id": "u0",
    "title": "Lesson one",
}
LESSON_EXERCISES = ["e-0", "e-1", "e-2"]
#: A star of three lessons, three exercises each, behind a prerequisite nobody has lit.
STAR_LESSONS = {
    "l1": ["c-1", "c-2", "c-3"],
    "l2": ["c-4", "c-5", "c-6"],
    "l3": ["c-7", "c-8", "c-9"],
}


def _catalog() -> dict:
    return {
        "subjects": [{"id": "math", "order": 1}],
        "topics": [{"id": "brueche", "subjectId": "math", "title": "Brüche", "order": 1}],
        "units": [
            {"id": "u0", "subjectId": "math", "topicId": "brueche", "title": "u0", "order": 1},
            {
                "id": "u1",
                "subjectId": "math",
                "topicId": "brueche",
                "title": "u1",
                "order": 2,
                "prerequisiteUnitIds": ["u0"],
            },
        ],
        "lessons": [
            {"id": "l0", "unitId": "u0", "subjectId": "math", "topicId": "brueche"},
            *(
                {"id": lesson_id, "unitId": "u1", "subjectId": "math", "topicId": "brueche"}
                for lesson_id in STAR_LESSONS
            ),
        ],
    }


def _exercise(exercise_id: str, lesson_id: str) -> dict:
    return {
        "challenge_id": exercise_id,
        "lesson_id": lesson_id,
        "subject_id": "math",
        "topic_id": "brueche",
        "unit_id": "u1" if lesson_id in STAR_LESSONS else "u0",
        "prompt": f"Prompt {exercise_id}",
        "type": "text_input",
        "correct_answer": f"answer-{exercise_id}",
    }


def _right(exercise_id: str) -> str:
    return f"answer-{exercise_id}"


@dataclass
class World:
    table: FakeTable
    exercises: dict[str, dict]
    reviews: list[tuple[str, bool]]
    completed: list[tuple[str, str]]
    #: Exercises the catalog no longer resolves.
    gone: set[str]

    def paper(self, quiz_id: str, student_id: str = STUDENT) -> dict:
        return self.table.rows[(f"QUIZ#{student_id}", f"PAPER#{quiz_id}")]

    def rows(self, prefix: str, student_id: str = STUDENT) -> list[dict]:
        return [
            row
            for (pk, sk), row in self.table.rows.items()
            if pk == f"QUIZ#{student_id}" and sk.startswith(prefix)
        ]

    def star_state(self, unit_id: str = "u1"):
        return knowledge_mastery_service.unit_states(_evidence())[unit_id]


def _evidence() -> student_evidence.StudentEvidence:
    """What a fresh request reads of the student, from the table the quiz writes to."""
    return student_evidence.for_student(STUDENT)


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> World:
    table = FakeTable()
    table.seed_active_account(STUDENT)
    table.seed_active_account("student-2")
    exercises = {item: _exercise(item, "lesson-1") for item in LESSON_EXERCISES}
    exercises |= {
        item: _exercise(item, lesson_id) for lesson_id, ids in STAR_LESSONS.items() for item in ids
    }
    exercises["c-0"] = _exercise("c-0", "l0")
    state = World(table, exercises, [], [], set())

    monkeypatch.setattr(practice_repo, "get_table", lambda: table)
    monkeypatch.setattr(review_repo, "get_table", lambda: table)
    monkeypatch.setattr(usage_ledger_repo, "get_table", lambda: table)
    monkeypatch.setattr(
        practice_repo,
        "get_challenge",
        lambda item_id: None if item_id in state.gone else exercises.get(item_id),
    )
    monkeypatch.setattr(practice_repo, "get_lesson", lambda _lesson_id: dict(LESSON))
    monkeypatch.setattr(practice_repo, "get_lessons", lambda **_kwargs: [dict(LESSON)])
    monkeypatch.setattr(
        practice_repo,
        "get_challenges",
        lambda lesson_id: [exercises[item] for item in LESSON_EXERCISES]
        if lesson_id == "lesson-1"
        else [],
    )
    monkeypatch.setattr(practice_repo, "challenges_answered_right", lambda *_args: set())
    monkeypatch.setattr(
        practice_repo,
        "mark_lesson_completed",
        lambda student_id, item: state.completed.append((student_id, item["lesson_id"])),
    )
    monkeypatch.setattr(
        practice.curriculum_analytics_service, "record_lesson_completed", lambda **_kwargs: None
    )
    monkeypatch.setattr(practice.curriculum_service, "list_catalog", lambda **_k: _catalog())
    monkeypatch.setattr(
        student_evidence,
        "indexed_lessons",
        lambda: {
            "l0": [{"id": "c-0"}],
            **{key: [{"id": item} for item in ids] for key, ids in STAR_LESSONS.items()},
        },
    )
    monkeypatch.setattr(
        answer_recording.review_service,
        "record_answer",
        lambda **kwargs: state.reviews.append(
            (kwargs["challenge"]["challenge_id"], kwargs["correct"])
        ),
    )
    monkeypatch.setattr(practice, "_record_practice_usage", lambda **_k: None)
    monkeypatch.setattr(answer_recording, "record_practice_usage", lambda **_k: None)
    return state


# ── the two kinds, as the interface tests drive them ────────────────────────


@dataclass(frozen=True)
class Kind:
    name: str
    config: quiz.QuizKind
    scope_id: str
    start: Callable[..., dict]

    def asked(self, view: dict) -> str:
        return str(view["exercise"]["challengeId"])

    def answer(
        self,
        view: dict,
        *,
        right: bool,
        exercise_id: str = "asked",
        now: datetime | None = None,
        student_id: str = STUDENT,
    ) -> dict:
        named = self.asked(view) if exercise_id == "asked" else exercise_id
        return quiz.answer(
            self.config,
            student_id,
            view["quizId"],
            scope_id=self.scope_id,
            exercise_id=named,
            raw_answer=_right(named) if right else "wrong",
            locale="de",
            now=now,
        )


def _start_lesson(now: datetime | None = None, *, kind: str = rules.SKIP_QUIZ) -> dict:
    return quiz.start_lesson_quiz(STUDENT, "lesson-1", kind=kind, locale="de", now=now)


def _start_star(now: datetime | None = None) -> dict:
    return quiz.start_star_quiz(STUDENT, "u1", locale="de", now=now)


LESSON_KIND = Kind("lesson", quiz.LESSON, "lesson-1", _start_lesson)
STAR_KIND = Kind("star", quiz.STAR, "u1", _start_star)
KINDS = pytest.mark.parametrize("kind", [LESSON_KIND, STAR_KIND], ids=lambda kind: kind.name)


def _refused(reason: quiz.Reason, call: Callable[[], Any]) -> quiz.Refused:
    with pytest.raises(quiz.Refused) as refused:
        call()
    assert refused.value.reason is reason
    return refused.value


def _finish(kind: Kind, view: dict, *, wrong_at: set[int] = frozenset()) -> tuple[dict, list[str]]:
    """Answer a paper to its end, getting the answers at `wrong_at` (0-based) wrong."""
    asked: list[str] = []
    while view.get("exercise"):
        asked.append(kind.asked(view))
        view = kind.answer(view, right=len(asked) - 1 not in wrong_at)
    return view, asked


# ── the rules ───────────────────────────────────────────────────────────────


def test_a_skip_quiz_asks_every_unanswered_exercise_and_two_reviews() -> None:
    drawn = rules.compose_skip_quiz(
        ["c-1", "c-2", "c-3", "c-4"], ["c-5", "c-6", "c-7"], random.Random(1)
    )

    assert {"c-1", "c-2", "c-3", "c-4"} <= set(drawn)
    assert len(drawn) == 6


def test_a_skip_quiz_tops_up_past_two_reviews_to_reach_the_minimum_size() -> None:
    drawn = rules.compose_skip_quiz(["c-1"], ["c-2", "c-3", "c-4", "c-5"], random.Random(1))

    assert len(drawn) == 3
    assert "c-1" in drawn


def test_a_skip_quiz_cannot_ask_more_review_exercises_than_the_lesson_has() -> None:
    assert sorted(rules.compose_skip_quiz(["c-1"], ["c-2"], random.Random(1))) == ["c-1", "c-2"]


def test_a_test_out_quiz_draws_five_exercises_at_most() -> None:
    drawn = rules.compose_test_out_quiz([f"c-{index}" for index in range(9)], random.Random(1))

    assert len(drawn) == 5
    assert len(set(drawn)) == 5


def test_a_star_paper_asks_every_lesson_and_six_to_ten_in_all() -> None:
    flat = [item for ids in STAR_LESSONS.values() for item in ids]
    for seed in range(20):
        paper = rules.compose_star_quiz(list(STAR_LESSONS.values()), random.Random(seed))

        assert len(paper) == 6
        assert all(any(item in paper for item in ids) for ids in STAR_LESSONS.values())
        # Course order: the lessons' exercises come in the order the chapter teaches them.
        assert paper == sorted(paper, key=flat.index)


def test_a_star_paper_size_follows_its_lessons() -> None:
    sizes = {
        count: len(
            rules.compose_star_quiz(
                [[f"{n}-{k}" for k in range(5)] for n in range(count)], random.Random(count)
            )
        )
        for count in (1, 4, 6, 8, 10)
    }

    assert sizes == {1: 5, 4: 6, 6: 6, 8: 8, 10: 10}
    assert sorted(rules.compose_star_quiz([["a", "b"], ["c"]], random.Random(1))) == ["a", "b", "c"]
    assert rules.compose_star_quiz([[], ["a"]], random.Random(4)) == ["a"]
    twelve = [[f"{n}-a", f"{n}-b"] for n in range(12)]
    assert len(rules.compose_star_quiz(twelve, random.Random(3))) == 12


def _log(*answers: tuple[str, bool]) -> list[dict]:
    return [{"exerciseId": item, "correct": correct} for item, correct in answers]


def test_the_lesson_rule_sends_a_wrong_answer_to_the_back_and_loses_on_the_second() -> None:
    order = ["a", "b", "c"]

    assert rules.lesson_standing(order, _log(("a", False))) == rules.Standing(
        rules.IN_PROGRESS, 1, ("b", "c", "a")
    )
    assert rules.lesson_standing(order, _log(("a", False), ("b", True), ("c", True), ("a", True))) == (
        rules.Standing(rules.PASSED, 1, ())
    )
    assert rules.lesson_standing(order, _log(("a", False), ("b", False))).status == rules.FAILED
    # A dropped exercise is neither asked nor asked again.
    assert rules.lesson_standing(order, _log(("a", False)), ["a"]).remaining == ("b", "c")


def test_the_star_rule_asks_each_exercise_once_in_order() -> None:
    order = ["a", "b", "c"]

    assert rules.star_standing(order, _log(("a", False))) == rules.Standing(
        rules.IN_PROGRESS, 1, ("b", "c")
    )
    assert rules.star_standing(order, _log(("a", False), ("b", True), ("c", True))).status == (
        rules.PASSED
    )
    assert rules.star_standing(order, _log(("a", False), ("b", False))).status == rules.FAILED
    assert rules.star_standing(order, [], ["a"]).remaining == ("b", "c")


# ── the paper row ───────────────────────────────────────────────────────────


@KINDS
def test_a_paper_is_one_row_in_the_quiz_partition(world: World, kind: Kind) -> None:
    view = kind.start()
    kind.answer(view, right=True)

    paper = world.paper(view["quizId"])
    assert paper["entity_type"] == practice_repo.QUIZ_PAPER_ENTITY
    assert paper["kind"] in kind.config.paper_kinds
    assert paper[kind.config.scope_field] == kind.scope_id
    assert paper["status"] == rules.IN_PROGRESS
    assert paper["answered"] == 1
    assert [answer["exerciseId"] for answer in paper["answers"]] == [paper["order"][0]]
    assert paper["dropped"] == []
    assert int(paper["expires_at"]) > 0
    # Nothing else: no session or star paper of the old shapes.
    assert {sk.split("#")[0] for (_pk, sk) in world.table.rows if _pk == f"QUIZ#{STUDENT}"} == {
        "PAPER"
    }


@KINDS
def test_a_paper_never_hands_the_client_an_answer(world: World, kind: Kind) -> None:
    view = kind.start()
    marked = kind.answer(view, right=False)

    for exercise in world.exercises.values():
        assert exercise["correct_answer"] not in str(view)
        assert exercise["correct_answer"] not in str(marked)
    assert view["exercise"]["hintAvailable"] is False


# ── the ladder, both kinds ──────────────────────────────────────────────────


@KINDS
def test_the_same_exercise_sent_twice_is_judged_once(world: World, kind: Kind) -> None:
    view = kind.start()
    asked = kind.asked(view)

    first = kind.answer(view, right=False)
    # A retry after a lost response: same exercise, even a different answer.
    again = kind.answer(view, right=True, exercise_id=asked)

    assert again == first
    assert again["correct"] is False
    assert world.paper(view["quizId"])["answered"] == 1


@KINDS
def test_an_answer_to_another_exercise_is_out_of_order(world: World, kind: Kind) -> None:
    view = kind.start()
    paper = world.paper(view["quizId"])
    later = next(item for item in paper["order"] if item != kind.asked(view))

    _refused(quiz.Reason.OUT_OF_ORDER, lambda: kind.answer(view, right=True, exercise_id=later))
    assert world.paper(view["quizId"])["answered"] == 0


@KINDS
def test_an_expired_paper_takes_no_answer(world: World, kind: Kind) -> None:
    start = datetime.now(timezone.utc)
    view = kind.start(start)

    _refused(
        quiz.Reason.EXPIRED,
        lambda: kind.answer(view, right=True, now=start + rules.PAPER_TTL + timedelta(seconds=1)),
    )


@KINDS
def test_a_finished_paper_takes_no_new_answer(world: World, kind: Kind) -> None:
    view = kind.start()
    order = list(world.paper(view["quizId"])["order"])
    lost, asked = _finish(kind, view, wrong_at={0, 1})
    assert lost["status"] == rules.FAILED
    unasked = next(item for item in order if item not in asked)

    _refused(quiz.Reason.FINISHED, lambda: kind.answer(view, right=True, exercise_id=unasked))


@KINDS
def test_another_students_paper_is_unknown(world: World, kind: Kind) -> None:
    view = kind.start()

    _refused(
        quiz.Reason.UNKNOWN, lambda: kind.answer(view, right=True, student_id="student-2")
    )


def test_a_paper_of_one_kind_is_unknown_to_the_other(world: World) -> None:
    lesson = LESSON_KIND.start()

    _refused(
        quiz.Reason.UNKNOWN,
        lambda: quiz.answer(
            quiz.STAR,
            STUDENT,
            lesson["quizId"],
            scope_id="lesson-1",
            exercise_id=LESSON_KIND.asked(lesson),
            raw_answer="x",
            locale="de",
        ),
    )


@KINDS
def test_an_exercise_gone_from_the_catalog_is_dropped_and_the_next_one_asked(
    world: World, kind: Kind
) -> None:
    view = kind.start()
    asked = kind.asked(view)
    world.gone.add(asked)

    _refused(quiz.Reason.GONE, lambda: kind.answer(view, right=True, exercise_id=asked))

    paper = world.paper(view["quizId"])
    assert paper["dropped"] == [asked]
    assert paper["answered"] == 0
    following = next(item for item in paper["order"] if item != asked)
    reply = kind.answer(view, right=True, exercise_id=following)
    assert reply["correct"] is True
    assert reply["status"] == rules.IN_PROGRESS


@KINDS
def test_a_paper_with_nothing_left_to_ask_ends_instead_of_hanging(world: World, kind: Kind) -> None:
    view = kind.start()
    world.gone.update(world.exercises)

    _refused(quiz.Reason.GONE, lambda: kind.answer(view, right=True))
    _refused(quiz.Reason.FINISHED, lambda: kind.answer(view, right=True))
    # Ended for want of exercises, not lost: nothing a loss does.
    assert world.rows("STARQUIZ_COOLDOWN#") == []


@KINDS
def test_two_answers_racing_on_one_paper_record_one_and_replay_it(
    world: World, kind: Kind, monkeypatch: pytest.MonkeyPatch
) -> None:
    view = kind.start()
    stale = practice_repo.get_quiz_paper(STUDENT, view["quizId"])
    first = kind.answer(view, right=True)
    # The second request read the paper before the first wrote it.
    read = practice_repo.get_quiz_paper
    reads = iter([stale])
    monkeypatch.setattr(
        practice_repo, "get_quiz_paper", lambda *args, **kwargs: next(reads, None) or read(*args, **kwargs)
    )

    second = kind.answer(view, right=False)

    assert second == first
    assert world.paper(view["quizId"])["answered"] == 1


@KINDS
def test_an_answer_that_is_no_answer_is_refused_and_records_nothing(world: World, kind: Kind) -> None:
    view = kind.start()

    _refused(
        quiz.Reason.ANSWER_INVALID,
        lambda: quiz.answer(
            kind.config,
            STUDENT,
            view["quizId"],
            scope_id=kind.scope_id,
            exercise_id=kind.asked(view),
            raw_answer={"not": "an answer"},
            locale="de",
        ),
    )
    assert world.paper(view["quizId"])["answered"] == 0


# ── passing and losing, both kinds ──────────────────────────────────────────


def test_a_passed_lesson_quiz_issues_a_credential_and_lights_nothing(world: World) -> None:
    passed, _ = _finish(LESSON_KIND, LESSON_KIND.start())

    assert passed["status"] == rules.PASSED
    [credential] = world.rows("CREDENTIAL#")
    assert passed["credential"] == credential["SK"].removeprefix("CREDENTIAL#")
    assert credential["lesson_id"] == "lesson-1"
    assert credential["student_id"] == STUDENT
    assert passed["credentialExpiresAt"] == credential["expires_at_iso"]
    assert world.rows("STARQUIZ_") == []
    assert _evidence().lit_facts == {}
    assert world.reviews == []


def test_a_passed_star_quiz_lights_the_star_and_schedules_every_answer(world: World) -> None:
    passed, asked = _finish(STAR_KIND, STAR_KIND.start(), wrong_at={2})

    assert passed["status"] == rules.PASSED
    assert passed["mistakes"] == 1
    assert passed["retryAt"] is None
    assert [row["unit_id"] for row in world.rows("STARQUIZ_PASSED#")] == ["u1"]
    assert world.star_state().state is LIT
    facts = _evidence().lit_facts
    assert [(fact.unit_id, fact.source.value) for fact in facts.values()] == [("u1", "quiz")]
    assert knowledge_mastery_service.unacknowledged_lit(facts) == ("u1",)
    # Every answer of the paper is scheduled, right or wrong, as ordinary practice would be.
    assert world.reviews == [(item, index != 2) for index, item in enumerate(asked)]
    # The lessons are as they were.
    assert world.star_state().lessons_done == 0
    assert world.rows("CREDENTIAL#") == []


def test_a_lost_lesson_quiz_issues_no_credential(world: World) -> None:
    lost, _ = _finish(LESSON_KIND, LESSON_KIND.start(), wrong_at={0, 1})

    assert lost["status"] == rules.FAILED
    assert lost["credential"] is None
    assert world.rows("CREDENTIAL#") == []
    assert world.rows("STARQUIZ_") == []


def test_a_lost_star_quiz_writes_a_cooldown_and_nothing_else(world: World) -> None:
    before = datetime.now(timezone.utc)
    lost, asked = _finish(STAR_KIND, STAR_KIND.start(), wrong_at={0, 1})

    assert lost["status"] == rules.FAILED
    assert len(asked) == 2
    retry = datetime.fromisoformat(lost["retryAt"])
    assert before + rules.COOLDOWN <= retry <= datetime.now(timezone.utc) + rules.COOLDOWN
    [cooldown] = world.rows("STARQUIZ_COOLDOWN#")
    assert cooldown["retry_at"] == lost["retryAt"]
    assert world.reviews == []
    assert _evidence().lit_facts == {}


@KINDS
def test_the_answer_that_decided_the_paper_replays_with_what_it_decided(
    world: World, kind: Kind
) -> None:
    view = kind.start()
    passed, asked = _finish(kind, view)

    again = kind.answer(view, right=False, exercise_id=asked[-1])

    assert again == passed


# ── usage ───────────────────────────────────────────────────────────────────


_REAL_RECORD_PRACTICE_USAGE = answer_recording.record_practice_usage


@KINDS
def test_every_quiz_answer_writes_one_usage_event(
    world: World, kind: Kind, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The real ledger, not the silenced one: `practice_quiz_answer` had no
    # definition, so every quiz answer's event was dropped (#294).
    monkeypatch.setattr(answer_recording, "record_practice_usage", _REAL_RECORD_PRACTICE_USAGE)
    view = kind.start()
    first = kind.answer(view, right=False)
    kind.answer(first, right=True)

    events = [
        row
        for (pk, _sk), row in world.table.rows.items()
        if pk == f"USAGE_LEDGER#{STUDENT}"
        and row["action"] == usage_ledger_service.PRACTICE_QUIZ_ANSWER_ACTION
    ]
    assert sorted(row["idempotency_key"] for row in events) == [
        f"practice_quiz_answer:{view['quizId']}:{n}:{STUDENT}" for n in (1, 2)
    ]
    assert {row["metadata"]["summary_group"] for row in events} == {"practice"}


def test_the_quiz_answer_action_is_defined_like_a_practice_answer() -> None:
    definitions = {
        item["action"]: item for item in usage_ledger_service.list_usage_action_definitions()
    }

    quiz_answer = definitions[usage_ledger_service.PRACTICE_QUIZ_ANSWER_ACTION]
    assert quiz_answer["summary_group"] == "practice"
    assert quiz_answer["quota_enforced"] is False
    assert quiz_answer["support_visible"] is True
    assert usage_ledger_service.PRACTICE_QUIZ_ANSWER_ACTION in (
        usage_ledger_service.PRIVATE_LEARNING_ACTIONS & usage_ledger_repo.PRIVATE_LEARNING_ACTIONS
    )


# ── the lesson quiz alone ───────────────────────────────────────────────────


def test_a_lesson_quiz_forgives_one_wrong_answer_and_sends_it_to_the_back(world: World) -> None:
    view = LESSON_KIND.start()
    first_asked = LESSON_KIND.asked(view)
    assert view["heartsLeft"] == rules.LESSON_QUIZ_HEARTS
    assert view["remaining"] == 3

    after = LESSON_KIND.answer(view, right=False)

    assert after["correct"] is False
    assert after["status"] == rules.IN_PROGRESS
    assert after["heartsLeft"] == 1
    assert after["remaining"] == 3
    assert LESSON_KIND.asked(after) != first_asked
    lost = LESSON_KIND.answer(after, right=False)
    assert lost["status"] == rules.FAILED
    assert lost["heartsLeft"] == 0


def test_a_lesson_quiz_asks_a_wrong_exercise_again_as_a_new_answer(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    # One exercise only: answered wrong, it is the one asked again. Naming it
    # then is a new answer, not a retry of the first.
    monkeypatch.setattr(
        practice_repo, "get_challenges", lambda _lesson_id: [world.exercises["e-0"]]
    )
    view = LESSON_KIND.start()
    wrong = LESSON_KIND.answer(view, right=False)
    assert LESSON_KIND.asked(wrong) == "e-0"

    passed = LESSON_KIND.answer(wrong, right=True)

    assert passed["status"] == rules.PASSED
    assert passed["credential"]


def test_spending_a_credential_twice_is_refused(world: World) -> None:
    passed, _ = _finish(LESSON_KIND, LESSON_KIND.start())

    quiz.spend_credential(STUDENT, "lesson-1", passed["credential"])

    _refused(
        quiz.Reason.CREDENTIAL_INVALID,
        lambda: quiz.spend_credential(STUDENT, "lesson-1", passed["credential"]),
    )


def test_an_expired_credential_is_refused(world: World) -> None:
    passed, _ = _finish(LESSON_KIND, LESSON_KIND.start())
    later = datetime.now(timezone.utc) + rules.CREDENTIAL_TTL + timedelta(seconds=1)

    _refused(
        quiz.Reason.CREDENTIAL_EXPIRED,
        lambda: quiz.spend_credential(STUDENT, "lesson-1", passed["credential"], now=later),
    )


def test_a_credential_is_for_its_own_student_and_lesson(world: World) -> None:
    passed, _ = _finish(LESSON_KIND, LESSON_KIND.start())
    credential = passed["credential"]

    _refused(
        quiz.Reason.CREDENTIAL_INVALID,
        lambda: quiz.spend_credential("student-2", "lesson-1", credential),
    )
    _refused(
        quiz.Reason.CREDENTIAL_INVALID,
        lambda: quiz.spend_credential(STUDENT, "lesson-2", credential),
    )
    # Neither spent it.
    quiz.spend_credential(STUDENT, "lesson-1", credential)


def test_a_credential_that_names_no_quiz_is_refused(world: World) -> None:
    practice_repo.put_quiz_credential(
        STUDENT,
        credential_id="nameless",
        lesson_id="lesson-1",
        quiz_id="",
        expires_at=int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()),
        expires_at_iso="",
    )

    _refused(
        quiz.Reason.CREDENTIAL_INVALID,
        lambda: quiz.spend_credential(STUDENT, "lesson-1", "nameless"),
    )


def test_a_lesson_without_exercises_has_no_quiz(world: World) -> None:
    _refused(
        quiz.Reason.NOTHING_TO_ASK,
        lambda: quiz.start_lesson_quiz(STUDENT, "lesson-empty", locale="de"),
    )


def test_a_test_out_quiz_is_kept_as_its_kind(world: World) -> None:
    view = LESSON_KIND.start(kind=rules.TEST_OUT_QUIZ)

    assert view["kind"] == rules.TEST_OUT_QUIZ
    assert world.paper(view["quizId"])["kind"] == rules.TEST_OUT_QUIZ


# ── the star quiz alone ─────────────────────────────────────────────────────


def test_a_star_behind_an_unlit_prerequisite_can_be_taken(world: World) -> None:
    assert world.star_state().unlit_prerequisite_ids == ("u0",)

    view = STAR_KIND.start()

    assert view["status"] == rules.IN_PROGRESS
    assert view["total"] == 6
    assert view["mistakesAllowed"] == 1


def test_a_lit_star_cannot_be_taken(world: World) -> None:
    _finish(STAR_KIND, STAR_KIND.start())

    _refused(quiz.Reason.ALREADY_LIT, STAR_KIND.start)


def test_an_unknown_star_cannot_be_taken(world: World) -> None:
    _refused(
        quiz.Reason.NO_SUCH_STAR,
        lambda: quiz.start_star_quiz(STUDENT, "no-such-star", locale="de"),
    )


def test_starting_again_hands_back_the_paper_already_open(world: World) -> None:
    first = STAR_KIND.start()
    STAR_KIND.answer(first, right=True)

    again = STAR_KIND.start()

    assert again["quizId"] == first["quizId"]
    assert again["answered"] == 1


def test_an_expired_star_paper_is_not_handed_back(world: World) -> None:
    first = STAR_KIND.start()

    again = STAR_KIND.start(datetime.now(timezone.utc) + rules.PAPER_TTL + timedelta(seconds=1))

    assert again["quizId"] != first["quizId"]


def test_a_lost_star_cools_down_for_24_hours_then_opens(world: World) -> None:
    lost, _ = _finish(STAR_KIND, STAR_KIND.start(), wrong_at={0, 1})

    refused = _refused(quiz.Reason.COOLING_DOWN, STAR_KIND.start)
    assert refused.retry_at == lost["retryAt"]
    assert _evidence().star_quiz_retry_at == {"u1": lost["retryAt"]}

    later = datetime.fromisoformat(lost["retryAt"]) + timedelta(minutes=1)
    assert STAR_KIND.start(later)["status"] == rules.IN_PROGRESS


def test_the_map_says_when_a_lost_star_can_be_taken_again(world: World) -> None:
    lost, _ = _finish(STAR_KIND, STAR_KIND.start(), wrong_at={0, 1})

    sky = knowledge_map_service.build_map(
        subject_id="math",
        catalog=_catalog(),
        unit_states=knowledge_mastery_service.unit_states(_evidence()),
        review_due_by_unit={},
        streak_days=0,
        score=0,
        enrolled_subject_ids=frozenset({"math"}),
        star_quiz_retry_at=_evidence().star_quiz_retry_at,
    )

    assert {star["unitId"]: star["starQuizRetryAt"] for star in sky["stars"]} == {
        "u0": None,
        "u1": lost["retryAt"],
    }


def test_a_passed_star_stays_lit_when_a_lesson_is_added(world: World) -> None:
    _finish(STAR_KIND, STAR_KIND.start())
    STAR_LESSONS["l4"] = ["c-10"]
    try:
        state = knowledge_mastery_service.unit_states(_evidence())["u1"]
    finally:
        del STAR_LESSONS["l4"]

    assert state.state is LIT


# ── the routes ──────────────────────────────────────────────────────────────


def _actor(user_id: str = STUDENT) -> Actor:
    return Actor(
        user_id=user_id,
        issuer="https://identity.test",
        subject=f"{user_id}-subject",
        role=CanonicalRole.STUDENT,
        account_status=AccountStatus.ACTIVE,
        cognito_group="student",
    )


class _Facts:
    async def facts_for(self, *_args):
        return AuthorizationFacts()


def _client(user_id: str = STUDENT) -> TestClient:
    app = FastAPI()
    app.include_router(practice.router, prefix="/practice")
    app.dependency_overrides[get_actor] = lambda: _actor(user_id)
    app.dependency_overrides[get_authorization_fact_repository] = lambda: _Facts()
    return TestClient(app)


LESSON_START = ("lesson start", "start_lesson_quiz", "post", "/practice/lessons/lesson-1/quiz", {})
LESSON_ANSWER = (
    "lesson answer",
    "answer",
    "post",
    "/practice/lessons/lesson-1/quiz/q/answer",
    {"answer": "x", "exerciseId": "e-0"},
)
STAR_START = ("star start", "start_star_quiz", "post", "/practice/knowledge-map/stars/u1/quiz", {})
STAR_ANSWER = (
    "star answer",
    "answer",
    "post",
    "/practice/knowledge-map/stars/u1/quiz/q/answer",
    {"answer": "x", "exerciseId": "c-1"},
)
COMPLETE = (
    "complete",
    "spend_credential",
    "post",
    "/practice/lessons/lesson-1/complete",
    {"quizCredential": "c"},
)

ROUTE_REFUSALS = [
    (LESSON_START, quiz.Reason.NOTHING_TO_ASK, "lesson_quiz_unavailable"),
    (LESSON_ANSWER, quiz.Reason.UNKNOWN, "lesson_quiz_not_found"),
    (LESSON_ANSWER, quiz.Reason.FINISHED, "lesson_quiz_finished"),
    (LESSON_ANSWER, quiz.Reason.EXPIRED, "lesson_quiz_expired"),
    (LESSON_ANSWER, quiz.Reason.GONE, "lesson_quiz_unavailable"),
    (LESSON_ANSWER, quiz.Reason.OUT_OF_ORDER, "lesson_quiz_out_of_order"),
    (LESSON_ANSWER, quiz.Reason.ANSWER_INVALID, "practice_answer_invalid"),
    (COMPLETE, quiz.Reason.CREDENTIAL_INVALID, "lesson_quiz_credential_invalid"),
    (COMPLETE, quiz.Reason.CREDENTIAL_EXPIRED, "lesson_quiz_credential_expired"),
    (STAR_START, quiz.Reason.NO_SUCH_STAR, "star_quiz_unknown_star"),
    (STAR_START, quiz.Reason.ALREADY_LIT, "star_quiz_already_lit"),
    (STAR_START, quiz.Reason.NOTHING_TO_ASK, "star_quiz_unavailable"),
    (STAR_ANSWER, quiz.Reason.UNKNOWN, "star_quiz_not_found"),
    (STAR_ANSWER, quiz.Reason.FINISHED, "star_quiz_finished"),
    (STAR_ANSWER, quiz.Reason.EXPIRED, "star_quiz_expired"),
    (STAR_ANSWER, quiz.Reason.GONE, "star_quiz_unavailable"),
    (STAR_ANSWER, quiz.Reason.OUT_OF_ORDER, "star_quiz_out_of_order"),
    (STAR_ANSWER, quiz.Reason.ANSWER_INVALID, "practice_answer_invalid"),
]


@pytest.mark.parametrize(
    ("route", "reason", "code"),
    ROUTE_REFUSALS,
    ids=[f"{route[0]}-{reason.value}" for route, reason, _ in ROUTE_REFUSALS],
)
def test_each_refusal_is_its_kinds_error(
    world: World, monkeypatch: pytest.MonkeyPatch, route: tuple, reason: quiz.Reason, code: str
) -> None:
    _name, function, method, path, body = route

    def refuse(*_args: Any, **_kwargs: Any) -> None:
        raise quiz.Refused(reason)

    monkeypatch.setattr(quiz, function, refuse)

    response = getattr(_client(), method)(path, json=body)

    assert_violation(response, code)


def test_a_star_cooling_down_says_when_it_opens(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: Any, **_kwargs: Any) -> None:
        raise quiz.Refused(quiz.Reason.COOLING_DOWN, retry_at="2026-11-08T10:00:00+00:00")

    monkeypatch.setattr(quiz, "start_star_quiz", refuse)

    response = _client().post("/practice/knowledge-map/stars/u1/quiz")

    assert_violation(response, "star_quiz_cooling_down", retryAt="2026-11-08T10:00:00+00:00")


def test_the_lesson_quiz_answer_body_needs_its_exercise_id(world: World) -> None:
    client = _client()
    view = client.post("/practice/lessons/lesson-1/quiz", json={"kind": "skip"}).json()
    path = f"/practice/lessons/lesson-1/quiz/{view['quizId']}/answer"
    asked = view["exercise"]["challengeId"]

    unnamed = client.post(path, json={"answer": _right(asked)})
    empty = client.post(path, json={"answer": _right(asked), "exerciseId": ""})
    unknown_field = client.post(path, json={"answer": "x", "exerciseId": asked, "somethingElse": 1})

    assert unnamed.status_code == 422
    assert empty.status_code == 422
    assert unknown_field.status_code == 422
    assert world.paper(view["quizId"])["answered"] == 0
    # The practice answer keeps refusing anything but its answer.
    assert (
        client.post("/practice/challenges/e-0/answer", json={"answer": "x", "exerciseId": "e-0"}).status_code
        == 422
    )


def test_a_lesson_quiz_answer_sent_again_through_its_route_gets_the_first_result(
    world: World,
) -> None:
    client = _client()
    view = client.post("/practice/lessons/lesson-1/quiz", json={"kind": "skip"}).json()
    path = f"/practice/lessons/lesson-1/quiz/{view['quizId']}/answer"
    asked = view["exercise"]["challengeId"]

    first = client.post(path, json={"answer": _right(asked), "exerciseId": asked})
    # The response was lost; the client sends the same answer again.
    again = client.post(path, json={"answer": _right(asked), "exerciseId": asked})

    assert first.status_code == 200, first.text
    assert again.status_code == 200, again.text
    assert again.json() == first.json()
    assert world.paper(view["quizId"])["answered"] == 1


def test_a_lesson_quiz_is_taken_through_its_routes(world: World) -> None:
    client = _client()
    view = client.post("/practice/lessons/lesson-1/quiz", json={"kind": "skip"}).json()
    quiz_id = view["quizId"]
    wrong_once = False
    while view["exercise"] is not None:
        asked = view["exercise"]["challengeId"]
        answer = "wrong" if not wrong_once else _right(asked)
        wrong_once = True
        reply = client.post(
            f"/practice/lessons/lesson-1/quiz/{quiz_id}/answer",
            json={"answer": answer, "exerciseId": asked},
        )
        assert reply.status_code == 200, reply.text
        view = reply.json()

    assert view["status"] == rules.PASSED
    assert view["heartsLeft"] == 1
    done = client.post(
        "/practice/lessons/lesson-1/complete", json={"quizCredential": view["credential"]}
    )
    assert done.status_code == 200, done.text
    assert world.completed == [(STUDENT, "lesson-1")]
    again = client.post(
        "/practice/lessons/lesson-1/complete", json={"quizCredential": view["credential"]}
    )
    assert_violation(again, "lesson_quiz_credential_invalid")


def test_a_star_quiz_is_taken_through_its_routes(world: World) -> None:
    client = _client()
    view = client.post("/practice/knowledge-map/stars/u1/quiz").json()
    while view["exercise"] is not None:
        asked = view["exercise"]["challengeId"]
        reply = client.post(
            f"/practice/knowledge-map/stars/u1/quiz/{view['quizId']}/answer",
            json={"exerciseId": asked, "answer": _right(asked)},
        )
        assert reply.status_code == 200, reply.text
        view = reply.json()

    assert view["status"] == rules.PASSED
    assert world.star_state().state is LIT
    assert_violation(client.post("/practice/knowledge-map/stars/u1/quiz"), "star_quiz_already_lit")


def test_completing_without_a_credential_still_needs_every_exercise_right(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(practice_repo, "unanswered_challenge_ids", lambda *_args: ["e-1"])

    response = _client().post("/practice/lessons/lesson-1/complete")

    assert_violation(response, "lesson_exercises_unanswered")
    assert world.completed == []
