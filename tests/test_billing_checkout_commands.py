from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from stoa.config import Settings, get_settings
from stoa.db.repositories.checkout_command_repo import (
    CheckoutCommandDisposition,
    CheckoutCommandResult,
    ProviderCreateClaim,
)
from stoa.models.billing import CheckoutCommandState
from stoa.routers import parents
from stoa.services import subscription_service


PARENT_ID = "parent-private-canary"
STUDENT_ID = "student-private-canary"
OTHER_STUDENT_ID = "other-student-private-canary"
SECRET = "sk_test_private_canary"
PROVIDER_KEY = "a" * 64
CHECKOUT_REF = "co_" + "R" * 32
SESSION_ID = "cs_test_checkout_command"
SESSION_URL = f"https://checkout.stripe.com/c/pay/{SESSION_ID}"


def _settings() -> Settings:
    return Settings(
        stripe_api_key=SECRET,
        stripe_student_price_id="price_test_student",
        stripe_teacher_supported_price_id="price_test_teacher_supported",
        stripe_family_price_id="price_test_family",
        stripe_checkout_web_origins=["http://localhost:5173"],
    )


def _profiles() -> dict[str, dict[str, object]]:
    return {
        PARENT_ID: {
            "user_id": PARENT_ID,
            "role": "parent",
            "account_status": "active",
            "version": 7,
        },
        STUDENT_ID: {
            "user_id": STUDENT_ID,
            "role": "student",
            "account_status": "active",
            "version": 11,
        },
        OTHER_STUDENT_ID: {
            "user_id": OTHER_STUDENT_ID,
            "role": "student",
            "account_status": "active",
            "version": 13,
        },
    }


def _install_active_binding(monkeypatch, *, student_id: str = STUDENT_ID) -> None:
    profiles = _profiles()
    monkeypatch.setattr(
        subscription_service.user_repo,
        "get_user",
        lambda user_id: profiles.get(user_id),
    )
    monkeypatch.setattr(
        subscription_service.user_repo,
        "get_parent_student_binding",
        lambda parent_id, requested_student_id: (
            {
                "entity_type": "parent_student_binding",
                "parent_id": parent_id,
                "student_id": requested_student_id,
                "relationship": "child",
                "status": "active",
            }
            if parent_id == PARENT_ID and requested_student_id == student_id
            else None
        ),
    )
    monkeypatch.setattr(
        subscription_service.user_repo,
        "get_student_parent_binding",
        lambda requested_student_id, parent_id: (
            {
                "entity_type": "parent_student_binding",
                "parent_id": parent_id,
                "student_id": requested_student_id,
                "relationship": "child",
                "status": "active",
            }
            if parent_id == PARENT_ID and requested_student_id == student_id
            else None
        ),
    )


