"""Phase 473 immutable practice receipt and non-derivable hint contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from scripts import seed_practice
from stoa.db.repositories import practice_repo
from stoa.routers import practice
from stoa.services import practice_projection_service


PRIVATE_KEYS = {
    "answer",
    "answerKey",
    "correctAnswer",
    "correctFeedback",
    "explanation",
    "feedback",
    "hint",
    "incorrectFeedback",
    "standardAnswer",
}
PRIVATE_CANARIES = {
    "STANDARD-ANSWER-CANARY",
    "EXPLANATION-CANARY",
    "CORRECT-FEEDBACK-CANARY",
    "INCORRECT-FEEDBACK-CANARY",
    "HINT-CANARY",
    "PRIVATE-NESTED-CANARY",
}


def _challenge(**overrides: Any) -> dict[str, Any]:
    challenge = {
        "PK": "PRACTICE",
        "SK": "CHALLENGE#lesson-1#challenge-1",
        "challenge_id": "challenge-1",
        "lesson_id": "lesson-1",
        "unit_id": "unit-1",
        "subject_id": "math",
        "grade_level": "secondary",
        "topic_id": "topic-1",
        "topic_title": "Equations",
        "order": 1,
        "type": "multiple_choice",
        "prompt": "Solve x + 4 = 9.",
        "options": ["x = 4", "x = 5"],
        "correct_answer": "x = 5",
        "explanation": "Subtract four from both sides.",
        "correct_feedback": "Correct.",
        "incorrect_feedback": "Review inverse operations.",
        "directional_hint_template_id": "review_problem_structure",
    }
    challenge.update(overrides)
    return challenge


def _versioned_challenge(**overrides: Any) -> dict[str, Any]:
    challenge = _challenge(**overrides)
    content_hash = practice_repo.canonical_challenge_content_hash(challenge)
    challenge["challenge_content_hash"] = content_hash
    challenge["challenge_version"] = f"sha256:{content_hash}"
    return challenge


def _receipt(**overrides: Any) -> dict[str, Any]:
    challenge = _versioned_challenge()
    receipt = {
        "PK": "ATTEMPTS#student-1",
        "SK": "ATTEMPT#attempt-1",
        "attempt_id": "attempt-1",
        "student_id": "student-1",
        "user_id": "student-1",
        "challenge_id": challenge["challenge_id"],
        "challenge_version": challenge["challenge_version"],
        "challenge_content_hash": challenge["challenge_content_hash"],
        "submitted_answer": "x = 4",
        "student_answer": "x = 4",
        "correct": False,
        "standard_answer": challenge["correct_answer"],
        "explanation": challenge["explanation"],
        "correct_feedback": challenge["correct_feedback"],
        "incorrect_feedback": challenge["incorrect_feedback"],
        "feedback": challenge["incorrect_feedback"],
        "next_challenge_id": "challenge-2",
        "prompt": challenge["prompt"],
        "options": challenge["options"],
        "challenge_type": challenge["type"],
        "subject_id": challenge["subject_id"],
        "topic_id": challenge["topic_id"],
        "lesson_id": challenge["lesson_id"],
        "unit_id": challenge["unit_id"],
        "created_at": "2026-07-17T00:00:00+00:00",
    }
    receipt.update(overrides)
    return receipt


def _hint_decision(challenge: Mapping[str, Any], **overrides: Any) -> dict[str, Any]:
    content_hash = practice_repo.canonical_challenge_content_hash(challenge)
    decision = {
        "template_id": challenge["directional_hint_template_id"],
        "challenge_version": f"sha256:{content_hash}",
        "content_hash": content_hash,
        "reviewer_id": "teacher-reviewer-1",
        "reviewer_role": "teacher",
        "policy_version": "practice-directional-hints-v1",
        "decision": "non_derivable",
        "approved_at": "2026-07-17T00:00:00+00:00",
    }
    decision.update(overrides)
    return decision


class _LookupTable:
    def __init__(self, responses: list[dict[str, Any]]):
        self.responses = list(responses)
        self.get_calls: list[dict[str, Any]] = []
        self.query_calls: list[dict[str, Any]] = []

    def get_item(self, **kwargs: Any) -> dict[str, Any]:
        self.get_calls.append(kwargs)
        return self.responses.pop(0) if self.responses else {}

    def query(self, **kwargs: Any) -> dict[str, Any]:
        self.query_calls.append(kwargs)
        raise AssertionError("challenge identity must never use scan/query lookup")


def _pointer(challenge: Mapping[str, Any], **overrides: Any) -> dict[str, Any]:
    pointer = {
        "PK": "PRACTICE_CHALLENGE_LOOKUP",
        "SK": f"CHALLENGE#{challenge['challenge_id']}",
        "entity_type": "practice_challenge_pointer",
        "challenge_id": challenge["challenge_id"],
        "target_pk": challenge["PK"],
        "target_sk": challenge["SK"],
        "challenge_version": challenge["challenge_version"],
        "challenge_content_hash": challenge["challenge_content_hash"],
    }
    pointer.update(overrides)
    return pointer


def test_get_challenge_uses_pointer_then_exact_canonical_get(monkeypatch) -> None:
    challenge = _versioned_challenge()
    table = _LookupTable([{"Item": _pointer(challenge)}, {"Item": challenge}])
    monkeypatch.setattr(practice_repo, "get_table", lambda: table)

    assert practice_repo.get_challenge("challenge-1") == challenge
    assert [call["Key"] for call in table.get_calls] == [
        {"PK": "PRACTICE_CHALLENGE_LOOKUP", "SK": "CHALLENGE#challenge-1"},
        {"PK": "PRACTICE", "SK": "CHALLENGE#lesson-1#challenge-1"},
    ]
    assert table.query_calls == []


@pytest.mark.parametrize(
    "pointer_override",
    [
        None,
        {"target_pk": ""},
        {"target_sk": "TOPIC#wrong"},
        {"challenge_id": "different"},
        {"challenge_version": "sha256:" + "0" * 64},
        {"challenge_content_hash": "0" * 64},
        {"correct_answer": "pointer-answer-canary"},
    ],
)
def test_get_challenge_rejects_missing_or_malformed_pointer(monkeypatch, pointer_override) -> None:
    challenge = _versioned_challenge()
    if pointer_override is None:
        responses = [{}]
    else:
        responses = [{"Item": _pointer(challenge, **pointer_override)}, {"Item": challenge}]
    table = _LookupTable(responses)
    monkeypatch.setattr(practice_repo, "get_table", lambda: table)

    assert practice_repo.get_challenge("challenge-1") is None
    assert table.query_calls == []


@pytest.mark.parametrize(
    "canonical_override",
    [
        {"challenge_id": "different"},
        {"challenge_version": "sha256:" + "0" * 64},
        {"challenge_content_hash": "0" * 64},
        {"prompt": "edited after hashing"},
    ],
)
def test_get_challenge_validates_canonical_id_version_and_hash(
    monkeypatch, canonical_override
) -> None:
    challenge = _versioned_challenge()
    malformed = {**challenge, **canonical_override}
    table = _LookupTable([{"Item": _pointer(challenge)}, {"Item": malformed}])
    monkeypatch.setattr(practice_repo, "get_table", lambda: table)

    assert practice_repo.get_challenge("challenge-1") is None


class _PagedTable:
    def __init__(self, pages: list[dict[str, Any]]):
        self.pages = list(pages)
        self.calls: list[dict[str, Any]] = []

    def query(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self.pages.pop(0)


def test_challenge_lists_fully_paginate(monkeypatch) -> None:
    first = _versioned_challenge(challenge_id="challenge-1", order=1)
    second = _versioned_challenge(
        challenge_id="challenge-2",
        SK="CHALLENGE#lesson-1#challenge-2",
        order=2,
    )
    marker = {"PK": "PRACTICE", "SK": first["SK"]}
    table = _PagedTable([{"Items": [first], "LastEvaluatedKey": marker}, {"Items": [second]}])
    monkeypatch.setattr(practice_repo, "get_table", lambda: table)

    assert [item["challenge_id"] for item in practice_repo.get_challenges("lesson-1")] == [
        "challenge-1",
        "challenge-2",
    ]
    assert table.calls[1]["ExclusiveStartKey"] == marker


def test_challenge_lists_reject_duplicate_ids_versions_and_stalled_markers(monkeypatch) -> None:
    first = _versioned_challenge()
    duplicate = {**first, "SK": "CHALLENGE#other-lesson#challenge-1"}
    marker = {"PK": "PRACTICE", "SK": first["SK"]}
    table = _PagedTable([{"Items": [first], "LastEvaluatedKey": marker}, {"Items": [duplicate]}])
    monkeypatch.setattr(practice_repo, "get_table", lambda: table)
    with pytest.raises(ValueError, match="duplicate"):
        practice_repo.get_all_challenges()

    stalled = _PagedTable(
        [
            {"Items": [first], "LastEvaluatedKey": marker},
            {"Items": [], "LastEvaluatedKey": marker},
        ]
    )
    monkeypatch.setattr(practice_repo, "get_table", lambda: stalled)
    with pytest.raises(ValueError, match="pagination"):
        practice_repo.get_all_challenges()


def test_seed_refuses_duplicates_and_writes_answer_free_pointers() -> None:
    first = _challenge()
    duplicate = _challenge(SK="CHALLENGE#lesson-2#challenge-1", lesson_id="lesson-2")
    with pytest.raises(ValueError, match="duplicate challenge_id"):
        seed_practice.prepare_challenge_items([first, duplicate])

    canonical, pointer = seed_practice.prepare_challenge_items([first])
    assert canonical["challenge_version"].startswith("sha256:")
    assert canonical["challenge_content_hash"] in canonical["challenge_version"]
    assert pointer == _pointer(canonical)
    assert not PRIVATE_KEYS.intersection(pointer)
    assert not any(canary in str(pointer) for canary in PRIVATE_CANARIES)


def test_snapshot_result_uses_only_complete_receipt() -> None:
    receipt = _receipt()
    result = practice_projection_service.build_attempt_result(receipt)
    assert result.model_dump(by_alias=True) == {
        "attemptId": "attempt-1",
        "challengeId": "challenge-1",
        "correct": False,
        "standardAnswer": "x = 5",
        "explanation": "Subtract four from both sides.",
        "feedback": "Review inverse operations.",
        "nextChallengeId": "challenge-2",
        "retryAllowed": True,
        "attemptsRemaining": 2,
    }

    for missing in (
        "challenge_version",
        "challenge_content_hash",
        "standard_answer",
        "explanation",
        "correct_feedback",
        "incorrect_feedback",
        "created_at",
    ):
        partial = dict(receipt)
        partial.pop(missing)
        with pytest.raises(ValueError, match="complete immutable attempt receipt"):
            practice_projection_service.build_attempt_result(partial)


def _route_client(monkeypatch, receipt: dict[str, Any]) -> TestClient:
    monkeypatch.setattr(
        practice.practice_repo,
        "get_attempt",
        lambda student_id, attempt_id: receipt
        if (student_id, attempt_id) == ("student-1", "attempt-1")
        else None,
    )
    monkeypatch.setattr(practice.practice_repo, "get_mistakes", lambda _student_id: [receipt])
    app = FastAPI()
    app.include_router(practice.router, prefix="/practice")
    install_actor_overrides(app, {"sub": "student-1", "role": "student"})
    return TestClient(app)


@pytest.mark.parametrize("mutation", ["edit", "delete", "duplicate", "id_reuse"])
def test_attempt_result_and_mistakes_ignore_current_challenge(monkeypatch, mutation) -> None:
    receipt = _receipt()
    current = {
        "edit": _versioned_challenge(correct_answer="MUTATED-ANSWER", explanation="MUTATED"),
        "delete": None,
        "duplicate": [_versioned_challenge(), _versioned_challenge(SK="duplicate")],
        "id_reuse": _versioned_challenge(correct_answer="REUSED-ANSWER", prompt="REUSED"),
    }[mutation]
    current_reads: list[str] = []

    def load_current(challenge_id: str):
        current_reads.append(challenge_id)
        if isinstance(current, list):
            raise ValueError("duplicate challenge rows")
        return current

    monkeypatch.setattr(practice.practice_repo, "get_challenge", load_current)
    client = _route_client(monkeypatch, receipt)

    result = client.get("/practice/attempts/attempt-1/result")
    mistakes = client.get("/practice/mistakes")
    assert result.status_code == 200, result.text
    assert result.json()["standardAnswer"] == "x = 5"
    assert result.json()["explanation"] == "Subtract four from both sides."
    assert result.json()["feedback"] == "Review inverse operations."
    assert result.json()["nextChallengeId"] == "challenge-2"
    assert mistakes.status_code == 200, mistakes.text
    assert mistakes.json()["items"][0]["prompt"] == "Solve x + 4 = 9."
    assert current_reads == []


def test_partial_attempt_route_reveals_no_answer(monkeypatch) -> None:
    partial = _receipt()
    partial.pop("standard_answer")
    client = _route_client(monkeypatch, partial)
    response = client.get("/practice/attempts/attempt-1/result")
    assert response.status_code == 404
    assert "x = 5" not in response.text
    assert "Subtract four" not in response.text


def _approved_challenge(**overrides: Any) -> dict[str, Any]:
    challenge = _challenge()
    challenge.update(overrides)
    challenge["hint_non_derivability_decision"] = _hint_decision(challenge)
    return challenge


@pytest.mark.parametrize(
    "free_form",
    [
        "The unknown is five.",
        "Die Lösung lautet fünf.",
        "Compute ten divided by two.",
        "Choose the second option.",
        "eCA9IDU=",
        "U+0078 U+0020 U+003D U+0020 U+0035",
        "Take nine, subtract four, and the remaining value is the unknown.",
    ],
)
def test_valid_provenance_never_authorizes_free_form_semantic_adversaries(free_form) -> None:
    challenge = _approved_challenge(hint=free_form, hint_approved=True)
    challenge["hint_non_derivability_decision"] = _hint_decision(challenge)
    assert practice_projection_service.approved_directional_hint(challenge) is None


def test_only_closed_parameter_free_template_can_render() -> None:
    challenge = _approved_challenge()
    expected = practice_projection_service.DIRECTIONAL_HINT_TEMPLATES[
        "review_problem_structure"
    ]
    assert practice_projection_service.approved_directional_hint(challenge) == expected

    invalid_cases = [
        _approved_challenge(directional_hint_template_id="unknown-template"),
        _approved_challenge(directional_hint_parameters={"number": "5"}),
        _approved_challenge(hint="legacy free-form hint"),
        _approved_challenge(hint_approved=True),
        _approved_challenge(hint_non_derivability_decision="approved"),
    ]
    for invalid in invalid_cases:
        if isinstance(invalid.get("hint_non_derivability_decision"), Mapping):
            invalid["hint_non_derivability_decision"] = _hint_decision(invalid)
        assert practice_projection_service.approved_directional_hint(invalid) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("prompt", "Edited prompt"),
        ("options", ["new", "choices"]),
        ("correct_answer", "changed answer"),
        ("explanation", "changed explanation"),
        ("correct_feedback", "changed correct feedback"),
        ("incorrect_feedback", "changed incorrect feedback"),
        ("directional_hint_template_id", "check_each_step"),
        ("private_content", {"nested": "changed"}),
    ],
)
def test_any_content_or_template_change_invalidates_hint_decision(field, value) -> None:
    challenge = _approved_challenge()
    challenge[field] = value
    assert practice_projection_service.approved_directional_hint(challenge) is None


def test_seed_validator_rejects_legacy_dynamic_and_malformed_hint_decisions() -> None:
    valid = _approved_challenge()
    canonical, _pointer_row = seed_practice.prepare_challenge_items([valid])
    assert canonical["directional_hint_template_id"] == "review_problem_structure"

    for invalid in (
        _approved_challenge(hint="legacy"),
        _approved_challenge(hint_approved=True),
        _approved_challenge(directional_hint_parameters={"answer": "five"}),
        _approved_challenge(directional_hint_template_id="unknown"),
        _approved_challenge(
            hint_non_derivability_decision={"decision": "non_derivable"}
        ),
    ):
        with pytest.raises(ValueError, match="hint"):
            seed_practice.prepare_challenge_items([invalid])


def _assert_answer_free(value: object, path: str = "root") -> None:
    if isinstance(value, Mapping):
        leaked = PRIVATE_KEYS.intersection(value)
        assert not leaked, f"private keys {sorted(leaked)} at {path}"
        for key, child in value.items():
            _assert_answer_free(child, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            _assert_answer_free(child, f"{path}[{index}]")
    elif isinstance(value, str):
        assert value not in PRIVATE_CANARIES, f"private value at {path}"


def test_every_student_preview_route_recursively_filters_real_row_canaries(monkeypatch) -> None:
    subject = {"subject_id": "math", "name": "Math", "order": 1, "status": "active"}
    topic = {
        "topic_id": "topic-1",
        "subject_id": "math",
        "title": "Equations",
        "order": 1,
        "status": "active",
    }
    unit = {
        "unit_id": "unit-1",
        "topic_id": "topic-1",
        "subject_id": "math",
        "title": "Unit",
        "order": 1,
        "status": "active",
    }
    lesson = {
        "lesson_id": "lesson-1",
        "unit_id": "unit-1",
        "topic_id": "topic-1",
        "subject_id": "math",
        "title": "Lesson",
        "order": 1,
        "status": "active",
        "explanation": "EXPLANATION-CANARY",
        "private": {"feedback": "PRIVATE-NESTED-CANARY"},
    }
    challenge = _challenge(
        correct_answer="STANDARD-ANSWER-CANARY",
        explanation="EXPLANATION-CANARY",
        correct_feedback="CORRECT-FEEDBACK-CANARY",
        incorrect_feedback="INCORRECT-FEEDBACK-CANARY",
        hint="HINT-CANARY",
        nested={"answerKey": "PRIVATE-NESTED-CANARY"},
        status="active",
    )
    monkeypatch.setattr(practice.practice_repo, "get_subjects", lambda: [subject])
    monkeypatch.setattr(practice.practice_repo, "get_topics", lambda *_a, **_k: [topic])
    monkeypatch.setattr(practice.practice_repo, "get_topic", lambda _id: topic)
    monkeypatch.setattr(practice.practice_repo, "get_units", lambda _id: [unit])
    monkeypatch.setattr(practice.practice_repo, "get_lessons", lambda **_k: [lesson])
    monkeypatch.setattr(practice.practice_repo, "get_lesson", lambda _id: lesson)
    monkeypatch.setattr(practice.practice_repo, "get_challenges", lambda _id: [challenge])
    monkeypatch.setattr(practice.practice_repo, "get_all_challenges", lambda **_k: [challenge])
    monkeypatch.setattr(practice.practice_repo, "get_progress", lambda *_a, **_k: [])
    monkeypatch.setattr(practice.practice_repo, "get_mistakes", lambda _id: [])

    app = FastAPI()
    app.include_router(practice.router, prefix="/practice")
    install_actor_overrides(app, {"sub": "student-1", "role": "student"})
    client = TestClient(app)
    responses = [
        client.get("/practice/overview"),
        client.get("/practice/curriculum/catalog"),
        client.get("/practice/curriculum/lessons/lesson-1"),
        client.get("/practice/curriculum/exercises"),
        client.get("/practice/math/topic-1/roadmap"),
        client.get("/practice/math/topic-1/path"),
        client.get("/practice/lessons/lesson-1"),
    ]
    for response in responses:
        assert response.status_code == 200, response.text
        _assert_answer_free(response.json())

