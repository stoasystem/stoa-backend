"""The star quiz: one paper that lights a whole knowledge point (#165, stoa-frontend#475)."""

import random
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from fakes.dynamodb import FakeTable

from stoa.db.repositories import practice_repo
from stoa.deps import get_actor
from stoa.routers import practice
from stoa.security.authorization import AuthorizationFacts
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.security.route_authorization import get_authorization_fact_repository
from stoa.services import knowledge_map_service, knowledge_mastery_service, star_quiz_service

LIT = knowledge_mastery_service.LearningState.LIT
# Taken before conftest swaps it for an empty default: these tests read the real one.
_RETRY_AT = knowledge_map_service._star_quiz_retry_at

# A star of three lessons, three exercises each, behind a prerequisite nobody has lit.
LESSONS = {"l1": ["c-1", "c-2", "c-3"], "l2": ["c-4", "c-5", "c-6"], "l3": ["c-7", "c-8", "c-9"]}


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
                for lesson_id in LESSONS
            ),
        ],
    }


def _exercise(challenge_id: str) -> dict:
    return {
        "challenge_id": challenge_id,
        "lesson_id": "l1",
        "subject_id": "math",
        "topic_id": "brueche",
        "unit_id": "u1",
        "prompt": f"Prompt {challenge_id}",
        "type": "text_input",
        "correct_answer": f"answer-{challenge_id}",
    }


def _actor(user_id: str = "student-1") -> Actor:
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


def _client(user_id: str = "student-1") -> TestClient:
    app = FastAPI()
    app.include_router(practice.router, prefix="/practice")
    app.dependency_overrides[get_actor] = lambda: _actor(user_id)
    app.dependency_overrides[get_authorization_fact_repository] = lambda: _Facts()
    return TestClient(app)


class _World:
    def __init__(self, table: FakeTable, reviews: list, completed: set):
        self.table = table
        self.reviews = reviews
        self.completed = completed

    def state(self, unit_id: str = "u1"):
        return knowledge_mastery_service.unit_states("student-1", catalog=_catalog())[unit_id]


def _world(monkeypatch, *, completed=(), right=()) -> _World:
    table = FakeTable()
    table.seed_active_account("student-1")
    table.seed_active_account("student-2")
    exercises = {item: _exercise(item) for ids in (*LESSONS.values(), ["c-0"]) for item in ids}
    reviews: list = []
    done = set(completed)

    monkeypatch.setattr(practice_repo, "get_table", lambda: table)
    monkeypatch.setattr(practice_repo, "get_challenge", lambda item_id: exercises.get(item_id))
    monkeypatch.setattr(practice.curriculum_service, "list_catalog", lambda **_k: _catalog())
    monkeypatch.setattr(
        knowledge_mastery_service,
        "_indexed_lessons",
        lambda: {"l0": [{"id": "c-0"}], **{k: [{"id": i} for i in v] for k, v in LESSONS.items()}},
    )
    monkeypatch.setattr(knowledge_mastery_service, "_completed_lesson_ids", lambda *a, **k: frozenset(done))
    monkeypatch.setattr(knowledge_mastery_service, "_exercises_answered_right", lambda *a, **k: frozenset(right))
    # The real read of the passes, from the table the routes write to.
    monkeypatch.setattr(
        knowledge_mastery_service,
        "_star_quiz_passed",
        lambda student_id: practice_repo.star_quiz_passed_unit_ids(student_id),
    )
    monkeypatch.setattr(
        practice.review_service,
        "record_answer",
        lambda **kwargs: reviews.append((kwargs["challenge"]["challenge_id"], kwargs["correct"])),
    )
    monkeypatch.setattr(practice, "_record_practice_usage", lambda **_k: None)
    return _World(table, reviews, done)


def _start(client: TestClient, unit_id: str = "u1"):
    return client.post(f"/practice/knowledge-map/stars/{unit_id}/quiz")


def _answer(client: TestClient, quiz: dict, *, right: bool, exercise_id: str | None = None):
    asked = exercise_id or quiz["exercise"]["challengeId"]
    return client.post(
        f"/practice/knowledge-map/stars/{quiz['unitId']}/quiz/{quiz['quizId']}/answer",
        json={"exerciseId": asked, "answer": f"answer-{asked}" if right else "wrong"},
    )


def _take(client: TestClient, *, wrong_at: set[int]) -> tuple[dict, list[str]]:
    """Answer a whole paper, getting the answers at `wrong_at` (0-based) wrong."""
    quiz = _start(client).json()
    asked: list[str] = []
    index = 0
    while quiz.get("exercise"):
        asked.append(quiz["exercise"]["challengeId"])
        response = _answer(client, quiz, right=index not in wrong_at)
        assert response.status_code == 200, response.text
        quiz = response.json()
        index += 1
    return quiz, asked


