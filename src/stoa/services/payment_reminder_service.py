"""Safe, idempotent payment-method expiry reminder orchestration."""

from __future__ import annotations

import calendar
import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from enum import StrEnum
from typing import Protocol
from zoneinfo import ZoneInfo

from stoa.db.repositories import notification_repo
from stoa.services import notification_service, paid_entitlement_service


REMINDER_SCHEMA_VERSION = "payment_expiry_reminder.v1"
ZURICH = ZoneInfo("Europe/Zurich")
_HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_BRAND = re.compile(r"^[a-z0-9][a-z0-9 _-]{0,23}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_UNSAFE_PAYMENT_KEYS = frozenset(
    {
        "account_number",
        "api_key",
        "card_number",
        "client_secret",
        "cvc",
        "cvv",
        "fingerprint",
        "number",
        "pan",
        "secret",
        "token",
    }
)


class PaymentReminderDisposition(StrEnum):
    """Closed scheduler outcomes for one observed method/month."""

    PENDING = "pending"
    DELIVERED = "delivered"
    REPLAYED = "replayed"
    RESOLVED = "resolved"


@dataclass(frozen=True, slots=True)
class EmailEligibility:
    """Conservative verified-deliverable email decision."""

    eligible: bool
    reason: str
    address: str | None = None


@dataclass(frozen=True, slots=True)
class BillingReminderRecipient:
    """One exact current family account and its private-delivery generation."""

    account_id: str
    role: str
    account_fence_generation: int
    email_eligibility: EmailEligibility


@dataclass(frozen=True, slots=True)
class PaymentReminderDelivery:
    """Safe result for one independently processed recipient/channel intent."""

    recipient_id: str
    channel: str
    operation_id: str
    status: str


@dataclass(frozen=True, slots=True)
class PaymentReminderRun:
    """Safe scheduler result without provider identifiers or email addresses."""

    disposition: PaymentReminderDisposition
    reminder: dict[str, object]
    deliveries: tuple[PaymentReminderDelivery, ...] = ()


class PaymentMethodProvider(Protocol):
    """Provider adapter that resolves a subscription's actual default method."""

    def resolve_default_payment_method(
        self, subscription: Mapping[str, object]
    ) -> Mapping[str, object]: ...


ProfileResolver = Callable[[str], Mapping[str, object] | None]
InAppDelivery = Callable[[str, Mapping[str, object]], None]
EmailDelivery = Callable[[str, Mapping[str, object]], None]


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is invalid")
    return value.strip()


def _positive_integer(value: object, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field} is invalid")
    return value


def _digest(value: Mapping[str, object]) -> str:
    encoded = json.dumps(
        dict(value), ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _contains_unsafe_payment_key(value: object) -> bool:
    if isinstance(value, Mapping):
        for raw_key, member in value.items():
            key = str(raw_key).strip().lower().replace("-", "_")
            if key in _UNSAFE_PAYMENT_KEYS:
                return True
            if _contains_unsafe_payment_key(member):
                return True
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_unsafe_payment_key(member) for member in value)
    return False


def project_masked_payment_method(
    payment_method: Mapping[str, object],
    *,
    source_subscription_digest: str,
    observation_version: int,
) -> dict[str, object]:
    """Return the closed safe projection and reject card-secret-shaped inputs."""
    if not isinstance(payment_method, Mapping) or _contains_unsafe_payment_key(payment_method):
        raise ValueError("unsafe payment method data")
    if payment_method.get("type") not in {None, "card"}:
        raise ValueError("unsupported payment method")
    provider_id = _required_text(payment_method.get("id"), "payment method")
    if len(provider_id) > 256:
        raise ValueError("payment method is invalid")
    card = payment_method.get("card")
    if not isinstance(card, Mapping):
        raise ValueError("payment method card is invalid")
    brand = _required_text(card.get("brand"), "payment method brand").lower()
    if not _BRAND.fullmatch(brand):
        raise ValueError("payment method brand is invalid")
    last4 = _required_text(card.get("last4"), "payment method last4")
    if len(last4) != 4 or not last4.isascii() or not last4.isdigit():
        raise ValueError("payment method last4 is invalid")
    exp_month = _positive_integer(card.get("exp_month"), "payment method expiry")
    exp_year = _positive_integer(card.get("exp_year"), "payment method expiry")
    if not 1 <= exp_month <= 12 or not 2000 <= exp_year <= 9999:
        raise ValueError("payment method expiry is invalid")
    source_digest = _required_text(source_subscription_digest, "source subscription digest").lower()
    if not _HEX_DIGEST.fullmatch(source_digest):
        raise ValueError("source subscription digest is invalid")
    observed_version = _positive_integer(observation_version, "observation version")
    method_digest = hashlib.sha256(f"stoa.payment-method.v1:{provider_id}".encode()).hexdigest()
    return {
        "payment_method_digest": method_digest,
        "brand": brand,
        "last4": last4,
        "exp_month": exp_month,
        "exp_year": exp_year,
        "source_subscription_digest": source_digest,
        "observation_version": observed_version,
    }


