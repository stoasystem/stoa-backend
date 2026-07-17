from collections.abc import Mapping, Sequence

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from stoa.models.practice import (
    PracticeAttemptResult,
    PracticeChallengePreview,
    PracticeHintResponse,
    PrivilegedPracticeAnswer,
)
from stoa.routers import practice
from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationFacts,
    AuthorizationPurpose,
    CurriculumAnswerAuthorizationFacts,
    ResourceRef,
    ResourceType,
    operator_capability_decision,
)
from stoa.security.route_authorization import get_authorization_fact_repository
from actor_helpers import install_actor_overrides


FORBIDDEN_PREVIEW_KEYS = {
    "correctAnswer",
    "answerKey",
    "standardAnswer",
    "explanation",
    "feedback",
    "correctFeedback",
    "incorrectFeedback",
    "hint",
}


def assert_recursive_preview_is_answer_free(value: object, path: str = "root") -> None:
    if isinstance(value, Mapping):
        leaked = FORBIDDEN_PREVIEW_KEYS.intersection(value)
        assert not leaked, f"answer-derived keys {sorted(leaked)} leaked at {path}"
        for key, child in value.items():
            assert_recursive_preview_is_answer_free(child, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            assert_recursive_preview_is_answer_free(child, f"{path}[{index}]")


def _preview(**overrides) -> PracticeChallengePreview:
    payload = {
        "challengeId": "challenge-1",
        "lessonId": "lesson-1",
        "prompt": "Solve x + 4 = 9.",
        "type": "text_input",
        "options": None,
        "hintAvailable": True,
    }
    payload.update(overrides)
    return PracticeChallengePreview.model_validate(payload)


def _recorded_result(**overrides) -> PracticeAttemptResult:
    payload = {
        "challengeId": "challenge-1",
        "correct": False,
        "standardAnswer": "x = 5",
        "explanation": "Subtract four from both sides.",
        "feedback": "Review inverse operations and try again.",
        "nextChallengeId": "challenge-2",
        "retryAllowed": True,
        "attemptsRemaining": 2,
    }
    payload.update(overrides)
    return PracticeAttemptResult.from_recorded_attempt(
        {"attempt_id": "attempt-1"}, **payload
    )


def test_preview_schema_and_openapi_properties_are_answer_free() -> None:
    schema = PracticeChallengePreview.model_json_schema(by_alias=True)
    assert not FORBIDDEN_PREVIEW_KEYS.intersection(schema["properties"])

    app = FastAPI()

    @app.get("/preview", response_model=PracticeChallengePreview)
    def preview() -> PracticeChallengePreview:
        return _preview()

    openapi_properties = app.openapi()["components"]["schemas"]["PracticeChallengePreview"]["properties"]
    assert not FORBIDDEN_PREVIEW_KEYS.intersection(openapi_properties)


@pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_PREVIEW_KEYS))
def test_preview_schema_rejects_answer_derived_fields(forbidden: str) -> None:
    with pytest.raises(ValidationError):
        _preview(**{forbidden: "answer-canary"})


def test_preview_serialization_is_structurally_answer_free() -> None:
    preview = _preview()
    payload = preview.model_dump(by_alias=True, exclude_none=True)
    assert set(payload) == {
        "challengeId", "lessonId", "prompt", "type", "hintAvailable"
    }
    assert_recursive_preview_is_answer_free(payload)


def test_hint_schema_carries_only_approved_directional_hint() -> None:
    hint = PracticeHintResponse(
        challengeId="challenge-1",
        hintAvailable=True,
        hint="Use the inverse operation on both sides.",
    )
    assert hint.model_dump(by_alias=True) == {
        "challengeId": "challenge-1",
        "hintAvailable": True,
        "hint": "Use the inverse operation on both sides.",
    }
    with pytest.raises(ValidationError):
        PracticeHintResponse(
            challengeId="challenge-1",
            hintAvailable=True,
            hint="Try an inverse operation.",
            standardAnswer="x = 5",
        )


