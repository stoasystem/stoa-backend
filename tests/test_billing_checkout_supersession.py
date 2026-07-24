"""Confirmed checkout plan-change supersession and race contract."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

import pytest

from stoa.config import Settings
from stoa.db.repositories import checkout_command_repo
from stoa.db.repositories.checkout_command_repo import (
    CheckoutCommandDisposition,
    CheckoutCommandResult,
)
from stoa.models.billing import CheckoutCommandState, CheckoutIntent, PurchasablePlanId
from stoa.services import subscription_service


PARENT_ID = "parent-supersession-canary"
OTHER_PARENT_ID = "other-parent-supersession-canary"
STUDENT_ID = "student-supersession-canary"
OLD_REF = "co_" + "O" * 32
NEW_REF = "co_" + "N" * 32
OLD_SESSION_ID = "cs_test_old_supersession"
NEW_SESSION_ID = "cs_test_new_supersession"
NEW_SESSION_URL = f"https://checkout.stripe.com/c/pay/{NEW_SESSION_ID}"
NOW = "2026-07-24T10:55:00+00:00"


def _settings() -> Settings:
    return Settings(
        stripe_api_key="sk_test_supersession_canary",
        stripe_student_price_id="price_test_student",
        stripe_teacher_supported_price_id="price_test_teacher_supported",
        stripe_family_price_id="price_test_family",
        stripe_checkout_web_origins=["http://localhost:5173"],
    )


def _new_intent(key: str = "confirmed-plan-change-key") -> CheckoutIntent:
    command_id = checkout_command_repo.checkout_command_id(PARENT_ID, key)
    return CheckoutIntent(
        commandId=command_id,
        parentId=PARENT_ID,
        idempotencyKey=key,
        planId=PurchasablePlanId.TEACHER_SUPPORTED,
        beneficiaryIds=(STUDENT_ID,),
        priceCatalogVersion=1,
        planVersion=1,
        createdAt=datetime.fromisoformat(NOW),
    )


def _old_command() -> dict[str, object]:
    return {
        "command_id": "checkout-old-command",
        "parent_id": PARENT_ID,
        "checkout_ref": OLD_REF,
        "plan_id": "student",
        "beneficiary_ids": [STUDENT_ID],
        "provider_session_id": OLD_SESSION_ID,
        "provider_effect_status": "session_attached",
        "expiration_effect_status": "not_started",
        "command_state": CheckoutCommandState.PROVIDER_SESSION_OPEN,
        "command_version": 3,
        "account_fence_generation": 7,
    }


class SupersessionHarness:
    """Synchronized repository double that preserves the old guard until transfer."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.old = _old_command()
        self.new: dict[str, object] | None = None
        self.events: list[str] = []
        self.guard_command_id = str(self.old["command_id"])

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            subscription_service.checkout_command_repo,
            "get_checkout_command_by_public_ref",
            self.get_by_ref,
        )
        monkeypatch.setattr(
            subscription_service.checkout_command_repo,
            "claim_session_expiration",
            self.claim_expiration,
            raising=False,
        )
        monkeypatch.setattr(
            subscription_service.checkout_command_repo,
            "record_session_expiration",
            self.record_expiration,
            raising=False,
        )
        monkeypatch.setattr(
            subscription_service.checkout_command_repo,
            "supersede_checkout_command",
            self.supersede,
            raising=False,
        )

    def get_by_ref(self, checkout_ref: str, *, parent_id: str) -> CheckoutCommandResult:
        with self.lock:
            if checkout_ref != OLD_REF or parent_id != PARENT_ID:
                return CheckoutCommandResult(CheckoutCommandDisposition.NOT_FOUND)
            return CheckoutCommandResult(
                CheckoutCommandDisposition.REPLAYED,
                command=dict(self.old),
            )

    def claim_expiration(
        self,
        command: dict[str, object],
        *,
        now_iso: str,
    ) -> Any:
        del command, now_iso
        with self.lock:
            if self.old["expiration_effect_status"] == "not_started":
                self.events.append("claim_expiration")
                self.old["expiration_effect_status"] = "expire_claimed"
                self.old["command_version"] = int(self.old["command_version"]) + 1
                return checkout_command_repo.CheckoutSupersessionResult(
                    checkout_command_repo.CheckoutSupersessionDisposition.EXPIRATION_CLAIMED,
                    command=dict(self.old),
                )
            return checkout_command_repo.CheckoutSupersessionResult(
                checkout_command_repo.CheckoutSupersessionDisposition.EXPIRATION_BUSY,
                command=dict(self.old),
            )

    def record_expiration(
        self,
        command: dict[str, object],
        *,
        provider_session_status: str,
        now_iso: str,
    ) -> Any:
        del command, now_iso
        with self.lock:
            self.events.append(f"record_{provider_session_status}")
            self.old["command_version"] = int(self.old["command_version"]) + 1
            if provider_session_status == "expired":
                self.old["expiration_effect_status"] = "nonpayable_proven"
                self.old["command_state"] = CheckoutCommandState.TERMINAL_WITHOUT_PAYMENT
                disposition = (
                    checkout_command_repo.CheckoutSupersessionDisposition.NONPAYABLE_PROVEN
                )
            elif provider_session_status == "complete":
                self.old["expiration_effect_status"] = "payment_reconciliation_required"
                self.old["command_state"] = CheckoutCommandState.RECONCILING
                disposition = (
                    checkout_command_repo.CheckoutSupersessionDisposition.RECONCILIATION_REQUIRED
                )
            else:
                self.old["expiration_effect_status"] = "expiration_outcome_unknown"
                self.old["command_state"] = CheckoutCommandState.OPERATOR_ATTENTION_REQUIRED
                disposition = (
                    checkout_command_repo.CheckoutSupersessionDisposition.PROVIDER_UNKNOWN
                )
            return checkout_command_repo.CheckoutSupersessionResult(
                disposition,
                command=dict(self.old),
            )

    def supersede(
        self,
        old_command: dict[str, object],
        new_intent: CheckoutIntent,
        *,
        price_id: str,
        environment: str,
        now_iso: str,
    ) -> Any:
        del old_command, price_id, environment, now_iso
        with self.lock:
            if self.new is None:
                assert self.old["expiration_effect_status"] == "nonpayable_proven"
                self.events.append("supersede")
                self.new = {
                    "command_id": new_intent.command_id,
                    "parent_id": new_intent.parent_id,
                    "checkout_ref": NEW_REF,
                    "plan_id": str(new_intent.plan_id),
                    "beneficiary_ids": list(new_intent.beneficiary_ids),
                    "provider_effect_status": "not_started",
                    "command_state": CheckoutCommandState.INTENT_RECORDED,
                    "command_version": 1,
                }
                self.old["superseded_by_command_id"] = new_intent.command_id
                self.guard_command_id = new_intent.command_id
            return checkout_command_repo.CheckoutSupersessionResult(
                checkout_command_repo.CheckoutSupersessionDisposition.SUPERSEDED,
                command=dict(self.new),
            )