# ── the paper ────────────────────────────────────────────────────────────────


def test_a_paper_asks_every_lesson_and_six_to_ten_in_all() -> None:
    for seed in range(20):
        paper = star_quiz_service.compose(list(LESSONS.values()), random.Random(seed))

        assert len(paper) == 6
        assert all(any(item in paper for item in ids) for ids in LESSONS.values())
        # Course order: the lessons' exercises come in the order the chapter teaches them.
        flat = [item for ids in LESSONS.values() for item in ids]
        assert paper == sorted(paper, key=flat.index)


def test_a_star_with_fewer_exercises_asks_them_all() -> None:
    assert sorted(star_quiz_service.compose([["a", "b"], ["c"]], random.Random(1))) == ["a", "b", "c"]


def test_a_paper_asks_one_per_lesson_between_six_and_ten() -> None:
    sizes = {
        count: len(
            star_quiz_service.compose(
                [[f"{n}-{k}" for k in range(5)] for n in range(count)], random.Random(count)
            )
        )
        for count in (1, 4, 6, 8, 10)
    }

    assert sizes == {1: 5, 4: 6, 6: 6, 8: 8, 10: 10}


def test_a_star_of_more_than_ten_lessons_still_asks_each_one() -> None:
    lessons = [[f"{n}-a", f"{n}-b"] for n in range(12)]

    paper = star_quiz_service.compose(lessons, random.Random(3))

    assert len(paper) == 12
    assert all(any(item in paper for item in ids) for ids in lessons)


def test_a_lesson_with_no_exercise_is_skipped_not_asked() -> None:
    assert star_quiz_service.compose([[], ["a"]], random.Random(4)) == ["a"]


# ── who may take it ──────────────────────────────────────────────────────────


def test_a_star_behind_an_unlit_prerequisite_can_be_taken(monkeypatch) -> None:
    world = _world(monkeypatch)
    assert world.state().unlit_prerequisite_ids == ("u0",)

    response = _start(_client())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "inProgress"
    assert body["total"] == 6
    assert body["mistakesAllowed"] == 1
    assert "correct_answer" not in str(body)


def test_a_star_in_progress_can_be_taken(monkeypatch) -> None:
    _world(monkeypatch, completed={"l1"}, right={"c-1", "c-2", "c-3"})

    assert _start(_client()).status_code == 200


def test_a_lit_star_cannot_be_taken(monkeypatch) -> None:
    _world(monkeypatch, completed=set(LESSONS), right={i for ids in LESSONS.values() for i in ids})

    response = _start(_client())

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "star_quiz_already_lit"


def test_an_unknown_star_is_not_found(monkeypatch) -> None:
    _world(monkeypatch)

    response = _start(_client(), "no-such-star")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "star_quiz_unknown_star"


def test_starting_again_hands_back_the_paper_already_open(monkeypatch) -> None:
    _world(monkeypatch)
    client = _client()
    first = _start(client).json()
    _answer(client, first, right=True)

    again = _start(client).json()

    assert again["quizId"] == first["quizId"]
    assert again["answered"] == 1


# ── passing ──────────────────────────────────────────────────────────────────


def test_passing_with_one_mistake_lights_the_star_from_the_quiz(monkeypatch) -> None:
    world = _world(monkeypatch)

    result, asked = _take(_client(), wrong_at={2})

    assert result["status"] == "passed"
    assert result["mistakes"] == 1
    assert result["retryAt"] is None
    assert world.state().state is LIT
    ledger = practice_repo.read_lit_ledger("student-1")
    assert [(row["unit_id"], row["lit_at_source"]) for row in ledger["units"]] == [("u1", "quiz")]
    # Every answer of the paper is scheduled, right or wrong, as ordinary practice would be.
    assert world.reviews == [(item, index != 2) for index, item in enumerate(asked)]


def test_passing_leaves_the_lessons_as_they_were(monkeypatch) -> None:
    world = _world(monkeypatch)

    _take(_client(), wrong_at=set())

    state = world.state()
    assert state.state is LIT
    assert state.lessons_done == 0
    assert state.next_lesson is not None and state.next_lesson.lesson_id == "l1"
    assert practice_repo.get_progress("student-1", None) == []


def test_a_star_lit_by_its_quiz_is_celebrated_and_says_so_on_the_map(monkeypatch) -> None:
    _world(monkeypatch)
    _take(_client(), wrong_at=set())
    facts = knowledge_map_service._stored_lit_facts(practice_repo.read_lit_ledger("student-1")["units"])

    assert facts["u1"].source is knowledge_mastery_service.LitSource.QUIZ
    assert knowledge_mastery_service.unacknowledged_lit(facts) == ("u1",)


