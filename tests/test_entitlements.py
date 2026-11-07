from stoa.config import Settings
from stoa.services import entitlement_service


class FakeTable:
    def __init__(self):
        self.items = {}

    def put_item(self, Item):
        self.items[(Item["PK"], Item["SK"])] = dict(Item)

    def get_item(self, Key, **_kwargs):
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


def _install(monkeypatch, link_rows):
    table = FakeTable()
    profiles = {
        "parent-1": {
            "user_id": "parent-1",
            "role": "parent",
            "account_status": "active",
            "version": 11,
            "subscription_tier": "free_trial",
        },
        "student-1": {
            "user_id": "student-1",
            "role": "student",
            "account_status": "active",
            "version": 21,
            "subscription_tier": "free_trial",
        },
    }

    def get_user(user_id, **_kwargs):
        return profiles.get(user_id)

    monkeypatch.setattr(entitlement_service, "get_table", lambda: table)
    monkeypatch.setattr(entitlement_service.user_repo, "get_user", get_user)
    monkeypatch.setattr(
        entitlement_service.paid_entitlement_service.account_deletion_repo,
        "require_active_account_fence",
        lambda user_id, *, table: {"generation": 1 if user_id == "parent-1" else 2},
    )
    # The relationship the billing rests on: a current link, both sides active.
    link_rows.link("parent-1", "student-1")
    return table, profiles


def test_active_parent_billing_grants_linked_student_paid_entitlement(monkeypatch, link_rows):
    table, profiles = _install(monkeypatch, link_rows)
    table.put_item(
        Item={
            "PK": "SUBSCRIPTION_BILLING#parent-1",
            "SK": "SUMMARY",
            "billing_status": "active",
            "subscription_tier": "family",
            "current_period_start": "2026-07-01T00:00:00+00:00",
            "current_period_end": "2026-08-01T00:00:00+00:00",
        }
    )
    table.put_item(
        Item={
            "PK": "PAID_GRANT#parent-1",
            "SK": "BENEFICIARY#student-1",
            "entity_type": "beneficiary_grant",
            "schema_version": "paid_beneficiary_grant.v1",
            "parent_id": "parent-1",
            "beneficiary_id": "student-1",
            "grant_status": "active",
            "grant_version": 7,
            "plan_id": "family",
            "plan_version": 2,
            "allowance_version": 2,
            "subscription_id_digest": "a" * 64,
            "activation_version": 7,
        }
    )

    entitlement = entitlement_service.resolve_student_entitlement(
        "student-1",
        settings=_settings(),
        student_profile=profiles["student-1"],
    )

    assert entitlement["effectivePlan"] == "family"
    assert entitlement["source"] == "paid_beneficiary_grant"
    assert entitlement["limits"]["dailyAiQuestionLimit"] == 100
    assert entitlement["limits"]["dailyChatMessageLimit"] == 200
    assert entitlement["limits"]["dailyHintLimit"] == 80
    assert entitlement["blockingReason"] is None


def test_pending_checkout_does_not_grant_paid_parent_access(monkeypatch, link_rows):
    table, profiles = _install(monkeypatch, link_rows)
    table.put_item(
        Item={
            "PK": "SUBSCRIPTION_BILLING#parent-1",
            "SK": "SUMMARY",
            "billing_status": "checkout_pending",
            "requested_tier": "family",
            "subscription_tier": "free_trial",
        }
    )

    entitlement = entitlement_service.resolve_student_entitlement(
        "student-1",
        settings=_settings(),
        student_profile=profiles["student-1"],
    )

    assert entitlement["effectivePlan"] == "free_trial"
    assert entitlement["limits"]["dailyAiQuestionLimit"] == 2
    assert entitlement["limits"]["dailyChatMessageLimit"] == 8
    assert entitlement["limits"]["dailyHintLimit"] == 2
    assert entitlement["blockingReason"] == "checkout_pending"


