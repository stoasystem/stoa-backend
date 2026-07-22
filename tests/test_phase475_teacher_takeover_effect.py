from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import pytest
from fastapi import HTTPException

from stoa.db.repositories import notification_repo, question_repo
from stoa.routers import teachers
from stoa.security.authorization import (
    AuthorizationFacts,
    AuthorizedResource,
    ResourceRef,
    ResourceType,
    TeacherAuthorizationFacts,
)
from stoa.services import notification_service


CLAIM_ID = question_repo.teacher_takeover_claim_id("question-1", "teacher-1")
SESSION_ID = question_repo.teacher_session_id_for_claim(CLAIM_ID)
CLAIMED_AT = "2026-07-21T10:05:00+00:00"


def _claimed_question() -> dict[str, object]:
    return {
        "PK": "QUESTION#question-1",
        "SK": "META",
        "entity_type": "question",
        "question_id": "question-1",
        "student_id": "student-1",
        "subject": "math",
        "status": "teacher_active",
        "version": 2,
        "teacher_id": "teacher-1",
        "teacher_takeover_claim_id": CLAIM_ID,
        "session_id": SESSION_ID,
        "teacher_started_at": CLAIMED_AT,
        "teacher_taken_over_at": CLAIMED_AT,
        "account_fence_generation": 7,
    }


def _authorized(question: Mapping[str, object]) -> AuthorizedResource:
    return AuthorizedResource(
        ref=ResourceRef(
            resource_type=ResourceType.QUESTION,
            resource_id="question-1",
            student_id="student-1",
        ),
        value=question,
        facts=AuthorizationFacts(
            teacher=TeacherAuthorizationFacts(
                question=question,
                teacher_account={
                    "user_id": "teacher-1",
                    "role": "teacher",
                    "account_status": "active",
                },
            )
        ),
    )


def test_effect_identity_is_stable_and_binds_claim_plus_session() -> None:
    first = notification_service.teacher_takeover_effect_id(CLAIM_ID, SESSION_ID)

    assert first == notification_service.teacher_takeover_effect_id(
        CLAIM_ID, SESSION_ID
    )
    assert first != notification_service.teacher_takeover_effect_id(
        CLAIM_ID, f"{SESSION_ID}-changed"
    )
    assert first != notification_service.teacher_takeover_effect_id(
        f"{CLAIM_ID}-changed", SESSION_ID
    )


def test_begin_dependency_failure_then_retry_creates_one_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    question = _claimed_question()
    events: dict[str, dict[str, Any]] = {}
    registrations: list[dict[str, Any]] = []
    deliveries: list[dict[str, Any]] = []
    attempts = 0

    def load_event(event_id: str) -> dict[str, Any] | None:
        event = events.get(event_id)
        return dict(event) if event is not None else None

    def register(**kwargs: Any) -> dict[str, Any]:
        registrations.append(kwargs)
        return {"status": "registered"}

    def create_event(**kwargs: Any) -> dict[str, Any]:
        event_id = str(kwargs["event_id"])
        assert event_id not in events
        stored = {
            **kwargs,
            "entity_type": notification_repo.NOTIFICATION_ENTITY,
            "event_id": event_id,
            "owner_id": kwargs["owner_id"],
            "account_fence_generation": kwargs["account_fence_generation"],
        }
        events[event_id] = stored
        return {"eventId": event_id}

    def run_delivery(**kwargs: Any) -> dict[str, str]:
        nonlocal attempts
        attempts += 1
        deliveries.append(kwargs)
        if attempts == 1:
            return {"status": "retryable_dependency"}
        kwargs["provider_call"]()
        return {"status": "accepted"}

    monkeypatch.setattr(
        notification_service.notification_repo,
        "load_delivery_event_strong",
        load_event,
    )
    monkeypatch.setattr(
        notification_service.notification_repo,
        "register_delivery_intent",
        register,
    )
    monkeypatch.setattr(notification_service, "create_event", create_event)
    monkeypatch.setattr(notification_service, "run_delivery_intent", run_delivery)

    failed = notification_service.ensure_teacher_takeover_notification(
        question=question,
        teacher_id="teacher-1",
        session_id=SESSION_ID,
    )
    recovered = notification_service.ensure_teacher_takeover_notification(
        question=question,
        teacher_id="teacher-1",
        session_id=SESSION_ID,
    )
    replayed = notification_service.ensure_teacher_takeover_notification(
        question=question,
        teacher_id="teacher-1",
        session_id=SESSION_ID,
    )

    assert failed["status"] == "retryable_dependency"
    assert recovered["status"] == replayed["status"] == "accepted"
    assert failed["effect_id"] == recovered["effect_id"] == replayed["effect_id"]
    assert len(events) == 1
    assert len(deliveries) == 2
    assert {call["operation_id"] for call in registrations} == {
        failed["effect_id"]
    }
    assert {call["operation_id"] for call in deliveries} == {
        failed["effect_id"]
    }