def payment_expiry_reminder_at(*, exp_month: int, exp_year: int) -> datetime:
    """Return Zurich midnight seven local calendar days before month end."""
    month = _positive_integer(exp_month, "expiry month")
    year = _positive_integer(exp_year, "expiry year")
    if not 1 <= month <= 12 or not 2000 <= year <= 9999:
        raise ValueError("payment method expiry is invalid")
    last_day = calendar.monthrange(year, month)[1]
    month_end = datetime.combine(datetime(year, month, last_day).date(), time.min, tzinfo=ZURICH)
    return month_end - timedelta(days=7)


def _email_eligibility(profile: Mapping[str, object]) -> EmailEligibility:
    raw_address = profile.get("email")
    address = raw_address.strip().lower() if isinstance(raw_address, str) else ""
    if not address or not _EMAIL.fullmatch(address):
        return EmailEligibility(False, "invalid")
    verification = str(profile.get("email_verification_status") or "").lower()
    if verification != "verified" and profile.get("email_verified") is not True:
        return EmailEligibility(False, "unverified")
    delivery = str(profile.get("email_delivery_status") or "").lower()
    if delivery == "bounced":
        return EmailEligibility(False, "bounced")
    if delivery == "suppressed":
        return EmailEligibility(False, "suppressed")
    if delivery != "deliverable":
        return EmailEligibility(False, "unknown")
    return EmailEligibility(True, "deliverable", address)


def _recipient_from_profile(
    profile: Mapping[str, object] | None,
    *,
    account_id: str,
    expected_role: str,
) -> BillingReminderRecipient | None:
    if (
        not isinstance(profile, Mapping)
        or profile.get("user_id") != account_id
        or profile.get("role") != expected_role
        or profile.get("account_status") != "active"
    ):
        return None
    generation = _positive_integer(
        profile.get("account_fence_generation"), "account fence generation"
    )
    return BillingReminderRecipient(
        account_id=account_id,
        role=expected_role,
        account_fence_generation=generation,
        email_eligibility=_email_eligibility(profile),
    )


def resolve_billing_reminder_recipients(
    *,
    parent_id: str,
    beneficiary_ids: Sequence[str],
    subscription_id_digest: str,
    profile_resolver: ProfileResolver,
    table: object | None = None,
) -> tuple[BillingReminderRecipient, ...]:
    """Resolve parent plus current explicit grant beneficiaries only."""
    parent = _required_text(parent_id, "parent")
    digest = _required_text(subscription_id_digest, "source subscription digest").lower()
    if not _HEX_DIGEST.fullmatch(digest):
        raise ValueError("source subscription digest is invalid")
    parent_recipient = _recipient_from_profile(
        profile_resolver(parent), account_id=parent, expected_role="parent"
    )
    if parent_recipient is None:
        raise ValueError("parent reminder profile is invalid")
    if (
        not isinstance(beneficiary_ids, Sequence)
        or isinstance(beneficiary_ids, (str, bytes, bytearray))
        or len(beneficiary_ids) != len(set(beneficiary_ids))
    ):
        raise ValueError("beneficiary ids are invalid")
    recipients = [parent_recipient]
    for raw_beneficiary_id in beneficiary_ids:
        beneficiary_id = _required_text(raw_beneficiary_id, "beneficiary")
        grant = paid_entitlement_service.get_active_beneficiary_grant(
            parent, beneficiary_id, table=table
        )
        if (
            not isinstance(grant, Mapping)
            or grant.get("parent_id") != parent
            or grant.get("beneficiary_id") != beneficiary_id
            or grant.get("subscription_id_digest") != digest
        ):
            continue
        recipient = _recipient_from_profile(
            profile_resolver(beneficiary_id),
            account_id=beneficiary_id,
            expected_role="student",
        )
        if recipient is not None:
            recipients.append(recipient)
    return tuple(recipients)


