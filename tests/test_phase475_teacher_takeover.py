from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from stoa.db.repositories import account_deletion_repo, question_repo
from stoa.routers import teachers
from stoa.security.authorization import AuthorizationFacts, TeacherAuthorizationFacts
from stoa.security.route_authorization import get_authorization_fact_repository


NOW = "2026-07-21T10:05:00+00:00"


class BarrierTakeoverTable:
    def __init__(self, question: dict[str, object], *, parties: int = 1):
        self.question = dict(question)
        self.teacher_profiles = {
            "teacher-1": {
                "PK": "USER#teacher-1",
                "SK": "PROFILE",
                "user_id": "teacher-1",
                "role": "teacher",
                "account_status": "active",
                "version": 7,
            },
            "teacher-2": {
                "PK": "USER#teacher-2",
                "SK": "PROFILE",
                "user_id": "teacher-2",
                "role": "teacher",
                "account_status": "active",
                "version": 7,
            },
        }
        self.teacher_fences = {
            teacher_id: {
                "PK": f"USER#{teacher_id}",
                "SK": "ACCOUNT_FENCE",
                "entity_type": "account_fence",
                "status": "active",
                "generation": 3,
            }
            for teacher_id in self.teacher_profiles
        }
        self.sessions: dict[str, dict[str, object]] = {}
        self.transactions: list[list[dict[str, object]]] = []
        self._barrier = threading.Barrier(parties) if parties > 1 else None
        self._lock = threading.Lock()

    def get_item(self, *, Key, ConsistentRead=False):
        assert ConsistentRead is True
        with self._lock:
            if Key == {"PK": "USER#student-1", "SK": "ACCOUNT_FENCE"}:
                return {
                    "Item": {
                        **Key,
                        "entity_type": "account_fence",
                        "status": "active",
                        "generation": 1,
                    }
                }
            if Key.get("SK") == "ACCOUNT_FENCE":
                teacher_id = str(Key.get("PK") or "").removeprefix("USER#")
                fence = self.teacher_fences.get(teacher_id)
                return {"Item": dict(fence)} if fence else {}
            if Key.get("SK") == "PROFILE":
                teacher_id = str(Key.get("PK") or "").removeprefix("USER#")
                profile = self.teacher_profiles.get(teacher_id)
                return {"Item": dict(profile)} if profile else {}
            if Key == {"PK": "QUESTION#question-1", "SK": "META"}:
                return {"Item": dict(self.question)}
            session_id = str(Key.get("PK") or "").removeprefix("SESSION#")
            session = self.sessions.get(session_id)
            return {"Item": dict(session)} if session else {}

    def transact_account_deletion(self, operations):
        if self._barrier is not None:
            self._barrier.wait(timeout=5)
        with self._lock:
            copied = [dict(operation) for operation in operations]
            self.transactions.append(copied)
            update = next(
                operation["Update"]
                for operation in operations
                if "Update" in operation
            )
            values = update["ExpressionAttributeValues"]
            teacher_id = str(values[":teacher"])
            teacher_fence = self.teacher_fences.get(teacher_id)
            teacher_profile = self.teacher_profiles.get(teacher_id)
            profile_condition = next(
                operation["ConditionCheck"]
                for operation in operations
                if operation.get("ConditionCheck", {}).get("Key", {}).get("SK")
                == "PROFILE"
            )
            profile_values = profile_condition["ExpressionAttributeValues"]
            expected_version = values.get(":expected_version")
            current_version = self.question.get("version")
            version_matches = (
                current_version is None
                if expected_version is None
                else current_version == expected_version
            )
            dispatch_status = str(
                self.question.get("dispatch_status") or "unassigned"
            )
            dispatch_matches = dispatch_status in {"", "unassigned", "pending"} or (
                dispatch_status == "dispatched"
                and self.question.get("dispatched_teacher_id") == values[":teacher"]
                and str(self.question.get("dispatch_deadline_at") or "")
                > values[":claimed_at"]
            )
            session = next(
                operation["Put"]["Item"]
                for operation in operations
                if "Put" in operation
            )
            if (
                not teacher_fence
                or teacher_fence.get("status") != "active"
                or not teacher_profile
                or teacher_profile.get("PK") != profile_condition["Key"]["PK"]
                or teacher_profile.get("SK") != profile_condition["Key"]["SK"]
                or teacher_profile.get("user_id") != profile_values[":teacher_id"]
                or teacher_profile.get("role") != profile_values[":teacher_role"]
                or teacher_profile.get("account_status") != profile_values[":active"]
                or teacher_profile.get("version")
                != profile_values[":teacher_profile_version"]
                or self.question.get("status") != "escalated"
                or not version_matches
                or not dispatch_matches
                or session["session_id"] in self.sessions
            ):
                raise account_deletion_repo.AccountDeletionConflict(
                    "conditional account lifecycle conflict"
                )
            self.question.update(
                status="teacher_active",
                version=values[":next_version"],
                teacher_id=values[":teacher"],
                teacher_takeover_claim_id=values[":claim"],
                session_id=values[":session"],
                teacher_started_at=values[":claimed_at"],
                teacher_taken_over_at=values[":claimed_at"],
            )
            if dispatch_status == "dispatched":
                self.question.update(
                    dispatch_status="accepted",
                    dispatch_accepted_at=values[":claimed_at"],
                )
            if ":takeover_sla" in values:
                self.question["sla_request_to_takeover_seconds"] = values[
                    ":takeover_sla"
                ]
            self.sessions[str(session["session_id"])] = dict(session)


