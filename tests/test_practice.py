import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.deps import get_actor
from stoa.routers import practice
from stoa.security.authorization import AuthorizationFacts
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.security.route_authorization import get_authorization_fact_repository


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


def _client(actor: Actor | None = None, facts=None) -> TestClient:
    app = FastAPI()
    app.include_router(practice.router, prefix="/practice")
    app.dependency_overrides[get_actor] = lambda: actor or _actor()
    app.dependency_overrides[get_authorization_fact_repository] = lambda: facts or _Facts()
    return TestClient(app)


def test_practice_catalog_is_explicitly_safe_public(monkeypatch):
    monkeypatch.setattr(
        practice.practice_repo,
        "get_subjects",
        lambda: [{"subject_id": "math", "name": "Math", "order": 1}],
    )

    response = _client().get("/practice/subjects")

    assert response.status_code == 200
    route = next(
        route for route in practice.router.routes if getattr(route, "path", "") == "/subjects"
    )
    dependency = route.dependant.dependencies[0].call
    assert dependency.safe_public is True
    assert dependency.authorization_specs


def test_practice_completion_uses_actor_and_authorized_lesson_once(monkeypatch):
    lesson = {
        "lesson_id": "lesson-1",
        "subject_id": "math",
        "topic_id": "algebra",
    }
    calls = {"load": 0, "write": []}

    def get_lesson(_lesson_id):
        calls["load"] += 1
        return lesson

    monkeypatch.setattr(practice.practice_repo, "get_lesson", get_lesson)
    monkeypatch.setattr(
        practice.practice_repo,
        "mark_lesson_completed",
        lambda student_id, item: calls["write"].append((student_id, item)),
    )
    monkeypatch.setattr(practice.practice_repo, "get_lessons", lambda **_kwargs: [lesson])
    monkeypatch.setattr(
        practice.practice_repo,
        "get_progress",
        lambda student_id, *_args: [{"lesson_id": "lesson-1", "status": "completed"}],
    )
    monkeypatch.setattr(
        practice.curriculum_analytics_service,
        "record_lesson_completed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(practice, "_record_practice_usage", lambda **_kwargs: None)

    response = _client(_actor("student-canonical")).post(
        "/practice/lessons/lesson-1/complete"
    )

    assert response.status_code == 200
    assert calls == {
        "load": 1,
        "write": [("student-canonical", lesson)],
    }


def test_practice_authorization_outage_prevents_completion_write(monkeypatch):
    writes = []
    monkeypatch.setattr(
        practice.practice_repo,
        "get_lesson",
        lambda _lesson_id: {"lesson_id": "lesson-1", "student_id": "student-1"},
    )
    monkeypatch.setattr(
        practice.practice_repo,
        "mark_lesson_completed",
        lambda *_args: writes.append("write"),
    )

    class _Outage:
        async def facts_for(self, *_args):
            raise TimeoutError("authorization canary")

    response = _client(facts=_Outage()).post("/practice/lessons/lesson-1/complete")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "authorization_temporarily_unavailable"
    assert writes == []


def test_practice_hint_body_cannot_select_another_student(monkeypatch):
    challenge = _approved_hint_challenge({
        "challenge_id": "challenge-1",
        "prompt": "Solve",
        "correct_answer": "x = 5",
        "explanation": "Subtract four from both sides.",
    })
    monkeypatch.setattr(practice.practice_repo, "get_challenge", lambda _id: challenge)
    monkeypatch.setattr(
        practice,
        "_hint_limit_for_student",
        lambda student_id: 5 if student_id == "student-canonical" else 0,
    )
    monkeypatch.setattr(practice, "_record_practice_usage", lambda **_kwargs: None)
    from stoa.services import rate_limit

    monkeypatch.setattr(
        rate_limit,
        "check_and_record_hint",
        lambda student_id, *_args, **_kwargs: {"studentId": student_id},
    )

    response = _client(_actor("student-canonical")).post(
        "/practice/hints",
        json={
            "challengeId": "challenge-1",
            "idempotencyKey": "hint-owner-1",
            "studentId": "student-other",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "challengeId": "challenge-1",
        "hintAvailable": True,
        "hint": practice.practice_projection_service.DIRECTIONAL_HINT_TEMPLATES[
            "review_problem_structure"
        ],
    }


def _challenge() -> dict:
    return {
        "challenge_id": "challenge-1",
        "lesson_id": "lesson-1",
        "subject_id": "math",
        "topic_id": "algebra",
        "prompt": "Solve x + 4 = 9",
        "correct_answer": "x = 5",
        "explanation": "Subtract four from both sides.",
        "correct_feedback": "Correct.",
        "incorrect_feedback": "Review inverse operations.",
    }


def _approved_hint_challenge(challenge: dict | None = None) -> dict:
    item = dict(challenge or _challenge())
    item["directional_hint_template_id"] = "review_problem_structure"
    item.update(practice.practice_repo.version_challenge(item))
    item["hint_non_derivability_decision"] = {
        "template_id": "review_problem_structure",
        "challenge_version": item["challenge_version"],
        "content_hash": item["challenge_content_hash"],
        "reviewer_id": "teacher-reviewer-1",
        "reviewer_role": "teacher",
        "policy_version": "practice-directional-hints-v1",
        "decision": "non_derivable",
        "approved_at": "2026-07-17T00:00:00+00:00",
    }
    return item


def _install_answer_dependencies(monkeypatch, challenge: dict | None = None) -> dict:
    item = challenge or _challenge()
    monkeypatch.setattr(practice.practice_repo, "get_challenge", lambda _id: item)
    monkeypatch.setattr(practice.practice_repo, "get_challenges", lambda _id: [item])
    monkeypatch.setattr(
        practice.curriculum_analytics_service,
        "record_practice_attempt",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(practice, "_record_practice_usage", lambda **_kwargs: None)
    return item


def test_answer_is_revealed_only_after_every_attempt_is_persisted(monkeypatch):
    _install_answer_dependencies(monkeypatch)
    writes = []

    def put_attempt(student_id, challenge_id, submitted_answer, correct, **metadata):
        writes.append((student_id, challenge_id, submitted_answer, correct, metadata))
        return {
            "attempt_id": "attempt-1",
            "student_id": student_id,
            "challenge_id": challenge_id,
            "student_answer": submitted_answer,
            "correct": correct,
            **metadata,
        }

    monkeypatch.setattr(practice.practice_repo, "put_attempt", put_attempt)

    incorrect = _client().post(
        "/practice/challenges/challenge-1/answer", json={"answer": "x = 4"}
    )
    correct = _client().post(
        "/practice/challenges/challenge-1/answer", json={"answer": "x = 5"}
    )

    assert incorrect.status_code == 200
    assert incorrect.json()["standardAnswer"] == "x = 5"
    assert incorrect.json()["explanation"] == "Subtract four from both sides."
    assert correct.status_code == 200
    assert correct.json()["standardAnswer"] == "x = 5"
    assert [write[3] for write in writes] == [False, True]
    assert [write[2] for write in writes] == ["x = 4", "x = 5"]


def test_attempt_write_failure_returns_no_answer_or_provider_detail(monkeypatch, caplog):
    _install_answer_dependencies(monkeypatch)

    def fail_write(*_args, **_kwargs):
        raise RuntimeError("STANDARD-ANSWER-CANARY EXPLANATION-CANARY provider-detail")

    monkeypatch.setattr(practice.practice_repo, "put_attempt", fail_write)

    with caplog.at_level(logging.WARNING):
        response = _client().post(
            "/practice/challenges/challenge-1/answer", json={"answer": "x = 4"}
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "practice_attempt_unavailable"
    assert "x = 5" not in response.text
    assert "CANARY" not in response.text
    assert "CANARY" not in caplog.text
    assert "provider-detail" not in caplog.text


def test_attempt_result_is_owner_scoped_and_unknown_matches_foreign(monkeypatch):
    challenge = _install_answer_dependencies(monkeypatch)
    versioned = practice.practice_repo.version_challenge(challenge)
    attempt = {
        "attempt_id": "attempt-1",
        "student_id": "student-1",
        "challenge_id": challenge["challenge_id"],
        "challenge_version": versioned["challenge_version"],
        "challenge_content_hash": versioned["challenge_content_hash"],
        "subject_id": challenge["subject_id"],
        "topic_id": challenge["topic_id"],
        "lesson_id": challenge["lesson_id"],
        "student_answer": "x = 4",
        "correct": False,
        "standard_answer": challenge["correct_answer"],
        "explanation": challenge["explanation"],
        "correct_feedback": challenge["correct_feedback"],
        "incorrect_feedback": challenge["incorrect_feedback"],
        "feedback": challenge["incorrect_feedback"],
        "next_challenge_id": None,
        "created_at": "2026-07-17T00:00:00+00:00",
    }
    monkeypatch.setattr(
        practice.practice_repo,
        "get_attempt",
        lambda student_id, attempt_id: (
            attempt if student_id == "student-1" and attempt_id == "attempt-1" else None
        ),
    )

    owner = _client(_actor("student-1")).get(
        "/practice/attempts/attempt-1/result"
    )
    foreign = _client(_actor("student-2")).get(
        "/practice/attempts/attempt-1/result"
    )
    random = _client(_actor("student-2")).get(
        "/practice/attempts/random/result"
    )

    assert owner.status_code == 200
    assert owner.json()["attemptId"] == "attempt-1"
    assert foreign.status_code == random.status_code == 404
    assert foreign.json()["detail"]["code"] == random.json()["detail"]["code"]
    assert foreign.json()["detail"]["message"] == random.json()["detail"]["message"]


def test_hint_requires_approval_and_rejects_answer_or_explanation_canaries(monkeypatch):
    from stoa.services import rate_limit

    monkeypatch.setattr(
        rate_limit,
        "check_and_record_hint",
        lambda *_args, **_kwargs: {"counterValue": 1},
    )
    monkeypatch.setattr(practice, "_record_practice_usage", lambda **_kwargs: None)
    monkeypatch.setattr(practice, "_hint_limit_for_student", lambda _id: 5)

    cases = [
        {**_challenge(), "directional_hint_template_id": "review_problem_structure"},
        _approved_hint_challenge({**_challenge(), "hint": "The answer is x = 5."}),
        _approved_hint_challenge(
            {**_challenge(), "hint": "Subtract four from both sides."}
        ),
    ]
    for challenge in cases:
        monkeypatch.setattr(practice.practice_repo, "get_challenge", lambda _id, item=challenge: item)
        response = _client().post(
            "/practice/hints",
            json={"challengeId": "challenge-1", "idempotencyKey": "hint-approved-1"},
        )
        assert response.status_code == 200
        assert response.json() == {
            "challengeId": "challenge-1",
            "hintAvailable": False,
            "hint": None,
        }


def test_hint_requires_explicit_idempotency_key_before_rate_admission(monkeypatch):
    calls = []
    monkeypatch.setattr(
        practice.practice_repo,
        "get_challenge",
        lambda _id: _approved_hint_challenge(),
    )
    from stoa.services import rate_limit

    monkeypatch.setattr(
        rate_limit,
        "check_and_record_hint",
        lambda *_args, **_kwargs: calls.append("admit"),
    )

    response = _client().post(
        "/practice/hints", json={"challengeId": "challenge-1"}
    )

    assert response.status_code == 422
    assert calls == []
