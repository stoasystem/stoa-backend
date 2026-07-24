from __future__ import annotations

import hashlib
import hmac
import inspect
import json
import time
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi import HTTPException

from stoa.config import Settings
from stoa.db.repositories import billing_fact_repo
from stoa.models.billing import BillingFact, BillingFactKind
from stoa.routers import billing as billing_router
from stoa.services import subscription_service


SECRET = "whsec_plan476_signed_fixture"
NOW_EPOCH = 1_784_899_200
NOW_ISO = datetime.fromtimestamp(NOW_EPOCH, tz=timezone.utc).isoformat()


def _settings() -> Settings:
    return Settings(
        environment="test",
        stripe_api_key="sk_test_plan476",
        stripe_webhook_secret=SECRET,
        stripe_student_price_id="price_test_student_v1",
        stripe_teacher_supported_price_id="price_test_teacher_v1",
        stripe_family_price_id="price_test_family_v1",
    )


def _signed_payload(event: dict[str, Any], *, timestamp: int = NOW_EPOCH) -> tuple[bytes, str]:
    payload = json.dumps(event, separators=(",", ":")).encode()
    signature = hmac.new(
        SECRET.encode(),
        f"{timestamp}.".encode() + payload,
        hashlib.sha256,
    ).hexdigest()
    return payload, f"t={timestamp},v1={signature}"


def _command() -> dict[str, object]:
    return {
        "PK": "CHECKOUT_COMMAND#checkout-command-1",
        "SK": "COMMAND",
        "entity_type": "checkout_command",
        "schema_version": "checkout_command.v1",
        "command_id": "checkout-command-1",
        "parent_id": "parent-1",
        "checkout_ref": "co_abcdefghijklmnopqrstuvwxyzABCDEFGH",
        "provider_session_id": "cs_test_plan476",
        "command_state": "provider_session_open",
        "command_version": 7,
        "plan_id": "student",
        "beneficiary_ids": ["student-1"],
        "price_id": "price_test_student_v1",
        "plan_version": 3,
        "environment": "test",
    }


def _session() -> dict[str, object]:
    return {
        "id": "cs_test_plan476",
        "object": "checkout.session",
        "livemode": False,
        "client_reference_id": "co_abcdefghijklmnopqrstuvwxyzABCDEFGH",
        "metadata": {
            "stoa_checkout_ref": "co_abcdefghijklmnopqrstuvwxyzABCDEFGH",
        },
        "customer": "cus_test_plan476",
        "subscription": "sub_test_plan476",
        "invoice": "in_test_plan476",
    }


def _invoice(*, basil: bool = False) -> dict[str, object]:
    value: dict[str, object] = {
        "id": "in_test_plan476",
        "object": "invoice",
        "livemode": False,
        "paid": True,
        "status": "paid",
        "customer": "cus_test_plan476",
    }
    if basil:
        value["parent"] = {
            "type": "subscription_details",
            "subscription_details": {"subscription": "sub_test_plan476"},
        }
    else:
        value["subscription"] = "sub_test_plan476"
    return value


def _subscription(*, status: str = "active") -> dict[str, object]:
    return {
        "id": "sub_test_plan476",
        "object": "subscription",
        "livemode": False,
        "status": status,
        "customer": "cus_test_plan476",
        "metadata": {
            "stoa_checkout_ref": "co_abcdefghijklmnopqrstuvwxyzABCDEFGH",
        },
        "items": {
            "data": [
                {
                    "price": {"id": "price_test_student_v1"},
                    "quantity": 1,
                }
            ]
        },
    }


def _event(
    event_id: str,
    event_type: str,
    provider_object: dict[str, object],
    *,
    created: int = NOW_EPOCH,
    api_version: str = "2025-03-31.basil",
) -> dict[str, object]:
    return {
        "id": event_id,
        "type": event_type,
        "created": created,
        "livemode": False,
        "api_version": api_version,
        "data": {"object": provider_object},
    }