def _question(**extra: object) -> dict[str, object]:
    return {
        "PK": "QUESTION#question-1",
        "SK": "META",
        "entity_type": "question",
        "question_id": "question-1",
        "student_id": "student-1",
        "subject": "math",
        "status": "escalated",
        "version": 1,
        **extra,
    }


def _client(teacher_id: str, *, profile_version: int = 7) -> TestClient:
    app = FastAPI()
    app.include_router(teachers.router, prefix="/teachers")
    install_actor_overrides(
        app, {"sub": teacher_id, "role": "teacher", "assigned": True}
    )

    class VersionedTeacherFacts:
        async def facts_for(self, _actor, resource, _action, _purpose, value):
            return AuthorizationFacts(
                teacher=TeacherAuthorizationFacts(
                    question=value,
                    teacher_account={
                        "PK": f"USER#{teacher_id}",
                        "SK": "PROFILE",
                        "user_id": teacher_id,
                        "role": "teacher",
                        "account_status": "active",
                        "version": profile_version,
                    },
                    student_account={
                        "user_id": resource.student_id,
                        "role": "student",
                        "account_status": "active",
                    },
                )
            )

    app.dependency_overrides[get_authorization_fact_repository] = VersionedTeacherFacts
    return TestClient(app)


def test_two_barrier_claimants_produce_one_owner_session_and_private_loser(
    monkeypatch,
):
    table = BarrierTakeoverTable(_question(), parties=2)
    monkeypatch.setattr(question_repo, "get_table", lambda: table)
    monkeypatch.setattr(teachers, "get_table", lambda: table)
    monkeypatch.setattr(teachers, "_now", lambda: NOW)
    notifications: list[dict[str, object]] = []
    monkeypatch.setattr(
        teachers.notification_service,
        "emit_teacher_takeover",
        lambda **kwargs: notifications.append(kwargs),
    )
    clients = (_client("teacher-1"), _client("teacher-2"))

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda pair: pair[0].post(
                    "/teachers/questions/question-1/takeover"
                ),
                zip(clients, ("teacher-1", "teacher-2"), strict=True),
            )
        )

    assert sorted(response.status_code for response in responses) == [200, 409]
    winner = next(response for response in responses if response.status_code == 200)
    loser = next(response for response in responses if response.status_code == 409)
    assert loser.json() == {
        "detail": {
            "code": "teacher_takeover_already_claimed",
            "message": "Question was taken by another teacher.",
            "action": "refresh_teacher_queue",
        }
    }
    owner = str(table.question["teacher_id"])
    assert owner not in str(loser.json())
    assert len(table.sessions) == 1
    session = next(iter(table.sessions.values()))
    assert session["teacher_id"] == owner
    assert winner.json()["session_id"] == session["session_id"]
    assert table.question["session_id"] == session["session_id"]
    assert notifications == []


def test_same_winner_retry_replays_same_session_without_write(monkeypatch):
    table = BarrierTakeoverTable(_question())
    monkeypatch.setattr(question_repo, "get_table", lambda: table)
    monkeypatch.setattr(teachers, "get_table", lambda: table)
    monkeypatch.setattr(teachers, "_now", lambda: NOW)
    client = _client("teacher-1")

    first = client.post("/teachers/questions/question-1/takeover")
    writes_after_first = len(table.transactions)
    replay = client.post("/teachers/questions/question-1/takeover")

    assert first.status_code == replay.status_code == 200
    assert replay.json() == first.json()
    assert len(table.transactions) == writes_after_first == 1
    assert len(table.sessions) == 1


