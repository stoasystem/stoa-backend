"""Phase 475 bounded mistake-answer persistence and legacy projection."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from stoa.db.repositories import practice_repo
from stoa.routers import practice
from stoa.services import practice_projection_service


class _PutTable:
    def __init__(self) -> None:
        self.puts: list[dict[str, Any]] = []

    def put_item(self, **kwargs: Any) -> None:
        self.puts.append(kwargs)


@pytest.mark.parametrize(
    "answer",
    [
        "  Grüezi 世界\n第二行  ",
        [" Auswahl A ", "Überraschung", "二"],
    ],
)
def test_wrong_answer_round_trips_exactly_after_normalization(
    monkeypatch: pytest.MonkeyPatch,
    answer: str | list[str],
) -> None:
    table = _PutTable()
    monkeypatch.setattr(practice_repo, "get_table", lambda: table)

    stored = practice_repo.put_attempt(
        "student-1",
        "challenge-1",
        answer,
        False,
        attempt_id="attempt-1",
        created_at="2026-07-22T00:00:00+00:00",
    )
    projected = practice_projection_service.build_mistake_projection(stored)
    payload = projected.model_dump(by_alias=True)

    assert stored["student_answer"] == answer
    assert stored["submitted_answer"] == answer
    assert stored["submitted_answer_schema_version"] == 1
    assert table.puts[0]["Item"]["student_answer"] == answer
    assert payload["answerState"] == "recorded"
    assert payload["yourAnswer"] == answer
    assert payload["message"] is None


@pytest.mark.parametrize(
    "answer,error_fragment",
    [
        ({"raw-secret": "not-supported"}, "unsupported value type"),
        ([["too-deep"]], "depth bound"),
        (["item"] * 51, "item bound"),
        ("界" * 2049, "serialized byte bound"),
    ],
)
def test_invalid_answers_fail_before_repository_access_without_echoing_input(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    answer: object,
    error_fragment: str,
) -> None:
    table_accesses: list[str] = []
    monkeypatch.setattr(
        practice_repo,
        "get_table",
        lambda: table_accesses.append("table") or _PutTable(),
    )

    with caplog.at_level(logging.WARNING), pytest.raises(
        ValueError, match=error_fragment
    ) as raised:
        practice_repo.put_attempt(
            "student-1",
            "challenge-1",
            answer,
            False,
        )

    assert table_accesses == []
    assert "raw-secret" not in str(raised.value)
    assert "raw-secret" not in caplog.text


def _mistake_client(
    monkeypatch: pytest.MonkeyPatch,
    attempts: list[dict[str, Any]],
) -> TestClient:
    monkeypatch.setattr(
        practice.practice_repo,
        "get_mistakes",
        lambda student_id: attempts if student_id == "student-1" else [],
    )
    app = FastAPI()
    app.include_router(practice.router, prefix="/practice")
    install_actor_overrides(app, {"sub": "student-1", "role": "student"})
    return TestClient(app)


def test_legacy_missing_answer_is_explicit_unknown_and_never_uses_standard_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _mistake_client(
        monkeypatch,
        [
            {
                "PK": "MISTAKES#student-1",
                "SK": "ATTEMPT#legacy-1",
                "challenge_id": "challenge-1",
                "subject_id": "math",
                "topic_id": "algebra",
                "prompt": "Solve x + 4 = 9.",
                "standard_answer": "CORRECT-ANSWER-CANARY",
                "created_at": "2025-01-01T00:00:00+00:00",
            }
        ],
    )

    response = client.get("/practice/mistakes")

    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["answerState"] == "unknown_legacy"
    assert item["yourAnswer"] is None
    assert item["message"] == "当时提交的答案未保存"
    assert "CORRECT-ANSWER-CANARY" not in response.text
    assert item["yourAnswer"] != ""


def test_route_rejects_unsupported_answer_before_attempt_write_and_redacts_value(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    challenge = {
        "challenge_id": "challenge-1",
        "lesson_id": "lesson-1",
        "subject_id": "math",
        "topic_id": "algebra",
        "prompt": "Solve",
        "correct_answer": "CORRECT-ANSWER-CANARY",
        "explanation": "EXPLANATION-CANARY",
    }
    writes: list[object] = []
    monkeypatch.setattr(
        practice.practice_repo,
        "get_challenge",
        lambda _challenge_id: challenge,
    )
    monkeypatch.setattr(
        practice.practice_repo,
        "put_attempt",
        lambda *_args, **_kwargs: writes.append("write"),
    )
    client = _mistake_client(monkeypatch, [])

    with caplog.at_level(logging.WARNING):
        response = client.post(
            "/practice/challenges/challenge-1/answer",
            json={"answer": {"raw-secret": "must-not-echo"}},
        )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "practice_answer_invalid"
    assert writes == []
    assert "raw-secret" not in response.text
    assert "must-not-echo" not in response.text
    assert "raw-secret" not in caplog.text
    assert "CORRECT-ANSWER-CANARY" not in response.text
    assert "EXPLANATION-CANARY" not in response.text


def test_mistake_response_schema_types_answer_state_and_nullable_answer() -> None:
    route = next(
        route
        for route in practice.router.routes
        if getattr(route, "path", "") == "/mistakes"
    )
    response_schema = route.response_model.model_json_schema(by_alias=True)
    mistake_schema = response_schema["$defs"]["PracticeMistake"]["properties"]

    assert "answerState" in mistake_schema
    assert "yourAnswer" in mistake_schema
    assert set(response_schema["$defs"]["LegacyAnswerState"]["enum"]) == {
        "recorded",
        "unknown_legacy",
    }
