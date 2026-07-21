from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from stoa.db.repositories import account_deletion_repo, question_repo
from stoa.routers import teachers


NOW = "2026-07-21T10:05:00+00:00"


class BarrierTakeoverTable:
    def __init__(self, question: dict[str, object], *, parties: int = 1):
        self.question = dict(question)
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
            update = operations[1]["Update"]
            values = update["ExpressionAttributeValues"]
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
            session = operations[2]["Put"]["Item"]
            if (
                self.question.get("status") != "escalated"
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


def _client(teacher_id: str) -> TestClient:
    app = FastAPI()
    app.include_router(teachers.router, prefix="/teachers")
    install_actor_overrides(
        app, {"sub": teacher_id, "role": "teacher", "assigned": True}
    )
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
        sla_fields={"sla_request_to_takeover_seconds": 300},
        table=table,
    )

    assert result.disposition is question_repo.TeacherTakeoverDisposition.CLAIMED
    claim_id = question_repo.teacher_takeover_claim_id(
        "question-1", "teacher-1"
    )
    assert result.session_id == question_repo.teacher_session_id_for_claim(claim_id)
    update = table.transactions[0][1]["Update"]
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
            table=table,
        )
        assert (
            result.disposition
            is question_repo.TeacherTakeoverDisposition.ALREADY_CLAIMED
        )
        assert result.session_id is None
        assert table.transactions == []
        assert table.sessions == {}