def test_unavailable_hint_contains_no_answer_bearing_fallback() -> None:
    unavailable = PracticeHintResponse(
        challengeId="challenge-1",
        hintAvailable=False,
        hint=None,
    )
    assert unavailable.model_dump(by_alias=True) == {
        "challengeId": "challenge-1",
        "hintAvailable": False,
        "hint": None,
    }


def test_attempt_repository_records_correct_and_incorrect_answers_immutably(monkeypatch) -> None:
    from stoa.db.repositories import practice_repo

    class Table:
        def __init__(self):
            self.puts = []

        def put_item(self, **kwargs):
            self.puts.append(kwargs)

    table = Table()
    monkeypatch.setattr(practice_repo, "get_table", lambda: table)

    correct = practice_repo.put_attempt(
        "student-1",
        "challenge-1",
        "x = 5",
        True,
        attempt_id="attempt-correct",
        created_at="2026-07-16T00:00:00+00:00",
    )
    incorrect = practice_repo.put_attempt(
        "student-1",
        "challenge-1",
        "x = 4",
        False,
        attempt_id="attempt-incorrect",
        created_at="2026-07-16T00:01:00+00:00",
    )

    assert correct["student_answer"] == "x = 5"
    assert correct["correct"] is True
    assert incorrect["student_answer"] == "x = 4"
    assert incorrect["correct"] is False
    assert all(
        put["ConditionExpression"]
        == "attribute_not_exists(PK) AND attribute_not_exists(SK)"
        for put in table.puts
    )


@pytest.mark.parametrize("missing", ["attemptId", "standardAnswer", "explanation", "feedback"])
def test_attempt_result_schema_requires_recorded_answer_fields(missing: str) -> None:
    payload = _recorded_result().model_dump(by_alias=True)
    payload.pop(missing)
    with pytest.raises(ValidationError):
        PracticeAttemptResult.model_validate(payload)


@pytest.mark.parametrize("attempt_id", [None, "", "   "])
def test_result_factory_refuses_answer_reveal_when_attempt_persistence_fails(attempt_id) -> None:
    with pytest.raises(ValueError, match="recorded attempt receipt"):
        PracticeAttemptResult.from_recorded_attempt(
            None if attempt_id is None else {"attempt_id": attempt_id},
            challengeId="challenge-1",
            correct=True,
            standardAnswer="x = 5",
            explanation="Subtract four.",
            feedback="Correct.",
            nextChallengeId=None,
            retryAllowed=False,
            attemptsRemaining=0,
        )


def test_attempt_result_exposes_answers_only_after_recorded_receipt() -> None:
    payload = _recorded_result().model_dump(by_alias=True)
    assert payload["attemptId"] == "attempt-1"
    assert payload["standardAnswer"] == "x = 5"
    assert {"explanation", "feedback", "retryAllowed"} <= set(payload)


def test_privileged_answer_is_the_only_pre_attempt_answer_schema() -> None:
    privileged = PrivilegedPracticeAnswer(
        challengeId="challenge-1",
        standardAnswer="x = 5",
        explanation="Subtract four from both sides.",
        correctFeedback="Correct.",
        incorrectFeedback="Try the inverse operation.",
    )
    fields = set(privileged.model_dump(by_alias=True))
    assert {"standardAnswer", "explanation", "correctFeedback", "incorrectFeedback"} <= fields
    assert not FORBIDDEN_PREVIEW_KEYS.intersection(
        PracticeChallengePreview.model_json_schema(by_alias=True)["properties"]
    )


@pytest.mark.parametrize(
    "nested",
    [
        {"lessons": [{"challenges": [{"correctAnswer": "canary"}]}]},
        {"path": {"units": [{"lessons": [{"answerKey": "canary"}]}]}},
        {"catalog": [{"exercise": {"explanation": "canary"}}]},
    ],
)
def test_recursive_preview_canary_detects_nested_answer_leaks(nested: dict) -> None:
    with pytest.raises(AssertionError, match="leaked"):
        assert_recursive_preview_is_answer_free(nested)


