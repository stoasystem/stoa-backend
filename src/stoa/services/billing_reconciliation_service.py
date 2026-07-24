"""Lease-bound recovery of one original checkout command.

The provider boundary in this module is deliberately retrieval-only.  Session
creation remains owned by the command-first checkout path; a recheck can only
inspect persisted coordinates and conditionally attach the exact Session that
already belongs to the stored command.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable
from urllib.parse import urlsplit

from stoa.db.dynamodb import get_table
from stoa.db.repositories import checkout_command_repo
from stoa.models.billing import CheckoutCommandState


DEFAULT_RECONCILIATION_LEASE_SECONDS = 30
_SUPPORTED_ENVIRONMENTS = frozenset({"test", "sandbox", "staging"})
_TERMINAL_WITHOUT_PAYMENT_STATUSES = frozenset({"expired", "canceled"})


class BillingReconciliationDisposition(StrEnum):
    """Closed internal outcomes for one owner-authorized recheck."""

    ACTIVE = "active"
    ATTACHED = "attached"
    REPLAYED = "replayed"
    CONFIRMING = "confirming"
    TERMINAL_NOT_COMPLETED = "terminal_not_completed"
    SUPPORT_NEEDED = "support_needed"
    LEASE_BUSY = "lease_busy"
    NOT_FOUND = "not_found"
    RETRYABLE = "retryable"


class BillingReconciliationFailurePoint(StrEnum):
    """Deterministic test-only boundaries around durable and provider effects."""

    BEFORE_COMMAND_READ = "before_command_read"
    AFTER_COMMAND_BEFORE_PROVIDER = "after_command_before_provider"
    AFTER_PROVIDER_BEFORE_ATTACH = "after_provider_before_attach"
    AFTER_ATTACH_BEFORE_RETURN = "after_attach_before_return"


class BillingReconciliationInjectedFailure(RuntimeError):
    """Raised only by a caller-supplied deterministic failure injector."""


@dataclass(frozen=True, slots=True)
class ProviderCheckoutSessionEvidence:
    """Normalized provider read containing only fields needed for reconciliation."""

    session_id: str
    checkout_url: str
    client_reference_id: str
    metadata_checkout_ref: str
    customer_id: str
    price_id: str
    environment: str
    livemode: bool
    status: str
    created_at: str


@runtime_checkable
class BillingReconciliationProvider(Protocol):
    """Retrieval-only provider capability; creation is intentionally impossible."""

    def find_checkout_session(
        self,
        *,
        checkout_ref: str,
        provider_key_digest: str,
    ) -> ProviderCheckoutSessionEvidence | None: ...

    def retrieve_checkout_session(
        self,
        *,
        session_id: str,
    ) -> ProviderCheckoutSessionEvidence: ...


@runtime_checkable
class _WebhookCommandTable(Protocol):
    """Least-capability table boundary for signed webhook command binding."""

    def get_item(self, **kwargs: object) -> object: ...

    def update_item(self, **kwargs: object) -> object: ...


class BillingReconciliationRepository(Protocol):
    """Narrow checkout repository surface used by reconciliation."""

    def get_checkout_command_by_public_ref(
        self,
        checkout_ref: str,
        *,
        parent_id: str,
        table: object | None = None,
    ) -> checkout_command_repo.CheckoutCommandResult: ...

    def claim_provider_create(
        self,
        command: Mapping[str, object],
        *,
        lease_owner: str,
        now_epoch: int,
        lease_expires_at: int,
        now_iso: str,
        table: object | None = None,
    ) -> checkout_command_repo.CheckoutCommandResult: ...

    def attach_provider_session(
        self,
        claim: checkout_command_repo.ProviderCreateClaim,
        *,
        provider_session_id: str,
        provider_session_url: str,
        now_iso: str,
        table: object | None = None,
    ) -> checkout_command_repo.CheckoutCommandResult: ...

    def mark_provider_outcome_unknown(
        self,
        claim: checkout_command_repo.ProviderCreateClaim,
        *,
        now_iso: str,
        table: object | None = None,
    ) -> checkout_command_repo.CheckoutCommandResult: ...


class _CheckoutCommandRepositoryAdapter:
    """Bind the production dependency without exposing a provider capability."""

    get_checkout_command_by_public_ref = staticmethod(
        checkout_command_repo.get_checkout_command_by_public_ref
    )
    claim_provider_create = staticmethod(checkout_command_repo.claim_provider_create)
    attach_provider_session = staticmethod(
        checkout_command_repo.attach_provider_session
    )
    mark_provider_outcome_unknown = staticmethod(
        checkout_command_repo.mark_provider_outcome_unknown
    )


_DEFAULT_REPOSITORY = _CheckoutCommandRepositoryAdapter()


@dataclass(frozen=True, slots=True)
class BillingReconciliationResult:
    """Internal result with a separately allowlisted support projection."""

    disposition: BillingReconciliationDisposition
    command_id: str | None
    lifecycle_state: str
    safe_action: str
    reconciliation_lease_generation: int
    last_rechecked_at: str
    reconciliation_reason: str
    failure_code: str | None = None
    provider_session_id: str | None = None


type FailureInjector = Callable[[BillingReconciliationFailurePoint], None]


def _required_text(
    value: object,
    field: str,
    *,
    maximum: int = 255,
) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} is invalid")
    if len(value) > maximum or any(character.isspace() for character in value):
        raise ValueError(f"{field} is invalid")
    return value


def _webhook_item(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or any(
        not isinstance(key, str) for key in value
    ):
        raise ValueError("billing webhook dependency returned malformed data")
    return {str(key): member for key, member in value.items()}


def _webhook_get(
    table: object,
    key: Mapping[str, str],
) -> dict[str, object] | None:
    if not isinstance(table, _WebhookCommandTable):
        raise ValueError("billing webhook persistence is unavailable")
    response = table.get_item(Key=dict(key), ConsistentRead=True)
    if not isinstance(response, Mapping):
        raise ValueError("billing webhook dependency returned malformed data")
    return _webhook_item(response.get("Item"))


def load_checkout_command_for_webhook(
    checkout_ref: str,
    *,
    table: object | None = None,
) -> dict[str, object] | None:
    """Resolve one provider metadata reference to its exact durable command."""
    reference = _required_text(checkout_ref, "checkout_ref")
    target = table or get_table()
    lookup = _webhook_get(
        target,
        {"PK": f"CHECKOUT_PUBLIC#{reference}", "SK": "LOOKUP"},
    )
    if (
        lookup is None
        or lookup.get("entity_type") != "checkout_public_lookup"
        or lookup.get("schema_version") != checkout_command_repo.PUBLIC_LOOKUP_SCHEMA_VERSION
        or lookup.get("checkout_ref") != reference
        or not isinstance(lookup.get("command_id"), str)
    ):
        return None
    command_id = str(lookup["command_id"])
    command = _webhook_get(
        target,
        {"PK": f"CHECKOUT_COMMAND#{command_id}", "SK": "COMMAND"},
    )
    if (
        command is None
        or command.get("entity_type") != "checkout_command"
        or command.get("schema_version") != checkout_command_repo.COMMAND_SCHEMA_VERSION
        or command.get("command_id") != command_id
        or command.get("checkout_ref") != reference
        or command.get("parent_id") != lookup.get("parent_id")
    ):
        return None
    return command


def bind_webhook_provider_identity(
    command: Mapping[str, object],
    *,
    provider_customer_id_digest: str,
    provider_subscription_id_digest: str,
    expected_initial_invoice_id_digest: str,
    now_iso: str,
    table: object | None = None,
) -> dict[str, object] | None:
    """Conditionally bind verified provider objects to one immutable command."""
    command_id = _required_text(command.get("command_id"), "command_id")
    parent_id = _required_text(command.get("parent_id"), "parent_id")
    command_version = command.get("command_version")
    if type(command_version) is not int or command_version < 1:
        raise ValueError("command_version is invalid")
    digests = {
        "provider_customer_id_digest": _required_text(
            provider_customer_id_digest,
            "provider_customer_id_digest",
            maximum=64,
        ),
        "provider_subscription_id_digest": _required_text(
            provider_subscription_id_digest,
            "provider_subscription_id_digest",
            maximum=64,
        ),
        "expected_initial_invoice_id_digest": _required_text(
            expected_initial_invoice_id_digest,
            "expected_initial_invoice_id_digest",
            maximum=64,
        ),
    }
    if any(
        len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
        for value in digests.values()
    ):
        raise ValueError("provider identity digest is invalid")
    timestamp = _required_text(now_iso, "now_iso", maximum=64)
    target = table or get_table()
    if not isinstance(target, _WebhookCommandTable):
        raise ValueError("billing webhook persistence is unavailable")

    if all(command.get(key) == value for key, value in digests.items()):
        return dict(command)
    if any(
        command.get(key) not in {None, value}
        for key, value in digests.items()
    ):
        return None
    values: dict[str, object] = {
        ":entity": "checkout_command",
        ":schema": checkout_command_repo.COMMAND_SCHEMA_VERSION,
        ":command_id": command_id,
        ":parent_id": parent_id,
        ":expected_version": command_version,
        ":next_version": command_version + 1,
        ":reconciling": CheckoutCommandState.RECONCILING,
        ":updated_at": timestamp,
        **{f":{key}": value for key, value in digests.items()},
    }
    try:
        response = target.update_item(
            Key={"PK": f"CHECKOUT_COMMAND#{command_id}", "SK": "COMMAND"},
            UpdateExpression=(
                "SET provider_customer_id_digest=:provider_customer_id_digest, "
                "provider_subscription_id_digest=:provider_subscription_id_digest, "
                "expected_initial_invoice_id_digest=:expected_initial_invoice_id_digest, "
                "command_state=:reconciling, command_version=:next_version, "
                "updated_at=:updated_at"
            ),
            ConditionExpression=(
                "entity_type=:entity AND schema_version=:schema "
                "AND command_id=:command_id AND parent_id=:parent_id "
                "AND command_version=:expected_version "
                "AND (attribute_not_exists(provider_customer_id_digest) "
                "OR provider_customer_id_digest=:provider_customer_id_digest) "
                "AND (attribute_not_exists(provider_subscription_id_digest) "
                "OR provider_subscription_id_digest=:provider_subscription_id_digest) "
                "AND (attribute_not_exists(expected_initial_invoice_id_digest) "
                "OR expected_initial_invoice_id_digest=:expected_initial_invoice_id_digest)"
            ),
            ExpressionAttributeValues=values,
            ReturnValues="ALL_NEW",
        )
    except Exception:
        refreshed = _webhook_get(
            target,
            {"PK": f"CHECKOUT_COMMAND#{command_id}", "SK": "COMMAND"},
        )
        if refreshed is not None and all(
            refreshed.get(key) == value for key, value in digests.items()
        ):
            return refreshed
        return None
    if not isinstance(response, Mapping):
        return None
    updated = _webhook_item(response.get("Attributes"))
    if updated is None or not all(
        updated.get(key) == value for key, value in digests.items()
    ):
        return None
    return updated


def _generation(command: Mapping[str, object]) -> int:
    value = command.get("lease_generation")
    return value if type(value) is int and value >= 0 else 0


def _command_id(command: Mapping[str, object]) -> str | None:
    value = command.get("command_id")
    return value if isinstance(value, str) and value else None


def _result(
    disposition: BillingReconciliationDisposition,
    *,
    command: Mapping[str, object] | None,
    now_iso: str,
    lifecycle_state: str,
    safe_action: str,
    reason: str,
    failure_code: str | None = None,
    provider_session_id: str | None = None,
) -> BillingReconciliationResult:
    return BillingReconciliationResult(
        disposition=disposition,
        command_id=_command_id(command or {}),
        lifecycle_state=lifecycle_state,
        safe_action=safe_action,
        reconciliation_lease_generation=_generation(command or {}),
        last_rechecked_at=now_iso,
        reconciliation_reason=reason,
        failure_code=failure_code,
        provider_session_id=provider_session_id,
    )


def _inject(
    failure_injector: FailureInjector | None,
    point: BillingReconciliationFailurePoint,
) -> None:
    if failure_injector is not None:
        failure_injector(point)


def _support_needed(
    *,
    command: Mapping[str, object] | None,
    now_iso: str,
    reason: str,
    failure_code: str,
    provider_session_id: str | None = None,
) -> BillingReconciliationResult:
    return _result(
        BillingReconciliationDisposition.SUPPORT_NEEDED,
        command=command,
        now_iso=now_iso,
        lifecycle_state="support_needed",
        safe_action="contact_support",
        reason=reason,
        failure_code=failure_code,
        provider_session_id=provider_session_id,
    )


def _validate_provider_evidence(
    evidence: ProviderCheckoutSessionEvidence,
    *,
    command: Mapping[str, object],
) -> str | None:
    """Return a closed mismatch code or ``None`` for exact sandbox evidence."""
    try:
        session_id = _required_text(evidence.session_id, "session_id")
        checkout_url = _required_text(
            evidence.checkout_url, "checkout_url", maximum=2048
        )
        client_reference = _required_text(
            evidence.client_reference_id, "client_reference_id"
        )
        metadata_reference = _required_text(
            evidence.metadata_checkout_ref, "metadata_checkout_ref"
        )
        customer_id = _required_text(evidence.customer_id, "customer_id")
        price_id = _required_text(evidence.price_id, "price_id")
        environment = _required_text(
            evidence.environment, "environment", maximum=32
        ).lower()
        status = _required_text(evidence.status, "status", maximum=32).lower()
        _required_text(evidence.created_at, "created_at", maximum=64)
    except (AttributeError, TypeError, ValueError):
        return "provider_evidence_malformed"

    if evidence.livemode is not False or not session_id.startswith("cs_test_"):
        return "provider_live_object_refused"
    parsed_url = urlsplit(checkout_url)
    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname != "checkout.stripe.com"
        or parsed_url.username is not None
        or parsed_url.password is not None
    ):
        return "provider_evidence_malformed"

    checkout_ref = command.get("checkout_ref")
    if (
        not isinstance(checkout_ref, str)
        or client_reference != checkout_ref
        or metadata_reference != checkout_ref
    ):
        return "provider_identity_mismatch"

    expected_customer = command.get("provider_customer_id")
    if isinstance(expected_customer, str) and customer_id != expected_customer:
        return "provider_owner_mismatch"
    if price_id != command.get("price_id"):
        return "provider_price_mismatch"

    expected_environment = str(command.get("environment") or "").lower()
    if (
        environment not in _SUPPORTED_ENVIRONMENTS
        or expected_environment not in _SUPPORTED_ENVIRONMENTS
        or environment != expected_environment
    ):
        return "provider_environment_mismatch"
    if status not in {"open", "complete", *_TERMINAL_WITHOUT_PAYMENT_STATUSES}:
        return "provider_status_unknown"
    return None


def _classify_provider_session(
    evidence: ProviderCheckoutSessionEvidence,
    *,
    command: Mapping[str, object],
    now_iso: str,
    open_disposition: BillingReconciliationDisposition,
) -> BillingReconciliationResult:
    mismatch = _validate_provider_evidence(evidence, command=command)
    if mismatch is not None:
        return _support_needed(
            command=command,
            now_iso=now_iso,
            reason="provider_evidence_refused",
            failure_code=mismatch,
        )

    status = evidence.status.lower()
    if status in _TERMINAL_WITHOUT_PAYMENT_STATUSES:
        return _result(
            BillingReconciliationDisposition.TERMINAL_NOT_COMPLETED,
            command=command,
            now_iso=now_iso,
            lifecycle_state="not_completed",
            safe_action="start_checkout",
            reason="provider_terminal_without_payment",
            provider_session_id=evidence.session_id,
        )
    if status == "complete":
        return _result(
            BillingReconciliationDisposition.CONFIRMING,
            command=command,
            now_iso=now_iso,
            lifecycle_state="confirming",
            safe_action="recheck_payment",
            reason="provider_checkout_complete_awaiting_authoritative_activation",
            provider_session_id=evidence.session_id,
        )
    return _result(
        open_disposition,
        command=command,
        now_iso=now_iso,
        lifecycle_state="confirming",
        safe_action="recheck_payment",
        reason=(
            "provider_session_attached"
            if open_disposition is BillingReconciliationDisposition.ATTACHED
            else "provider_session_replayed"
        ),
        provider_session_id=evidence.session_id,
    )


def _mark_unknown(
    repository: BillingReconciliationRepository,
    claim: checkout_command_repo.ProviderCreateClaim,
    *,
    now_iso: str,
    table: object | None,
) -> Mapping[str, object] | None:
    try:
        result = repository.mark_provider_outcome_unknown(
            claim,
            now_iso=now_iso,
            table=table,
        )
    except Exception:
        return None
    return result.command


def _reconcile_attached(
    *,
    command: Mapping[str, object],
    provider: BillingReconciliationProvider,
    now_iso: str,
) -> BillingReconciliationResult:
    session_id = command.get("provider_session_id")
    if not isinstance(session_id, str) or not session_id:
        return _support_needed(
            command=command,
            now_iso=now_iso,
            reason="attached_command_missing_session_identity",
            failure_code="local_attachment_malformed",
        )
    try:
        evidence = provider.retrieve_checkout_session(session_id=session_id)
    except Exception:
        return _support_needed(
            command=command,
            now_iso=now_iso,
            reason="provider_read_unavailable",
            failure_code="provider_read_unavailable",
            provider_session_id=session_id,
        )
    return _classify_provider_session(
        evidence,
        command=command,
        now_iso=now_iso,
        open_disposition=BillingReconciliationDisposition.REPLAYED,
    )


def reconcile_checkout_command(
    checkout_ref: str,
    *,
    parent_id: str,
    lease_owner: str,
    provider: BillingReconciliationProvider,
    now_epoch: int,
    now_iso: str,
    lease_seconds: int = DEFAULT_RECONCILIATION_LEASE_SECONDS,
    repository: BillingReconciliationRepository = _DEFAULT_REPOSITORY,
    table: object | None = None,
    failure_injector: FailureInjector | None = None,
) -> BillingReconciliationResult:
    """Recheck and repair only the original owner-authorized checkout command."""
    reference = _required_text(checkout_ref, "checkout_ref")
    owner = _required_text(parent_id, "parent_id")
    worker = _required_text(lease_owner, "lease_owner")
    timestamp = _required_text(now_iso, "now_iso", maximum=64)
    if (
        type(now_epoch) is not int
        or now_epoch < 0
        or type(lease_seconds) is not int
        or lease_seconds < 1
        or lease_seconds > 300
    ):
        raise ValueError("reconciliation lease is invalid")
    if not isinstance(provider, BillingReconciliationProvider):
        raise ValueError("retrieval-only provider dependency is required")

    _inject(
        failure_injector,
        BillingReconciliationFailurePoint.BEFORE_COMMAND_READ,
    )
    try:
        lookup = repository.get_checkout_command_by_public_ref(
            reference,
            parent_id=owner,
            table=table,
        )
    except Exception:
        return _result(
            BillingReconciliationDisposition.RETRYABLE,
            command=None,
            now_iso=timestamp,
            lifecycle_state="support_needed",
            safe_action="recheck_payment",
            reason="command_read_unavailable",
            failure_code="checkout_dependency_unavailable",
        )
    if lookup.disposition is checkout_command_repo.CheckoutCommandDisposition.NOT_FOUND:
        return _result(
            BillingReconciliationDisposition.NOT_FOUND,
            command=None,
            now_iso=timestamp,
            lifecycle_state="support_needed",
            safe_action="contact_support",
            reason="checkout_not_found",
            failure_code="checkout_not_found",
        )
    if (
        lookup.disposition is not checkout_command_repo.CheckoutCommandDisposition.REPLAYED
        or lookup.command is None
    ):
        disposition = (
            BillingReconciliationDisposition.RETRYABLE
            if lookup.disposition
            is checkout_command_repo.CheckoutCommandDisposition.RETRYABLE
            else BillingReconciliationDisposition.SUPPORT_NEEDED
        )
        return _result(
            disposition,
            command=lookup.command,
            now_iso=timestamp,
            lifecycle_state="support_needed",
            safe_action=(
                "recheck_payment"
                if disposition is BillingReconciliationDisposition.RETRYABLE
                else "contact_support"
            ),
            reason="checkout_evidence_unavailable",
            failure_code="checkout_evidence_unavailable",
        )

    command: Mapping[str, object] = lookup.command
    try:
        command_state = CheckoutCommandState(str(command.get("command_state") or ""))
    except ValueError:
        return _support_needed(
            command=command,
            now_iso=timestamp,
            reason="checkout_command_malformed",
            failure_code="checkout_command_malformed",
        )

    if command_state is CheckoutCommandState.ACTIVATION_RECORDED:
        return _result(
            BillingReconciliationDisposition.ACTIVE,
            command=command,
            now_iso=timestamp,
            lifecycle_state="active",
            safe_action="view_billing",
            reason="authoritative_activation_recorded",
            provider_session_id=(
                str(command["provider_session_id"])
                if isinstance(command.get("provider_session_id"), str)
                else None
            ),
        )
    if command_state is CheckoutCommandState.TERMINAL_WITHOUT_PAYMENT:
        return _result(
            BillingReconciliationDisposition.TERMINAL_NOT_COMPLETED,
            command=command,
            now_iso=timestamp,
            lifecycle_state="not_completed",
            safe_action="start_checkout",
            reason="terminal_without_payment_recorded",
        )
    if command.get("provider_effect_status") == "session_attached":
        return _reconcile_attached(
            command=command,
            provider=provider,
            now_iso=timestamp,
        )

    try:
        claim_result = repository.claim_provider_create(
            command,
            lease_owner=worker,
            now_epoch=now_epoch,
            lease_expires_at=now_epoch + lease_seconds,
            now_iso=timestamp,
            table=table,
        )
    except Exception:
        return _result(
            BillingReconciliationDisposition.RETRYABLE,
            command=command,
            now_iso=timestamp,
            lifecycle_state="support_needed",
            safe_action="recheck_payment",
            reason="reconciliation_claim_unavailable",
            failure_code="checkout_dependency_unavailable",
        )
    if (
        claim_result.disposition
        is checkout_command_repo.CheckoutCommandDisposition.ALREADY_ATTACHED
        and claim_result.command is not None
    ):
        return _reconcile_attached(
            command=claim_result.command,
            provider=provider,
            now_iso=timestamp,
        )
    if (
        claim_result.disposition
        is checkout_command_repo.CheckoutCommandDisposition.LEASE_BUSY
    ):
        return _result(
            BillingReconciliationDisposition.LEASE_BUSY,
            command=claim_result.command or command,
            now_iso=timestamp,
            lifecycle_state="confirming",
            safe_action="recheck_payment",
            reason="reconciliation_lease_busy",
            failure_code="reconciliation_in_progress",
        )
    if (
        claim_result.disposition
        is not checkout_command_repo.CheckoutCommandDisposition.CLAIMED
        or claim_result.provider_claim is None
        or claim_result.command is None
    ):
        return _result(
            BillingReconciliationDisposition.RETRYABLE,
            command=claim_result.command or command,
            now_iso=timestamp,
            lifecycle_state="support_needed",
            safe_action="recheck_payment",
            reason="reconciliation_claim_conflict",
            failure_code="reconciliation_retry_required",
        )

    claimed_command = claim_result.command
    claim = claim_result.provider_claim
    _inject(
        failure_injector,
        BillingReconciliationFailurePoint.AFTER_COMMAND_BEFORE_PROVIDER,
    )
    try:
        evidence = provider.find_checkout_session(
            checkout_ref=reference,
            provider_key_digest=str(claim.provider_key_digest),
        )
    except Exception:
        unknown_command = _mark_unknown(
            repository,
            claim,
            now_iso=timestamp,
            table=table,
        )
        return _support_needed(
            command=unknown_command or claimed_command,
            now_iso=timestamp,
            reason="provider_outcome_unknown",
            failure_code="provider_outcome_unknown",
        )
    if evidence is None:
        unknown_command = _mark_unknown(
            repository,
            claim,
            now_iso=timestamp,
            table=table,
        )
        return _support_needed(
            command=unknown_command or claimed_command,
            now_iso=timestamp,
            reason="provider_outcome_unknown",
            failure_code="provider_outcome_unknown",
        )

    mismatch = _validate_provider_evidence(evidence, command=claimed_command)
    if mismatch is not None:
        unknown_command = _mark_unknown(
            repository,
            claim,
            now_iso=timestamp,
            table=table,
        )
        return _support_needed(
            command=unknown_command or claimed_command,
            now_iso=timestamp,
            reason="provider_evidence_refused",
            failure_code=mismatch,
        )

    _inject(
        failure_injector,
        BillingReconciliationFailurePoint.AFTER_PROVIDER_BEFORE_ATTACH,
    )
    try:
        attached = repository.attach_provider_session(
            claim,
            provider_session_id=evidence.session_id,
            provider_session_url=evidence.checkout_url,
            now_iso=timestamp,
            table=table,
        )
    except Exception:
        return _result(
            BillingReconciliationDisposition.RETRYABLE,
            command=claimed_command,
            now_iso=timestamp,
            lifecycle_state="support_needed",
            safe_action="recheck_payment",
            reason="local_attachment_unavailable",
            failure_code="local_attachment_unavailable",
            provider_session_id=evidence.session_id,
        )
    if (
        attached.disposition
        not in {
            checkout_command_repo.CheckoutCommandDisposition.ATTACHED,
            checkout_command_repo.CheckoutCommandDisposition.ALREADY_ATTACHED,
        }
        or attached.command is None
    ):
        return _result(
            BillingReconciliationDisposition.RETRYABLE,
            command=attached.command or claimed_command,
            now_iso=timestamp,
            lifecycle_state="support_needed",
            safe_action="recheck_payment",
            reason="local_attachment_unavailable",
            failure_code="local_attachment_unavailable",
            provider_session_id=evidence.session_id,
        )
    _inject(
        failure_injector,
        BillingReconciliationFailurePoint.AFTER_ATTACH_BEFORE_RETURN,
    )
    return _classify_provider_session(
        evidence,
        command=attached.command,
        now_iso=timestamp,
        open_disposition=BillingReconciliationDisposition.ATTACHED,
    )


def project_checkout_support_state(
    result: BillingReconciliationResult,
) -> dict[str, object]:
    """Project one allowlisted support state with suffix-only provider identity."""
    if not isinstance(result, BillingReconciliationResult):
        raise ValueError("billing reconciliation result is required")
    provider_suffix = (
        result.provider_session_id[-6:]
        if isinstance(result.provider_session_id, str)
        and len(result.provider_session_id) >= 6
        else None
    )
    return {
        "lifecycleState": result.lifecycle_state,
        "lastRecheckedAt": result.last_rechecked_at,
        "safeAction": result.safe_action,
        "failureClass": result.failure_code or "none",
        "providerSessionSuffix": provider_suffix,
        "reconciliationLeaseGeneration": result.reconciliation_lease_generation,
    }


__all__ = [
    "BillingReconciliationDisposition",
    "BillingReconciliationFailurePoint",
    "BillingReconciliationInjectedFailure",
    "BillingReconciliationProvider",
    "BillingReconciliationResult",
    "ProviderCheckoutSessionEvidence",
    "project_checkout_support_state",
    "reconcile_checkout_command",
]
