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

from datetime import datetime, timezone

from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from audit_helpers import MemoryAuthorizationAuditSink
from fakes.dynamodb import FakeTable
from stoa.config import Settings, get_settings
from stoa.db.repositories import account_deletion_repo, curriculum_ops_repo, usage_ledger_repo
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.routers import questions
from stoa.services import curriculum_ops_service, usage_ledger_service
from test_curriculum_ops import _draft_payload, _operator_user
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


# -- the retry owes the ledger row -----------------------------------------------------


def _settings() -> Settings:
    return Settings(free_tier_daily_question_limit=2)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(questions.router, prefix="/questions")
    app.dependency_overrides[get_settings] = _settings
    app.dependency_overrides[get_actor] = lambda: _actor()
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app, raise_server_exceptions=False)


def test_a_retry_after_a_failed_ledger_write_records_exactly_one_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First attempt: admitted, dispatched, ledger refused. Retries: replayed, one row."""
    ledger = FakeTable()
    monkeypatch.setattr(usage_ledger_repo, "get_table", lambda: ledger)
    question = {
        "question_id": "question-1",
        "student_id": "student-1",
        "subject": "math",
        "status": "ai_answered",
        "version": 1,
    }
    dispatches: list[str] = []
    refusals = {"left": 1}
    real_put_item = ledger.put_item

    def put_item_refused_once(**kwargs: object) -> dict[str, object]:
        if refusals["left"]:
            refusals["left"] -= 1
            raise ClientError(
                {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "slow"}},
                "PutItem",
            )
        return real_put_item(**kwargs)

    monkeypatch.setattr(ledger, "put_item", put_item_refused_once)
    monkeypatch.setattr(
        questions.teacher_support_allowance_service,
        "admit_teacher_support_case",
        lambda *, persist_case, **_kwargs: questions.teacher_support_allowance_service.TeacherSupportAdmissionResult(
            questions.teacher_support_allowance_service.TeacherSupportAdmissionDisposition.ADMITTED
            if persist_case(())
            else questions.teacher_support_allowance_service.TeacherSupportAdmissionDisposition.REPLAYED
        ),
    )
    monkeypatch.setattr(questions.question_repo, "get_question", lambda question_id: dict(question))

    def mutate(item: dict[str, object], *, status: str, extra_attrs: dict[str, object], **_kwargs: object):
        question.update({**extra_attrs, "status": status, "version": int(item["version"]) + 1})
        return questions.question_repo.QuestionMutationResult(
            questions.question_repo.QuestionMutationDisposition.APPLIED,
            "question-1",
            dict(question),
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
    client = _client()

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


def test_the_first_attempt_still_records_the_event_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """The control: with nothing refused, one call is one row, and a replay adds none."""
    ledger = FakeTable()
    monkeypatch.setattr(usage_ledger_repo, "get_table", lambda: ledger)
    question = {
        "question_id": "question-1",
        "student_id": "student-1",
        "subject": "math",
        "status": "ai_answered",
        "version": 1,
    }
    monkeypatch.setattr(
        questions.teacher_support_allowance_service,
        "admit_teacher_support_case",
        lambda *, persist_case, **_kwargs: questions.teacher_support_allowance_service.TeacherSupportAdmissionResult(
            questions.teacher_support_allowance_service.TeacherSupportAdmissionDisposition.ADMITTED
            if persist_case(())
            else questions.teacher_support_allowance_service.TeacherSupportAdmissionDisposition.REPLAYED
        ),
    )
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
        questions.teacher_dispatch_service, "dispatch_question", lambda *_a, **_k: {"status": "deferred"}
    )
    client = _client()

    assert client.post("/questions/question-1/request-teacher").status_code == 202
    assert client.post("/questions/question-1/request-teacher").status_code == 202

    assert len(_ledger_rows(ledger)) == 1
    assert datetime.fromisoformat(str(_ledger_rows(ledger)[0]["created_at"])).tzinfo is timezone.utc
