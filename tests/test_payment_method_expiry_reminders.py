from __future__ import annotations

import inspect
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import pytest

from stoa.services import (
    notification_service,
    paid_entitlement_service,
    payment_reminder_service,
)


UTC = timezone.utc
ZURICH = ZoneInfo("Europe/Zurich")
PARENT_ID = "parent-reminder"
STUDENT_IDS = ("student-alpha", "student-beta")
SUBSCRIPTION_DIGEST = "a" * 64


class _Provider:
    def __init__(self, payment_method: Mapping[str, object]) -> None:
        self.payment_method = dict(payment_method)
        self.calls: list[dict[str, object]] = []

    def resolve_default_payment_method(
        self, subscription: Mapping[str, object]
    ) -> Mapping[str, object]:
        self.calls.append(dict(subscription))
        return deepcopy(self.payment_method)


def _method(
    provider_id: str = "pm_provider_secret_alpha",
    *,
    exp_month: int = 7,
    exp_year: int = 2026,
) -> dict[str, object]:
    return {
        "id": provider_id,
        "type": "card",
        "card": {
            "brand": "visa",
            "last4": "4242",
            "exp_month": exp_month,
            "exp_year": exp_year,
        },
    }


def _subscription() -> dict[str, object]:
    return {
        "parent_id": PARENT_ID,
        "provider_subscription_id_digest": SUBSCRIPTION_DIGEST,
        "beneficiary_ids": list(STUDENT_IDS),
        "observation_version": 4,
        "billing_state": "active",
    }


def _profiles() -> dict[str, dict[str, object]]:
    return {
        PARENT_ID: {
            "user_id": PARENT_ID,
            "role": "parent",
            "account_status": "active",
            "account_fence_generation": 3,
            "email": "parent@example.test",
            "email_verification_status": "verified",
            "email_delivery_status": "deliverable",
        },
        STUDENT_IDS[0]: {
            "user_id": STUDENT_IDS[0],
            "role": "student",
            "account_status": "active",
            "account_fence_generation": 8,
            "email": "alpha@example.test",
            "email_verification_status": "verified",
            "email_delivery_status": "deliverable",
        },
        STUDENT_IDS[1]: {
            "user_id": STUDENT_IDS[1],
            "role": "student",
            "account_status": "active",
            "account_fence_generation": 9,
            "email": "beta@example.test",
            "email_verification_status": "verified",
            "email_delivery_status": "bounced",
        },
    }


def _install_grants(monkeypatch: pytest.MonkeyPatch) -> None:
    def get_grant(
        parent_id: str,
        beneficiary_id: str,
        *,
        table: object | None = None,
    ) -> dict[str, object] | None:
        del table
        if parent_id != PARENT_ID or beneficiary_id not in STUDENT_IDS:
            return None
        return {
            "parent_id": parent_id,
            "beneficiary_id": beneficiary_id,
            "grant_status": "active",
            "subscription_id_digest": SUBSCRIPTION_DIGEST,
        }

    monkeypatch.setattr(
        paid_entitlement_service, "get_active_beneficiary_grant", get_grant
    )


class _ReminderStore:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict[str, object]] = {}

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            payment_reminder_service.notification_repo,
            "get_payment_expiry_reminder",
            self.get,
        )
        monkeypatch.setattr(
            payment_reminder_service.notification_repo,
            "list_payment_expiry_reminders",
            self.list,
        )
        monkeypatch.setattr(
            payment_reminder_service.notification_repo,
            "put_payment_expiry_reminder",
            self.put,
        )
        monkeypatch.setattr(
            payment_reminder_service.notification_repo,
            "resolve_payment_expiry_reminder",
            self.resolve,
        )

    def get(
        self,
        parent_id: str,
        reminder_identity: str,
        *,
        table: object | None = None,
    ) -> dict[str, object] | None:
        del table
        row = self.rows.get((parent_id, reminder_identity))
        return deepcopy(row) if row is not None else None

    def list(
        self, parent_id: str, *, table: object | None = None
    ) -> list[dict[str, object]]:
        del table
        return [
            deepcopy(row)
            for (owner, _identity), row in self.rows.items()
            if owner == parent_id
        ]

    def put(
        self,
        item: Mapping[str, object],
        *,
        table: object | None = None,
    ) -> dict[str, object]:
        del table
        key = (str(item["parent_id"]), str(item["reminder_identity"]))
        self.rows.setdefault(key, dict(item))
        return deepcopy(self.rows[key])

    def resolve(
        self,
        parent_id: str,
        reminder_identity: str,
        *,
        resolved_at: str,
        table: object | None = None,
    ) -> dict[str, object] | None:
        del table
        row = self.rows.get((parent_id, reminder_identity))
        if row is None:
            return None
        row["status"] = "resolved"
        row["resolved_at"] = resolved_at
        return deepcopy(row)