def test_takeover_transaction_binds_version_dispatch_and_deterministic_session():
    table = BarrierTakeoverTable(
        _question(
            dispatch_status="dispatched",
            dispatched_teacher_id="teacher-1",
            dispatch_deadline_at="2026-07-21T10:15:00+00:00",
        )
    )

    result = question_repo.claim_teacher_takeover(
        "question-1",
        "teacher-1",
        claimed_at=NOW,
        question=dict(table.question),
        teacher_profile_key={"PK": "USER#teacher-1", "SK": "PROFILE"},
        teacher_profile_version=7,
        sla_fields={"sla_request_to_takeover_seconds": 300},
        table=table,
    )

    assert result.disposition is question_repo.TeacherTakeoverDisposition.CLAIMED
    claim_id = question_repo.teacher_takeover_claim_id(
        "question-1", "teacher-1"
    )
    assert result.session_id == question_repo.teacher_session_id_for_claim(claim_id)
    operations = table.transactions[0]
    teacher_fence = operations[1]["ConditionCheck"]
    teacher_profile = operations[2]["ConditionCheck"]
    update = operations[3]["Update"]
    assert teacher_fence["Key"] == {
        "PK": "USER#teacher-1",
        "SK": "ACCOUNT_FENCE",
    }
    assert teacher_profile["Key"] == {
        "PK": "USER#teacher-1",
        "SK": "PROFILE",
    }
    assert (
        teacher_profile["ConditionExpression"]
        == "attribute_exists(PK) AND attribute_exists(SK) AND "
        "#user_id=:teacher_id AND #role=:teacher_role AND "
        "#account_status=:active AND #version=:teacher_profile_version"
    )
    assert teacher_profile["ExpressionAttributeValues"] == {
        ":teacher_id": "teacher-1",
        ":teacher_role": "teacher",
        ":active": "active",
        ":teacher_profile_version": 7,
    }
    assert "#status=:escalated" in update["ConditionExpression"]
    assert "#version=:expected_version" in update["ConditionExpression"]
    assert "dispatched_teacher_id=:teacher" in update["ConditionExpression"]
    assert "dispatch_deadline_at>:claimed_at" in update["ConditionExpression"]
    assert table.question["dispatch_status"] == "accepted"
    assert table.question["sla_request_to_takeover_seconds"] == 300


def test_wrong_or_stale_dispatch_owner_cannot_claim_and_creates_no_session():
    cases = (
        (
            "teacher-2",
            {
                "dispatch_status": "dispatched",
                "dispatched_teacher_id": "teacher-1",
                "dispatch_deadline_at": "2026-07-21T10:15:00+00:00",
            },
        ),
        (
            "teacher-1",
            {
                "dispatch_status": "dispatched",
                "dispatched_teacher_id": "teacher-1",
                "dispatch_deadline_at": "2026-07-21T10:00:00+00:00",
            },
        ),
    )
    for teacher_id, dispatch in cases:
        table = BarrierTakeoverTable(_question(**dispatch))
        result = question_repo.claim_teacher_takeover(
            "question-1",
            teacher_id,
            claimed_at=NOW,
            question=dict(table.question),
            teacher_profile_key={"PK": f"USER#{teacher_id}", "SK": "PROFILE"},
            teacher_profile_version=7,
            table=table,
        )
        assert (
            result.disposition
            is question_repo.TeacherTakeoverDisposition.ALREADY_CLAIMED
        )
        assert result.session_id is None
        assert table.transactions == []
        assert table.sessions == {}


@pytest.mark.parametrize(
    ("profile_change", "fence_status"),
    [
        ({"account_status": "suspended"}, "active"),
        ({"account_status": "deleted"}, "active"),
        ({"account_status": "inactive"}, "active"),
        ({"role": "student"}, "active"),
        ({"role": "tutor"}, "active"),
        ({"role": "instructor"}, "active"),
        ({"role": "teachers"}, "active"),
        ({"version": 8}, "active"),
        ({}, "deletion_pending"),
        ({}, "deleted"),
    ],
)
def test_stale_authorized_teacher_lifecycle_race_rolls_back_every_artifact(
    monkeypatch,
    profile_change: dict[str, object],
    fence_status: str,
):
    table = BarrierTakeoverTable(_question())
    table.teacher_profiles["teacher-1"].update(profile_change)
    table.teacher_fences["teacher-1"]["status"] = fence_status
    before = dict(table.question)
    notifications: list[dict[str, object]] = []
    monkeypatch.setattr(question_repo, "get_table", lambda: table)
    monkeypatch.setattr(teachers, "get_table", lambda: table)
    monkeypatch.setattr(teachers, "_now", lambda: NOW)
    monkeypatch.setattr(
        teachers.notification_service,
        "ensure_teacher_takeover_notification",
        lambda **kwargs: notifications.append(kwargs),
    )

    response = _client("teacher-1", profile_version=7).post(
        "/teachers/questions/question-1/takeover"
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "teacher_takeover_temporarily_unavailable",
            "message": "Teacher takeover is temporarily unavailable. Try again.",
            "action": "retry_teacher_takeover",
        }
    }
    assert table.question == before
    assert table.sessions == {}
    assert notifications == []