def test_recursive_preview_fixture_accepts_nested_answer_free_content() -> None:
    assert_recursive_preview_is_answer_free(
        {"lessons": [{"challenges": [_preview().model_dump(by_alias=True)]}]}
    )


def test_every_practice_preview_route_recursively_omits_answer_canaries(monkeypatch) -> None:
    topic = {
        "topic_id": "topic-1",
        "subject_id": "math",
        "title": "Algebra",
        "order": 1,
    }
    unit = {
        "unit_id": "unit-1",
        "subject_id": "math",
        "topic_id": "topic-1",
        "title": "Equations",
        "order": 1,
    }
    lesson = {
        "lesson_id": "lesson-1",
        "unit_id": "unit-1",
        "subject_id": "math",
        "topic_id": "topic-1",
        "title": "Solve equations",
        "explanation": "LESSON-EXPLANATION-CANARY",
        "examples": [{"answerKey": "NESTED-ANSWER-CANARY"}],
        "order": 1,
    }
    challenge = {
        "challenge_id": "challenge-1",
        "lesson_id": "lesson-1",
        "unit_id": "unit-1",
        "subject_id": "math",
        "topic_id": "topic-1",
        "prompt": "Solve x + 4 = 9",
        "options": ["x = 4", "x = 5"],
        "correct_answer": "STANDARD-ANSWER-CANARY",
        "explanation": "EXPLANATION-CANARY",
        "correct_feedback": "CORRECT-FEEDBACK-CANARY",
        "incorrect_feedback": "INCORRECT-FEEDBACK-CANARY",
        "hint": "HINT-CANARY",
        "hint_approved": False,
    }
    subject = {"subject_id": "math", "name": "Math", "order": 1}
    monkeypatch.setattr(practice.practice_repo, "get_subjects", lambda: [subject])
    monkeypatch.setattr(practice.practice_repo, "get_topics", lambda *_args, **_kwargs: [topic])
    monkeypatch.setattr(practice.practice_repo, "get_topic", lambda _id: topic)
    monkeypatch.setattr(practice.practice_repo, "get_units", lambda _id: [unit])
    monkeypatch.setattr(practice.practice_repo, "get_lessons", lambda **_kwargs: [lesson])
    monkeypatch.setattr(practice.practice_repo, "get_lesson", lambda _id: lesson)
    monkeypatch.setattr(practice.practice_repo, "get_challenges", lambda _id: [challenge])
    monkeypatch.setattr(practice.practice_repo, "get_progress", lambda *_args: [])
    monkeypatch.setattr(practice.practice_repo, "get_mistakes", lambda _id: [])

    app = FastAPI()
    app.include_router(practice.router, prefix="/practice")
    install_actor_overrides(app, {"sub": "student-1", "role": "student"})
    client = TestClient(app)

    responses = [
        client.get("/practice/overview"),
        client.get("/practice/math/topic-1/roadmap"),
        client.get("/practice/math/topic-1/path"),
        client.get("/practice/lessons/lesson-1"),
    ]
    for response in responses:
        assert response.status_code == 200, response.text
        assert_recursive_preview_is_answer_free(response.json())
        serialized = response.text
        assert "STANDARD-ANSWER-CANARY" not in serialized
        assert "EXPLANATION-CANARY" not in serialized
        assert "FEEDBACK-CANARY" not in serialized

    lesson_body = responses[-1].json()
    assert lesson_body["challenges"][0]["options"] == ["x = 4", "x = 5"]
    assert lesson_body["challenges"][0]["hintAvailable"] is False


def test_student_preview_openapi_has_no_answer_toggle_or_result_fields() -> None:
    app = FastAPI()
    app.include_router(practice.router, prefix="/practice")
    schema = app.openapi()
    for path in (
        "/practice/curriculum/lessons/{lesson_id}",
        "/practice/curriculum/exercises",
    ):
        parameters = schema["paths"][path]["get"].get("parameters", [])
        assert "includeAnswers" not in {item["name"] for item in parameters}
    preview_properties = PracticeChallengePreview.model_json_schema(by_alias=True)["properties"]
    assert not FORBIDDEN_PREVIEW_KEYS.intersection(preview_properties)
    assert "attemptId" not in preview_properties


