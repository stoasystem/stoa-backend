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
    challenge = {
        "challenge_id": "challenge-1",
        "prompt": "Solve",
        "hint": "Try again",
    }
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
        json={"challengeId": "challenge-1", "studentId": "student-other"},
    )

    assert response.status_code == 200