def test_lost_notification_write_response_reconciles_without_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    question = _claimed_question()
    events: dict[str, dict[str, Any]] = {}
    provider_calls = 0

    monkeypatch.setattr(
        notification_service.notification_repo,
        "load_delivery_event_strong",
        lambda event_id: dict(events[event_id]) if event_id in events else None,
    )
    monkeypatch.setattr(
        notification_service.notification_repo,
        "register_delivery_intent",
        lambda **_kwargs: {"status": "registered"},
    )

    def create_then_lose_response(**kwargs: Any) -> dict[str, Any]:
        nonlocal provider_calls
        provider_calls += 1
        event_id = str(kwargs["event_id"])
        events[event_id] = {
            **kwargs,
            "entity_type": notification_repo.NOTIFICATION_ENTITY,
            "event_id": event_id,
            "owner_id": kwargs["owner_id"],
            "account_fence_generation": kwargs["account_fence_generation"],
        }
        raise TimeoutError("lost response after durable notification write")

    def run_delivery(**kwargs: Any) -> dict[str, str]:
        try:
            kwargs["provider_call"]()
        except TimeoutError:
            return {"status": "provider_acceptance_unknown"}
        return {"status": "accepted"}

    monkeypatch.setattr(
        notification_service, "create_event", create_then_lose_response
    )
    monkeypatch.setattr(notification_service, "run_delivery_intent", run_delivery)

    first = notification_service.ensure_teacher_takeover_notification(
        question=question,
        teacher_id="teacher-1",
        session_id=SESSION_ID,
    )
    retry = notification_service.ensure_teacher_takeover_notification(
        question=question,
        teacher_id="teacher-1",
        session_id=SESSION_ID,
    )

    assert first["status"] == retry["status"] == "accepted"
    assert provider_calls == 1
    assert len(events) == 1


def test_route_keeps_winner_session_when_effect_fails_then_replays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    question = _claimed_question()
    dispositions = iter(
        (
            question_repo.TeacherTakeoverDisposition.CLAIMED,
            question_repo.TeacherTakeoverDisposition.REPLAYED,
        )
    )
    ensure_attempts = 0

    def claim(*_args: Any, **_kwargs: Any) -> question_repo.TeacherTakeoverResult:
        return question_repo.TeacherTakeoverResult(
            next(dispositions),
            "question-1",
            session_id=SESSION_ID,
            question=dict(question),
            session={
                "session_id": SESSION_ID,
                "teacher_id": "teacher-1",
                "question_id": "question-1",
            },
        )

    def ensure(**_kwargs: Any) -> dict[str, str]:
        nonlocal ensure_attempts
        ensure_attempts += 1
        if ensure_attempts == 1:
            raise TimeoutError("notification dependency unavailable")
        return {"effect_id": "opaque-effect", "status": "accepted"}

    monkeypatch.setattr(teachers.question_repo, "claim_teacher_takeover", claim)
    monkeypatch.setattr(teachers.notification_service, "ensure_teacher_takeover_notification", ensure)
    monkeypatch.setattr(teachers, "get_table", lambda: object())
    monkeypatch.setattr(teachers, "_now", lambda: CLAIMED_AT)

    first = asyncio.run(teachers.takeover("question-1", _authorized(question)))
    retry = asyncio.run(teachers.takeover("question-1", _authorized(question)))

    assert first.question_id == retry.question_id == "question-1"
    assert first.session_id == retry.session_id == SESSION_ID
    assert first.status == retry.status == "teacher_active"
    assert first.notification_effect_status == "retryable_dependency"
    assert retry.notification_effect_status == "accepted"
    assert question["status"] == "teacher_active"
    assert question["teacher_id"] == "teacher-1"
    assert ensure_attempts == 2


def test_losing_claim_never_reaches_notification_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    question = _claimed_question()
    ensure_calls = 0

    monkeypatch.setattr(
        teachers.question_repo,
        "claim_teacher_takeover",
        lambda *_args, **_kwargs: question_repo.TeacherTakeoverResult(
            question_repo.TeacherTakeoverDisposition.ALREADY_CLAIMED,
            "question-1",
        ),
    )

    def ensure(**_kwargs: Any) -> dict[str, str]:
        nonlocal ensure_calls
        ensure_calls += 1
        return {"effect_id": "should-not-exist", "status": "accepted"}

    monkeypatch.setattr(teachers.notification_service, "ensure_teacher_takeover_notification", ensure)
    monkeypatch.setattr(teachers, "get_table", lambda: object())

    with pytest.raises(HTTPException) as captured:
        asyncio.run(teachers.takeover("question-1", _authorized(question)))

    assert captured.value.status_code == 409
    assert ensure_calls == 0