def _reminder_identity(projected: Mapping[str, object]) -> str:
    return _digest(
        {
            "domain": "stoa.payment-expiry-reminder.v1",
            "payment_method_digest": projected["payment_method_digest"],
            "exp_month": projected["exp_month"],
            "exp_year": projected["exp_year"],
        }
    )


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _safe_reminder(row: Mapping[str, object]) -> dict[str, object]:
    return {
        key: row.get(key)
        for key in (
            "schema_version",
            "payment_method_digest",
            "brand",
            "last4",
            "exp_month",
            "exp_year",
            "source_subscription_digest",
            "observation_version",
            "reminder_identity",
            "reminder_at",
            "status",
            "resolved_at",
            "notified_at",
        )
        if key in row
    }


def clear_replaced_payment_reminder(
    *,
    parent_id: str,
    current_reminder_identity: str,
    current_observation_version: int,
    resolved_at: datetime,
    table: object | None = None,
) -> tuple[dict[str, object], ...]:
    """Resolve every prior method/month as soon as a replacement is observed."""
    parent = _required_text(parent_id, "parent")
    current_identity = _required_text(current_reminder_identity, "payment reminder identity")
    current_version = _positive_integer(current_observation_version, "observation version")
    resolved: list[dict[str, object]] = []
    for item in notification_repo.list_payment_expiry_reminders(parent, table=table):
        identity = str(item.get("reminder_identity") or "")
        item_version = _positive_integer(item.get("observation_version"), "observation version")
        if item_version > current_version:
            continue
        if item_version == current_version and identity != current_identity:
            raise ValueError("payment method observation version conflicts")
        if (
            identity
            and identity != current_identity
            and item_version < current_version
            and item.get("status") != "resolved"
        ):
            updated = notification_repo.resolve_payment_expiry_reminder(
                parent,
                identity,
                resolved_at=_iso(resolved_at),
                table=table,
            )
            if updated is not None:
                resolved.append(_safe_reminder(updated))
    return tuple(resolved)


def _delivery_operation_id(
    *,
    reminder_identity: str,
    recipient_id: str,
    channel: str,
) -> str:
    identity = _digest(
        {
            "domain": "stoa.payment-expiry-delivery.v1",
            "reminder_identity": reminder_identity,
            "recipient_id": recipient_id,
            "channel": channel,
        }
    )
    return f"payment-expiry-{identity[:40]}"


