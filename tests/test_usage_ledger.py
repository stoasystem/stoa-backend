from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.config import Settings
from stoa.deps import get_current_user
from stoa.routers import admin, parents
from stoa.services import usage_ledger_service
from stoa.db.repositories import usage_ledger_repo


class FakeTable:
    def __init__(self):
        self.items = {}

    def put_item(self, Item, ConditionExpression=None):
        key = (Item["PK"], Item["SK"])
        if ConditionExpression == "attribute_not_exists(PK)" and key in self.items:
            raise ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException", "Message": "duplicate"}},
                "PutItem",
            )
        self.items[key] = dict(Item)

    def get_item(self, Key):
        item = self.items.get((Key["PK"], Key["SK"]))
        return {"Item": dict(item)} if item else {}

    def query(self, **kwargs):
        pk = _condition_value(kwargs.get("KeyConditionExpression"), "PK")
        sk_prefix = _condition_value(kwargs.get("KeyConditionExpression"), "SK")
        items = [
            dict(item)
            for (item_pk, item_sk), item in self.items.items()
            if item_pk == pk and item_sk.startswith(sk_prefix or "")
        ]
        return {"Items": items[: kwargs.get("Limit", len(items))]}

    def update_item(self, Key, UpdateExpression, ExpressionAttributeValues, ExpressionAttributeNames=None):
        item = self.items.setdefault((Key["PK"], Key["SK"]), {"PK": Key["PK"], "SK": Key["SK"]})
        names = ExpressionAttributeNames or {}
        expression = UpdateExpression.removeprefix("SET ")
        for assignment in _split_assignments(expression):
            field_expr, value_expr = [part.strip() for part in assignment.split("=")]
            field = names.get(field_expr, field_expr)
            if value_expr.startswith("if_not_exists"):
                current = item.get(field)
                fallback = value_expr[value_expr.rfind(",") + 1 : value_expr.rfind(")")].strip()
                item[field] = current if current is not None else ExpressionAttributeValues[fallback]
            else:
                item[field] = ExpressionAttributeValues[value_expr]


def _condition_value(condition, key_name: str):
    if condition is None:
        return None
    for child in getattr(condition, "_values", ()):
        values = getattr(child, "_values", ())
        if len(values) == 2 and getattr(values[0], "name", None) == key_name:
            return values[1]
        nested = _condition_value(child, key_name)
        if nested is not None:
            return nested
    return None


def _split_assignments(expression: str) -> list[str]:
    assignments = []
    start = 0
    depth = 0
    for index, char in enumerate(expression):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            assignments.append(expression[start:index].strip())
            start = index + 1
    assignments.append(expression[start:].strip())
    return assignments


def _settings() -> Settings:
    return Settings(
        free_tier_daily_question_limit=2,
        standard_tier_daily_question_limit=30,
        premium_tier_daily_question_limit=100,
    )


def test_question_usage_event_is_privacy_safe_and_idempotent(monkeypatch):
    table = FakeTable()
    monkeypatch.setattr(usage_ledger_repo, "get_table", lambda: table)

    entitlement = {
        "effectivePlan": "premium",
        "source": "provider_billing",
        "parentId": "parent-1",
        "limits": {"dailyAiQuestionLimit": 100},
        "billingState": "active",
        "period": {"start": "2026-07-01", "end": "2026-08-01"},
    }

    created = usage_ledger_service.record_question_usage_event(
        student_id="student-1",
        question_id="question-1",
        quota_period="2026-07-03",
        idempotency_key="request-1",
        counter_key="USAGE#student-1/QUESTION#2026-07-03",
        counter_value=1,
        quantity=1,
        entitlement=entitlement,
        created_at="2026-07-03T12:00:00+00:00",
    )
    duplicate = usage_ledger_service.record_question_usage_event(
        student_id="student-1",
        question_id="question-1",
        quota_period="2026-07-03",
        idempotency_key="request-1",
        counter_key="USAGE#student-1/QUESTION#2026-07-03",
        counter_value=1,
        quantity=1,
        entitlement=entitlement,
        created_at="2026-07-03T12:00:00+00:00",
    )

    assert created["idempotency_status"] == "created"
    assert duplicate["idempotency_status"] == "duplicate"
    assert created["privacy"] == {
        "raw_content_stored": False,
        "raw_learning_content_stored": False,
        "private_artifact_keys_stored": False,
        "provider_payloads_stored": False,
        "auth_tokens_stored": False,
        "verification_codes_stored": False,
    }
    assert "content" not in created
    assert "image_s3_key" not in created
    assert created["entitlement_snapshot"]["effectivePlan"] == "premium"


