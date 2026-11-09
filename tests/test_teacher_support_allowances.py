"""Teacher-support allowance admission and route-wiring contract."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fakes.dynamodb import FakeTable, condition_holds, from_wire
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import asyncio
import inspect
import threading
from typing import Any, Callable, Mapping

import pytest

from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo, parent_link_repo
from stoa.routers import conversations, teachers
from stoa.security.authorization import AuthorizedResource, ResourceRef, ResourceType
from stoa.services import (
    help_requests,
    paid_entitlement_service,
    teacher_support_allowance_service,
)
from fakes.admission import seed_period_active


UTC = timezone.utc
NOW = datetime(2026, 3, 25, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _usage_period_active(monkeypatch):
    """Every student here may ask a teacher; an ended period is #344's own test."""
    seed_period_active(monkeypatch)


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
            assert self._counter_barrier is not None
            self._counter_barrier.wait(timeout=3)
        return {"Item": item} if item is not None else {}

    def transact_write_items(self, *, TransactItems: list[dict[str, Any]]) -> None:  # noqa: N803
        """Conditions first, then effects - including the ConditionCheck rows.

        This used to `continue` past every ConditionCheck, which meant the
        fences an admission carries - the student's profile version, the
        allowance version, the account fence - were never evaluated by any test
        using this double. Code that dropped them entirely stayed green.
        """
        operations = from_wire(TransactItems)
        with self._lock:
            snapshot = deepcopy(self.items)
            for operation in operations:
                if "ConditionCheck" in operation:
                    check = operation["ConditionCheck"]
                    key = (str(check["Key"]["PK"]), str(check["Key"]["SK"]))
                    if not condition_holds(
                        check.get("ConditionExpression"),
                        snapshot.get(key),
                        names=check.get("ExpressionAttributeNames"),
                        values=check.get("ExpressionAttributeValues"),
                    ):
                        raise account_deletion_repo.AccountDeletionConflict(
                            "condition check failed"
                        )
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
    }


class _GrantsByBeneficiary(dict):
    """Grants by beneficiary; storing one also links its parent to the beneficiary.

    A grant only pays while the relationship it rests on is current, and the
    judge reads that from the link rows, so every grant a test stores comes with
    the link it needs.
    """

    def __init__(self, links: Any) -> None:
        super().__init__()
        self._links = links

    def __setitem__(self, student_id: str, grant: dict[str, object]) -> None:
        previous = self.get(student_id)
        if previous is not None:
            self._links.unlink(str(previous["parent_id"]), student_id)
        super().__setitem__(student_id, grant)
        self._links.link(str(grant["parent_id"]), student_id)


@pytest.fixture
def grants(monkeypatch: pytest.MonkeyPatch, link_rows: Any) -> dict[str, dict[str, object]]:
    values = _GrantsByBeneficiary(link_rows)

    def get_user(user_id: str, **_kwargs: object) -> dict[str, object]:
        parents = {str(grant.get("parent_id")) for grant in values.values()}
        return {
            "user_id": user_id,
            "role": "parent" if user_id in parents else "student",
            "account_status": "active",
        }

    monkeypatch.setattr(teacher_support_allowance_service.user_repo, "get_user", get_user)
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


def seed_fenced_rows(table: AtomicSupportTable, beneficiary_id: str) -> None:
    """Put on the table every row an admission fences against.

    The scope is resolved from patched repositories, so without this the rows
    those fences name exist only in the patch. The double used to skip every
    ConditionCheck, which is why no test needed this - and why code that
    dropped a fence altogether stayed green.
    """
    profile = teacher_support_allowance_service.user_repo.get_user(beneficiary_id) or {}
    parents = paid_entitlement_service.beneficiary_parents(beneficiary_id)
    parent_id = parents[0].parent_id if parents else ""
    grant = (
        teacher_support_allowance_service.paid_entitlement_service.get_active_beneficiary_grant(
            parent_id, beneficiary_id
        )
        if parent_id
        else None
    )

    def put(row: dict[str, Any]) -> None:
        table.items.setdefault((str(row["PK"]), str(row["SK"])), row)

    put({
        "PK": f"USER#{beneficiary_id}",
        "SK": "PROFILE",
        **{key: value for key, value in profile.items() if value is not None},
        "version": Decimal(str((grant or {}).get("student_profile_version") or 1)),
    })
    put({
        "PK": f"USER#{beneficiary_id}",
        "SK": "ACCOUNT_FENCE",
        "status": "active",
        "generation": Decimal("6"),
    })
    if grant is None:
        return
    put({**deepcopy(grant)})
    put({
        "PK": f"USER#{parent_id}",
        "SK": "PROFILE",
        "user_id": parent_id,
        "role": "parent",
        "account_status": "active",
        "version": Decimal(str(grant.get("parent_profile_version") or 1)),
    })
    put({
        "PK": f"USER#{parent_id}",
        "SK": "ACCOUNT_FENCE",
        "status": "active",
        "generation": Decimal(str(grant.get("parent_account_fence_generation") or 1)),
    })
    # Both link rows, as the judge read them: the admission fences them active.
    for side in (
        parent_link_repo.get_parent_side_link(parent_id, beneficiary_id),
        parent_link_repo.get_student_side_link(beneficiary_id, parent_id),
    ):
        assert side is not None
        put(deepcopy(dict(side)))