def test_manual_override_no_longer_grants_anything(monkeypatch, link_rows):
    """Card 007 froze the admin override; it was the one bypass with no billing
    fact behind it. Pinned as the frozen state rather than deleted, because a
    legacy `manual_override` row is still sitting in the table."""
    table, profiles = _install(monkeypatch, link_rows)
    table.put_item(
        Item={
            "PK": "SUBSCRIPTION_BILLING#parent-1",
            "SK": "SUMMARY",
            "billing_status": "manual_override",
            "subscription_tier": "student",
            "manual_override_source": "subreq-1",
        }
    )

    entitlement = entitlement_service.resolve_student_entitlement(
        "student-1",
        settings=_settings(),
        student_profile=profiles["student-1"],
    )

    assert entitlement["effectivePlan"] == "free_trial"
    assert entitlement["source"] == "free_tier"
    assert entitlement["blockingReason"] == "billing_frozen"
    assert entitlement["limits"]["dailyAiQuestionLimit"] == 2


def test_manual_override_takes_precedence_once_unfrozen(monkeypatch, link_rows):
    """The behaviour was switched off, not deleted: this is what unfreezing restores."""
    monkeypatch.setattr(entitlement_service, "MANUAL_BILLING_OVERRIDE_ENABLED", True)
    table, profiles = _install(monkeypatch, link_rows)
    table.put_item(
        Item={
            "PK": "SUBSCRIPTION_BILLING#parent-1",
            "SK": "SUMMARY",
            "billing_status": "manual_override",
            "subscription_tier": "student",
            "manual_override_source": "subreq-1",
        }
    )

    entitlement = entitlement_service.resolve_student_entitlement(
        "student-1",
        settings=_settings(),
        student_profile=profiles["student-1"],
    )

    assert entitlement["effectivePlan"] == "student"
    assert entitlement["source"] == "manual_override"
    assert entitlement["limits"]["dailyAiQuestionLimit"] == 30
    assert entitlement["limits"]["dailyChatMessageLimit"] == 80
    assert entitlement["limits"]["dailyHintLimit"] == 30


def test_legacy_binding_rows_and_profile_pointer_alone_buy_a_student_nothing(
    monkeypatch, link_rows
):
    """#287: a paid parent reaches a student only through a current link.

    The retired binding rows and a profile's `parent_id` are what used to
    authorize this; with no link they name no parent of record, so the parent's
    grant and active billing do not reach the student.
    """
    table, profiles = _install(monkeypatch, link_rows)
    link_rows.unlink("parent-1", "student-1")
    profiles["student-1"].update(parent_id="parent-1", parent_binding_status="active")
    for pk, sk, entity in (
        ("USER#parent-1", "CHILD#student-1", "parent_student_binding"),
        ("USER#student-1", "PARENT#parent-1", "student_parent_binding"),
    ):
        table.put_item(
            Item={
                "PK": pk,
                "SK": sk,
                "entity_type": entity,
                "parent_id": "parent-1",
                "student_id": "student-1",
                "relationship": "child",
                "status": "active",
                "version": 31,
            }
        )
    table.put_item(
        Item={
            "PK": "SUBSCRIPTION_BILLING#parent-1",
            "SK": "SUMMARY",
            "billing_status": "active",
            "subscription_tier": "family",
            "current_period_start": "2026-07-01T00:00:00+00:00",
            "current_period_end": "2026-08-01T00:00:00+00:00",
        }
    )
    table.put_item(
        Item={
            "PK": "PAID_GRANT#parent-1",
            "SK": "BENEFICIARY#student-1",
            "entity_type": "beneficiary_grant",
            "schema_version": "paid_beneficiary_grant.v1",
            "parent_id": "parent-1",
            "beneficiary_id": "student-1",
            "grant_status": "active",
            "grant_version": 7,
            "plan_id": "family",
            "plan_version": 2,
            "allowance_version": 2,
            "subscription_id_digest": "a" * 64,
            "activation_version": 7,
        }
    )

    entitlement = entitlement_service.resolve_student_entitlement(
        "student-1",
        settings=_settings(),
        student_profile=profiles["student-1"],
    )

    assert entitlement["effectivePlan"] == "free_trial"
    assert entitlement["source"] != "paid_beneficiary_grant"
    assert entitlement["limits"]["dailyAiQuestionLimit"] == 2