def test_attempt_result_identifier_has_executable_practice_authorization() -> None:
    from stoa.main import app
    from stoa.security.route_inventory import inventory_application

    item = next(
        item
        for item in inventory_application(app)
        if item.path == "/practice/attempts/{attempt_id}/result"
    )
    assert item.identifiers == ("attempt_id",)
    assert item.classification == "authorized"
    assert item.authorization_spec is not None
    assert item.authorization_spec.resource_type == "practice"


def _privileged_answer_client(
    monkeypatch,
    *,
    role: str,
    assignment: dict | None = None,
    account_status: str = "active",
    challenge: dict | None = None,
):
    challenge = challenge or {
        "challenge_id": "challenge-1",
        "challenge_version": "sha256:" + "a" * 64,
        "challenge_content_hash": "a" * 64,
        "course_id": "course-1",
        "class_id": "class-1",
        "lesson_id": "lesson-1",
        "subject_id": "math",
        "grade_level": "secondary",
        "prompt": "Solve x + 4 = 9.",
        "correct_answer": "x = 5",
        "explanation": "Subtract four from both sides.",
        "correct_feedback": "Correct.",
        "incorrect_feedback": "Use the inverse operation.",
    }
    monkeypatch.setattr(
        practice.practice_repo,
        "get_challenge",
        lambda challenge_id: dict(challenge)
        if challenge_id == challenge["challenge_id"]
        else None,
    )
    app = FastAPI()
    app.include_router(practice.router, prefix="/practice")
    actor = install_actor_overrides(
        app,
        {"sub": f"{role}-1", "role": role, "accountStatus": account_status},
    )

    class Facts:
        async def facts_for(self, *_args):
            if role != "teacher":
                return AuthorizationFacts()
            return AuthorizationFacts(
                curriculum_answer=CurriculumAnswerAuthorizationFacts(
                    assignment=assignment,
                    teacher_account={
                        "user_id": actor.user_id,
                        "role": "teacher",
                        "account_status": account_status,
                    },
                )
            )

    app.dependency_overrides[get_authorization_fact_repository] = Facts
    return TestClient(app), actor


def _answer_assignment(**overrides):
    assignment = {
        "PK": "TEACHER_ASSIGNMENT#teacher-1",
        "SK": "CURRICULUM#CURRENT",
        "entity_type": "teacher_curriculum_assignment",
        "version": 1,
        "teacher_id": "teacher-1",
        "status": "active",
        "curriculum_scope": {
            "course_id": "course-1",
            "class_id": "class-1",
            "subject_id": "math",
            "grade_level": "secondary",
        },
        "resource_types": ["curriculum_answer"],
        "actions": ["read"],
        "purposes": ["curriculum_answer_read"],
    }
    assignment.update(overrides)
    return assignment


def test_explicit_privileged_answer_route_allows_scoped_teacher_and_admin(monkeypatch):
    teacher, _ = _privileged_answer_client(
        monkeypatch, role="teacher", assignment=_answer_assignment()
    )
    admin, _ = _privileged_answer_client(monkeypatch, role="admin")

    expected = {
        "challengeId": "challenge-1",
        "standardAnswer": "x = 5",
        "explanation": "Subtract four from both sides.",
        "correctFeedback": "Correct.",
        "incorrectFeedback": "Use the inverse operation.",
    }
    assert teacher.get(
        "/practice/curriculum/challenges/challenge-1/answer"
    ).json() == expected
    assert admin.get(
        "/practice/curriculum/challenges/challenge-1/answer"
    ).json() == expected