def run_payment_expiry_reminders(
    *,
    subscription: Mapping[str, object],
    provider: PaymentMethodProvider,
    profile_resolver: ProfileResolver,
    deliver_in_app: InAppDelivery,
    deliver_email: EmailDelivery,
    now: datetime | None = None,
    table: object | None = None,
) -> PaymentReminderRun:
    """Observe, persist, clear, and independently deliver one safe reminder."""
    if not isinstance(subscription, Mapping):
        raise ValueError("subscription is invalid")
    observation = dict(subscription)
    parent_id = _required_text(observation.get("parent_id"), "parent")
    subscription_digest = _required_text(
        observation.get("provider_subscription_id_digest"),
        "source subscription digest",
    )
    beneficiaries = observation.get("beneficiary_ids")
    if not isinstance(beneficiaries, Sequence) or isinstance(
        beneficiaries, (str, bytes, bytearray)
    ):
        raise ValueError("beneficiary ids are invalid")
    observed_at = now or datetime.now(timezone.utc)
    if observed_at.tzinfo is None:
        raise ValueError("scheduler time must be timezone-aware")
    projected = project_masked_payment_method(
        provider.resolve_default_payment_method(observation),
        source_subscription_digest=subscription_digest,
        observation_version=_positive_integer(
            observation.get("observation_version"), "observation version"
        ),
    )
    projected_version = _positive_integer(projected["observation_version"], "observation version")
    reminder_at = payment_expiry_reminder_at(
        exp_month=_positive_integer(projected["exp_month"], "expiry month"),
        exp_year=_positive_integer(projected["exp_year"], "expiry year"),
    )
    identity = _reminder_identity(projected)
    recipients = resolve_billing_reminder_recipients(
        parent_id=parent_id,
        beneficiary_ids=beneficiaries,
        subscription_id_digest=subscription_digest,
        profile_resolver=profile_resolver,
        table=table,
    )
    prior_rows = notification_repo.list_payment_expiry_reminders(parent_id, table=table)
    newest_observation = max(
        (
            _positive_integer(row.get("observation_version"), "observation version")
            for row in prior_rows
        ),
        default=0,
    )
    if newest_observation > projected_version:
        stale = notification_repo.get_payment_expiry_reminder(parent_id, identity, table=table)
        return PaymentReminderRun(
            PaymentReminderDisposition.RESOLVED,
            _safe_reminder(stale or {**projected, "status": "resolved"}),
        )
    clear_replaced_payment_reminder(
        parent_id=parent_id,
        current_reminder_identity=identity,
        current_observation_version=projected_version,
        resolved_at=observed_at,
        table=table,
    )
    existing = notification_repo.get_payment_expiry_reminder(parent_id, identity, table=table)
    if existing is None:
        existing = notification_repo.put_payment_expiry_reminder(
            {
                "entity_type": notification_repo.PAYMENT_EXPIRY_REMINDER_ENTITY,
                "schema_version": REMINDER_SCHEMA_VERSION,
                "parent_id": parent_id,
                "owner_id": parent_id,
                "account_fence_generation": recipients[0].account_fence_generation,
                **projected,
                "reminder_identity": identity,
                "reminder_at": _iso(reminder_at),
                "status": "pending",
                "resolved_at": None,
                "notified_at": None,
                "created_at": _iso(observed_at),
                "updated_at": _iso(observed_at),
            },
            table=table,
        )
    safe_reminder = _safe_reminder(existing)
    if existing.get("status") == "resolved":
        return PaymentReminderRun(PaymentReminderDisposition.RESOLVED, safe_reminder)
    if observed_at.astimezone(ZURICH) < reminder_at:
        return PaymentReminderRun(PaymentReminderDisposition.PENDING, safe_reminder)

    was_notified = existing.get("status") == "notified"
    payload: dict[str, object] = {
        "schema_version": REMINDER_SCHEMA_VERSION,
        "kind": "payment_method_expiry",
        "brand": projected["brand"],
        "last4": projected["last4"],
        "exp_month": projected["exp_month"],
        "exp_year": projected["exp_year"],
        "reminder_at": _iso(reminder_at),
    }
    event_id = f"payment-expiry-{identity[:40]}"
    deliveries: list[PaymentReminderDelivery] = []
    for recipient in recipients:
        channels = ["in_app"]
        if recipient.email_eligibility.eligible:
            channels.append("email")
        for channel in channels:
            operation_id = _delivery_operation_id(
                reminder_identity=identity,
                recipient_id=recipient.account_id,
                channel=channel,
            )

            def provider_call(
                *,
                selected_recipient: BillingReminderRecipient = recipient,
                selected_channel: str = channel,
            ) -> None:
                if selected_channel == "in_app":
                    deliver_in_app(selected_recipient.account_id, dict(payload))
                    return
                address = selected_recipient.email_eligibility.address
                if address is None:
                    raise ValueError("eligible email address is missing")
                deliver_email(address, dict(payload))

            try:
                result = notification_service.register_delivery_intent(
                    recipient_id=recipient.account_id,
                    generation=recipient.account_fence_generation,
                    operation_id=operation_id,
                    channel=channel,
                    event_ids=[event_id],
                    payload={
                        **payload,
                        "recipient_id": recipient.account_id,
                        "channel": channel,
                    },
                    provider_call=provider_call,
                )
                status = str(result.get("status") or "failed")
            except Exception:
                status = "failed"
            deliveries.append(
                PaymentReminderDelivery(
                    recipient_id=recipient.account_id,
                    channel=channel,
                    operation_id=operation_id,
                    status=status,
                )
            )
    updated = notification_repo.mark_payment_expiry_reminder_notified(
        parent_id,
        identity,
        notified_at=_iso(observed_at),
        table=table,
    )
    if updated is not None:
        safe_reminder = _safe_reminder(updated)
    return PaymentReminderRun(
        (
            PaymentReminderDisposition.REPLAYED
            if was_notified
            else PaymentReminderDisposition.DELIVERED
        ),
        safe_reminder,
        tuple(deliveries),
    )


__all__ = [
    "BillingReminderRecipient",
    "EmailEligibility",
    "PaymentMethodProvider",
    "PaymentReminderDelivery",
    "PaymentReminderDisposition",
    "PaymentReminderRun",
    "clear_replaced_payment_reminder",
    "payment_expiry_reminder_at",
    "project_masked_payment_method",
    "resolve_billing_reminder_recipients",
    "run_payment_expiry_reminders",
]