def _install_active_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    profiles = {
        PARENT_ID: {
            "user_id": PARENT_ID,
            "role": "parent",
            "account_status": "active",
        },
        STUDENT_ID: {
            "user_id": STUDENT_ID,
            "role": "student",
            "account_status": "active",
        },
    }
    monkeypatch.setattr(
        subscription_service.user_repo,
        "get_user",
        lambda user_id: profiles.get(user_id),
    )
    binding = {
        "parent_id": PARENT_ID,
        "student_id": STUDENT_ID,
        "relationship": "child",
        "status": "active",
    }
    monkeypatch.setattr(
        subscription_service.user_repo,
        "get_parent_student_binding",
        lambda parent_id, student_id: (
            dict(binding)
            if (parent_id, student_id) == (PARENT_ID, STUDENT_ID)
            else None
        ),
    )
    monkeypatch.setattr(
        subscription_service.user_repo,
        "get_student_parent_binding",
        lambda student_id, parent_id: (
            dict(binding)
            if (parent_id, student_id) == (PARENT_ID, STUDENT_ID)
            else None
        ),
    )


def _confirm(settings: Settings | None = None) -> dict[str, Any]:
    return subscription_service.confirm_checkout_plan_change(
        parent_id=PARENT_ID,
        checkout_ref=OLD_REF,
        idempotency_key="confirmed-plan-change-key",
        plan="teacher_supported",
        beneficiary_ids=(STUDENT_ID,),
        settings=settings or _settings(),
    )


def test_repository_exports_version_conditioned_supersession_contract() -> None:
    expected = {
        "CheckoutSupersessionDisposition",
        "claim_session_expiration",
        "record_session_expiration",
        "supersede_checkout_command",
    }
    assert expected <= set(checkout_command_repo.__all__)


def test_open_session_is_expired_proven_and_superseded_before_new_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_active_scope(monkeypatch)
    harness = SupersessionHarness()
    harness.install(monkeypatch)
    provider_statuses = iter(("open", "expired"))
    monkeypatch.setattr(
        subscription_service,
        "_retrieve_provider_checkout_session",
        lambda **kwargs: {
            "id": OLD_SESSION_ID,
            "status": next(provider_statuses),
            "livemode": False,
        },
        raising=False,
    )
    monkeypatch.setattr(
        subscription_service,
        "_expire_provider_checkout_session",
        lambda **kwargs: harness.events.append("provider_expire")
        or {"id": OLD_SESSION_ID, "status": "expired", "livemode": False},
        raising=False,
    )
    monkeypatch.setattr(
        subscription_service,
        "create_or_resume_checkout_command",
        lambda **kwargs: harness.events.append("provider_create")
        or {
            "checkoutRef": NEW_REF,
            "commandState": "provider_session_open",
            "checkoutSessionId": NEW_SESSION_ID,
            "checkoutUrl": NEW_SESSION_URL,
            "safeActions": ["recheck_payment", "contact_support"],
            "targetPlan": kwargs["plan"],
            "beneficiaries": list(kwargs["beneficiary_ids"]),
        },
    )

    response = _confirm()

    assert response["checkoutRef"] == NEW_REF
    assert harness.events == [
        "claim_expiration",
        "provider_expire",
        "record_expired",
        "supersede",
        "provider_create",
    ]
    assert harness.guard_command_id == str(harness.new["command_id"])