class CommandHarness:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.command: dict[str, object] | None = None
        self.events: list[str] = []
        self.attach_calls = 0
        self.unknown_calls = 0

    def install(self, monkeypatch) -> None:
        monkeypatch.setattr(
            subscription_service.checkout_command_repo,
            "register_checkout_command",
            self.register,
        )
        monkeypatch.setattr(
            subscription_service.checkout_command_repo,
            "claim_provider_create",
            self.claim,
        )
        monkeypatch.setattr(
            subscription_service.checkout_command_repo,
            "attach_provider_session",
            self.attach,
        )
        monkeypatch.setattr(
            subscription_service.checkout_command_repo,
            "mark_provider_outcome_unknown",
            self.mark_unknown,
        )
        monkeypatch.setattr(
            subscription_service.checkout_command_repo,
            "get_checkout_command_by_public_ref",
            self.get_by_ref,
        )

    def register(self, intent, *, price_id, environment, now_iso=None):
        with self.lock:
            self.events.append("register")
            fingerprint = (
                intent.command_id,
                str(intent.plan_id),
                tuple(sorted(intent.beneficiary_ids)),
                price_id,
                environment,
            )
            if self.command is None:
                self.command = {
                    "command_id": intent.command_id,
                    "parent_id": intent.parent_id,
                    "checkout_ref": CHECKOUT_REF,
                    "plan_id": str(intent.plan_id),
                    "beneficiary_ids": sorted(intent.beneficiary_ids),
                    "provider_key_digest": PROVIDER_KEY,
                    "provider_effect_status": "not_started",
                    "command_state": CheckoutCommandState.INTENT_RECORDED,
                    "command_version": 1,
                    "_fingerprint": fingerprint,
                }
                return CheckoutCommandResult(
                    CheckoutCommandDisposition.CREATED,
                    command=dict(self.command),
                )
            if self.command["command_id"] != intent.command_id:
                return CheckoutCommandResult(
                    CheckoutCommandDisposition.OPEN_COMMAND_EXISTS
                )
            if self.command["_fingerprint"] != fingerprint:
                return CheckoutCommandResult(
                    CheckoutCommandDisposition.IDENTITY_MISMATCH
                )
            return CheckoutCommandResult(
                CheckoutCommandDisposition.REPLAYED,
                command=dict(self.command),
            )

    def claim(
        self,
        command,
        *,
        lease_owner,
        now_epoch,
        lease_expires_at,
        now_iso,
    ):
        del now_epoch, now_iso
        with self.lock:
            self.events.append("claim")
            assert self.command is not None
            if self.command["provider_effect_status"] == "session_attached":
                return CheckoutCommandResult(
                    CheckoutCommandDisposition.ALREADY_ATTACHED,
                    command=dict(self.command),
                )
            if self.command["provider_effect_status"] == "create_claimed":
                return CheckoutCommandResult(
                    CheckoutCommandDisposition.LEASE_BUSY,
                    command=dict(self.command),
                )
            self.command["provider_effect_status"] = "create_claimed"
            self.command["command_state"] = CheckoutCommandState.PROVIDER_CREATE_PENDING
            self.command["command_version"] = int(self.command["command_version"]) + 1
            claim = ProviderCreateClaim(
                command_id=str(self.command["command_id"]),
                parent_id=str(self.command["parent_id"]),
                command_version=int(self.command["command_version"]),
                lease_owner=lease_owner,
                lease_generation=1,
                lease_expires_at=lease_expires_at,
                provider_key_digest=PROVIDER_KEY,
            )
            return CheckoutCommandResult(
                CheckoutCommandDisposition.CLAIMED,
                command=dict(self.command),
                provider_claim=claim,
            )

    def attach(
        self,
        claim,
        *,
        provider_session_id,
        provider_session_url,
        now_iso,
    ):
        del claim, now_iso
        with self.lock:
            self.events.append("attach")
            self.attach_calls += 1
            assert self.command is not None
            self.command.update(
                provider_effect_status="session_attached",
                command_state=CheckoutCommandState.PROVIDER_SESSION_OPEN,
                provider_session_id=provider_session_id,
                provider_session_url=provider_session_url,
                command_version=int(self.command["command_version"]) + 1,
            )
            return CheckoutCommandResult(
                CheckoutCommandDisposition.ATTACHED,
                command=dict(self.command),
            )

    def mark_unknown(self, claim, *, now_iso):
        del claim, now_iso
        with self.lock:
            self.unknown_calls += 1
            assert self.command is not None
            self.command["provider_effect_status"] = "provider_outcome_unknown"
            return CheckoutCommandResult(
                CheckoutCommandDisposition.PROVIDER_OUTCOME_UNKNOWN,
                command=dict(self.command),
            )

    def get_by_ref(self, checkout_ref, *, parent_id):
        with self.lock:
            if (
                self.command is None
                or checkout_ref != self.command["checkout_ref"]
                or parent_id != self.command["parent_id"]
            ):
                return CheckoutCommandResult(CheckoutCommandDisposition.NOT_FOUND)
            return CheckoutCommandResult(
                CheckoutCommandDisposition.REPLAYED,
                command=dict(self.command),
            )


def _create(
    *,
    key: str = "checkout-key-0001",
    plan: str = "student",
    beneficiaries: tuple[str, ...] = (STUDENT_ID,),
    settings: Settings | None = None,
) -> dict[str, Any]:
    return subscription_service.create_or_resume_checkout_command(
        parent_id=PARENT_ID,
        idempotency_key=key,
        plan=plan,
        beneficiary_ids=beneficiaries,
        settings=settings or _settings(),
    )


def test_command_and_provider_intent_are_durable_before_stripe_and_attach(monkeypatch):
    _install_active_binding(monkeypatch)
    harness = CommandHarness()
    harness.install(monkeypatch)
    provider_calls: list[dict[str, object]] = []

    def create_provider(**kwargs):
        harness.events.append("provider")
        provider_calls.append(dict(kwargs))
        return {
            "id": SESSION_ID,
            "url": SESSION_URL,
            "livemode": False,
        }

    monkeypatch.setattr(
        subscription_service,
        "_create_provider_checkout_session",
        create_provider,
    )

    response = _create()

    assert harness.events == ["register", "claim", "provider", "attach"]
    assert provider_calls[0]["provider_idempotency_key"] == PROVIDER_KEY
    assert provider_calls[0]["checkout_ref"] == CHECKOUT_REF
    assert response == {
        "checkoutRef": CHECKOUT_REF,
        "commandState": "provider_session_open",
        "checkoutSessionId": SESSION_ID,
        "checkoutUrl": SESSION_URL,
        "safeActions": ["recheck_payment", "contact_support"],
        "targetPlan": "student",
        "beneficiaries": [STUDENT_ID],
    }


