"""Same-command checkout reconciliation and support-projection contract."""

from __future__ import annotations

import inspect
from dataclasses import replace
from typing import Any

import pytest

from stoa.db.repositories import checkout_command_repo
from stoa.models.billing import CheckoutCommandState
from stoa.services import billing_reconciliation_service


CHECKOUT_REF = "co_abcdefghijklmnopqrstuvwxyzABCDEFGH"
OTHER_CHECKOUT_REF = "co_HGFEDCBAzyxwvutsrqponmlkjihgfedc"
PARENT_ID = "parent-private-canary"
OTHER_PARENT_ID = "other-parent-private-canary"
COMMAND_ID = "checkout-" + ("a" * 64)
PROVIDER_KEY = "b" * 64
SESSION_ID = "cs_test_reconciliation_123456789"
SESSION_URL = "https://checkout.stripe.com/c/pay/cs_test_reconciliation_123456789"
PRICE_ID = "price_test_family_v7"
NOW_ISO = "2026-07-24T10:30:00+00:00"
NOW_EPOCH = 1784889000


def _command(
    *,
    effect_status: str = "provider_outcome_unknown",
    command_state: CheckoutCommandState = CheckoutCommandState.OPERATOR_ATTENTION_REQUIRED,
    lease_generation: int = 1,
    lease_expires_at: int = NOW_EPOCH - 1,
    provider_session_id: str | None = None,
    provider_session_url: str | None = None,
    provider_customer_id: str | None = "cus_test_parent",
) -> dict[str, object]:
    item: dict[str, object] = {
        "entity_type": "checkout_command",
        "schema_version": checkout_command_repo.COMMAND_SCHEMA_VERSION,
        "command_id": COMMAND_ID,
        "parent_id": PARENT_ID,
        "checkout_ref": CHECKOUT_REF,
        "command_state": command_state,
        "command_version": 3,
        "provider_effect_status": effect_status,
        "provider_key_digest": PROVIDER_KEY,
        "lease_owner": "checkout-worker",
        "lease_generation": lease_generation,
        "lease_expires_at": lease_expires_at,
        "price_id": PRICE_ID,
        "environment": "test",
        "plan_id": "family",
        "beneficiary_ids": ["student-a", "student-b"],
        "created_at": "2026-07-24T10:00:00+00:00",
        "updated_at": "2026-07-24T10:05:00+00:00",
    }
    if provider_session_id is not None:
        item["provider_session_id"] = provider_session_id
    if provider_session_url is not None:
        item["provider_session_url"] = provider_session_url
    if provider_customer_id is not None:
        item["provider_customer_id"] = provider_customer_id
    return item


def _session(
    *,
    session_id: str = SESSION_ID,
    checkout_ref: str = CHECKOUT_REF,
    metadata_checkout_ref: str = CHECKOUT_REF,
    price_id: str = PRICE_ID,
    environment: str = "test",
    customer_id: str = "cus_test_parent",
    livemode: bool = False,
    status: str = "open",
) -> billing_reconciliation_service.ProviderCheckoutSessionEvidence:
    return billing_reconciliation_service.ProviderCheckoutSessionEvidence(
        session_id=session_id,
        checkout_url=SESSION_URL,
        client_reference_id=checkout_ref,
        metadata_checkout_ref=metadata_checkout_ref,
        customer_id=customer_id,
        price_id=price_id,
        environment=environment,
        livemode=livemode,
        status=status,
        created_at="2026-07-24T10:04:00+00:00",
    )