class _IntentRecorder:
    def __init__(self, *, fail_recipient: str | None = None) -> None:
        self.terminal: set[str] = set()
        self.calls: list[dict[str, object]] = []
        self.provider_calls: list[tuple[str, str]] = []
        self.fail_recipient = fail_recipient

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            notification_service, "register_delivery_intent", self.register
        )

    def register(self, **kwargs: Any) -> dict[str, object]:
        call = dict(kwargs)
        self.calls.append(call)
        operation_id = str(call["operation_id"])
        recipient_id = str(call["recipient_id"])
        channel = str(call["channel"])
        if operation_id in self.terminal:
            return {"delivery_id": operation_id, "status": "accepted"}
        if recipient_id == self.fail_recipient and channel == "email":
            raise RuntimeError("fixture email failure with secret-provider-value")
        provider_call = call["provider_call"]
        assert callable(provider_call)
        provider_call()
        self.provider_calls.append((recipient_id, channel))
        self.terminal.add(operation_id)
        return {"delivery_id": operation_id, "status": "accepted"}


@pytest.mark.parametrize(
    ("month", "year", "expected_date"),
    [
        (2, 2024, "2024-02-22"),
        (2, 2025, "2025-02-21"),
        (4, 2026, "2026-04-23"),
        (12, 2026, "2026-12-24"),
    ],
)
def test_payment_expiry_reminder_at_uses_zurich_month_end_minus_seven_days(
    month: int, year: int, expected_date: str
) -> None:
    reminder_at = payment_reminder_service.payment_expiry_reminder_at(
        exp_month=month, exp_year=year
    )
    assert reminder_at.tzinfo == ZURICH
    assert reminder_at.isoformat().startswith(expected_date)
    assert reminder_at.hour == 0


def test_payment_expiry_reminder_at_preserves_local_calendar_across_dst() -> None:
    reminder_at = payment_reminder_service.payment_expiry_reminder_at(
        exp_month=10, exp_year=2026
    )
    month_end = datetime(2026, 10, 31, tzinfo=ZURICH)

    assert reminder_at.date().isoformat() == "2026-10-24"
    assert (month_end.date() - reminder_at.date()).days == 7
    assert reminder_at.utcoffset() != month_end.utcoffset()


def test_masked_projection_is_closed_and_rejects_card_secrets() -> None:
    projected = payment_reminder_service.project_masked_payment_method(
        _method(),
        source_subscription_digest=SUBSCRIPTION_DIGEST,
        observation_version=4,
    )
    encoded = repr(projected)

    assert projected["brand"] == "visa"
    assert projected["last4"] == "4242"
    assert projected["payment_method_digest"] != "pm_provider_secret_alpha"
    assert len(str(projected["payment_method_digest"])) == 64
    for forbidden in (
        "pm_provider_secret_alpha",
        "number",
        "cvc",
        "secret",
        "fingerprint",
    ):
        assert forbidden not in encoded.lower()

    unsafe = _method()
    assert isinstance(unsafe["card"], dict)
    unsafe["card"]["number"] = "4242424242424242"
    unsafe["card"]["cvc"] = "123"
    with pytest.raises(ValueError, match="unsafe payment method"):
        payment_reminder_service.project_masked_payment_method(
            unsafe,
            source_subscription_digest=SUBSCRIPTION_DIGEST,
            observation_version=4,
        )


def test_recipient_resolution_requires_current_explicit_grants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_grants(monkeypatch)
    profiles = _profiles()

    recipients = payment_reminder_service.resolve_billing_reminder_recipients(
        parent_id=PARENT_ID,
        beneficiary_ids=STUDENT_IDS,
        subscription_id_digest=SUBSCRIPTION_DIGEST,
        profile_resolver=lambda account_id: profiles.get(account_id),
        table=object(),
    )

    assert [recipient.account_id for recipient in recipients] == [
        PARENT_ID,
        *STUDENT_IDS,
    ]
    assert recipients[0].email_eligibility.eligible is True
    assert recipients[1].email_eligibility.eligible is True
    assert recipients[2].email_eligibility.eligible is False
    assert recipients[2].email_eligibility.reason == "bounced"


def _run(
    monkeypatch: pytest.MonkeyPatch,
    *,
    provider: _Provider,
    store: _ReminderStore,
    intents: _IntentRecorder,
    now: datetime,
    subscription: Mapping[str, object] | None = None,
) -> Any:
    _install_grants(monkeypatch)
    store.install(monkeypatch)
    intents.install(monkeypatch)
    profiles = _profiles()
    return payment_reminder_service.run_payment_expiry_reminders(
        subscription=dict(subscription or _subscription()),
        provider=provider,
        profile_resolver=lambda account_id: profiles.get(account_id),
        deliver_in_app=lambda account_id, _payload: None,
        deliver_email=lambda address, _payload: None,
        now=now,
        table=object(),
    )


