from __future__ import annotations

import ast
import threading
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from stoa.db.repositories import account_deletion_repo, question_repo


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-07-22T10:00:00+00:00"


def _question(**extra: object) -> dict[str, object]:
    return {
        "PK": "QUESTION#question-1",
        "SK": "META",
        "entity_type": "question",
        "question_id": "question-1",
        "student_id": "student-1",
        "subject": "math",
        "status": "pending",
        "version": 1,
        **extra,
    }


class QuestionCasTable:
    def __init__(self, question: Mapping[str, object]):
        self.question = dict(question)
        self.sessions: dict[str, dict[str, object]] = {}
        self.transactions: list[list[dict[str, object]]] = []
        self.before_ai_commit: threading.Barrier | None = None
        self.release_ai_commit: threading.Event | None = None
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
        copied = [dict(operation) for operation in operations]
        update = operations[1]["Update"]
        values = update["ExpressionAttributeValues"]
        if values.get(":next_status") == "ai_answered":
            if self.before_ai_commit is not None:
                self.before_ai_commit.wait(timeout=5)
            if self.release_ai_commit is not None:
                assert self.release_ai_commit.wait(timeout=5)
        with self._lock:
            self.transactions.append(copied)
            if len(operations) == 3:
                self._apply_takeover(operations)
                return
            self._apply_cas(update)

    def _apply_cas(self, update):
        values = update["ExpressionAttributeValues"]
        expected_status = values[":expected_status"]
        expected_version = values.get(":expected_version")
        if expected_version is None:
            if "attribute_not_exists(#version)" not in update["ConditionExpression"]:
                raise AssertionError("legacy initialization must be explicit")
            matches = self.question.get("version") is None
        else:
            matches = self.question.get("version") == expected_version
        if (
            self.question.get("student_id") != values[":owner"]
            or self.question.get("status") != expected_status
            or not matches
        ):
            raise account_deletion_repo.AccountDeletionConflict("question CAS lost")
        self.question["version"] = values[":next_version"]
        self.question["status"] = values[":next_status"]
        for token, value in values.items():
            if token.startswith(":field_"):
                self.question[token.removeprefix(":field_")] = value

    def _apply_takeover(self, operations):
        update = operations[1]["Update"]
        values = update["ExpressionAttributeValues"]
        if (
            self.question.get("status") != "escalated"
            or self.question.get("version") != values.get(":expected_version")
        ):
            raise account_deletion_repo.AccountDeletionConflict("takeover CAS lost")
        session = operations[2]["Put"]["Item"]
        self.question.update(
            status="teacher_active",
            version=values[":next_version"],
            teacher_id=values[":teacher"],
            teacher_takeover_claim_id=values[":claim"],
            session_id=values[":session"],
            teacher_started_at=values[":claimed_at"],
            teacher_taken_over_at=values[":claimed_at"],
        )
        self.sessions[str(session["session_id"])] = dict(session)


def test_question_mutation_has_owner_state_version_and_one_increment():
    observed = _question()
    table = QuestionCasTable(observed)

    result = question_repo.mutate_question(
        observed,
        status="ai_answered",
        allowed_source_statuses=frozenset({"pending"}),
        extra_attrs={"ai_response": {"answer": "42"}},
        table=table,
    )

    assert result.disposition is question_repo.QuestionMutationDisposition.APPLIED
    assert result.question == table.question
    assert table.question["version"] == 2
    update = table.transactions[0][1]["Update"]
    assert "student_id=:owner" in update["ConditionExpression"]
    assert "#status=:expected_status" in update["ConditionExpression"]
    assert "#version=:expected_version" in update["ConditionExpression"]
    assert update["UpdateExpression"].count("#version=:next_version") == 1


def test_legacy_version_initialization_is_explicit_and_state_constrained():
    observed = _question()
    observed.pop("version")
    table = QuestionCasTable(observed)

    result = question_repo.initialize_legacy_question_version(
        observed,
        allowed_source_statuses=frozenset({"pending"}),
        table=table,
    )

    assert result.disposition is question_repo.QuestionMutationDisposition.APPLIED
    assert result.question is not None
    assert result.question["version"] == 1
    update = table.transactions[0][1]["Update"]
    assert "attribute_not_exists(#version)" in update["ConditionExpression"]
    assert "#status=:expected_status" in update["ConditionExpression"]
    assert "student_id=:owner" in update["ConditionExpression"]


def test_disallowed_observed_source_returns_invalid_transition_without_write():
    observed = _question(status="resolved")
    table = QuestionCasTable(observed)

    result = question_repo.mutate_question(
        observed,
        status="escalated",
        allowed_source_statuses=frozenset({"pending", "ai_answered"}),
        table=table,
    )

    assert (
        result.disposition
        is question_repo.QuestionMutationDisposition.INVALID_TRANSITION
    )
    assert table.transactions == []


def test_takeover_first_makes_barriered_stale_ai_completion_lose():
    stale_ai_snapshot = _question()
    escalated = _question(status="escalated", version=2)
    table = QuestionCasTable(escalated)
    table.before_ai_commit = threading.Barrier(2)
    table.release_ai_commit = threading.Event()

    with ThreadPoolExecutor(max_workers=2) as pool:
        ai_future = pool.submit(
            question_repo.mutate_question,
            stale_ai_snapshot,
            status="ai_answered",
            allowed_source_statuses=frozenset({"pending"}),
            extra_attrs={"ai_response": {"answer": "stale"}},
            table=table,
        )
        table.before_ai_commit.wait(timeout=5)
        takeover = question_repo.claim_teacher_takeover(
            "question-1",
            "teacher-1",
            claimed_at=NOW,
            question=escalated,
            table=table,
        )
        table.release_ai_commit.set()
        ai = ai_future.result(timeout=5)

    assert takeover.disposition is question_repo.TeacherTakeoverDisposition.CLAIMED
    assert ai.disposition is question_repo.QuestionMutationDisposition.STALE
    assert table.question["status"] == "teacher_active"
    assert table.question["teacher_id"] == "teacher-1"
    assert table.question["session_id"] == takeover.session_id
    assert "ai_response" not in table.question


