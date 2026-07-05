from stoa.config import Settings
from stoa.services import entitlement_service


class FakeTable:
    def __init__(self):
        self.items = {}

    def put_item(self, Item):
        self.items[(Item["PK"], Item["SK"])] = dict(Item)

    def get_item(self, Key):
        item = self.items.get((Key["PK"], Key["SK"]))
        return {"Item": dict(item)} if item else {}


def _settings() -> Settings:
    return Settings(
        free_tier_daily_question_limit=2,
        free_tier_daily_chat_message_limit=8,
        free_tier_daily_hint_limit=2,
        standard_tier_daily_question_limit=30,
        standard_tier_daily_chat_message_limit=80,
        standard_tier_daily_hint_limit=30,
        premium_tier_daily_question_limit=100,
        premium_tier_daily_chat_message_limit=200,
        premium_tier_daily_hint_limit=80,
    )


def _install(monkeypatch):
    table = FakeTable()
    profiles = {
        "parent-1": {"user_id": "parent-1", "role": "parent", "subscription_tier": "free"},
        "student-1": {
            "user_id": "student-1",
            "role": "student",
            "subscription_tier": "free",
            "parent_id": "parent-1",
            "parent_binding_status": "active",
        },
    }

    def get_user(user_id):
        return profiles.get(user_id)

    def get_parent_student_binding(parent_id, student_id):
        return table.items.get((f"USER#{parent_id}", f"CHILD#{student_id}"))

    monkeypatch.setattr(entitlement_service, "get_table", lambda: table)
    monkeypatch.setattr(entitlement_service.user_repo, "get_user", get_user)
    monkeypatch.setattr(
        entitlement_service.user_repo,
        "get_parent_student_binding",
        get_parent_student_binding,
    )
    table.put_item(
        Item={
            "PK": "USER#parent-1",
            "SK": "CHILD#student-1",
            "entity_type": "parent_student_binding",
            "parent_id": "parent-1",
            "student_id": "student-1",
            "status": "active",
        }
    )
    return table, profiles


def test_active_parent_billing_grants_linked_student_paid_entitlement(monkeypatch):
    table, profiles = _install(monkeypatch)
    table.put_item(
        Item={
            "PK": "SUBSCRIPTION_BILLING#parent-1",
            "SK": "SUMMARY",
            "billing_status": "active",
            "subscription_tier": "premium",
            "current_period_start": "2026-07-01T00:00:00+00:00",
            "current_period_end": "2026-08-01T00:00:00+00:00",
        }
    )

    entitlement = entitlement_service.resolve_student_entitlement(
        "student-1",
        settings=_settings(),
        student_profile=profiles["student-1"],
    )

    assert entitlement["effectivePlan"] == "premium"
    assert entitlement["source"] == "provider_billing"
    assert entitlement["limits"]["dailyAiQuestionLimit"] == 100
    assert entitlement["limits"]["dailyChatMessageLimit"] == 200
    assert entitlement["limits"]["dailyHintLimit"] == 80
    assert entitlement["blockingReason"] is None


def test_pending_checkout_does_not_grant_paid_parent_access(monkeypatch):
    table, profiles = _install(monkeypatch)
    table.put_item(
        Item={
            "PK": "SUBSCRIPTION_BILLING#parent-1",
            "SK": "SUMMARY",
            "billing_status": "checkout_pending",
            "requested_tier": "premium",
            "subscription_tier": "free",
        }
    )

    entitlement = entitlement_service.resolve_student_entitlement(
        "student-1",
        settings=_settings(),
        student_profile=profiles["student-1"],
    )

    assert entitlement["effectivePlan"] == "free"
    assert entitlement["limits"]["dailyAiQuestionLimit"] == 2
    assert entitlement["limits"]["dailyChatMessageLimit"] == 8
    assert entitlement["limits"]["dailyHintLimit"] == 2
    assert entitlement["blockingReason"] == "checkout_pending"


def test_manual_override_takes_precedence(monkeypatch):
    table, profiles = _install(monkeypatch)
    table.put_item(
        Item={
            "PK": "SUBSCRIPTION_BILLING#parent-1",
            "SK": "SUMMARY",
            "billing_status": "manual_override",
            "subscription_tier": "standard",
            "manual_override_source": "subreq-1",
        }
    )

    entitlement = entitlement_service.resolve_student_entitlement(
        "student-1",
        settings=_settings(),
        student_profile=profiles["student-1"],
    )

    assert entitlement["effectivePlan"] == "standard"
    assert entitlement["source"] == "manual_override"
    assert entitlement["limits"]["dailyAiQuestionLimit"] == 30
    assert entitlement["limits"]["dailyChatMessageLimit"] == 80
    assert entitlement["limits"]["dailyHintLimit"] == 30