def _case_committer(
    table: AtomicSupportTable,
    *,
    kind: str,
    case_id: str,
    beneficiary_id: str,
    calls: list[tuple[dict[str, Any], ...]] | None = None,
) -> Callable[[tuple[dict[str, Any], ...], Mapping[str, int]], bool]:
    seed_fenced_rows(table, beneficiary_id)

    def commit(
        allowance_operations: tuple[dict[str, Any], ...], fences: Mapping[str, int]
    ) -> bool:
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
            db_table.fenced(
                beneficiary_id,
                [*allowance_operations, case_operation],
                generation=6,
                also=fences,
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


def test_grant_numbers_stored_as_decimal_still_admit(
    grants: dict[str, dict[str, object]],
) -> None:
    """The DynamoDB resource API returns every stored number as Decimal.

    Fixtures that use int hid this: the grant resolved locally but never against
    a real table, so teacher support was denied for every paying beneficiary.
    """
    grant = _grant("student-1")
    grants["student-1"] = {
        key: Decimal(value) if type(value) is int else value
        for key, value in grant.items()
    }
    table = AtomicSupportTable()

    result = _admit(table, case_id="q-decimal", student_id="student-1")

    assert result.disposition.value == "admitted"


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
    # The rows an admission would fence against are the fixture's world, not
    # its effects. Snapshot them so "wrote nothing" stays an exact comparison.
    seed_fenced_rows(table, "student-1")
    before = deepcopy(table.items)

    result = _admit(table, case_id="denied", calls=calls)

    assert result.disposition.value == "plan_denied"
    assert calls == []
    assert table.items == before


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
    conversation_source = inspect.getsource(conversations.request_teacher_help)
    ask_source = inspect.getsource(help_requests.ask)
    later_source = "\n".join(
        inspect.getsource(member)
        for member in (
            conversations.send_message,
            conversations.stream_message,
            teachers.update_help_request,
            teachers.add_note,
            help_requests.dispatch,
            help_requests.take_or_finish,
            help_requests._advance,
            help_requests.reply,
        )
    )

    # The route asks; asking is where the case is admitted (#189).
    assert "help_requests.ask(" in conversation_source
    assert "admit_teacher_support_case" in ask_source
    assert "persist_case=" in ask_source
    assert "admit_teacher_support_case" not in later_source


def test_the_chat_escalation_dispatches_to_a_teacher() -> None:
    """An escalation that never dispatches is invisible to every teacher.

    The chat lane used to set escalation flags and stop, so the teacher queue
    stayed empty no matter how many students asked for help. (The question
    lane it was once checked beside was retired in #148.)
    """
    conversation_source = inspect.getsource(conversations.request_teacher_help)
    ask_source = inspect.getsource(help_requests.ask)

    assert "dispatch(record" in ask_source
    assert "plan_dispatch" in inspect.getsource(help_requests.dispatch)
    assert ask_source.index("admit_teacher_support_case") < ask_source.index("dispatch(record")
    # A conversation that already asked answers with its request before any
    # admission, so a repeat never spends a second case.
    assert ask_source.index("existing = get(") < ask_source.index("admit_teacher_support_case")
    # The usage row is written once asking has answered: for a case admitted
    # now, or for the request a repeat answers with, admitted before.
    assert conversation_source.index("help_requests.ask(") < conversation_source.index(
        "record_help_usage(outcome.record)"
    )


def test_a_counter_written_again_keeps_when_it_was_created(
    grants: dict[str, dict[str, object]],
) -> None:
    """Every admission used to rebuild the counter row and drop `created_at`."""
    grants["student-1"] = _grant("student-1")
    table = AtomicSupportTable()
    _admit(table, case_id="first", observed_at=NOW)
    [counter] = table.support_rows("teacher_support_counter")
    created = counter["created_at"]

    _admit(table, case_id="second", observed_at=NOW + timedelta(hours=1))

    [counter] = table.support_rows("teacher_support_counter")
    assert counter["admitted_cases"] == 2
    assert counter["created_at"] == created
    assert counter["updated_at"] == (NOW + timedelta(hours=1)).isoformat()


def test_a_counter_that_already_lost_created_at_still_admits(
    grants: dict[str, dict[str, object]],
) -> None:
    """Rows written before #245 have no `created_at`; they are read as they are."""
    grants["student-1"] = _grant("student-1")
    table = AtomicSupportTable()
    _admit(table, case_id="first")
    [key] = [
        key for key, item in table.items.items() if item.get("entity_type") == "teacher_support_counter"
    ]
    del table.items[key]["created_at"]

    assert _admit(table, case_id="second").disposition.value == "admitted"
    [counter] = table.support_rows("teacher_support_counter")
    assert counter["admitted_cases"] == 2
    assert "created_at" not in counter


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
    table = FakeTable()
    table.seed_active_account("student-1")
    db_table.install(table)
    monkeypatch.setattr(
        conversations,
        "active_conversation_generation",
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
        db_table,
        "transact",
        lambda *_args, **_kwargs: pytest.fail("denied durable case ran"),
    )
    monkeypatch.setattr(
        help_requests,
        "dispatch",
        lambda *_args, **_kwargs: pytest.fail("denied case was offered"),
    )
    monkeypatch.setattr(
        conversations.usage_ledger_service,
        "record_usage_event",
        lambda **_kwargs: pytest.fail("denied usage effect ran"),
    )

    with pytest.raises(help_requests.HelpRequestViolation) as denied:
        asyncio.run(
            conversations.request_teacher_help(
                body=conversations.TeacherHelpRequest(
                    conversationId="conversation-denied",
                    message="private request",
                ),
                authorized=authorized,
            )
        )

    assert denied.value.code == "teacher_support_not_included"
    assert denied.value.status_code == 403
    assert ("CONV#conversation-denied", "HELP") not in table.rows
    assert ("CONV#conversation-denied", "MSG#conversation-denied") not in table.rows