class FakeProvider:
    def __init__(self) -> None:
        self.session = _session()
        self.invoice = _invoice(basil=True)
        self.subscription = _subscription()
        self.calls: list[tuple[str, str]] = []

    def retrieve_checkout_session(self, provider_session_id: str) -> dict[str, object]:
        self.calls.append(("session", provider_session_id))
        return dict(self.session)

    def retrieve_invoice(self, provider_invoice_id: str) -> dict[str, object]:
        self.calls.append(("invoice", provider_invoice_id))
        return dict(self.invoice)

    def retrieve_subscription(self, provider_subscription_id: str) -> dict[str, object]:
        self.calls.append(("subscription", provider_subscription_id))
        return dict(self.subscription)


class FakePersistence:
    def __init__(self) -> None:
        self.event_ids: set[str] = set()
        self.semantic_ids: set[tuple[str, str]] = set()
        self.facts: dict[BillingFactKind, BillingFact] = {}
        self.activation_count = 0
        self.bound_command: dict[str, object] | None = None
        self.mutation_count = 0

    def register_provider_event(self, **kwargs: object) -> billing_fact_repo.BillingEventResult:
        self.mutation_count += 1
        event_id = str(kwargs["provider_event_id"])
        semantic = (str(kwargs["event_type"]), str(kwargs["provider_object_id"]))
        if event_id in self.event_ids:
            disposition = billing_fact_repo.BillingEventDisposition.EVENT_DUPLICATE
        elif semantic in self.semantic_ids:
            self.event_ids.add(event_id)
            disposition = billing_fact_repo.BillingEventDisposition.SEMANTIC_DUPLICATE
        else:
            self.event_ids.add(event_id)
            self.semantic_ids.add(semantic)
            disposition = billing_fact_repo.BillingEventDisposition.REGISTERED
        return billing_fact_repo.BillingEventResult(disposition)

    def bind_provider_identity(
        self,
        command: dict[str, object],
        *,
        provider_customer_id_digest: str,
        provider_subscription_id_digest: str,
        expected_initial_invoice_id_digest: str,
        now_iso: str,
    ) -> dict[str, object] | None:
        del now_iso
        self.mutation_count += 1
        candidate = {
            **command,
            "provider_customer_id_digest": provider_customer_id_digest,
            "provider_subscription_id_digest": provider_subscription_id_digest,
            "expected_initial_invoice_id_digest": expected_initial_invoice_id_digest,
            "command_state": "reconciling",
            "command_version": int(command["command_version"]) + 1,
        }
        if self.bound_command is None:
            self.bound_command = candidate
        elif any(
            self.bound_command[key] != candidate[key]
            for key in (
                "provider_customer_id_digest",
                "provider_subscription_id_digest",
                "expected_initial_invoice_id_digest",
            )
        ):
            return None
        return dict(self.bound_command)

    def record_provider_fact(
        self,
        fact: BillingFact,
    ) -> billing_fact_repo.FactRecordResult:
        self.mutation_count += 1
        current = self.facts.get(fact.kind)
        if current is None:
            disposition = billing_fact_repo.FactRecordDisposition.CREATED
            self.facts[fact.kind] = fact
        elif current.fact_version < fact.fact_version:
            disposition = billing_fact_repo.FactRecordDisposition.ADVANCED
            self.facts[fact.kind] = fact
        elif current == fact:
            disposition = billing_fact_repo.FactRecordDisposition.DUPLICATE
        else:
            disposition = billing_fact_repo.FactRecordDisposition.STALE
        return billing_fact_repo.FactRecordResult(disposition, self.facts.get(fact.kind))

    def load_activation_facts(self, command_id: str) -> tuple[BillingFact, ...]:
        assert command_id == "checkout-command-1"
        return tuple(self.facts.values())

    def commit_paid_activation(
        self,
        request: billing_fact_repo.PaidActivationRequest,
        *,
        billing_projection: dict[str, object],
        grant_items: list[dict[str, object]],
        allowance_item: dict[str, object],
    ) -> billing_fact_repo.ActivationResult:
        self.mutation_count += 1
        assert request.provider_livemode is False
        assert request.paid_invoice_fact_id
        assert request.active_subscription_fact_id
        assert billing_projection["plan_id"] == "student"
        assert [grant["beneficiary_id"] for grant in grant_items] == ["student-1"]
        assert allowance_item["allowance_version"] == request.allowance_version
        if self.activation_count:
            return billing_fact_repo.ActivationResult(
                billing_fact_repo.ActivationDisposition.ALREADY_COMMITTED
            )
        self.activation_count += 1
        return billing_fact_repo.ActivationResult(
            billing_fact_repo.ActivationDisposition.COMMITTED
        )


