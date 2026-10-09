"""The lesson quiz: drawing it, judging it, and the credential it issues (#92, #83)."""

import random

from fastapi import FastAPI
from fastapi.testclient import TestClient

from fakes.dynamodb import FakeTable

from stoa.deps import get_actor
from stoa.routers import practice
from stoa.security.authorization import AuthorizationFacts
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.security.route_authorization import get_authorization_fact_repository
from stoa.services import knowledge_mastery_service, lesson_quiz_service, usage_ledger_service


LESSON = {
    "lesson_id": "lesson-1",
    "subject_id": "math",
    "topic_id": "algebra",
    "unit_id": "unit-1",
    "title": "Lesson one",
}


def _exercise(index: int) -> dict:
    return {
        "challenge_id": f"c-{index}",
        "lesson_id": "lesson-1",
        "subject_id": "math",
        "topic_id": "algebra",
        "unit_id": "unit-1",
        "prompt": f"Prompt {index}",
        "type": "text_input",
        "correct_answer": f"answer-{index}",
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


def _client(actor: Actor | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(practice.router, prefix="/practice")
    app.dependency_overrides[get_actor] = lambda: actor or _actor()
    app.dependency_overrides[get_authorization_fact_repository] = lambda: _Facts()
    return TestClient(app)


def _judged(state: knowledge_mastery_service.LearningState):
    return knowledge_mastery_service.UnitMastery(
        unit_id="unit-1",
        topic_id="algebra",
        subject_id="math",
        state=state,
        progress=0.0,
        unmet_exercises=0,
        lesson_count=1,
        lessons_done=0,
        next_lesson=None,
    )


def _world(monkeypatch, *, exercises, answered_right=(), locked=False):
    """One lesson of `exercises`, with a quiz store the routes really write to."""
    table = FakeTable()
    table.seed_active_account("student-1")
    table.seed_active_account("student-2")
    by_id = {item["challenge_id"]: item for item in exercises}
    writes: list[tuple[str, str]] = []

    monkeypatch.setattr(practice.practice_repo, "get_table", lambda: table)
    monkeypatch.setattr(practice.practice_repo, "get_lesson", lambda _lesson_id: dict(LESSON))
    monkeypatch.setattr(practice.practice_repo, "get_challenges", lambda _lesson_id: list(exercises))
    monkeypatch.setattr(practice.practice_repo, "get_challenge", lambda item_id: by_id.get(item_id))
    monkeypatch.setattr(
        practice.practice_repo,
        "challenges_answered_right",
        lambda _student_id, _lesson_id: set(answered_right),
    )
    monkeypatch.setattr(
        practice.practice_repo,
        "mark_lesson_completed",
        lambda student_id, item: writes.append((student_id, item["lesson_id"])),
    )
    monkeypatch.setattr(practice.practice_repo, "get_lessons", lambda **_kwargs: [dict(LESSON)])
    monkeypatch.setattr(practice.practice_repo, "get_progress", lambda _student_id, *_args: [])
    monkeypatch.setattr(
        practice.curriculum_analytics_service, "record_lesson_completed", lambda **_kwargs: None
    )
    monkeypatch.setattr(practice, "_record_practice_usage", lambda **_kwargs: None)
    monkeypatch.setattr(
        practice.curriculum_service,
        "get_prerequisites",
        lambda _subject_id: {"unit-1": ["unit-0"]},
    )
    monkeypatch.setattr(
        knowledge_mastery_service,
        "unit_states",
        lambda _student_id, **_kwargs: {
            "unit-1": _judged(
                knowledge_mastery_service.LearningState.LOCKED
                if locked
                else knowledge_mastery_service.LearningState.READY
            )
        },
    )
    return table, writes


def _take_quiz(client, exercises, *, kind="skip", wrong_first=0):
    """Answer a whole quiz, getting `wrong_first` of the answers wrong on purpose."""
    answers = {item["challenge_id"]: item["correct_answer"] for item in exercises}
    started = client.post("/practice/lessons/lesson-1/quiz", json={"kind": kind})
    assert started.status_code == 200, started.text
    body = started.json()
    quiz_id = body["quizId"]
    asked = body["exercise"]
    seen = []
    while asked is not None:
        challenge_id = asked["challengeId"]
        seen.append(challenge_id)
        answer = "nonsense" if len(seen) <= wrong_first else answers[challenge_id]
        reply = client.post(
            f"/practice/lessons/lesson-1/quiz/{quiz_id}/answer", json={"answer": answer}
        )
        assert reply.status_code == 200, reply.text
        body = reply.json()
        asked = body["exercise"]
    return quiz_id, body, seen


# ── Drawing the quiz ────────────────────────────────────────────────────────

def test_a_skip_quiz_asks_every_exercise_that_is_still_unanswered():
    drawn = lesson_quiz_service.compose_skip_quiz(
        ["c-1", "c-2", "c-3", "c-4"], ["c-5", "c-6", "c-7"], random.Random(1)
    )

    assert {"c-1", "c-2", "c-3", "c-4"} <= set(drawn)


def test_a_skip_quiz_adds_two_review_exercises_when_several_are_still_skipped():
    drawn = lesson_quiz_service.compose_skip_quiz(
        ["c-1", "c-2", "c-3", "c-4"], ["c-5", "c-6", "c-7"], random.Random(1)
    )

    assert len(drawn) == 6


def test_a_skip_quiz_tops_up_past_two_reviews_to_reach_the_minimum_size():
    # One exercise left to answer is not a quiz: QUIZ_MIN_SIZE - 1 review
    # exercises join it, which is more than QUIZ_REVIEW_EXTRA would add.
    drawn = lesson_quiz_service.compose_skip_quiz(
        ["c-1"], ["c-2", "c-3", "c-4", "c-5"], random.Random(1)
    )

    assert len(drawn) == 3
    assert "c-1" in drawn


def test_a_skip_quiz_cannot_ask_more_review_exercises_than_the_lesson_has():
    drawn = lesson_quiz_service.compose_skip_quiz(["c-1"], ["c-2"], random.Random(1))

    assert sorted(drawn) == ["c-1", "c-2"]


def test_a_test_out_quiz_draws_five_exercises_at_most():
    drawn = lesson_quiz_service.compose_test_out_quiz(
        [f"c-{index}" for index in range(9)], random.Random(1)
    )

    assert len(drawn) == 5
    assert len(set(drawn)) == 5


# ── A locked lesson ─────────────────────────────────────────────────────────

def test_a_unit_with_no_stated_prerequisite_is_never_locked(monkeypatch):
    _, writes = _world(monkeypatch, exercises=[_exercise(0)], answered_right={"c-0"}, locked=True)
    monkeypatch.setattr(practice.curriculum_service, "get_prerequisites", lambda _subject: {})

    response = _client().post("/practice/lessons/lesson-1/complete")

    assert response.status_code == 200
    assert writes == [("student-1", "lesson-1")]


def test_a_locked_lesson_cannot_be_completed(monkeypatch):
    _, writes = _world(
        monkeypatch,
        exercises=[_exercise(0)],
        answered_right={"c-0"},
        locked=True,
    )

    response = _client().post("/practice/lessons/lesson-1/complete")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "lesson_locked"
    assert writes == []


def test_a_locked_lesson_has_no_quiz_to_start(monkeypatch):
    _world(monkeypatch, exercises=[_exercise(0), _exercise(1)], locked=True)

    response = _client().post("/practice/lessons/lesson-1/quiz", json={"kind": "testOut"})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "lesson_locked"


def test_an_open_lesson_with_every_exercise_right_is_still_completed(monkeypatch):
    _, writes = _world(monkeypatch, exercises=[_exercise(0)], answered_right={"c-0"})

    response = _client().post("/practice/lessons/lesson-1/complete")

    assert response.status_code == 200
    assert writes == [("student-1", "lesson-1")]


def test_completing_without_a_credential_still_needs_every_exercise_right(monkeypatch):
    _, writes = _world(
        monkeypatch, exercises=[_exercise(0), _exercise(1)], answered_right={"c-0"}
    )

    response = _client().post("/practice/lessons/lesson-1/complete")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "lesson_exercises_unanswered"
    assert writes == []


# ── Taking the quiz ─────────────────────────────────────────────────────────

# What the client may be shown of an exercise. Anything the paper is marked
# against must not be in it, and a response is checked against the whole set
# of answers rather than one of them: the paper is shuffled, so naming a
# single answer makes the assertion a coin toss that passes two times in
# three (found by the independent audit of #92).
QUIZ_EXERCISE_KEYS = {
    "challengeId",
    "hintAvailable",
    "lessonId",
    "options",
    "prompt",
    "subjectId",
    "topicId",
    "type",
    "unitId",
}


def test_a_quiz_never_hands_the_client_the_answer(monkeypatch):
    exercises = [_exercise(index) for index in range(3)]
    _world(monkeypatch, exercises=exercises)

    started = _client().post("/practice/lessons/lesson-1/quiz", json={"kind": "skip"})

    assert started.status_code == 200
    body = started.json()
    assert body["remaining"] == 3
    assert body["heartsLeft"] == lesson_quiz_service.QUIZ_HEARTS
    # Not "the first one's answer is absent": every answer, whichever was
    # shuffled to the front.
    for exercise in exercises:
        assert exercise["correct_answer"] not in started.text
    # And nothing beyond the agreed fields, so a new one cannot arrive
    # carrying something the paper is marked against. A subset, because a
    # text answer has no options to offer.
    assert set(body["exercise"]) <= QUIZ_EXERCISE_KEYS
    assert body["exercise"]["hintAvailable"] is False


def test_marking_an_answer_never_hands_back_the_one_it_marked_against(monkeypatch):
    exercises = [_exercise(index) for index in range(3)]
    _world(monkeypatch, exercises=exercises)
    client = _client()
    started = client.post("/practice/lessons/lesson-1/quiz", json={"kind": "skip"})
    quiz_id = started.json()["quizId"]

    marked = client.post(
        f"/practice/lessons/lesson-1/quiz/{quiz_id}/answer",
        json={"answer": "not the answer"},
    )

    assert marked.status_code == 200
    assert marked.json()["correct"] is False
    for exercise in exercises:
        assert exercise["correct_answer"] not in marked.text
    if marked.json().get("exercise"):
        assert set(marked.json()["exercise"]) <= QUIZ_EXERCISE_KEYS


def test_a_quiz_forgives_one_wrong_answer_and_is_lost_on_the_second(monkeypatch):
    exercises = [_exercise(index) for index in range(3)]
    _world(monkeypatch, exercises=exercises)
    client = _client()
    started = client.post("/practice/lessons/lesson-1/quiz", json={"kind": "skip"}).json()
    quiz_id = started["quizId"]

    first = client.post(
        f"/practice/lessons/lesson-1/quiz/{quiz_id}/answer", json={"answer": "nonsense"}
    ).json()
    second = client.post(
        f"/practice/lessons/lesson-1/quiz/{quiz_id}/answer", json={"answer": "nonsense"}
    ).json()

    assert first["correct"] is False
    assert first["status"] == "inProgress"
    assert first["heartsLeft"] == 1
    assert second["status"] == "failed"
    assert second["credential"] is None


def test_a_wrong_answer_sends_its_exercise_to_the_back_of_the_quiz(monkeypatch):
    exercises = [_exercise(index) for index in range(3)]
    _world(monkeypatch, exercises=exercises)
    client = _client()
    started = client.post("/practice/lessons/lesson-1/quiz", json={"kind": "skip"}).json()
    quiz_id = started["quizId"]
    first_asked = started["exercise"]["challengeId"]

    after = client.post(
        f"/practice/lessons/lesson-1/quiz/{quiz_id}/answer", json={"answer": "nonsense"}
    ).json()

    assert after["remaining"] == 3
    assert after["exercise"]["challengeId"] != first_asked


def test_a_lost_quiz_issues_no_credential_and_completes_nothing(monkeypatch):
    exercises = [_exercise(index) for index in range(3)]
    table, writes = _world(monkeypatch, exercises=exercises)
    _, body, _ = _take_quiz(_client(), exercises, wrong_first=2)

    assert body["status"] == "failed"
    assert body["credential"] is None
    credentials = [key for key in table.rows if key[1].startswith("CREDENTIAL#")]
    assert credentials == []
    assert writes == []


def test_another_students_quiz_cannot_be_answered(monkeypatch):
    exercises = [_exercise(index) for index in range(3)]
    _world(monkeypatch, exercises=exercises)
    started = _client().post("/practice/lessons/lesson-1/quiz", json={"kind": "skip"}).json()

    response = _client(_actor("student-2")).post(
        f"/practice/lessons/lesson-1/quiz/{started['quizId']}/answer",
        json={"answer": "answer-0"},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "lesson_quiz_not_found"


def test_an_expired_quiz_cannot_be_answered(monkeypatch):
    exercises = [_exercise(index) for index in range(3)]
    _world(monkeypatch, exercises=exercises)
    monkeypatch.setattr(lesson_quiz_service, "QUIZ_SESSION_TTL_SECONDS", -60)
    client = _client()
    started = client.post("/practice/lessons/lesson-1/quiz", json={"kind": "skip"}).json()

    response = client.post(
        f"/practice/lessons/lesson-1/quiz/{started['quizId']}/answer",
        json={"answer": "answer-0"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "lesson_quiz_expired"


# ── The credential ──────────────────────────────────────────────────────────

def test_a_passed_quiz_issues_a_credential_that_completes_the_lesson(monkeypatch):
    exercises = [_exercise(index) for index in range(3)]
    _, writes = _world(monkeypatch, exercises=exercises)
    client = _client()
    _, body, _ = _take_quiz(client, exercises)

    assert body["status"] == "passed"
    response = client.post(
        "/practice/lessons/lesson-1/complete", json={"quizCredential": body["credential"]}
    )

    assert response.status_code == 200
    assert writes == [("student-1", "lesson-1")]


def test_a_quiz_credential_is_refused_the_second_time(monkeypatch):
    exercises = [_exercise(index) for index in range(3)]
    _, writes = _world(monkeypatch, exercises=exercises)
    client = _client()
    _, body, _ = _take_quiz(client, exercises)
    credential = body["credential"]
    assert (
        client.post(
            "/practice/lessons/lesson-1/complete", json={"quizCredential": credential}
        ).status_code
        == 200
    )

    again = client.post(
        "/practice/lessons/lesson-1/complete", json={"quizCredential": credential}
    )

    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "lesson_quiz_credential_invalid"
    assert writes == [("student-1", "lesson-1")]


def test_an_expired_quiz_credential_is_refused(monkeypatch):
    exercises = [_exercise(index) for index in range(3)]
    _, writes = _world(monkeypatch, exercises=exercises)
    monkeypatch.setattr(lesson_quiz_service, "QUIZ_CREDENTIAL_TTL_SECONDS", -60)
    client = _client()
    _, body, _ = _take_quiz(client, exercises)

    response = client.post(
        "/practice/lessons/lesson-1/complete", json={"quizCredential": body["credential"]}
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "lesson_quiz_credential_expired"
    assert writes == []


def test_another_students_quiz_credential_completes_nothing(monkeypatch):
    exercises = [_exercise(index) for index in range(3)]
    table, writes = _world(monkeypatch, exercises=exercises)
    _, body, _ = _take_quiz(_client(), exercises)
    credential = body["credential"]

    stolen = _client(_actor("student-2")).post(
        "/practice/lessons/lesson-1/complete", json={"quizCredential": credential}
    )

    assert stolen.status_code == 409
    assert stolen.json()["detail"]["code"] == "lesson_quiz_credential_invalid"
    assert writes == []
    # The theft did not spend it either: its owner can still use it.
    assert ("QUIZ#student-1", f"CREDENTIAL#{credential}") in table.rows
    assert (
        _client().post(
            "/practice/lessons/lesson-1/complete", json={"quizCredential": credential}
        ).status_code
        == 200
    )


def test_a_quiz_credential_does_not_complete_a_different_lesson(monkeypatch):
    exercises = [_exercise(index) for index in range(3)]
    _, writes = _world(monkeypatch, exercises=exercises)
    client = _client()
    _, body, _ = _take_quiz(client, exercises)
    monkeypatch.setattr(
        practice.practice_repo,
        "get_lesson",
        lambda _lesson_id: {**LESSON, "lesson_id": "lesson-2"},
    )

    response = client.post(
        "/practice/lessons/lesson-2/complete", json={"quizCredential": body["credential"]}
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "lesson_quiz_credential_invalid"
    assert writes == []


def test_an_unknown_quiz_credential_is_refused_even_with_every_exercise_right(monkeypatch):
    # Presenting a credential is a claim about how this lesson was finished;
    # a forged one is not quietly excused by the other road being open.
    _, writes = _world(monkeypatch, exercises=[_exercise(0)], answered_right={"c-0"})

    response = _client().post(
        "/practice/lessons/lesson-1/complete", json={"quizCredential": "not-a-credential"}
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "lesson_quiz_credential_invalid"
    assert writes == []


def test_a_quiz_credential_is_bound_to_the_student_in_the_row_it_is_stored_as(monkeypatch):
    exercises = [_exercise(index) for index in range(3)]
    table, _ = _world(monkeypatch, exercises=exercises)
    _, body, _ = _take_quiz(_client(), exercises)

    row = table.rows[("QUIZ#student-1", f"CREDENTIAL#{body['credential']}")]

    assert row["student_id"] == "student-1"
    assert row["lesson_id"] == "lesson-1"
    assert int(row["expires_at"]) > 0


# ── what the independent audit found (#92) ─────────────────────────────────


def test_an_exercise_the_catalog_cannot_resolve_is_dropped_rather_than_asked(monkeypatch):
    """A paper used to stop dead on one unresolvable exercise.

    The queue was left untouched, so the retry, and every new paper, asked the
    same unanswerable question — and `complete` was shut for the same reason.
    Both ways out were closed at once.
    """
    exercises = [_exercise(index) for index in range(3)]
    _world(monkeypatch, exercises=exercises)
    # The catalog lists all three; the first one does not resolve. The paper is
    # shuffled, so the order is fixed here rather than hoped for — the same
    # trap the audit found in the answer-leak test.
    monkeypatch.setattr(
        practice.lesson_quiz_service, "compose_quiz", lambda *_a, **_k: ["c-0", "c-1", "c-2"]
    )
    resolvable = {item["challenge_id"]: item for item in exercises[1:]}
    monkeypatch.setattr(practice.practice_repo, "get_challenge", lambda item_id: resolvable.get(item_id))
    client = _client()
    quiz_id = client.post("/practice/lessons/lesson-1/quiz", json={"kind": "skip"}).json()["quizId"]

    answered = client.post(
        f"/practice/lessons/lesson-1/quiz/{quiz_id}/answer", json={"answer": "answer-1"}
    )

    # c-0 is gone from the paper and c-1 was asked and answered right.
    assert answered.status_code == 200, answered.text
    assert answered.json()["correct"] is True
    assert answered.json()["status"] == lesson_quiz_service.IN_PROGRESS


def test_a_paper_of_nothing_but_unresolvable_exercises_ends_instead_of_hanging(monkeypatch):
    exercises = [_exercise(index) for index in range(3)]
    _world(monkeypatch, exercises=exercises)
    monkeypatch.setattr(practice.practice_repo, "get_challenge", lambda _item_id: None)
    client = _client()
    quiz_id = client.post("/practice/lessons/lesson-1/quiz", json={"kind": "skip"}).json()["quizId"]

    first = client.post(f"/practice/lessons/lesson-1/quiz/{quiz_id}/answer", json={"answer": "a"})
    again = client.post(f"/practice/lessons/lesson-1/quiz/{quiz_id}/answer", json={"answer": "a"})

    assert first.status_code == 409
    assert first.json()["detail"]["code"] == "lesson_quiz_unavailable"
    # Over, rather than open for ever on a question nobody can answer.
    assert again.json()["detail"]["code"] == "lesson_quiz_finished"


def test_a_credential_that_names_no_quiz_completes_nothing(monkeypatch):
    """`quiz_id` was written and never read, which made it decoration.

    A credential is earned by one paper; one that cannot say which paper is
    not a credential, it is a bearer token for a lesson.
    """
    exercises = [_exercise(0)]
    _world(monkeypatch, exercises=exercises)
    client = _client()
    quiz_id = client.post("/practice/lessons/lesson-1/quiz", json={"kind": "skip"}).json()["quizId"]
    passed = client.post(
        f"/practice/lessons/lesson-1/quiz/{quiz_id}/answer", json={"answer": "answer-0"}
    ).json()
    stored = practice.practice_repo.get_quiz_credential("student-1", passed["credential"])
    assert stored
    nameless = "credential-with-no-quiz"
    practice.practice_repo.put_quiz_credential(
        "student-1",
        credential_id=nameless,
        lesson_id="lesson-1",
        quiz_id="",
        expires_at=int(stored["expires_at"]),
        expires_at_iso=str(stored["expires_at_iso"]),
    )

    done = client.post("/practice/lessons/lesson-1/complete", json={"quizCredential": nameless})

    assert done.status_code == 409
    assert done.json()["detail"]["code"] == "lesson_quiz_credential_invalid"


def test_answering_in_a_quiz_leaves_a_trace_in_the_ledger(monkeypatch):
    """It was the one answering route that recorded nothing.

    A reader's quizzes were invisible to the ledger the parent's and the
    teacher's reports are built from.
    """
    recorded: list[str] = []
    _world(monkeypatch, exercises=[_exercise(0)])
    # After `_world`, which silences the ledger for every other test here.
    monkeypatch.setattr(
        practice, "_record_practice_usage", lambda **kwargs: recorded.append(str(kwargs["action"]))
    )
    client = _client()
    quiz_id = client.post("/practice/lessons/lesson-1/quiz", json={"kind": "skip"}).json()["quizId"]

    answered = client.post(
        f"/practice/lessons/lesson-1/quiz/{quiz_id}/answer", json={"answer": "answer-0"}
    )

    assert answered.status_code == 200, answered.text
    assert usage_ledger_service.PRACTICE_QUIZ_ANSWER_ACTION in recorded