def test_usage_action_taxonomy_covers_v5_11_actions_and_preserves_question_contract():
    definitions = {
        item["action"]: item
        for item in usage_ledger_service.list_usage_action_definitions()
    }

    assert definitions["question_submission"]["usage_type"] == "daily_question_submission"
    assert definitions["question_submission"]["quota_enforced"] is True
    assert definitions["question_submission"]["counter_prefix"] == "QUESTION"
    assert definitions["chat_message"]["quota_enforced"] is True
    assert definitions["chat_message"]["summary_group"] == "chat"
    assert definitions["hint_request"]["counter_prefix"] == "HINT"
    assert definitions["question_teacher_help_request"]["quota_enforced"] is False
    assert definitions["conversation_teacher_help_request"]["summary_group"] == "teacher_help"
    assert definitions["practice_teacher_help_request"]["summary_group"] == "teacher_help"
    assert definitions["practice_answer"]["summary_group"] == "practice"
    assert definitions["practice_lesson_completion"]["support_visible"] is True
    assert definitions["assignment_completed"]["summary_group"] == "assignments"
    assert definitions["reviewed_assignment_generation"]["summary_group"] == "generation"


def test_usage_idempotency_and_metadata_helpers_are_privacy_safe():
    assert (
        usage_ledger_service.build_usage_idempotency_key(
            action="hint_request",
            resource_id="challenge-1",
            qualifier="student-1",
        )
        == "hint_request:challenge-1:student-1"
    )
    assert (
        usage_ledger_service.build_usage_idempotency_key(
            action="chat_message",
            resource_id="message-1",
            request_key="request-123",
        )
        == "request-123"
    )

    safe = usage_ledger_service.safe_usage_metadata(
        {
            "subject": "math",
            "challenge_id": "challenge-1",
            "attempt_result": "incorrect",
            "prompt": "raw prompt must not be stored",
            "student_answer": "x = 3",
            "provider_payload": {"tokens": 100},
            "private_artifact_key": "s3://private/key",
            "unknown_field": "dropped",
            "status": "completed",
        }
    )

    assert safe == {
        "subject": "math",
        "challenge_id": "challenge-1",
        "attempt_result": "incorrect",
        "status": "completed",
    }

    try:
        usage_ledger_service.build_usage_idempotency_key(
            action="not_governed",
            resource_id="x",
        )
    except ValueError as exc:
        assert "Unsupported usage ledger action" in str(exc)
    else:
        raise AssertionError("unsupported usage action should fail closed")


def test_record_usage_event_is_taxonomy_gated_and_content_safe(monkeypatch):
    table = FakeTable()
    monkeypatch.setattr(usage_ledger_repo, "get_table", lambda: table)

    created = usage_ledger_service.record_usage_event(
        student_id="student-1",
        action="conversation_teacher_help_request",
        quota_period="2026-07-04",
        idempotency_key="conversation_teacher_help_request:conv-1:req-1",
        created_at="2026-07-04T10:00:00+00:00",
        request_correlation_id="req-1",
        metadata={
            "conversation_id": "conv-1",
            "request_id": "req-1",
            "subject": "math",
            "message": "raw teacher help message",
            "provider_payload": {"secret": True},
        },
    )
    duplicate = usage_ledger_service.record_usage_event(
        student_id="student-1",
        action="conversation_teacher_help_request",
        quota_period="2026-07-04",
        idempotency_key="conversation_teacher_help_request:conv-1:req-1",
        created_at="2026-07-04T10:00:00+00:00",
    )

    assert created["idempotency_status"] == "created"
    assert duplicate["idempotency_status"] == "duplicate"
    assert created["metadata"]["usage_type"] == "support_conversation_teacher_help_request"
    assert created["metadata"]["summary_group"] == "teacher_help"
    assert created["metadata"]["quota_enforced"] is False
    assert created["metadata"]["conversation_id"] == "conv-1"
    assert "message" not in created["metadata"]
    assert "provider_payload" not in created["metadata"]
    assert created["privacy"]["raw_content_stored"] is False


def test_reconciliation_reports_and_repairs_counter_mismatch(monkeypatch):
    table = FakeTable()
    monkeypatch.setattr(usage_ledger_repo, "get_table", lambda: table)

    for index in range(2):
        usage_ledger_service.record_question_usage_event(
            student_id="student-1",
            question_id=f"question-{index}",
            quota_period="2026-07-03",
            idempotency_key=f"request-{index}",
            counter_key="USAGE#student-1/QUESTION#2026-07-03",
            counter_value=index + 1,
            quantity=1,
            entitlement={"effectivePlan": "free", "limits": {"dailyAiQuestionLimit": 2}},
            created_at="2026-07-03T12:00:00+00:00",
        )

    preview = usage_ledger_service.reconcile_question_usage(
        student_id="student-1",
        day="2026-07-03",
    )
    repaired = usage_ledger_service.reconcile_question_usage(
        student_id="student-1",
        day="2026-07-03",
        repair=True,
    )

    assert preview["status"] == "counter-missing"
    assert preview["ledgerCount"] == 2
    assert repaired["status"] == "matched"
    assert repaired["counterCount"] == 2
    assert repaired["repairMode"] == "applied"


