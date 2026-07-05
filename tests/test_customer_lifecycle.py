import pytest

from stoa.services import customer_lifecycle_service


def _fixture_account(**overrides):
    account = {
        "parent_id": "parent-1",
        "recipient_id": "parent-1",
        "role": "parent",
        "state_version": "state-1",
        "current_state": "parent_registered",
        "account_status": "active",
        "verification_state": "verified",
        "billing_status": "active",
        "quota_state": "available",
        "support_case_state": "none",
        "entitlement_status": "starter",
        "child_count": 1,
    }
    account.update(overrides)
    return account


def test_message_taxonomy_covers_required_lifecycle_events_and_privacy_contract():
    taxonomy = customer_lifecycle_service.message_taxonomy(provider_state="blocked")
    events = {row["event"] for row in taxonomy["events"]}
    assert {
        "onboarding_welcome",
        "email_verification_reminder",
        "payment_failed",
        "payment_recovered",
        "quota_warning",
        "subscription_state",
        "support_incident_update",
        "learning_progress_nudge",
        "re_engagement",
    }.issubset(events)
    for row in taxonomy["events"]:
        assert row["templateId"]
        assert row["preferenceGate"]
        assert row["providerDependency"]
        assert "prompt" in row["excludedFields"]
        assert "student_work" in row["excludedFields"]


def test_lifecycle_message_planning_is_idempotent_and_previewable():
    account = _fixture_account()
    first = customer_lifecycle_service.plan_lifecycle_message(
        event="onboarding_welcome",
        account=account,
        preferences={"account": True},
        provider_state="approved_fixture",
        template_approved=True,
        destination_approved=True,
        dry_run=True,
        request_id="req-1",
    )
    second = customer_lifecycle_service.plan_lifecycle_message(
        event="onboarding_welcome",
        account=account,
        preferences={"account": True},
        provider_state="approved_fixture",
        template_approved=True,
        destination_approved=True,
        dry_run=True,
        request_id="req-2",
    )
    assert first["state"] == "preview"
    assert first["idempotencyKey"] == second["idempotencyKey"]
    assert first["supportSafePayload"]["next_action"] == "complete child setup and first practice session"


def test_lifecycle_message_gates_preferences_templates_provider_and_stale_state():
    message = customer_lifecycle_service.plan_lifecycle_message(
        event="payment_failed",
        account=_fixture_account(current_state="parent_registered", attempt_count=3),
        preferences={"billing": False},
        provider_state="blocked",
        template_approved=False,
        destination_approved=False,
        dry_run=False,
    )
    assert message["state"] == "refused"
    assert set(message["refusalReasons"]) >= {
        "recipient_opted_out",
        "provider_not_approved",
        "template_not_approved",
        "destination_not_approved",
        "stale_or_mismatched_state",
    }
    assert message["retry"]["retryable"] is False


def test_parent_and_admin_surfaces_do_not_expose_internal_provider_payloads():
    messages = [
        customer_lifecycle_service.plan_lifecycle_message(
            event="learning_progress_nudge",
            account=_fixture_account(current_state="progress_available"),
            preferences={"learning_updates": True},
            provider_state="approved_fixture",
        )
    ]
    parent = customer_lifecycle_service.parent_message_history(messages, parent_id="parent-1")
    admin = customer_lifecycle_service.admin_message_history(messages)
    assert parent["messages"][0]["nextAction"] == "review weekly progress"
    assert "refusalReasons" not in parent["messages"][0]
    assert admin["messages"][0]["providerState"] == "approved_fixture"
    assert "provider_payload" not in str(parent["messages"]).lower()
    assert "provider_payload" not in str(admin["messages"]).lower()


def test_provider_activation_smoke_records_refusal_states_and_safe_evidence():
    smoke = customer_lifecycle_service.provider_activation_smoke(
        provider_approved=False,
        credential_configured=False,
        template_approved=False,
        destination_approved=False,
        opt_out=True,
        provider_failure=True,
        request_id="smoke-1",
    )
    assert smoke["state"] == "blocked"
    assert set(smoke["refusalReasons"]) == {
        "missing_provider_approval",
        "missing_provider_credential",
        "missing_template_approval",
        "unapproved_destination",
        "recipient_opted_out",
        "provider_failure",
    }
    assert smoke["evidence"]["rawProviderPayloadIncluded"] is False


def test_release_gate_evidence_covers_journeys_and_blocks_raw_private_fields():
    evidence = customer_lifecycle_service.release_gate_evidence()
    assert evidence["releaseState"] == "customer-lifecycle-ready-local-contracts"
    assert "support_incident_update" in evidence["journeyEvents"]
    assert evidence["templateInventoryCount"] >= 8
    assert evidence["providerBlockedState"]["state"] == "blocked"
    with pytest.raises(ValueError):
        customer_lifecycle_service.assert_support_safe({"provider_payload": {"secret": "x"}})