class FakeCheckoutRepository:
    def __init__(self, command: dict[str, object] | None = None) -> None:
        self.command = dict(command or _command())
        self.lookup_calls: list[tuple[str, str]] = []
        self.claim_calls = 0
        self.attach_calls = 0
        self.unknown_calls = 0
        self.claim_disposition = checkout_command_repo.CheckoutCommandDisposition.CLAIMED
        self.attach_failures = 0

    def get_checkout_command_by_public_ref(
        self,
        checkout_ref: str,
        *,
        parent_id: str,
        table: object | None = None,
    ) -> checkout_command_repo.CheckoutCommandResult:
        del table
        self.lookup_calls.append((checkout_ref, parent_id))
        if (
            checkout_ref != self.command.get("checkout_ref")
            or parent_id != self.command.get("parent_id")
        ):
            return checkout_command_repo.CheckoutCommandResult(
                checkout_command_repo.CheckoutCommandDisposition.NOT_FOUND
            )
        return checkout_command_repo.CheckoutCommandResult(
            checkout_command_repo.CheckoutCommandDisposition.REPLAYED,
            command=dict(self.command),
        )

    def claim_provider_create(
        self,
        command: dict[str, object],
        *,
        lease_owner: str,
        now_epoch: int,
        lease_expires_at: int,
        now_iso: str,
        table: object | None = None,
    ) -> checkout_command_repo.CheckoutCommandResult:
        del table, now_iso
        self.claim_calls += 1
        if self.claim_disposition is not checkout_command_repo.CheckoutCommandDisposition.CLAIMED:
            return checkout_command_repo.CheckoutCommandResult(
                self.claim_disposition,
                command=dict(self.command),
            )
        if (
            self.command.get("provider_effect_status")
            in {"create_claimed", "provider_outcome_unknown"}
            and int(self.command.get("lease_expires_at") or 0) > now_epoch
        ):
            return checkout_command_repo.CheckoutCommandResult(
                checkout_command_repo.CheckoutCommandDisposition.LEASE_BUSY,
                command=dict(self.command),
            )
        generation = int(self.command.get("lease_generation") or 0) + 1
        version = int(self.command["command_version"]) + 1
        self.command.update(
            provider_effect_status="create_claimed",
            command_state=CheckoutCommandState.PROVIDER_CREATE_PENDING,
            lease_owner=lease_owner,
            lease_generation=generation,
            lease_expires_at=lease_expires_at,
            command_version=version,
        )
        claim = checkout_command_repo.ProviderCreateClaim(
            command_id=COMMAND_ID,
            parent_id=PARENT_ID,
            command_version=version,
            lease_owner=lease_owner,
            lease_generation=generation,
            lease_expires_at=lease_expires_at,
            provider_key_digest=PROVIDER_KEY,
        )
        return checkout_command_repo.CheckoutCommandResult(
            checkout_command_repo.CheckoutCommandDisposition.CLAIMED,
            command=dict(self.command),
            provider_claim=claim,
        )

    def attach_provider_session(
        self,
        claim: checkout_command_repo.ProviderCreateClaim,
        *,
        provider_session_id: str,
        provider_session_url: str,
        now_iso: str,
        table: object | None = None,
    ) -> checkout_command_repo.CheckoutCommandResult:
        del table, now_iso
        self.attach_calls += 1
        if self.attach_failures:
            self.attach_failures -= 1
            return checkout_command_repo.CheckoutCommandResult(
                checkout_command_repo.CheckoutCommandDisposition.RETRYABLE,
                command=dict(self.command),
            )
        if (
            claim.command_id != self.command.get("command_id")
            or claim.lease_generation != self.command.get("lease_generation")
        ):
            return checkout_command_repo.CheckoutCommandResult(
                checkout_command_repo.CheckoutCommandDisposition.STALE_LEASE,
                command=dict(self.command),
            )
        self.command.update(
            provider_effect_status="session_attached",
            command_state=CheckoutCommandState.PROVIDER_SESSION_OPEN,
            provider_session_id=provider_session_id,
            provider_session_url=provider_session_url,
            command_version=int(self.command["command_version"]) + 1,
        )
        return checkout_command_repo.CheckoutCommandResult(
            checkout_command_repo.CheckoutCommandDisposition.ATTACHED,
            command=dict(self.command),
        )

    def mark_provider_outcome_unknown(
        self,
        claim: checkout_command_repo.ProviderCreateClaim,
        *,
        now_iso: str,
        table: object | None = None,
    ) -> checkout_command_repo.CheckoutCommandResult:
        del claim, table, now_iso
        self.unknown_calls += 1
        self.command.update(
            provider_effect_status="provider_outcome_unknown",
            command_state=CheckoutCommandState.OPERATOR_ATTENTION_REQUIRED,
            command_version=int(self.command["command_version"]) + 1,
        )
        return checkout_command_repo.CheckoutCommandResult(
            checkout_command_repo.CheckoutCommandDisposition.PROVIDER_OUTCOME_UNKNOWN,
            command=dict(self.command),
        )