def test_timeout_retries_identical_stripe_request_and_replays_one_session(monkeypatch):
    _install_active_binding(monkeypatch)
    harness = CommandHarness()
    harness.install(monkeypatch)
    calls: list[dict[str, object]] = []

    def ambiguous_provider(**kwargs):
        calls.append(dict(kwargs))
        if len(calls) == 1:
            raise TimeoutError("response lost after provider accepted request")
        return {"id": SESSION_ID, "url": SESSION_URL, "livemode": False}

    monkeypatch.setattr(
        subscription_service,
        "_create_provider_checkout_session",
        ambiguous_provider,
    )

    first = _create()
    replay = _create()

    assert calls[0] == calls[1]
    assert len(calls) == 2
    assert first == replay
    assert harness.attach_calls == 1
    assert harness.unknown_calls == 0


def test_concurrent_duplicate_clicks_share_one_provider_session(monkeypatch):
    _install_active_binding(monkeypatch)
    harness = CommandHarness()
    harness.install(monkeypatch)
    provider_count = 0
    provider_lock = threading.Lock()

    def slow_provider(**kwargs):
        nonlocal provider_count
        del kwargs
        with provider_lock:
            provider_count += 1
        time.sleep(0.03)
        return {"id": SESSION_ID, "url": SESSION_URL, "livemode": False}

    monkeypatch.setattr(
        subscription_service,
        "_create_provider_checkout_session",
        slow_provider,
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: _create(), range(2)))

    assert responses[0] == responses[1]
    assert provider_count == 1
    assert harness.attach_calls == 1


def test_same_key_payload_change_and_different_open_key_are_conflicts(monkeypatch):
    _install_active_binding(monkeypatch)
    harness = CommandHarness()
    harness.install(monkeypatch)
    monkeypatch.setattr(
        subscription_service,
        "_create_provider_checkout_session",
        lambda **kwargs: {"id": SESSION_ID, "url": SESSION_URL, "livemode": False},
    )
    _create()

    with pytest.raises(subscription_service.HTTPException) as changed:
        _create(plan="teacher_supported")
    assert changed.value.detail["code"] == "checkout_idempotency_mismatch"

    with pytest.raises(subscription_service.HTTPException) as open_command:
        _create(key="checkout-key-0002")
    assert open_command.value.detail["code"] == "checkout_already_in_progress"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("inactive_student", "checkout_beneficiary_invalid"),
        ("missing_forward", "checkout_beneficiary_invalid"),
        ("wrong_reverse_parent", "checkout_beneficiary_invalid"),
    ],
)
def test_invalid_inactive_or_unbound_beneficiary_never_reaches_provider(
    monkeypatch,
    mutation,
    expected_code,
):
    profiles = _profiles()
    if mutation == "inactive_student":
        profiles[STUDENT_ID]["account_status"] = "suspended"
    monkeypatch.setattr(
        subscription_service.user_repo,
        "get_user",
        lambda user_id: profiles.get(user_id),
    )
    monkeypatch.setattr(
        subscription_service.user_repo,
        "get_parent_student_binding",
        lambda parent_id, student_id: (
            None
            if mutation == "missing_forward"
            else {
                "entity_type": "parent_student_binding",
                "parent_id": parent_id,
                "student_id": student_id,
                "relationship": "child",
                "status": "active",
            }
        ),
    )
    monkeypatch.setattr(
        subscription_service.user_repo,
        "get_student_parent_binding",
        lambda student_id, parent_id: {
            "entity_type": "parent_student_binding",
            "parent_id": "different-parent" if mutation == "wrong_reverse_parent" else parent_id,
            "student_id": student_id,
            "relationship": "child",
            "status": "active",
        },
    )
    provider_calls = 0

    def provider(**kwargs):
        nonlocal provider_calls
        del kwargs
        provider_calls += 1
        return {"id": SESSION_ID, "url": SESSION_URL, "livemode": False}

    monkeypatch.setattr(
        subscription_service,
        "_create_provider_checkout_session",
        provider,
    )

    with pytest.raises(subscription_service.HTTPException) as exc:
        _create()
    assert exc.value.detail["code"] == expected_code
    assert provider_calls == 0


def test_cardinality_and_sandbox_configuration_fail_before_provider(monkeypatch):
    _install_active_binding(monkeypatch)
    provider_calls = 0

    def provider(**kwargs):
        nonlocal provider_calls
        del kwargs
        provider_calls += 1
        return {"id": SESSION_ID, "url": SESSION_URL, "livemode": False}

    monkeypatch.setattr(
        subscription_service,
        "_create_provider_checkout_session",
        provider,
    )

    with pytest.raises(subscription_service.HTTPException) as cardinality:
        _create(plan="student", beneficiaries=(STUDENT_ID, OTHER_STUDENT_ID))
    assert cardinality.value.detail["code"] == "checkout_beneficiary_cardinality"

    live_key = _settings()
    live_key.stripe_api_key = "sk_live_forbidden"
    with pytest.raises(subscription_service.HTTPException) as key_error:
        _create(settings=live_key)
    assert key_error.value.detail["code"] == "checkout_sandbox_required"

    live_price = _settings()
    live_price.stripe_student_price_id = "price_live_forbidden"
    with pytest.raises(subscription_service.HTTPException) as price_error:
        _create(settings=live_price)
    assert price_error.value.detail["code"] == "checkout_sandbox_required"
    assert provider_calls == 0


