"""A None in an index key attribute is left out of a plain write, and a refused
ledger write is not a duplicate.

On 2026-07-09 the usage ledger's `put_item` carried `parent_id: None`; the resource
interface sent it as NULL and the table refused it five times: "Type mismatch for
Index Key parent_id Expected: S Actual: NULL IndexName: GSI-ParentId". The
transaction serializers leave such an attribute out, and now so do the plain writes
of the two repositories that still had one: the usage ledger (a student with no
parent, `POST /questions/{id}/request-teacher`) and curriculum drafts
(`review_state` is unset until review).

Two more things the same incident showed, stoasystem/stoa-backend#52:

- `put_usage_event` answered every `AccountDeletionConflict` as "already written",
  and the account seam reports every refusal that way. Only an event that is in the
  table now is a duplicate.
- `request-teacher` writes its ledger row after the case is admitted and dispatched,
  and a retry that found the case replayed returned before writing it. The retry now
  owes the row, and once it is there every later retry is a duplicate.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from audit_helpers import MemoryAuthorizationAuditSink
from fakes.dynamodb import FakeTable
from stoa.config import Settings, get_settings
from stoa.db.repositories import account_deletion_repo, curriculum_ops_repo, usage_ledger_repo
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.models.billing import BillingPlanId
from stoa.routers import conversations, questions
from stoa.services import (
    curriculum_ops_service,
    teacher_support_allowance_service,
    usage_ledger_service,
)
from test_curriculum_ops import DRAFT_UNIT, _draft_payload, _operator_user
from test_conversations import _client as _conversation_client
from test_questions import _actor


NOW = "2026-09-26T12:00:00+00:00"


def _ledger_rows(table: FakeTable) -> list[dict[str, object]]:
    return [row for (pk, _sk), row in table.rows.items() if pk.startswith("USAGE_LEDGER#")]


# -- the plain write ------------------------------------------------------------------


def test_a_help_request_for_a_student_with_no_parent_is_stored_without_the_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = FakeTable()
    monkeypatch.setattr(usage_ledger_repo, "get_table", lambda: table)

    recorded = usage_ledger_service.record_usage_event(
        student_id="student-1",
        action=usage_ledger_service.QUESTION_TEACHER_HELP_ACTION,
        quota_period="2026-09-26",
        idempotency_key="question_teacher_help_request:question-1",
        created_at=NOW,
        request_correlation_id="question-1",
        metadata={"question_id": "question-1"},
    )

    assert recorded["idempotency_status"] == "created"
    assert recorded["parent_id"] is None
    (row,) = _ledger_rows(table)
    assert "parent_id" not in row
    assert row["student_id"] == "student-1"
    assert row["action"] == usage_ledger_service.QUESTION_TEACHER_HELP_ACTION


def test_a_fenced_private_event_is_stored_without_its_none_and_replays_as_a_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = FakeTable()
    table.seed_active_account("student-1")
    monkeypatch.setattr(usage_ledger_repo, "get_table", lambda: table)

    def record() -> str:
        return str(
            usage_ledger_service.record_usage_event(
                student_id="student-1",
                action="hint_request",
                quota_period="2026-09-26",
                idempotency_key="hint_request:challenge-1:student-1",
                created_at=NOW,
            )["idempotency_status"]
        )

    assert record() == "created"
    assert record() == "duplicate"
    (row,) = _ledger_rows(table)
    assert "parent_id" not in row
    assert row["account_fence_generation"] == 1


def test_a_curriculum_draft_is_stored_without_a_review_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = FakeTable()
    table.seed({"PK": "PRACTICE", "SK": f"UNIT#{DRAFT_UNIT['unit_id']}", **DRAFT_UNIT})
    monkeypatch.setattr(curriculum_ops_repo, "get_table", lambda: table)

    created = curriculum_ops_service.create_lesson_draft(
        _draft_payload(), _operator_user(curriculum_ops_service.AUTHOR_CAPABILITY)
    )

    assert created["reviewState"] is None
    version = table.rows[
        (f"CURRICULUM_VERSION#{created['publicLessonId']}", f"VERSION#{created['versionId']}")
    ]
    assert "review_state" not in version
    assert version["state"] == "draft"


# -- a refusal is not a duplicate ------------------------------------------------------


def _fenced_event() -> dict[str, object]:
    return {
        "PK": "USAGE_LEDGER#student-1",
        "SK": "EVENT#hint_request#2026-09-26#challenge-1",
        "student_id": "student-1",
        "action": "hint_request",
    }


def test_a_fence_that_moved_is_a_conflict_not_a_duplicate() -> None:
    table = FakeTable()
    table.seed_active_account("student-1", generation=2)

    with pytest.raises(account_deletion_repo.AccountDeletionConflict, match="conditional"):
        usage_ledger_repo.put_usage_event(_fenced_event(), account_fence_generation=1, table=table)

    assert _ledger_rows(table) == []


def test_a_refused_request_is_a_conflict_not_a_duplicate() -> None:
    class ThrottledTable(FakeTable):
        def transact_account_deletion(self, operations: list[dict[str, object]]) -> None:
            raise account_deletion_repo.AccountDeletionConflict(
                "account lifecycle dependency unavailable"
            )

    table = ThrottledTable()
    table.seed_active_account("student-1")

    with pytest.raises(account_deletion_repo.AccountDeletionConflict, match="dependency"):
        usage_ledger_repo.put_usage_event(_fenced_event(), account_fence_generation=1, table=table)


def test_only_an_event_already_in_the_table_is_a_duplicate() -> None:
    table = FakeTable()
    table.seed_active_account("student-1")

    assert usage_ledger_repo.put_usage_event(_fenced_event(), account_fence_generation=1, table=table)
    assert not usage_ledger_repo.put_usage_event(
        _fenced_event(), account_fence_generation=1, table=table
    )
    assert len(_ledger_rows(table)) == 1
    # The read that decides "duplicate" must see the write that refused ours, which
    # may be milliseconds old: an eventually consistent read could miss it and turn a
    # real duplicate into a raised conflict.
    reads = [request for operation, request in table.requests if operation == "get_item"]
    assert reads == [{"Key": {"PK": _fenced_event()["PK"], "SK": _fenced_event()["SK"]}, "ConsistentRead": True}]


# -- the retry owes the ledger row -----------------------------------------------------


def _settings() -> Settings:
    return Settings(free_tier_daily_question_limit=2)


def _question_client() -> TestClient:
    app = FastAPI()
    app.include_router(questions.router, prefix="/questions")
    app.dependency_overrides[get_settings] = _settings
    app.dependency_overrides[get_actor] = lambda: _actor()
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app, raise_server_exceptions=False)


def _admission(admitted_at: datetime, case_id: str = "question-1") -> teacher_support_allowance_service.TeacherSupportCaseAdmission:
    return teacher_support_allowance_service.TeacherSupportCaseAdmission(
        support_case_id=case_id,
        support_scope_id="scope-1",
        beneficiary_id="student-1",
        plan_id=BillingPlanId.FAMILY,
        week_identity="2026-W39",
        window_start=admitted_at - timedelta(days=1),
        window_end=admitted_at + timedelta(days=6),
        post_admission_count=1,
        limit=2,
        admitted_at=admitted_at,
    )


def _escalation_scaffold(
    monkeypatch: pytest.MonkeyPatch, ledger: FakeTable
) -> tuple[TestClient, dict[str, object], list[str]]:
    """`request-teacher` with admission, mutation and dispatch stubbed, the ledger real.

    Admission is granted once and replayed after, and the replay hands back the
    admission the first call persisted - `admitted_at` included - as the service
    does. The question row keeps the state the mutation gave it.
    """
    monkeypatch.setattr(usage_ledger_repo, "get_table", lambda: ledger)
    question: dict[str, object] = {
        "question_id": "question-1",
        "student_id": "student-1",
        "subject": "math",
        "status": "ai_answered",
        "version": 1,
    }
    dispatches: list[str] = []
    service = questions.teacher_support_allowance_service
    persisted: dict[str, object] = {}

    def admit(*, persist_case, observed_at, **_kwargs):
        if persist_case(()):
            persisted["admission"] = _admission(observed_at)
            return service.TeacherSupportAdmissionResult(
                service.TeacherSupportAdmissionDisposition.ADMITTED, persisted["admission"]
            )
        return service.TeacherSupportAdmissionResult(
            service.TeacherSupportAdmissionDisposition.REPLAYED, persisted.get("admission")
        )

    monkeypatch.setattr(service, "admit_teacher_support_case", admit)
    monkeypatch.setattr(questions.question_repo, "get_question", lambda question_id: dict(question))

    def mutate(item: dict[str, object], *, status: str, extra_attrs: dict[str, object], **_kwargs: object):
        question.update({**extra_attrs, "status": status, "version": int(item["version"]) + 1})
        return questions.question_repo.QuestionMutationResult(
            questions.question_repo.QuestionMutationDisposition.APPLIED, "question-1", dict(question)
        )

    monkeypatch.setattr(questions.question_repo, "mutate_question", mutate)
    monkeypatch.setattr(questions.notify_service, "enqueue_teacher_request", lambda **_kwargs: None)
    monkeypatch.setattr(
        questions.notification_service, "emit_teacher_requested", lambda **_kwargs: None
    )
    monkeypatch.setattr(
        questions.teacher_dispatch_service,
        "dispatch_question",
        lambda question_id, **_kwargs: dispatches.append(question_id) or {"status": "deferred"},
    )
    return _question_client(), question, dispatches


def _refuse_put_once(monkeypatch: pytest.MonkeyPatch, table: FakeTable) -> None:
    refusals = {"left": 1}
    real_put_item = table.put_item

    def put_item_refused_once(**kwargs: object) -> dict[str, object]:
        if refusals["left"]:
            refusals["left"] -= 1
            raise ClientError(
                {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "slow"}},
                "PutItem",
            )
        return real_put_item(**kwargs)

    monkeypatch.setattr(table, "put_item", put_item_refused_once)


def test_a_retry_after_a_failed_ledger_write_records_exactly_one_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First attempt: admitted, dispatched, ledger refused. Retries: replayed, one row."""
    ledger = FakeTable()
    client, question, dispatches = _escalation_scaffold(monkeypatch, ledger)
    _refuse_put_once(monkeypatch, ledger)

    first = client.post("/questions/question-1/request-teacher")
    assert first.status_code == 500
    assert question["status"] == "escalated"
    assert dispatches == ["question-1"]
    assert _ledger_rows(ledger) == []

    second = client.post("/questions/question-1/request-teacher")
    assert second.status_code == 202
    assert second.json()["dispatch"] == {"questionId": "question-1", "status": "replayed"}
    assert dispatches == ["question-1"]
    (row,) = _ledger_rows(ledger)
    assert row["action"] == usage_ledger_service.QUESTION_TEACHER_HELP_ACTION
    assert row["request_correlation_id"] == "question-1"
    assert row["metadata"]["question_id"] == "question-1"
    assert "parent_id" not in row

    third = client.post("/questions/question-1/request-teacher")
    assert third.status_code == 202
    assert dispatches == ["question-1"]
    assert len(_ledger_rows(ledger)) == 1