class RetrievalOnlyProvider:
    def __init__(
        self,
        *,
        found: billing_reconciliation_service.ProviderCheckoutSessionEvidence | None = None,
        retrieved: billing_reconciliation_service.ProviderCheckoutSessionEvidence | None = None,
    ) -> None:
        self.found = found
        self.retrieved = retrieved
        self.find_calls: list[tuple[str, str]] = []
        self.retrieve_calls: list[str] = []
        self.find_failures = 0
        self.retrieve_failures = 0

    def find_checkout_session(
        self,
        *,
        checkout_ref: str,
        provider_key_digest: str,
    ) -> billing_reconciliation_service.ProviderCheckoutSessionEvidence | None:
        self.find_calls.append((checkout_ref, provider_key_digest))
        if self.find_failures:
            self.find_failures -= 1
            raise TimeoutError("provider-private-canary")
        return self.found

    def retrieve_checkout_session(
        self,
        *,
        session_id: str,
    ) -> billing_reconciliation_service.ProviderCheckoutSessionEvidence:
        self.retrieve_calls.append(session_id)
        if self.retrieve_failures:
            self.retrieve_failures -= 1
            raise TimeoutError("provider-private-canary")
        if self.retrieved is None:
            raise LookupError("provider-private-canary")
        return self.retrieved


class FailIfCreateProvider(RetrievalOnlyProvider):
    def create_checkout_session(self, **kwargs: object) -> object:
        del kwargs
        raise AssertionError("reconciliation must not create a provider Session")


def _reconcile(
    repository: FakeCheckoutRepository,
    provider: RetrievalOnlyProvider,
    **overrides: Any,
) -> billing_reconciliation_service.BillingReconciliationResult:
    arguments: dict[str, object] = {
        "checkout_ref": CHECKOUT_REF,
        "parent_id": PARENT_ID,
        "lease_owner": "reconciliation-worker",
        "provider": provider,
        "repository": repository,
        "now_epoch": NOW_EPOCH,
        "now_iso": NOW_ISO,
        "lease_seconds": 30,
    }
    arguments.update(overrides)
    return billing_reconciliation_service.reconcile_checkout_command(**arguments)


def test_reconciliation_source_links_owner_lookup_claim_and_conditional_attach() -> None:
    source = inspect.getsource(billing_reconciliation_service)
    assert "checkout_command_repo.get_checkout_command_by_public_ref" in source
    assert "checkout_command_repo.claim_provider_create" in source
    assert "checkout_command_repo.attach_provider_session" in source
    assert "Session.create" not in source
    assert "create_checkout_session(" not in source


def test_fail_before_command_read_has_no_provider_call_or_mutation() -> None:
    repository = FakeCheckoutRepository()
    provider = FailIfCreateProvider(found=_session())

    with pytest.raises(
        billing_reconciliation_service.BillingReconciliationInjectedFailure
    ):
        _reconcile(
            repository,
            provider,
            failure_injector=lambda point: (
                (_ for _ in ()).throw(
                    billing_reconciliation_service.BillingReconciliationInjectedFailure(
                        point
                    )
                )
                if point
                is billing_reconciliation_service.BillingReconciliationFailurePoint.BEFORE_COMMAND_READ
                else None
            ),
        )

    assert repository.lookup_calls == []
    assert repository.claim_calls == repository.attach_calls == 0
    assert provider.find_calls == provider.retrieve_calls == []