def test_already_expired_session_skips_expire_and_preserves_prior_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_active_scope(monkeypatch)
    harness = SupersessionHarness()
    harness.install(monkeypatch)
    prior_access = {
        "plan": "student",
        "grant": {"student": STUDENT_ID, "status": "active", "version": 11},
    }
    before = repr(prior_access)
    monkeypatch.setattr(
        subscription_service,
        "_retrieve_provider_checkout_session",
        lambda **kwargs: {
            "id": OLD_SESSION_ID,
            "status": "expired",
            "livemode": False,
        },
        raising=False,
    )
    monkeypatch.setattr(
        subscription_service,
        "_expire_provider_checkout_session",
        lambda **kwargs: pytest.fail("already-expired Session must not be expired again"),
        raising=False,
    )
    monkeypatch.setattr(
        subscription_service,
        "create_or_resume_checkout_command",
        lambda **kwargs: {
            "checkoutRef": NEW_REF,
            "targetPlan": kwargs["plan"],
            "beneficiaries": list(kwargs["beneficiary_ids"]),
        },
    )

    _confirm()

    assert repr(prior_access) == before
    assert harness.old["expiration_effect_status"] == "nonpayable_proven"


@pytest.mark.parametrize("provider_outcome", ["complete", "timeout"])
def test_complete_or_unknown_session_retains_old_guard_and_never_creates(
    monkeypatch: pytest.MonkeyPatch,
    provider_outcome: str,
) -> None:
    _install_active_scope(monkeypatch)
    harness = SupersessionHarness()
    harness.install(monkeypatch)

    def retrieve(**kwargs: object) -> dict[str, object]:
        del kwargs
        if provider_outcome == "timeout":
            raise TimeoutError("provider outcome unknown")
        return {
            "id": OLD_SESSION_ID,
            "status": "complete",
            "payment_status": "unpaid",
            "livemode": False,
        }

    monkeypatch.setattr(
        subscription_service,
        "_retrieve_provider_checkout_session",
        retrieve,
        raising=False,
    )
    monkeypatch.setattr(
        subscription_service,
        "_expire_provider_checkout_session",
        lambda **kwargs: pytest.fail("unsafe expiration"),
        raising=False,
    )
    monkeypatch.setattr(
        subscription_service,
        "create_or_resume_checkout_command",
        lambda **kwargs: pytest.fail("unsafe replacement create"),
    )

    response = _confirm()

    assert response["publicOutcome"] == "support_needed"
    assert harness.guard_command_id == str(harness.old["command_id"])
    assert harness.new is None


def test_cross_owner_reference_is_concealed_before_provider_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_active_scope(monkeypatch)
    harness = SupersessionHarness()
    harness.install(monkeypatch)
    monkeypatch.setattr(
        subscription_service,
        "_retrieve_provider_checkout_session",
        lambda **kwargs: pytest.fail("provider must not be reached"),
        raising=False,
    )

    with pytest.raises(subscription_service.HTTPException) as exc:
        subscription_service.confirm_checkout_plan_change(
            parent_id=OTHER_PARENT_ID,
            checkout_ref=OLD_REF,
            idempotency_key="confirmed-plan-change-key",
            plan="teacher_supported",
            beneficiary_ids=(STUDENT_ID,),
            settings=_settings(),
        )

    assert exc.value.status_code == 404


def test_two_concurrent_confirmations_converge_on_one_new_command_and_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_active_scope(monkeypatch)
    harness = SupersessionHarness()
    harness.install(monkeypatch)
    expire_calls = 0
    create_calls = 0
    provider_lock = threading.Lock()

    def retrieve(**kwargs: object) -> dict[str, object]:
        del kwargs
        with harness.lock:
            expired = (
                harness.old["expiration_effect_status"] == "nonpayable_proven"
            )
        return {
            "id": OLD_SESSION_ID,
            "status": "expired" if expired else "open",
            "livemode": False,
        }

    def expire(**kwargs: object) -> dict[str, object]:
        nonlocal expire_calls
        del kwargs
        with provider_lock:
            expire_calls += 1
        return {"id": OLD_SESSION_ID, "status": "expired", "livemode": False}

    def create(**kwargs: object) -> dict[str, object]:
        nonlocal create_calls
        del kwargs
        with provider_lock:
            create_calls += 1
        return {
            "checkoutRef": NEW_REF,
            "checkoutSessionId": NEW_SESSION_ID,
        }

    monkeypatch.setattr(
        subscription_service,
        "_retrieve_provider_checkout_session",
        retrieve,
        raising=False,
    )
    monkeypatch.setattr(
        subscription_service,
        "_expire_provider_checkout_session",
        expire,
        raising=False,
    )
    monkeypatch.setattr(
        subscription_service,
        "create_or_resume_checkout_command",
        create,
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: _confirm(), range(2)))

    assert responses[0] == responses[1]
    assert expire_calls == 1
    assert create_calls == 2
    assert harness.new is not None
    assert harness.guard_command_id == str(harness.new["command_id"])