def test_a_passed_star_stays_lit_when_a_lesson_is_added(monkeypatch) -> None:
    world = _world(monkeypatch)
    _take(_client(), wrong_at=set())
    LESSONS["l4"] = ["c-10"]
    try:
        catalog = _catalog()
        states = knowledge_mastery_service.unit_states("student-1", catalog=catalog)
    finally:
        del LESSONS["l4"]

    assert states["u1"].state is LIT
    assert world.state().state is LIT


# ── losing ───────────────────────────────────────────────────────────────────


def test_a_second_mistake_loses_at_once_and_leaves_no_trace(monkeypatch) -> None:
    world = _world(monkeypatch)
    before = datetime.now(timezone.utc)

    result, asked = _take(_client(), wrong_at={0, 1})

    assert result["status"] == "failed"
    assert len(asked) == 2
    retry = datetime.fromisoformat(result["retryAt"])
    assert before + timedelta(hours=24) <= retry <= datetime.now(timezone.utc) + timedelta(hours=24)
    assert world.reviews == []
    assert world.state().state is not LIT
    assert practice_repo.read_lit_ledger("student-1")["units"] == []


def test_a_lost_star_cannot_be_taken_again_for_24_hours(monkeypatch) -> None:
    _world(monkeypatch)
    client = _client()
    lost, _ = _take(client, wrong_at={0, 1})

    response = _start(client)

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "star_quiz_cooling_down",
        "message": "This quiz can be taken again later.",
        "retryAt": lost["retryAt"],
    }


def test_a_lost_star_can_be_taken_once_the_24_hours_are_over(monkeypatch) -> None:
    world = _world(monkeypatch)
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    practice_repo.put_star_quiz_cooldown(
        "student-1", unit_id="u1", quiz_id="old", retry_at=past.isoformat(), expires_at=0
    )

    assert _start(_client()).status_code == 200
    assert world.state().state is not LIT


def test_the_map_says_when_a_lost_star_can_be_taken_again(monkeypatch) -> None:
    _world(monkeypatch)
    lost, _ = _take(_client(), wrong_at={0, 1})

    retry = _RETRY_AT("student-1")
    sky = knowledge_map_service.build_map(
        subject_id="math",
        catalog=_catalog(),
        unit_states=knowledge_mastery_service.unit_states("student-1", catalog=_catalog()),
        review_due_by_unit={},
        streak_days=0,
        score=0,
        enrolled_subject_ids=frozenset({"math"}),
        star_quiz_retry_at=retry,
    )

    assert retry == {"u1": lost["retryAt"]}
    assert {star["unitId"]: star["starQuizRetryAt"] for star in sky["stars"]} == {
        "u0": None,
        "u1": lost["retryAt"],
    }


# ── answering ────────────────────────────────────────────────────────────────


def test_the_same_answer_sent_twice_is_judged_once(monkeypatch) -> None:
    _world(monkeypatch)
    client = _client()
    quiz = _start(client).json()
    asked = quiz["exercise"]["challengeId"]

    first = _answer(client, quiz, right=False).json()
    # A retry after a lost response: same exercise, even a different answer.
    again = _answer(client, quiz, right=True, exercise_id=asked).json()

    assert again == first
    assert again["correct"] is False
    assert again["answered"] == 1


def test_an_answer_to_another_exercise_is_refused(monkeypatch) -> None:
    _world(monkeypatch)
    client = _client()
    quiz = _start(client).json()
    later = next(item for ids in LESSONS.values() for item in ids if item != quiz["exercise"]["challengeId"])

    response = _answer(client, quiz, right=True, exercise_id=later)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "star_quiz_out_of_order"


def test_another_students_paper_is_not_found(monkeypatch) -> None:
    _world(monkeypatch)
    quiz = _start(_client()).json()

    response = _answer(_client("student-2"), quiz, right=True)

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "star_quiz_not_found"


def test_a_finished_paper_takes_no_new_answer(monkeypatch) -> None:
    _world(monkeypatch)
    client = _client()
    quiz = _start(client).json()
    result, asked = _take(client, wrong_at={0, 1})

    response = _answer(client, quiz, right=True, exercise_id="c-9" if "c-9" not in asked else "c-8")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "star_quiz_finished"


def test_an_expired_paper_takes_no_answer(monkeypatch) -> None:
    world = _world(monkeypatch)
    client = _client()
    quiz = _start(client).json()
    key = {"PK": practice_repo.quiz_partition("student-1"), "SK": f"STARQUIZ#{quiz['quizId']}"}
    world.table.rows[(key["PK"], key["SK"])]["expires_at"] = 0

    response = _answer(client, quiz, right=True)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "star_quiz_expired"


# ── the lesson quiz is not this ──────────────────────────────────────────────


def test_the_lesson_quiz_still_completes_one_lesson_and_lights_nothing() -> None:
    import inspect

    source = inspect.getsource(practice.answer_lesson_quiz)
    assert "star_quiz" not in source and "record_lit_unit" not in source