def test_failure_after_command_before_provider_retries_only_original_command() -> None:
    repository = FakeCheckoutRepository()
    provider = FailIfCreateProvider(found=_session())
    failed = False

    def inject(
        point: billing_reconciliation_service.BillingReconciliationFailurePoint,
    ) -> None:
        nonlocal failed
        if (
            point
            is billing_reconciliation_service.BillingReconciliationFailurePoint.AFTER_COMMAND_BEFORE_PROVIDER
            and not failed
        ):
            failed = True
            raise billing_reconciliation_service.BillingReconciliationInjectedFailure(
                point
            )

    with pytest.raises(
        billing_reconciliation_service.BillingReconciliationInjectedFailure
    ):
        _reconcile(repository, provider, failure_injector=inject)
    assert provider.find_calls == []

    result = _reconcile(
        repository,
        provider,
        now_epoch=NOW_EPOCH + 31,
        now_iso="2026-07-24T10:30:31+00:00",
    )
    assert result.disposition is billing_reconciliation_service.BillingReconciliationDisposition.ATTACHED
    assert repository.lookup_calls == [(CHECKOUT_REF, PARENT_ID)] * 2
    assert repository.attach_calls == 1
    assert provider.find_calls == [(CHECKOUT_REF, PROVIDER_KEY)]


def test_provider_timeout_remains_unknown_then_same_command_recovers() -> None:
    repository = FakeCheckoutRepository()
    provider = FailIfCreateProvider(found=_session())
    provider.find_failures = 1

    unknown = _reconcile(repository, provider)
    assert unknown.disposition is billing_reconciliation_service.BillingReconciliationDisposition.SUPPORT_NEEDED
    assert unknown.failure_code == "provider_outcome_unknown"
    assert repository.unknown_calls == 1
    assert repository.attach_calls == 0

    recovered = _reconcile(
        repository,
        provider,
        now_epoch=NOW_EPOCH + 31,
        now_iso="2026-07-24T10:30:31+00:00",
    )
    assert recovered.disposition is billing_reconciliation_service.BillingReconciliationDisposition.ATTACHED
    assert recovered.command_id == COMMAND_ID
    assert repository.attach_calls == 1


def test_provider_success_then_local_attach_failure_recovers_one_session() -> None:
    repository = FakeCheckoutRepository()
    repository.attach_failures = 1
    provider = FailIfCreateProvider(found=_session())

    first = _reconcile(repository, provider)
    assert first.disposition is billing_reconciliation_service.BillingReconciliationDisposition.RETRYABLE
    assert repository.attach_calls == 1

    second = _reconcile(
        repository,
        provider,
        now_epoch=NOW_EPOCH + 31,
        now_iso="2026-07-24T10:30:31+00:00",
    )
    assert second.disposition is billing_reconciliation_service.BillingReconciliationDisposition.ATTACHED
    assert repository.attach_calls == 2
    assert repository.command["provider_session_id"] == SESSION_ID


def test_failure_after_provider_before_attach_recovers_without_create() -> None:
    repository = FakeCheckoutRepository()
    provider = FailIfCreateProvider(found=_session())
    failed = False

    def inject(
        point: billing_reconciliation_service.BillingReconciliationFailurePoint,
    ) -> None:
        nonlocal failed
        if (
            point
            is billing_reconciliation_service.BillingReconciliationFailurePoint.AFTER_PROVIDER_BEFORE_ATTACH
            and not failed
        ):
            failed = True
            raise billing_reconciliation_service.BillingReconciliationInjectedFailure(
                point
            )

    with pytest.raises(
        billing_reconciliation_service.BillingReconciliationInjectedFailure
    ):
        _reconcile(repository, provider, failure_injector=inject)
    assert repository.attach_calls == 0

    result = _reconcile(
        repository,
        provider,
        now_epoch=NOW_EPOCH + 31,
        now_iso="2026-07-24T10:30:31+00:00",
    )
    assert result.disposition is billing_reconciliation_service.BillingReconciliationDisposition.ATTACHED
    assert repository.attach_calls == 1