def test_parent_usage_summaries_use_active_child_bindings(monkeypatch):
    table = FakeTable()
    profiles = {
        "student-1": {
            "user_id": "student-1",
            "role": "student",
            "subscription_tier": "free",
            "parent_id": "parent-1",
            "parent_binding_status": "active",
        }
    }
    monkeypatch.setattr(usage_ledger_repo, "get_table", lambda: table)
    monkeypatch.setattr(usage_ledger_service.user_repo, "get_user", lambda user_id: profiles.get(user_id))
    monkeypatch.setattr(
        usage_ledger_service.user_repo,
        "list_parent_student_bindings",
        lambda parent_id: [
            {"parent_id": parent_id, "student_id": "student-1", "status": "active"},
            {"parent_id": parent_id, "student_id": "student-2", "status": "inactive"},
        ],
    )
    monkeypatch.setattr(
        usage_ledger_service.entitlement_service,
        "resolve_student_entitlement",
        lambda student_id, settings, student_profile=None: {
            "studentId": student_id,
            "parentId": "parent-1",
            "effectivePlan": "standard",
            "source": "provider_billing",
            "billingState": "active",
            "limits": {"dailyAiQuestionLimit": 30},
        },
    )
    table.items[("USAGE#student-1", "QUESTION#2026-07-03")] = {
        "PK": "USAGE#student-1",
        "SK": "QUESTION#2026-07-03",
        "count": 3,
    }

    summaries = usage_ledger_service.list_parent_usage_summaries(
        parent_id="parent-1",
        settings=_settings(),
        day="2026-07-03",
    )

    assert len(summaries) == 1
    assert summaries[0]["studentId"] == "student-1"
    assert summaries[0]["consumed"] == 3
    assert summaries[0]["limit"] == 30
    assert summaries[0]["remaining"] == 27
    assert summaries[0]["reconciliation"]["status"] == "ledger-missing"


def test_student_usage_summary_includes_multi_action_groups(monkeypatch):
    table = FakeTable()
    monkeypatch.setattr(usage_ledger_repo, "get_table", lambda: table)
    monkeypatch.setattr(usage_ledger_service.user_repo, "get_user", lambda user_id: {"user_id": user_id})
    monkeypatch.setattr(
        usage_ledger_service.entitlement_service,
        "resolve_student_entitlement",
        lambda student_id, settings, student_profile=None: {
            "studentId": student_id,
            "parentId": "parent-1",
            "effectivePlan": "premium",
            "source": "provider_billing",
            "billingState": "active",
            "limits": {"dailyAiQuestionLimit": 100},
        },
    )
    table.items[("USAGE#student-1", "QUESTION#2026-07-04")] = {
        "PK": "USAGE#student-1",
        "SK": "QUESTION#2026-07-04",
        "count": 1,
    }
    table.items[("USAGE#student-1", "CHAT#2026-07-04")] = {
        "PK": "USAGE#student-1",
        "SK": "CHAT#2026-07-04",
        "count": 1,
    }
    usage_ledger_service.record_question_usage_event(
        student_id="student-1",
        question_id="question-1",
        quota_period="2026-07-04",
        idempotency_key="question-1",
        counter_key="USAGE#student-1/QUESTION#2026-07-04",
        counter_value=1,
        quantity=1,
        entitlement={"effectivePlan": "premium", "limits": {"dailyAiQuestionLimit": 100}, "parentId": "parent-1"},
        created_at="2026-07-04T10:00:00+00:00",
    )
    usage_ledger_service.record_usage_event(
        student_id="student-1",
        action="chat_message",
        quota_period="2026-07-04",
        idempotency_key="chat-1",
        counter_key="USAGE#student-1/CHAT#2026-07-04",
        counter_value=1,
        created_at="2026-07-04T10:01:00+00:00",
        metadata={"conversation_id": "conv-1", "content": "drop me"},
    )
    usage_ledger_service.record_usage_event(
        student_id="student-1",
        action="practice_answer",
        quota_period="2026-07-04",
        idempotency_key="practice-1",
        created_at="2026-07-04T10:02:00+00:00",
        metadata={"challenge_id": "challenge-1", "student_answer": "drop me"},
    )

    summary = usage_ledger_service.build_student_usage_summary(
        student_id="student-1",
        settings=_settings(),
        day="2026-07-04",
    )

    actions = {item["action"]: item for item in summary["actions"]}
    groups = {item["group"]: item for item in summary["groups"]}
    assert summary["action"] == "question_submission"
    assert summary["consumed"] == 1
    assert summary["remaining"] == 99
    assert actions["question_submission"]["reconciliation"]["status"] == "matched"
    assert actions["chat_message"]["reconciliation"]["status"] == "matched"
    assert actions["practice_answer"]["reconciliation"]["status"] == "ledger-only"
    assert groups["chat"]["consumed"] == 1
    assert groups["practice"]["supportVisibleConsumed"] == 1
    assert summary["totals"]["supportVisibleConsumed"] >= 3
    assert summary["unreconciled"] is False