def test_a_retry_on_a_later_day_keys_the_row_by_the_admission_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The period in the key is the admission's, so a replay tomorrow is still a duplicate."""
    import time_machine

    ledger = FakeTable()
    client, question, _dispatches = _escalation_scaffold(monkeypatch, ledger)
    _refuse_put_once(monkeypatch, ledger)

    with time_machine.travel("2026-09-26T23:30:00+00:00", tick=False):
        assert client.post("/questions/question-1/request-teacher").status_code == 500
    with time_machine.travel("2026-09-27T09:00:00+00:00", tick=False):
        assert client.post("/questions/question-1/request-teacher").status_code == 202
        assert client.post("/questions/question-1/request-teacher").status_code == 202

    (row,) = _ledger_rows(ledger)
    assert row["quota_period"] == "2026-09-26"
    assert str(row["created_at"]).startswith("2026-09-26T23:30:00")
    assert str(question["teacher_requested_at"]).startswith("2026-09-26T23:30:00")


def test_a_replay_from_a_stale_question_snapshot_is_keyed_by_the_persisted_admission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The snapshot this request authorized against was read before another request
    admitted the case, so it has no `teacher_requested_at`; the day comes from the
    admission the service persisted, not from the retry."""
    import time_machine

    ledger = FakeTable()
    client, question, dispatches = _escalation_scaffold(monkeypatch, ledger)
    admitted_at = datetime(2026, 9, 26, 23, 59, 59, tzinfo=timezone.utc)
    service = questions.teacher_support_allowance_service
    monkeypatch.setattr(
        service,
        "admit_teacher_support_case",
        lambda **_kwargs: service.TeacherSupportAdmissionResult(
            service.TeacherSupportAdmissionDisposition.REPLAYED, _admission(admitted_at)
        ),
    )
    question.update({"status": "escalated"})  # admitted elsewhere; no teacher_requested_at

    with time_machine.travel("2026-09-27T09:00:00+00:00", tick=False):
        response = client.post("/questions/question-1/request-teacher")

    assert response.status_code == 202
    assert dispatches == []
    (row,) = _ledger_rows(ledger)
    assert row["quota_period"] == "2026-09-26"
    assert str(row["created_at"]).startswith("2026-09-26T23:59:59")


def test_the_first_attempt_still_records_the_event_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """The control: with nothing refused, one call is one row, and a replay adds none."""
    ledger = FakeTable()
    client, _question, dispatches = _escalation_scaffold(monkeypatch, ledger)

    assert client.post("/questions/question-1/request-teacher").status_code == 202
    assert client.post("/questions/question-1/request-teacher").status_code == 202

    assert dispatches == ["question-1"]
    assert len(_ledger_rows(ledger)) == 1
    assert datetime.fromisoformat(str(_ledger_rows(ledger)[0]["created_at"])).tzinfo is timezone.utc


# -- the conversation lane has the same debt -------------------------------------------


def test_a_repeat_conversation_help_request_after_a_failed_ledger_write_records_one_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The escalation lands on the conversation in the admission's transaction; the
    ledger row is written after dispatch, fenced. A refusal there leaves the row
    missing, and a repeat request - answered from the conversation's escalation -
    owes it, keyed by that escalation's request and day."""
    table = FakeTable()
    table.seed_active_account("student-1")
    table.seed(
        {
            "PK": "CONV#conv-1",
            "SK": "CONV",
            "entity_type": "conversation",
            "conversation_id": "conv-1",
            "student_id": "student-1",
            "owner_id": "student-1",
            "account_fence_generation": 1,
            "subject": "physics",
            "grade": "Sek1",
            "status": "active",
            "created_at": NOW,
            "updated_at": NOW,
        }
    )
    monkeypatch.setattr(conversations, "get_table", lambda: table)
    monkeypatch.setattr(usage_ledger_repo, "get_table", lambda: table)
    service = conversations.teacher_support_allowance_service
    monkeypatch.setattr(
        service,
        "admit_teacher_support_case",
        lambda *, persist_case, **_kwargs: service.TeacherSupportAdmissionResult(
            service.TeacherSupportAdmissionDisposition.ADMITTED
            if persist_case(())
            else service.TeacherSupportAdmissionDisposition.REPLAYED
        ),
    )
    dispatches: list[str] = []
    monkeypatch.setattr(
        conversations,
        "_dispatch_escalated_conversation",
        lambda **kwargs: dispatches.append(str(kwargs["request_id"])) or ("pending", None),
    )
    monkeypatch.setattr(conversations.user_repo, "get_user", lambda *_args, **_kwargs: None)
    refusals = {"left": 1}
    real_seam = table.transact_account_deletion

    def seam_refused_once(operations: list[dict[str, object]]) -> None:
        # The escalation itself goes through this seam too; only the ledger's
        # Put is refused, once, as a throttle would.
        writes_ledger = any(
            str(operation.get("Put", {}).get("Item", {}).get("PK", "")).startswith("USAGE_LEDGER#")
            for operation in operations
        )
        if writes_ledger and refusals["left"]:
            refusals["left"] -= 1
            raise account_deletion_repo.AccountDeletionConflict(
                "account lifecycle dependency unavailable"
            )
        real_seam(operations)

    monkeypatch.setattr(table, "transact_account_deletion", seam_refused_once)
    client = _conversation_client(conversations.teacher_help_router, "/teacher-help")
    body = {"conversationId": "conv-1", "message": "please help"}

    with pytest.raises(account_deletion_repo.AccountDeletionConflict):
        client.post("/teacher-help/request", json=body)
    escalation_request_id = table.rows[("CONV#conv-1", "CONV")]["escalation_request_id"]
    assert dispatches == [escalation_request_id]
    assert _ledger_rows(table) == []

    second = client.post("/teacher-help/request", json=body)
    assert second.status_code == 200
    assert second.json()["requestId"] == escalation_request_id
    assert dispatches == [escalation_request_id]
    (row,) = _ledger_rows(table)
    assert row["action"] == usage_ledger_service.CONVERSATION_TEACHER_HELP_ACTION
    assert row["request_correlation_id"] == escalation_request_id
    assert row["account_fence_generation"] == 1
    assert "parent_id" not in row

    third = client.post("/teacher-help/request", json=body)
    assert third.status_code == 200
    assert len(_ledger_rows(table)) == 1