def test_live_provider_object_is_never_attached(monkeypatch):
    _install_active_binding(monkeypatch)
    harness = CommandHarness()
    harness.install(monkeypatch)
    monkeypatch.setattr(
        subscription_service,
        "_create_provider_checkout_session",
        lambda **kwargs: {"id": "cs_live_forbidden", "url": SESSION_URL, "livemode": True},
    )

    with pytest.raises(subscription_service.HTTPException) as exc:
        _create()

    assert exc.value.detail["code"] == "checkout_provider_ambiguous"
    assert harness.attach_calls == 0
    assert harness.unknown_calls == 1


def test_provider_call_uses_only_opaque_reference_and_stable_key(monkeypatch):
    captured: dict[str, object] = {}

    class FakeSession:
        @staticmethod
        def create(**kwargs):
            captured.update(kwargs)
            return {
                "id": SESSION_ID,
                "url": SESSION_URL,
                "livemode": False,
                "customer": "cus_test_checkout",
            }

    class FakeCheckout:
        Session = FakeSession

    class FakeStripe:
        checkout = FakeCheckout
        api_key = None

    monkeypatch.setattr(subscription_service, "_load_stripe_sdk", lambda: FakeStripe)
    return_urls = subscription_service.build_checkout_return_urls(CHECKOUT_REF, _settings())

    result = subscription_service._create_provider_checkout_session(
        checkout_ref=CHECKOUT_REF,
        provider_idempotency_key=PROVIDER_KEY,
        price_id="price_test_student",
        success_url=return_urls.success_url,
        cancel_url=return_urls.cancel_url,
        settings=_settings(),
    )

    assert result["livemode"] is False
    assert captured["idempotency_key"] == PROVIDER_KEY
    assert captured["client_reference_id"] == CHECKOUT_REF
    assert captured["metadata"] == {"stoa_checkout_ref": CHECKOUT_REF}
    assert captured["subscription_data"] == {
        "metadata": {"stoa_checkout_ref": CHECKOUT_REF}
    }
    request_text = json.dumps(captured, sort_keys=True)
    assert PARENT_ID not in request_text
    assert STUDENT_ID not in request_text
    assert SECRET not in request_text


def _app(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.include_router(parents.router, prefix="/parents")
    install_actor_overrides(app, {"sub": PARENT_ID, "role": "parent"})
    app.dependency_overrides[get_settings] = lambda: settings
    return app


def test_parent_route_requires_idempotency_header_and_forbids_old_callback_fields(
    monkeypatch,
):
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        subscription_service,
        "create_or_resume_checkout_command",
        lambda **kwargs: calls.append(kwargs)
        or {
            "checkoutRef": CHECKOUT_REF,
            "commandState": "provider_session_open",
            "checkoutSessionId": SESSION_ID,
            "checkoutUrl": SESSION_URL,
            "safeActions": ["recheck_payment"],
            "targetPlan": "student",
            "beneficiaries": [STUDENT_ID],
        },
    )
    client = TestClient(_app(_settings()))
    body = {"plan": "student", "beneficiaryIds": [STUDENT_ID]}

    assert client.post("/parents/me/subscription/checkout", json=body).status_code == 422
    assert (
        client.post(
            "/parents/me/subscription/checkout",
            headers={"Idempotency-Key": "checkout-key-0001"},
            json={**body, "successUrl": "https://evil.example/success"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/parents/me/subscription/checkout",
            headers={"Idempotency-Key": "checkout-key-0001"},
            json={**body, "cancelUrl": "https://evil.example/cancel"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/parents/me/subscription/checkout",
            headers={"Idempotency-Key": "checkout-key-0001"},
            json={**body, "unknown": True},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/parents/me/subscription/checkout",
            headers={"Idempotency-Key": "checkout-key-0001"},
            json={"plan": "free_trial", "beneficiaryIds": [STUDENT_ID]},
        ).status_code
        == 422
    )
    accepted = client.post(
        "/parents/me/subscription/checkout",
        headers={"Idempotency-Key": "checkout-key-0001"},
        json=body,
    )
    assert accepted.status_code == 201
    assert calls[0]["idempotency_key"] == "checkout-key-0001"
    assert calls[0]["beneficiary_ids"] == (STUDENT_ID,)