def test_router_source_binds_raw_official_verification_to_fact_registration() -> None:
    source = inspect.getsource(billing_router.handle_stripe_webhook)
    assert "await request.body()" in source
    assert "construct_event" in source
    assert "billing_fact_repo.register_provider_event" in source
    assert source.index("construct_event") < source.index("register_provider_event")


def test_official_signature_verification_rejects_unsigned_wrong_mutated_and_old(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(time, "time", lambda: NOW_EPOCH)
    event = _event("evt_signed", "invoice.paid", _invoice(basil=True))
    payload, signature = _signed_payload(event)
    verified = subscription_service.construct_event(
        payload=payload,
        signature_header=signature,
        settings=_settings(),
    )
    assert verified["id"] == "evt_signed"

    for candidate_payload, candidate_signature in (
        (payload, None),
        (payload, signature.replace(signature[-1], "0")),
        (payload + b" ", signature),
        _signed_payload(event, timestamp=NOW_EPOCH - 301),
    ):
        with pytest.raises(HTTPException) as error:
            subscription_service.construct_event(
                payload=candidate_payload,
                signature_header=candidate_signature,
                settings=_settings(),
            )
        assert error.value.status_code == 400


def test_invoice_subscription_extractor_supports_legacy_and_basil_and_fails_closed() -> None:
    assert (
        subscription_service.extract_invoice_subscription_id(
            _invoice(),
            api_version="2024-12-18.acacia",
        )
        == "sub_test_plan476"
    )
    assert (
        subscription_service.extract_invoice_subscription_id(
            _invoice(basil=True),
            api_version="2025-03-31.basil",
        )
        == "sub_test_plan476"
    )
    malformed = _invoice(basil=True)
    malformed["subscription"] = "sub_other"
    assert (
        subscription_service.extract_invoice_subscription_id(
            malformed,
            api_version="2025-03-31.basil",
        )
        is None
    )


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda session, invoice, subscription: session.update(livemode=True), "live_object"),
        (lambda session, invoice, subscription: invoice.update(customer="cus_other"), "customer_mismatch"),
        (
            lambda session, invoice, subscription: subscription["items"]["data"][0]["price"].update(
                id="price_other"
            ),
            "price_mismatch",
        ),
        (lambda session, invoice, subscription: subscription.update(status="past_due"), "subscription_inactive"),
        (lambda session, invoice, subscription: invoice.update(paid=False), "invoice_unpaid"),
    ],
)
def test_activation_predicate_fails_closed_on_provider_mismatch(
    mutation: Any,
    reason: str,
) -> None:
    session = _session()
    invoice = _invoice(basil=True)
    subscription = _subscription()
    mutation(session, invoice, subscription)
    result = subscription_service.activation_predicate(
        command=_command(),
        session=session,
        invoice=invoice,
        subscription=subscription,
        api_version="2025-03-31.basil",
    )
    assert result.accepted is False
    assert result.reason == reason