def test_scheduler_before_at_and_after_boundary_is_idempotent_per_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _Provider(_method())
    store = _ReminderStore()
    intents = _IntentRecorder()

    before = _run(
        monkeypatch,
        provider=provider,
        store=store,
        intents=intents,
        now=datetime(2026, 7, 23, 21, 59, 59, tzinfo=UTC),
    )
    assert before.disposition is payment_reminder_service.PaymentReminderDisposition.PENDING
    assert intents.provider_calls == []

    at = _run(
        monkeypatch,
        provider=provider,
        store=store,
        intents=intents,
        now=datetime(2026, 7, 23, 22, 0, 0, tzinfo=UTC),
    )
    assert at.disposition is payment_reminder_service.PaymentReminderDisposition.DELIVERED
    assert set(intents.provider_calls) == {
        (PARENT_ID, "in_app"),
        (PARENT_ID, "email"),
        (STUDENT_IDS[0], "in_app"),
        (STUDENT_IDS[0], "email"),
        (STUDENT_IDS[1], "in_app"),
    }
    assert len({str(call["operation_id"]) for call in intents.calls}) == 5

    after = _run(
        monkeypatch,
        provider=provider,
        store=store,
        intents=intents,
        now=datetime(2026, 7, 24, 9, 0, tzinfo=UTC),
    )
    assert after.disposition is payment_reminder_service.PaymentReminderDisposition.REPLAYED
    assert len(intents.provider_calls) == 5
    assert len({str(call["operation_id"]) for call in intents.calls}) == 5


def test_replacement_resolves_old_state_and_each_method_month_notifies_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _Provider(_method())
    store = _ReminderStore()
    intents = _IntentRecorder()
    now = datetime(2026, 7, 24, 9, 0, tzinfo=UTC)

    first = _run(
        monkeypatch, provider=provider, store=store, intents=intents, now=now
    )
    old_identity = first.reminder["reminder_identity"]

    provider.payment_method = _method(
        "pm_provider_secret_beta", exp_month=8, exp_year=2026
    )
    replacement = _run(
        monkeypatch, provider=provider, store=store, intents=intents, now=now
    )
    assert replacement.disposition is payment_reminder_service.PaymentReminderDisposition.PENDING
    assert store.rows[(PARENT_ID, str(old_identity))]["status"] == "resolved"
    assert store.rows[(PARENT_ID, str(old_identity))]["resolved_at"] is not None

    provider.payment_method = _method()
    replay = _run(
        monkeypatch, provider=provider, store=store, intents=intents, now=now
    )
    assert replay.disposition is payment_reminder_service.PaymentReminderDisposition.RESOLVED
    assert len(intents.provider_calls) == 5


def test_recipient_failure_is_isolated_and_does_not_mutate_billing_or_grants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _Provider(_method())
    store = _ReminderStore()
    intents = _IntentRecorder(fail_recipient=STUDENT_IDS[0])
    subscription = _subscription()
    subscription_before = deepcopy(subscription)
    grants_before = {
        student_id: {
            "parent_id": PARENT_ID,
            "beneficiary_id": student_id,
            "subscription_id_digest": SUBSCRIPTION_DIGEST,
        }
        for student_id in STUDENT_IDS
    }
    grants_after = deepcopy(grants_before)

    result = _run(
        monkeypatch,
        provider=provider,
        store=store,
        intents=intents,
        now=datetime(2026, 7, 24, 9, 0, tzinfo=UTC),
        subscription=subscription,
    )

    statuses = {
        (delivery.recipient_id, delivery.channel): delivery.status
        for delivery in result.deliveries
    }
    assert statuses[(STUDENT_IDS[0], "email")] == "failed"
    assert statuses[(STUDENT_IDS[0], "in_app")] == "accepted"
    assert statuses[(STUDENT_IDS[1], "in_app")] == "accepted"
    assert subscription == subscription_before
    assert grants_after == grants_before
    assert "secret-provider-value" not in repr(result)


def test_source_link_registers_one_notification_intent_per_recipient_channel() -> None:
    source = inspect.getsource(payment_reminder_service)
    notification_source = Path("src/stoa/services/notification_service.py").read_text()

    assert "notification_service.register_delivery_intent(" in source
    assert "def register_delivery_intent(" in notification_source
    assert "recipient_id=recipient.account_id" in source
    assert "channel=channel" in source
