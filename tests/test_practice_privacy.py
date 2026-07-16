from collections.abc import Mapping, Sequence

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from stoa.models.practice import (
    PracticeAttemptResult,
    PracticeChallengePreview,
    PracticeHintResponse,
    PrivilegedPracticeAnswer,
)


FORBIDDEN_PREVIEW_KEYS = {
    "correctAnswer",
    "answerKey",
    "explanation",
    "correctFeedback",
    "incorrectFeedback",
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
        "choices": None,
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
        hint="Use the inverse operation on both sides.",
    )
    assert hint.model_dump(by_alias=True) == {
        "challengeId": "challenge-1",
        "hint": "Use the inverse operation on both sides.",
    }
    with pytest.raises(ValidationError):
        PracticeHintResponse(
            challengeId="challenge-1",
            hint="Try an inverse operation.",
            standardAnswer="x = 5",
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