@pytest.mark.parametrize(
    "first_type",
    ["invoice.paid", "customer.subscription.updated"],
)
def test_signed_fact_orders_and_twenty_duplicates_activate_exactly_once(
    first_type: str,
) -> None:
    provider = FakeProvider()
    persistence = FakePersistence()
    first_object = (
        _invoice(basil=True)
        if first_type == "invoice.paid"
        else _subscription()
    )
    event = _event("evt_first", first_type, first_object)

    first = subscription_service.process_signed_billing_event(
        event=event,
        settings=_settings(),
        provider=provider,
        persistence=persistence,
        command=_command(),
    )
    assert first["signatureVerified"] is True
    assert first["activationDisposition"] == "committed"

    for _ in range(20):
        replay = subscription_service.process_signed_billing_event(
            event=event,
            settings=_settings(),
            provider=provider,
            persistence=persistence,
            command=_command(),
        )
        assert replay["factDisposition"] == "event_duplicate"
        assert replay["activationDisposition"] == "already_committed"
    assert persistence.activation_count == 1


def test_different_event_ids_equal_timestamps_and_stale_snapshot_do_not_regress() -> None:
    provider = FakeProvider()
    persistence = FakePersistence()
    first = _event("evt_a", "customer.subscription.updated", _subscription())
    second = _event("evt_b", "customer.subscription.updated", _subscription())
    stale = _event(
        "evt_c",
        "customer.subscription.updated",
        _subscription(status="canceled"),
        created=NOW_EPOCH - 60,
    )

    for event in (first, second, stale):
        result = subscription_service.process_signed_billing_event(
            event=event,
            settings=_settings(),
            provider=provider,
            persistence=persistence,
            command=_command(),
        )
        assert result["activationDisposition"] in {"committed", "already_committed"}
    assert persistence.activation_count == 1
    assert persistence.facts[BillingFactKind.SUBSCRIPTION_ACTIVE].fact_version == NOW_EPOCH


def test_checkout_completion_alone_remains_confirming() -> None:
    provider = FakeProvider()
    persistence = FakePersistence()
    result = subscription_service.process_signed_billing_event(
        event=_event(
            "evt_checkout",
            "checkout.session.completed",
            _session(),
        ),
        settings=_settings(),
        provider=provider,
        persistence=persistence,
        command=_command(),
    )
    assert result["reconciliationDisposition"] == "confirming"
    assert result["activationDisposition"] == "not_attempted"
    assert persistence.activation_count == 0


def test_live_event_and_provider_mismatch_mutate_no_grant_or_projection() -> None:
    provider = FakeProvider()
    persistence = FakePersistence()
    live_event = _event("evt_live", "invoice.paid", _invoice(basil=True))
    live_event["livemode"] = True
    result = subscription_service.process_signed_billing_event(
        event=live_event,
        settings=_settings(),
        provider=provider,
        persistence=persistence,
        command=_command(),
    )
    assert result["factDisposition"] == "refused_live"
    assert persistence.mutation_count == 0

    provider.session["customer"] = "cus_other"
    mismatch = subscription_service.process_signed_billing_event(
        event=_event("evt_mismatch", "invoice.paid", _invoice(basil=True)),
        settings=_settings(),
        provider=provider,
        persistence=persistence,
        command=_command(),
    )
    assert mismatch["activationDisposition"] == "predicate_refused"
    assert persistence.activation_count == 0


def test_response_and_source_do_not_expose_private_provider_material() -> None:
    provider = FakeProvider()
    persistence = FakePersistence()
    result = subscription_service.process_signed_billing_event(
        event=_event("evt_private_canary_123456", "invoice.paid", _invoice(basil=True)),
        settings=_settings(),
        provider=provider,
        persistence=persistence,
        command=_command(),
    )
    rendered = json.dumps(result, sort_keys=True)
    for forbidden in (
        SECRET,
        "evt_private_canary_123456",
        "cus_test_plan476",
        "sub_test_plan476",
        "in_test_plan476",
        "cs_test_plan476",
        "checkout.stripe.com",
        "4242424242424242",
        "cvc",
    ):
        assert forbidden not in rendered

    source = inspect.getsource(subscription_service.process_signed_billing_event)
    assert "_provider_event_is_stale" not in source
    assert "last_provider_event_at" not in source
