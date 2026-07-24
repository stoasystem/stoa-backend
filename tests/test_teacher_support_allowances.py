"""Teacher-support allowance admission and route-wiring contract."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import asyncio
import inspect
import threading
from typing import Any, Callable

from fastapi import HTTPException
import pytest

from stoa.config import Settings
from stoa.db.repositories import account_deletion_repo
from stoa.routers import conversations, questions, teachers
from stoa.security.authorization import AuthorizedResource, ResourceRef, ResourceType
from stoa.services import teacher_support_allowance_service


UTC = timezone.utc
NOW = datetime(2026, 3, 25, 12, tzinfo=UTC)


class AtomicSupportTable:
    """Small DynamoDB fake enforcing create-only rows and counter CAS."""

    def __init__(self, *, counter_barrier: threading.Barrier | None = None) -> None:
        self.items: dict[tuple[str, str], dict[str, object]] = {}
        self.transactions: list[list[dict[str, Any]]] = []
        self._lock = threading.Lock()
        self._counter_barrier = counter_barrier
        self._counter_reads = 0

    def get_item(
        self, *, Key: dict[str, str], ConsistentRead: bool = True
    ) -> dict[str, object]:
        assert ConsistentRead is True
        key = (Key["PK"], Key["SK"])
        wait = False
        with self._lock:
            item = deepcopy(self.items.get(key))
            if (
                self._counter_barrier is not None
                and Key["SK"].startswith("WEEK#")
                and self._counter_reads < self._counter_barrier.parties
            ):
                self._counter_reads += 1
                wait = True
        if wait:
            self._counter_barrier.wait(timeout=3)
        return {"Item": item} if item is not None else {}

    def transact_account_deletion(self, operations: list[dict[str, Any]]) -> None:
        with self._lock:
            snapshot = deepcopy(self.items)
            for operation in operations:
                if "ConditionCheck" in operation:
                    continue
                put = operation["Put"]
                item = deepcopy(put["Item"])
                key = (str(item["PK"]), str(item["SK"]))
                current = snapshot.get(key)
                condition = str(put.get("ConditionExpression") or "")
                values = put.get("ExpressionAttributeValues", {})
                if "attribute_not_exists(PK)" in condition and current is not None:
                    raise account_deletion_repo.AccountDeletionConflict(
                        "conditional create conflict"
                    )
                if ":expected_state_version" in values and (
                    current is None
                    or current.get("state_version") != values[":expected_state_version"]
                ):
                    raise account_deletion_repo.AccountDeletionConflict(
                        "counter version conflict"
                    )
                snapshot[key] = item
            self.items = snapshot
            self.transactions.append(deepcopy(operations))

    def support_rows(self, entity_type: str) -> list[dict[str, object]]:
        return [
            deepcopy(item)
            for item in self.items.values()
            if item.get("entity_type") == entity_type
        ]


def _grant(
    student_id: str,
    *,
    plan_id: str = "teacher_supported",
    parent_id: str = "parent-1",
    subscription_digest: str = "a" * 64,
    plan_version: int = 7,
    allowance_version: int = 11,
) -> dict[str, object]:
    return {
        "PK": f"PAID_GRANT#{parent_id}",
        "SK": f"BENEFICIARY#{student_id}",
        "entity_type": "beneficiary_grant",
        "schema_version": "paid_beneficiary_grant.v1",
        "parent_id": parent_id,
        "beneficiary_id": student_id,
        "grant_status": "active",
        "subscription_id_digest": subscription_digest,
        "grant_version": 13,
        "plan_id": plan_id,
        "plan_version": plan_version,
        "allowance_version": allowance_version,
        "activation_version": 13,
        "parent_profile_version": 3,
        "parent_account_fence_generation": 4,
        "student_profile_version": 5,
        "student_account_fence_generation": 6,
        "forward_relationship_version": 8,
        "reverse_relationship_version": 8,
    }


@pytest.fixture
def grants(monkeypatch: pytest.MonkeyPatch) -> dict[str, dict[str, object]]:
    values: dict[str, dict[str, object]] = {}
    monkeypatch.setattr(
        teacher_support_allowance_service.user_repo,
        "get_user",
        lambda student_id: {
            "user_id": student_id,
            "role": "student",
            "account_status": "active",
            "parent_id": values.get(student_id, {}).get("parent_id"),
            "parent_binding_status": "active",
        },
    )
    monkeypatch.setattr(
        teacher_support_allowance_service.paid_entitlement_service,
        "get_active_beneficiary_grant",
        lambda parent_id, student_id, **_kwargs: (
            deepcopy(values.get(student_id))
            if values.get(student_id, {}).get("parent_id") == parent_id
            else None
        ),
    )
    return values


def _case_committer(
    table: AtomicSupportTable,
    *,
    kind: str,
    case_id: str,
    beneficiary_id: str,
    calls: list[tuple[dict[str, Any], ...]] | None = None,
) -> Callable[[tuple[dict[str, Any], ...]], bool]:
    def commit(allowance_operations: tuple[dict[str, Any], ...]) -> bool:
        if calls is not None:
            calls.append(allowance_operations)
        case_operation = {
            "Put": {
                "Item": {
                    "PK": f"{kind.upper()}#{case_id}",
                    "SK": "CASE",
                    "entity_type": f"{kind}_support_case",
                    "case_id": case_id,
                },
                "ConditionExpression": (
                    "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                ),
            }
        }
        try:
            account_deletion_repo.transact(
                [
                    account_deletion_repo.active_fence_condition(beneficiary_id, 6),
                    *allowance_operations,
                    case_operation,
                ],
                table=table,
            )
        except account_deletion_repo.AccountDeletionConflict:
            return False
        return True

    return commit


def _admit(
    table: AtomicSupportTable,
    *,
    case_id: str,
    student_id: str = "student-1",
    kind: str = "question",
    observed_at: datetime = NOW,
    calls: list[tuple[dict[str, Any], ...]] | None = None,
):
    return teacher_support_allowance_service.admit_teacher_support_case(
        support_case_id=case_id,
        case_kind=kind,
        beneficiary_id=student_id,
        observed_at=observed_at,
        persist_case=_case_committer(
            table,
            kind=kind,
            case_id=case_id,
            beneficiary_id=student_id,
            calls=calls,
        ),
        table=table,
    )


@pytest.mark.parametrize("kind", ["question", "conversation"])
def test_first_durable_case_admission_debits_once_and_retry_replays(
    grants: dict[str, dict[str, object]],
    kind: str,
) -> None:
    grants["student-1"] = _grant("student-1")
    table = AtomicSupportTable()
    calls: list[tuple[dict[str, Any], ...]] = []

    first = _admit(table, case_id=f"{kind}-1", kind=kind, calls=calls)
    replay = _admit(table, case_id=f"{kind}-1", kind=kind, calls=calls)

    assert first.disposition.value == "admitted"
    assert replay.disposition.value == "replayed"
    assert first.admission == replay.admission
    assert first.admission is not None
    assert first.admission.post_admission_count == 1
    assert first.admission.limit == 2
    assert len(calls) == 1
    assert len(table.support_rows("teacher_support_admission")) == 1
    assert table.support_rows("teacher_support_counter")[0]["admitted_cases"] == 1


def test_teacher_supported_limit_is_two_per_beneficiary(
    grants: dict[str, dict[str, object]],
) -> None:
    grants["student-1"] = _grant("student-1")
    grants["student-2"] = _grant("student-2")
    table = AtomicSupportTable()

    results = [
        _admit(table, case_id=f"q-{index}", student_id="student-1")
        for index in range(3)
    ]
    other = _admit(table, case_id="q-other", student_id="student-2")

    assert [result.disposition.value for result in results] == [
        "admitted",
        "admitted",
        "limit_exceeded",
    ]
    assert other.disposition.value == "admitted"


def test_family_limit_is_ten_shared_across_three_beneficiaries(
    grants: dict[str, dict[str, object]],
) -> None:
    for student_id in ("student-1", "student-2", "student-3"):
        grants[student_id] = _grant(student_id, plan_id="family")
    table = AtomicSupportTable()

    results = [
        _admit(
            table,
            case_id=f"family-{index}",
            student_id=f"student-{(index % 3) + 1}",
        )
        for index in range(11)
    ]

    assert [result.disposition.value for result in results].count("admitted") == 10
    assert results[-1].disposition.value == "limit_exceeded"
    counters = table.support_rows("teacher_support_counter")
    assert len(counters) == 1
    assert counters[0]["admitted_cases"] == 10
    assert counters[0]["limit"] == 10


def test_concurrent_final_slot_has_one_winner(
    grants: dict[str, dict[str, object]],
) -> None:
    grants["student-1"] = _grant("student-1")
    table = AtomicSupportTable()
    assert _admit(table, case_id="first").disposition.value == "admitted"
    table._counter_barrier = threading.Barrier(2)
    table._counter_reads = 0

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda case_id: _admit(table, case_id=case_id),
                ("final-a", "final-b"),
            )
        )

    assert sorted(result.disposition.value for result in results) == [
        "admitted",
        "limit_exceeded",
    ]
    assert table.support_rows("teacher_support_counter")[0]["admitted_cases"] == 2


def test_zurich_dst_window_and_adjacent_week_do_not_roll_over(
    grants: dict[str, dict[str, object]],
) -> None:
    grants["student-1"] = _grant("student-1")
    table = AtomicSupportTable()

    spring = _admit(
        table,
        case_id="spring",
        observed_at=datetime(2026, 3, 25, 12, tzinfo=UTC),
    )
    next_week = _admit(
        table,
        case_id="next-week",
        observed_at=datetime(2026, 3, 30, 12, tzinfo=UTC),
    )

    assert spring.admission is not None
    assert spring.admission.week_identity == "2026-W13"
    assert (
        spring.admission.window_end - spring.admission.window_start
    ).total_seconds() == 167 * 3600
    assert next_week.admission is not None
    assert next_week.admission.week_identity == "2026-W14"
    assert next_week.admission.post_admission_count == 1
    assert len(table.support_rows("teacher_support_counter")) == 2


@pytest.mark.parametrize(
    "grant",
    [
        None,
        _grant("student-1", plan_id="student"),
        _grant("student-1", plan_id="free_trial"),
    ],
)
def test_denied_plan_persists_no_case_queue_notification_assignment_or_counter(
    grants: dict[str, dict[str, object]],
    grant: dict[str, object] | None,
) -> None:
    if grant is not None:
        grants["student-1"] = grant
    table = AtomicSupportTable()
    calls: list[tuple[dict[str, Any], ...]] = []

    result = _admit(table, case_id="denied", calls=calls)

    assert result.disposition.value == "plan_denied"
    assert calls == []
    assert table.items == {}


def test_cross_family_case_identity_cannot_replay_into_another_grant(
    grants: dict[str, dict[str, object]],
) -> None:
    grants["student-1"] = _grant("student-1", plan_id="family")
    grants["student-2"] = _grant(
        "student-2",
        plan_id="family",
        parent_id="parent-2",
        subscription_digest="b" * 64,
    )
    table = AtomicSupportTable()

    first = _admit(table, case_id="same-case", student_id="student-1")
    cross_family = _admit(table, case_id="same-case", student_id="student-2")

    assert first.disposition.value == "admitted"
    assert cross_family.disposition.value == "idempotency_conflict"
    assert len(table.support_rows("teacher_support_admission")) == 1


def test_projection_reports_exact_scope_week_count_and_limit(
    grants: dict[str, dict[str, object]],
) -> None:
    grants["student-1"] = _grant("student-1", plan_id="family")
    table = AtomicSupportTable()
    _admit(table, case_id="projection")

    projection = teacher_support_allowance_service.get_teacher_support_projection(
        beneficiary_id="student-1",
        observed_at=NOW,
        table=table,
    )

    assert projection == {
        "schemaVersion": "teacher_support_projection.v1",
        "planId": "family",
        "supportScope": "shared_family",
        "weekIdentity": "2026-W13",
        "admittedCases": 1,
        "remainingCases": 9,
        "limit": 10,
    }


def test_routes_admit_only_at_first_case_and_later_actions_do_not_mutate_allowance() -> None:
    question_source = inspect.getsource(questions.request_teacher)
    conversation_source = inspect.getsource(conversations.request_teacher_help)
    later_source = "\n".join(
        inspect.getsource(member)
        for member in (
            conversations.send_message,
            conversations.stream_message,
            teachers.reply,
            teachers.resolve,
        )
    )

    assert "admit_teacher_support_case" in question_source
    assert "admit_teacher_support_case" in conversation_source
    assert "persist_case=" in question_source
    assert "persist_case=" in conversation_source
    assert "admit_teacher_support_case" not in later_source
    assert question_source.index("admit_teacher_support_case") < question_source.index(
        "enqueue_teacher_request"
    )
    assert question_source.index("admit_teacher_support_case") < question_source.index(
        "emit_teacher_requested"
    )
    assert question_source.index("admit_teacher_support_case") < question_source.index(
        "dispatch_question"
    )
    assert conversation_source.index(
        "admit_teacher_support_case"
    ) < conversation_source.index("record_usage_event")


def test_service_reuses_allowance_week_budget_and_conditional_effect_counter() -> None:
    source = inspect.getsource(teacher_support_allowance_service)

    assert "allowance_service.zurich_week" in source
    assert "allowance_service.plan_allowance_budget" in source
    assert "attribute_not_exists(PK) AND attribute_not_exists(SK)" in source
    assert "state_version=:expected_state_version" in source


def test_question_plan_denial_runs_before_case_queue_notification_and_assignment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorized = AuthorizedResource(
        ResourceRef(
            resource_type=ResourceType.QUESTION,
            resource_id="question-denied",
            student_id="student-1",
        ),
        {
            "question_id": "question-denied",
            "student_id": "student-1",
            "subject": "math",
            "status": "ai_answered",
            "version": 1,
        },
    )
    monkeypatch.setattr(questions, "get_table", lambda: object())
    monkeypatch.setattr(
        questions.teacher_support_allowance_service,
        "admit_teacher_support_case",
        lambda **_kwargs: teacher_support_allowance_service.TeacherSupportAdmissionResult(
            teacher_support_allowance_service.TeacherSupportAdmissionDisposition.PLAN_DENIED
        ),
    )
    for dependency, name in (
        (questions.question_repo, "mutate_question"),
        (questions.notify_service, "enqueue_teacher_request"),
        (questions.notification_service, "emit_teacher_requested"),
        (questions.teacher_dispatch_service, "dispatch_question"),
        (questions.usage_ledger_service, "record_usage_event"),
    ):
        monkeypatch.setattr(
            dependency,
            name,
            lambda *_args, **_kwargs: pytest.fail("denied downstream effect ran"),
        )

    with pytest.raises(HTTPException) as denied:
        asyncio.run(
            questions.request_teacher(
                authorized=authorized,
                settings=Settings(),
            )
        )

    assert denied.value.status_code == 403


def test_conversation_plan_denial_runs_before_case_message_and_usage_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorized = AuthorizedResource(
        ResourceRef(
            resource_type=ResourceType.CONVERSATION,
            resource_id="conversation-denied",
            student_id="student-1",
        ),
        {
            "conversation_id": "conversation-denied",
            "student_id": "student-1",
            "subject": "physics",
            "grade": "Sek1",
        },
    )
    monkeypatch.setattr(conversations, "get_table", lambda: object())
    monkeypatch.setattr(
        conversations,
        "_active_conversation_generation",
        lambda *_args: 1,
    )
    monkeypatch.setattr(
        conversations.teacher_support_allowance_service,
        "admit_teacher_support_case",
        lambda **_kwargs: teacher_support_allowance_service.TeacherSupportAdmissionResult(
            teacher_support_allowance_service.TeacherSupportAdmissionDisposition.PLAN_DENIED
        ),
    )
    monkeypatch.setattr(
        conversations.attachment_repo,
        "record_teacher_help_request",
        lambda **_kwargs: pytest.fail("denied durable case ran"),
    )
    monkeypatch.setattr(
        conversations.usage_ledger_service,
        "record_usage_event",
        lambda **_kwargs: pytest.fail("denied usage effect ran"),
    )

    with pytest.raises(HTTPException) as denied:
        asyncio.run(
            conversations.request_teacher_help(
                body=conversations.TeacherHelpRequest(
                    conversationId="conversation-denied",
                    message="private request",
                ),
                authorized=authorized,
            )
        )

    assert denied.value.status_code == 403