def test_local_attach_then_response_loss_replays_same_command() -> None:
    repository = FakeCheckoutRepository()
    provider = FailIfCreateProvider(found=_session(), retrieved=_session())

    with pytest.raises(
        billing_reconciliation_service.BillingReconciliationInjectedFailure
    ):
        _reconcile(
            repository,
            provider,
            failure_injector=lambda point: (
                (_ for _ in ()).throw(
                    billing_reconciliation_service.BillingReconciliationInjectedFailure(
                        point
                    )
                )
                if point
                is billing_reconciliation_service.BillingReconciliationFailurePoint.AFTER_ATTACH_BEFORE_RETURN
                else None
            ),
        )
    assert repository.command["provider_session_id"] == SESSION_ID

    replay = _reconcile(repository, provider)
    assert replay.disposition is billing_reconciliation_service.BillingReconciliationDisposition.REPLAYED
    assert replay.command_id == COMMAND_ID
    assert repository.attach_calls == 1
    assert provider.retrieve_calls == [SESSION_ID]


def test_active_lease_contention_is_bounded_and_has_no_provider_effect() -> None:
    repository = FakeCheckoutRepository(
        _command(
            effect_status="create_claimed",
            command_state=CheckoutCommandState.PROVIDER_CREATE_PENDING,
            lease_expires_at=NOW_EPOCH + 30,
        )
    )
    provider = FailIfCreateProvider(found=_session())

    result = _reconcile(repository, provider)
    assert result.disposition is billing_reconciliation_service.BillingReconciliationDisposition.LEASE_BUSY
    assert result.safe_action == "recheck_payment"
    assert provider.find_calls == provider.retrieve_calls == []
    assert repository.attach_calls == 0


def test_expired_lease_recovers_once_and_repeated_recheck_replays() -> None:
    repository = FakeCheckoutRepository()
    provider = FailIfCreateProvider(found=_session(), retrieved=_session())

    recovered = _reconcile(repository, provider)
    replay = _reconcile(repository, provider)

    assert recovered.disposition is billing_reconciliation_service.BillingReconciliationDisposition.ATTACHED
    assert replay.disposition is billing_reconciliation_service.BillingReconciliationDisposition.REPLAYED
    assert repository.claim_calls == 1
    assert repository.attach_calls == 1
    assert provider.find_calls == [(CHECKOUT_REF, PROVIDER_KEY)]
    assert provider.retrieve_calls == [SESSION_ID]


@pytest.mark.parametrize(
    ("evidence", "failure_code"),
    [
        (_session(checkout_ref=OTHER_CHECKOUT_REF), "provider_identity_mismatch"),
        (
            _session(metadata_checkout_ref=OTHER_CHECKOUT_REF),
            "provider_identity_mismatch",
        ),
        (_session(customer_id="cus_test_foreign"), "provider_owner_mismatch"),
        (_session(price_id="price_test_student_v7"), "provider_price_mismatch"),
        (_session(environment="staging"), "provider_environment_mismatch"),
        (_session(livemode=True), "provider_live_object_refused"),
        (_session(session_id="cs_live_forbidden"), "provider_live_object_refused"),
    ],
)
def test_foreign_or_mismatched_provider_session_never_attaches(
    evidence: billing_reconciliation_service.ProviderCheckoutSessionEvidence,
    failure_code: str,
) -> None:
    repository = FakeCheckoutRepository()
    provider = FailIfCreateProvider(found=evidence)

    result = _reconcile(repository, provider)

    assert result.disposition is billing_reconciliation_service.BillingReconciliationDisposition.SUPPORT_NEEDED
    assert result.failure_code == failure_code
    assert repository.attach_calls == 0


@pytest.mark.parametrize(
    ("status", "disposition", "lifecycle", "action"),
    [
        ("open", "replayed", "confirming", "recheck_payment"),
        ("complete", "confirming", "confirming", "recheck_payment"),
        ("expired", "terminal_not_completed", "not_completed", "start_checkout"),
        ("canceled", "terminal_not_completed", "not_completed", "start_checkout"),
    ],
)
def test_attached_session_status_is_classified_without_activation(
    status: str,
    disposition: str,
    lifecycle: str,
    action: str,
) -> None:
    repository = FakeCheckoutRepository(
        _command(
            effect_status="session_attached",
            command_state=CheckoutCommandState.PROVIDER_SESSION_OPEN,
            provider_session_id=SESSION_ID,
            provider_session_url=SESSION_URL,
        )
    )
    provider = FailIfCreateProvider(retrieved=_session(status=status))

    result = _reconcile(repository, provider)

    assert result.disposition.value == disposition
    assert result.lifecycle_state == lifecycle
    assert result.safe_action == action
    assert result.disposition.value != "active"
    assert repository.claim_calls == repository.attach_calls == 0