def test_non_question_reconciliation_is_read_only(monkeypatch):
    table = FakeTable()
    monkeypatch.setattr(usage_ledger_repo, "get_table", lambda: table)

    result = usage_ledger_service.reconcile_usage_action(
        student_id="student-1",
        day="2026-07-04",
        action="practice_answer",
        repair=True,
    )

    assert result["action"] == "practice_answer"
    assert result["counterKey"] is None
    assert result["status"] == "ledger-only"
    assert result["repairMode"] == "unsupported"


def test_parent_child_usage_endpoint_is_privacy_safe(monkeypatch):
    app = FastAPI()
    app.include_router(parents.router, prefix="/parents")
    app.dependency_overrides[get_current_user] = lambda: {"sub": "parent-1", "role": "parent"}
    monkeypatch.setattr(
        parents.user_repo,
        "get_user",
        lambda user_id: {
            "user_id": user_id,
            "role": "parent" if user_id == "parent-1" else "student",
            "parent_id": "parent-1",
            "parent_binding_status": "active",
        },
    )
    monkeypatch.setattr(
        parents.user_repo,
        "get_parent_student_binding",
        lambda parent_id, student_id: {
            "parent_id": parent_id,
            "student_id": student_id,
            "status": "active",
        },
    )
    monkeypatch.setattr(
        parents.usage_ledger_service,
        "build_student_usage_summary",
        lambda student_id, settings, day=None: {
            "studentId": student_id,
            "parentId": "parent-1",
            "quotaPeriod": day or "2026-07-03",
            "action": "question_submission",
            "consumed": 1,
            "limit": 30,
            "remaining": 29,
            "effectivePlan": "standard",
            "entitlementSource": "provider_billing",
            "billingState": "active",
            "reconciliation": {"status": "matched"},
            "actions": [{"action": "chat_message", "consumed": 1, "summaryGroup": "chat"}],
            "groups": [{"group": "chat", "consumed": 1, "actions": ["chat_message"]}],
            "totals": {"consumed": 2, "actionCount": 2},
            "partial": False,
            "stale": False,
            "unreconciled": False,
        },
    )

    response = TestClient(app).get("/parents/me/children/student-1/usage?day=2026-07-03")

    assert response.status_code == 200
    body = response.json()
    assert body["studentId"] == "student-1"
    assert body["remaining"] == 29
    assert body["actions"][0]["action"] == "chat_message"
    assert body["groups"][0]["group"] == "chat"
    assert body["totals"]["actionCount"] == 2
    assert "content" not in str(body)
    assert "image_s3_key" not in str(body)


def test_admin_usage_reconciliation_endpoint_previews_without_repair(monkeypatch):
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    app.dependency_overrides[get_current_user] = lambda: {"sub": "admin-1", "role": "admin"}
    calls = []
    monkeypatch.setattr(
        admin.usage_ledger_service,
        "reconcile_usage_action",
        lambda **kwargs: calls.append(kwargs)
        or {
            "studentId": kwargs["student_id"],
            "action": "question_submission",
            "quotaPeriod": kwargs["day"],
            "counterKey": f"USAGE#{kwargs['student_id']}/QUESTION#{kwargs['day']}",
            "counterCount": 2,
            "ledgerCount": 1,
            "eventCount": 1,
            "status": "count-mismatch",
            "repairMode": "preview",
            "repaired": False,
            "partial": True,
        },
    )

    response = TestClient(app).get(
        "/admin/usage/reconciliation",
        params={"student_id": "student-1", "day": "2026-07-03"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "count-mismatch"
    assert calls == [{"student_id": "student-1", "day": "2026-07-03", "action": "question_submission", "repair": False}]