def test_anonymous_actor_cannot_use_privileged_answer_route(monkeypatch):
    monkeypatch.setattr(
        practice.practice_repo,
        "get_challenge",
        lambda _challenge_id: {
            "challenge_id": "challenge-1",
            "challenge_version": "sha256:" + "a" * 64,
            "challenge_content_hash": "a" * 64,
            "course_id": "course-1",
            "class_id": "class-1",
            "lesson_id": "lesson-1",
            "subject_id": "math",
            "correct_answer": "answer-canary",
        },
    )
    app = FastAPI()
    app.include_router(practice.router, prefix="/practice")
    response = TestClient(app).get(
        "/practice/curriculum/challenges/challenge-1/answer"
    )
    assert response.status_code == 401
    assert "answer-canary" not in response.text


@pytest.mark.parametrize(
    "role,assignment,account_status",
    [
        ("teacher", None, "active"),
        ("teacher", _answer_assignment(status="revoked"), "active"),
        (
            "teacher",
            _answer_assignment(
                curriculum_scope={
                    "course_id": "course-1",
                    "class_id": "class-1",
                    "subject_id": "physics",
                }
            ),
            "active",
        ),
        ("teacher", _answer_assignment(), "disabled"),
        ("student", None, "active"),
        ("parent", None, "active"),
    ],
)
def test_privileged_answer_route_hides_unassigned_stale_wrong_scope_and_roles(
    monkeypatch, role, assignment, account_status
):
    client, _ = _privileged_answer_client(
        monkeypatch,
        role=role,
        assignment=assignment,
        account_status=account_status,
    )
    hidden = client.get(
        "/practice/curriculum/challenges/challenge-1/answer"
    )
    random = client.get(
        "/practice/curriculum/challenges/random-challenge/answer"
    )
    assert hidden.status_code == random.status_code == 404
    assert hidden.json()["detail"]["code"] == random.json()["detail"]["code"]
    assert hidden.json()["detail"]["message"] == random.json()["detail"]["message"]
    assert "x = 5" not in hidden.text
    assert "Subtract four" not in hidden.text


def test_answer_dependency_loads_challenge_once_and_never_grants_mutation(monkeypatch):
    challenge = {
        "challenge_id": "challenge-1",
        "challenge_version": "sha256:" + "a" * 64,
        "challenge_content_hash": "a" * 64,
        "course_id": "course-1",
        "class_id": "class-1",
        "lesson_id": "lesson-1",
        "subject_id": "math",
        "grade_level": "secondary",
        "correct_answer": "x = 5",
        "explanation": "Subtract four.",
    }
    loads = []

    def load(challenge_id):
        loads.append(challenge_id)
        return dict(challenge)

    monkeypatch.setattr(practice.practice_repo, "get_challenge", load)
    client, actor = _privileged_answer_client(
        monkeypatch,
        role="teacher",
        assignment=_answer_assignment(),
        challenge=challenge,
    )
    monkeypatch.setattr(practice.practice_repo, "get_challenge", load)
    response = client.get(
        "/practice/curriculum/challenges/challenge-1/answer"
    )
    assert response.status_code == 200
    assert loads == ["challenge-1"]

    mutation = operator_capability_decision(
        actor,
        capability="curriculum_editor",
        resource=ResourceRef(
            ResourceType.OPERATOR_RESOURCE,
            "lesson-1",
            "lesson-1",
            relationship_known=True,
        ),
        action=AuthorizationAction.CURRICULUM_MUTATION,
        purpose=AuthorizationPurpose.CURRICULUM_OPERATIONS,
    )
    assert not mutation.allowed


def test_privileged_answer_openapi_is_explicit_and_preview_has_no_toggle():
    app = FastAPI()
    app.include_router(practice.router, prefix="/practice")
    operation = app.openapi()["paths"][
        "/practice/curriculum/challenges/{challenge_id}/answer"
    ]["get"]
    schema_ref = operation["responses"]["200"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    assert schema_ref.endswith("/PrivilegedPracticeAnswer")
    for path in (
        "/practice/curriculum/lessons/{lesson_id}",
        "/practice/curriculum/exercises",
    ):
        parameters = app.openapi()["paths"][path]["get"].get("parameters", [])
        assert "includeAnswers" not in {item["name"] for item in parameters}