def test_activation_recorded_replays_without_provider_access() -> None:
    repository = FakeCheckoutRepository(
        _command(
            effect_status="session_attached",
            command_state=CheckoutCommandState.ACTIVATION_RECORDED,
            provider_session_id=SESSION_ID,
            provider_session_url=SESSION_URL,
        )
    )
    provider = FailIfCreateProvider()

    result = _reconcile(repository, provider)
    assert result.disposition is billing_reconciliation_service.BillingReconciliationDisposition.ACTIVE
    assert result.lifecycle_state == "active"
    assert result.safe_action == "view_billing"
    assert provider.find_calls == provider.retrieve_calls == []


def test_cross_owner_lookup_is_concealed_before_provider_access() -> None:
    repository = FakeCheckoutRepository()
    provider = FailIfCreateProvider(found=_session())

    result = _reconcile(repository, provider, parent_id=OTHER_PARENT_ID)
    assert result.disposition is billing_reconciliation_service.BillingReconciliationDisposition.NOT_FOUND
    assert provider.find_calls == provider.retrieve_calls == []


def test_provider_ambiguity_and_malformed_evidence_never_mean_nonpayment() -> None:
    repository = FakeCheckoutRepository()
    provider = FailIfCreateProvider(found=None)

    no_proof = _reconcile(repository, provider)
    assert no_proof.disposition is billing_reconciliation_service.BillingReconciliationDisposition.SUPPORT_NEEDED
    assert no_proof.lifecycle_state == "support_needed"
    assert no_proof.safe_action == "contact_support"

    attached_repository = FakeCheckoutRepository(
        _command(
            effect_status="session_attached",
            command_state=CheckoutCommandState.PROVIDER_SESSION_OPEN,
            provider_session_id=SESSION_ID,
            provider_session_url=SESSION_URL,
        )
    )
    malformed_provider = FailIfCreateProvider(retrieved=None)
    malformed = _reconcile(attached_repository, malformed_provider)
    assert malformed.disposition is billing_reconciliation_service.BillingReconciliationDisposition.SUPPORT_NEEDED
    assert malformed.lifecycle_state == "support_needed"
    assert malformed.disposition is not billing_reconciliation_service.BillingReconciliationDisposition.TERMINAL_NOT_COMPLETED


def test_support_projection_is_closed_and_redacted() -> None:
    repository = FakeCheckoutRepository()
    provider = FailIfCreateProvider(
        found=replace(_session(), status="complete")
    )
    result = _reconcile(repository, provider)

    support = billing_reconciliation_service.project_checkout_support_state(result)
    assert set(support) == {
        "lifecycleState",
        "lastRecheckedAt",
        "safeAction",
        "failureClass",
        "providerSessionSuffix",
        "reconciliationLeaseGeneration",
    }
    assert support["providerSessionSuffix"] == SESSION_ID[-6:]
    assert support["reconciliationLeaseGeneration"] == 2
    serialized = repr(support)
    for forbidden in (
        PARENT_ID,
        OTHER_PARENT_ID,
        COMMAND_ID,
        CHECKOUT_REF,
        PROVIDER_KEY,
        SESSION_ID,
        SESSION_URL,
        PRICE_ID,
        "cus_test_parent",
        "provider-private-canary",
        "sk_test_",
        "https://",
    ):
        assert forbidden not in serialized


def test_provider_dependency_is_retrieval_only_and_result_fields_are_bounded() -> None:
    members = set(
        billing_reconciliation_service.BillingReconciliationProvider.__protocol_attrs__
    )
    assert members == {"find_checkout_session", "retrieve_checkout_session"}
    fields = set(
        billing_reconciliation_service.BillingReconciliationResult.__dataclass_fields__
    )
    assert {
        "reconciliation_lease_generation",
        "last_rechecked_at",
        "reconciliation_reason",
        "failure_code",
    } <= fields