def _conversation_replay_scaffold(
    monkeypatch: pytest.MonkeyPatch, *, marker: str | None
) -> tuple[TestClient, FakeTable]:
    """A replayed admission whose first read of the conversation raced the marker.

    `_get_conversation` answers without the marker, so the handler does not take the
    repeat path; admission replays; the table row carries `marker` (or not).
    """
    table = FakeTable()
    table.seed_active_account("student-1")
    row: dict[str, object] = {
        "PK": "CONV#conv-1",
        "SK": "CONV",
        "entity_type": "conversation",
        "conversation_id": "conv-1",
        "student_id": "student-1",
        "owner_id": "student-1",
        "account_fence_generation": 1,
        "subject": "physics",
        "grade": "Sek1",
        "status": "active",
        "created_at": NOW,
        "updated_at": NOW,
    }
    if marker is not None:
        row.update(
            {
                "escalated": True,
                "escalation_request_id": marker,
                "escalation_status": "pending",
                "escalated_at": "2026-09-26T23:59:59+00:00",
            }
        )
    table.seed(row)
    monkeypatch.setattr(conversations, "get_table", lambda: table)
    monkeypatch.setattr(usage_ledger_repo, "get_table", lambda: table)
    stale = {key: value for key, value in row.items() if not key.startswith("escalat")}
    monkeypatch.setattr(conversations, "_get_conversation", lambda _conv_id: dict(stale))
    service = conversations.teacher_support_allowance_service
    monkeypatch.setattr(
        service,
        "admit_teacher_support_case",
        lambda **_kwargs: service.TeacherSupportAdmissionResult(
            service.TeacherSupportAdmissionDisposition.REPLAYED,
            _admission(datetime(2026, 9, 26, 23, 59, 59, tzinfo=timezone.utc), "conv-1"),
        ),
    )
    monkeypatch.setattr(
        conversations, "_dispatch_escalated_conversation", lambda **_kwargs: pytest.fail("dispatched")
    )
    monkeypatch.setattr(conversations.user_repo, "get_user", lambda *_args, **_kwargs: None)
    return _conversation_client(conversations.teacher_help_router, "/teacher-help"), table


def test_a_replayed_conversation_admission_reads_the_marker_consistently_and_owes_the_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, table = _conversation_replay_scaffold(monkeypatch, marker="req-first")

    response = client.post(
        "/teacher-help/request", json={"conversationId": "conv-1", "message": "again"}
    )

    assert response.status_code == 200
    assert response.json()["requestId"] == "req-first"
    (row,) = _ledger_rows(table)
    assert row["request_correlation_id"] == "req-first"
    assert row["quota_period"] == "2026-09-26"
    reads = [request for operation, request in table.requests if operation == "get_item"]
    assert {"Key": {"PK": "CONV#conv-1", "SK": "CONV"}, "ConsistentRead": True} in reads


def test_a_replayed_conversation_admission_without_a_marker_asks_for_a_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No marker even on a consistent read: nothing to answer with, nothing to key by."""
    client, table = _conversation_replay_scaffold(monkeypatch, marker=None)

    response = client.post(
        "/teacher-help/request", json={"conversationId": "conv-1", "message": "again"}
    )

    assert response.status_code == 503
    assert response.json()["detail"]["action"] == "retry_same_case"
    assert _ledger_rows(table) == []