def test_ai_first_allows_refreshed_escalation_then_takeover():
    table = QuestionCasTable(_question())

    ai = question_repo.mutate_question(
        _question(),
        status="ai_answered",
        allowed_source_statuses=frozenset({"pending"}),
        extra_attrs={"ai_response": {"answer": "fresh"}},
        table=table,
    )
    assert ai.question is not None
    escalation = question_repo.mutate_question(
        ai.question,
        status="escalated",
        allowed_source_statuses=frozenset({"pending", "ai_answered"}),
        extra_attrs={"teacher_requested_at": NOW},
        table=table,
    )
    assert escalation.question is not None
    takeover = question_repo.claim_teacher_takeover(
        "question-1",
        "teacher-1",
        claimed_at=NOW,
        question=escalation.question,
        table=table,
    )

    assert ai.disposition is question_repo.QuestionMutationDisposition.APPLIED
    assert escalation.disposition is question_repo.QuestionMutationDisposition.APPLIED
    assert takeover.disposition is question_repo.TeacherTakeoverDisposition.CLAIMED
    assert table.question["version"] == 4
    assert table.question["status"] == "teacher_active"
    assert table.question["ai_response"] == {"answer": "fresh"}


def test_stale_same_state_metadata_writers_cannot_replay_after_later_states():
    cases = (
        (
            _question(status="ai_answered", version=2),
            _question(
                status="teacher_active",
                version=3,
                teacher_id="teacher-1",
                session_id="session-1",
            ),
            "ai_answered",
            frozenset({"ai_answered", "resolved"}),
            {"student_feedback": 5},
        ),
        (
            _question(
                status="teacher_active",
                version=3,
                teacher_id="teacher-1",
                session_id="session-1",
            ),
            _question(status="resolved", version=4, resolved_at=NOW),
            "teacher_active",
            frozenset({"teacher_active"}),
            {"teacher_response": "stale"},
        ),
    )
    for observed, current, target_status, allowed, attrs in cases:
        table = QuestionCasTable(current)
        result = question_repo.mutate_question(
            observed,
            status=target_status,
            allowed_source_statuses=allowed,
            extra_attrs=attrs,
            table=table,
        )

        assert result.disposition is question_repo.QuestionMutationDisposition.STALE
        assert all(table.question.get(key) != value for key, value in attrs.items())


def _question_repo_calls(path: str) -> list[tuple[str, str]]:
    tree = ast.parse((ROOT / path).read_text())
    calls: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for child in ast.walk(node):
            func = child.func if isinstance(child, ast.Call) else None
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "question_repo"
                and func.attr in {
                    "mutate_question",
                    "update_status",
                    "update_status_conditionally",
                }
            ):
                calls.append((node.name, func.attr))
    return calls


def _dict_value(node: ast.Dict, key: str) -> ast.expr | None:
    for candidate, value in zip(node.keys, node.values, strict=True):
        if isinstance(candidate, ast.Constant) and candidate.value == key:
            return value
    return None


def _is_question_partition_key(node: ast.expr | None) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str) and node.value.startswith("QUESTION#")
    if isinstance(node, ast.JoinedStr):
        return any(
            isinstance(value, ast.Constant)
            and isinstance(value.value, str)
            and value.value.startswith("QUESTION#")
            for value in node.values
        )
    return False


def _direct_question_updates(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    updates: set[str] = set()
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(function):
            if not isinstance(node, ast.Dict):
                continue
            update = _dict_value(node, "Update")
            if not isinstance(update, ast.Dict):
                continue
            key = _dict_value(update, "Key")
            if not isinstance(key, ast.Dict):
                continue
            if _is_question_partition_key(_dict_value(key, "PK")):
                updates.add(function.name)
    return updates


def test_production_question_writer_registry_is_closed_over_cas_calls():
    registry = {
        "src/stoa/routers/questions.py": {
            ("request_teacher", "mutate_question"),
            ("submit_feedback", "mutate_question"),
        },
        "src/stoa/routers/teachers.py": {
            ("reply", "mutate_question"),
            ("resolve", "mutate_question"),
        },
        "src/stoa/services/teacher_dispatch_service.py": {
            ("dispatch_question", "mutate_question"),
            ("reassign_timed_out_dispatches", "mutate_question"),
        },
    }
    for path, expected in registry.items():
        calls = _question_repo_calls(path)
        assert not {
            call for call in calls if call[1] in {"update_status", "update_status_conditionally"}
        }
        assert {call for call in calls if call[1] == "mutate_question"} == expected

    direct_registry = {
        "src/stoa/db/repositories/question_repo.py": {
            "claim_teacher_takeover",
            "build_question_update_transaction",
            "_question_mutation_operation",
        },
        "src/stoa/db/repositories/question_submission_repo.py": {
            "complete_question_effect",
            "reverse_terminal_question_admission",
        },
    }
    discovered: dict[str, set[str]] = {}
    for path in (ROOT / "src/stoa").rglob("*.py"):
        functions = _direct_question_updates(path)
        if functions:
            discovered[str(path.relative_to(ROOT))] = functions
    assert discovered == direct_registry
