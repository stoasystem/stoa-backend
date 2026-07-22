"""Capped, idempotent rate admission for logical chat and hint operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
import hashlib
import struct
from typing import Any, Mapping

from fastapi import HTTPException, status

from stoa.config import settings
from stoa.db.dynamodb import get_table
from stoa.db.repositories import account_deletion_repo


_RATE_KINDS = frozenset({"chat", "hint"})
_OPERATION_SCHEMA_VERSION = "rate-admission-operation.v2"
_OPERATION_TTL_SECONDS = 172800


class RateAdmissionDisposition(StrEnum):
    """Closed, provider-independent outcomes for one logical rate operation."""

    ADMITTED = "admitted"
    REPLAYED = "replayed"
    LIMIT_EXCEEDED = "limit_exceeded"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    RETRYABLE = "retryable"


@dataclass(frozen=True, slots=True)
class RateAdmissionResult:
    """Stable admission result without provider diagnostics or raw caller keys."""

    disposition: RateAdmissionDisposition
    owner_id: str
    kind: str
    operation_id: str
    quota_period: str
    counter_key: str
    counter_value: int
    limit: int
    expires_at: int
    decision: str

    def counter_receipt(self) -> dict[str, Any]:
        return {
            "quotaPeriod": self.quota_period,
            "counterKey": self.counter_key,
            "counterValue": self.counter_value,
            "limit": self.limit,
            "expiresAt": self.expires_at,
            "operationId": self.operation_id,
            "admissionStatus": self.decision,
        }


class _RateDependencyFailure(RuntimeError):
    pass


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _rate_kind(value: object) -> str:
    kind = _required_text(value, "kind").lower()
    if kind not in _RATE_KINDS:
        raise ValueError("unsupported rate kind")
    return kind


def _sha256_digest(value: object, field: str) -> str:
    digest = _required_text(value, field)
    if (
        len(digest) != 64
        or digest != digest.lower()
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return digest


def _frame(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack(">I", len(encoded)) + encoded


def build_rate_operation_id(
    kind: str,
    owner_id: str,
    caller_operation_id: str,
    quota_period: str | None = None,
) -> str:
    """Return a period-scoped opaque ID for one caller-owned logical operation."""
    normalized_kind = _rate_kind(kind)
    owner = _required_text(owner_id, "owner_id")
    caller_id = _required_text(caller_operation_id, "caller_operation_id")
    period = _required_text(quota_period or _today_utc(), "quota_period")
    framed = b"stoa.rate-admission.operation.v1"
    for value in (normalized_kind, owner, period, caller_id):
        framed += _frame(value)
    return hashlib.sha256(framed).hexdigest()


def _payload_digest(kind: str, resource_id: str) -> str:
    framed = b"stoa.rate-admission.payload.v1"
    framed += _frame(_rate_kind(kind))
    framed += _frame(_required_text(resource_id, "resource_id"))
    return hashlib.sha256(framed).hexdigest()


def _counter_key(owner_id: str, kind: str, quota_period: str) -> dict[str, str]:
    return {
        "PK": f"USAGE#{owner_id}",
        "SK": f"{kind.upper()}#{quota_period}",
    }


def _operation_key(owner_id: str, kind: str, operation_id: str) -> dict[str, str]:
    return {
        "PK": f"USAGE#{owner_id}",
        "SK": f"{kind.upper()}_QUOTA_OP#{operation_id}",
    }


def _get_item(table: object, key: dict[str, str]) -> dict[str, Any] | None:
    getter = getattr(table, "get_item", None)
    if not callable(getter):
        raise _RateDependencyFailure
    try:
        response = getter(Key=key, ConsistentRead=True)
    except Exception:
        raise _RateDependencyFailure from None
    if not isinstance(response, Mapping):
        raise _RateDependencyFailure
    item = response.get("Item")
    if item is None:
        return None
    if not isinstance(item, Mapping) or any(not isinstance(key, str) for key in item):
        raise _RateDependencyFailure
    return dict(item)


def _counter_state(
    table: object, key: dict[str, str]
) -> tuple[int, int, bool, bool]:
    item = _get_item(table, key) or {}
    count_exists = "count" in item
    expiry_exists = "expires_at" in item
    count = _stored_nonnegative_int(item.get("count", 0))
    expires_at = _stored_nonnegative_int(item.get("expires_at", 0))
    if count is None or expires_at is None:
        raise _RateDependencyFailure
    return count, expires_at, count_exists, expiry_exists


def _stored_nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, Decimal) and value.is_finite() and value == value.to_integral_value():
        integer = int(value)
        return integer if integer >= 0 else None
    return None


def _result(
    disposition: RateAdmissionDisposition,
    *,
    owner_id: str,
    kind: str,
    operation_id: str,
    quota_period: str,
    counter_key: dict[str, str],
    counter_value: int,
    limit: int,
    expires_at: int,
    decision: str | None = None,
) -> RateAdmissionResult:
    return RateAdmissionResult(
        disposition=disposition,
        owner_id=owner_id,
        kind=kind,
        operation_id=operation_id,
        quota_period=quota_period,
        counter_key=f"{counter_key['PK']}/{counter_key['SK']}",
        counter_value=counter_value,
        limit=limit,
        expires_at=expires_at,
        decision=decision or disposition.value,
    )


def _classify_operation(
    item: dict[str, Any],
    *,
    owner_id: str,
    kind: str,
    operation_id: str,
    quota_period: str,
    payload_digest: str,
    counter_key: dict[str, str],
    requested_limit: int,
) -> RateAdmissionResult:
    stored_counter_value = _stored_nonnegative_int(item.get("counter_value_after"))
    stored_limit = _stored_nonnegative_int(item.get("limit"))
    stored_expiry = _stored_nonnegative_int(item.get("receipt_expires_at"))
    receipt_is_invalid = (
        item.get("entity_type") != "rate_admission_operation"
        or item.get("schema_version") != _OPERATION_SCHEMA_VERSION
        or item.get("owner_id") != owner_id
        or item.get("kind") != kind
        or item.get("operation_id") != operation_id
        or item.get("quota_period") != quota_period
        or item.get("status") != "admitted"
        or not isinstance(item.get("payload_digest"), str)
        or item.get("decision") != RateAdmissionDisposition.ADMITTED.value
        or stored_counter_value is None
        or stored_counter_value <= 0
        or stored_limit is None
        or stored_limit <= 0
        or stored_expiry is None
    )
    if receipt_is_invalid:
        disposition = RateAdmissionDisposition.RETRYABLE
    elif item["payload_digest"] != payload_digest:
        disposition = RateAdmissionDisposition.IDEMPOTENCY_CONFLICT
    else:
        disposition = RateAdmissionDisposition.REPLAYED
    return _result(
        disposition,
        owner_id=owner_id,
        kind=kind,
        operation_id=operation_id,
        quota_period=quota_period,
        counter_key=counter_key,
        counter_value=stored_counter_value or 0,
        limit=stored_limit or requested_limit,
        expires_at=stored_expiry or 0,
        decision=(
            str(item["decision"])
            if not receipt_is_invalid
            else RateAdmissionDisposition.RETRYABLE.value
        ),
    )


def check_and_record_operation(
    *,
    owner_id: str,
    kind: str,
    operation_id: str,
    payload_digest: str,
    limit: int,
    quota_period: str | None = None,
    account_fence_generation: int | None = None,
    table: object | None = None,
    now: datetime | None = None,
) -> RateAdmissionResult:
    """Admit one logical operation once without ever incrementing past its cap."""
    owner = _required_text(owner_id, "owner_id")
    normalized_kind = _rate_kind(kind)
    opaque_operation_id = _sha256_digest(operation_id, "operation_id")
    digest = _sha256_digest(payload_digest, "payload_digest")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit must be a positive integer")
    observed_now = now or datetime.now(timezone.utc)
    if observed_now.tzinfo is None or observed_now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    period = _required_text(
        quota_period or observed_now.astimezone(timezone.utc).strftime("%Y-%m-%d"),
        "quota_period",
    )
    expires_at_value = int(observed_now.timestamp()) + _OPERATION_TTL_SECONDS
    target = table or get_table()
    counter_key = _counter_key(owner, normalized_kind, period)
    operation_key = _operation_key(owner, normalized_kind, opaque_operation_id)

    try:
        existing = _get_item(target, operation_key)
    except _RateDependencyFailure:
        return _result(
            RateAdmissionDisposition.RETRYABLE,
            owner_id=owner,
            kind=normalized_kind,
            operation_id=opaque_operation_id,
            quota_period=period,
            counter_key=counter_key,
            counter_value=0,
            limit=limit,
            expires_at=0,
        )
    if existing is not None:
        return _classify_operation(
            existing,
            owner_id=owner,
            kind=normalized_kind,
            operation_id=opaque_operation_id,
            quota_period=period,
            payload_digest=digest,
            counter_key=counter_key,
            requested_limit=limit,
        )

    try:
        counter_value, stored_expiry, _, _ = _counter_state(target, counter_key)
    except _RateDependencyFailure:
        return _result(
            RateAdmissionDisposition.RETRYABLE,
            owner_id=owner,
            kind=normalized_kind,
            operation_id=opaque_operation_id,
            quota_period=period,
            counter_key=counter_key,
            counter_value=0,
            limit=limit,
            expires_at=0,
        )

    try:
        if account_fence_generation is None:
            fence = account_deletion_repo.require_active_account_fence(owner, table=target)
            generation = int(fence["generation"])
        else:
            if (
                isinstance(account_fence_generation, bool)
                or not isinstance(account_fence_generation, int)
                or account_fence_generation <= 0
            ):
                raise ValueError("account_fence_generation must be positive")
            generation = account_fence_generation
    except (account_deletion_repo.AccountDeletionConflict, KeyError, TypeError, ValueError):
        return _result(
            RateAdmissionDisposition.RETRYABLE,
            owner_id=owner,
            kind=normalized_kind,
            operation_id=opaque_operation_id,
            quota_period=period,
            counter_key=counter_key,
            counter_value=counter_value,
            limit=limit,
            expires_at=stored_expiry,
        )

    for _ in range(3):
        try:
            existing = _get_item(target, operation_key)
            if existing is not None:
                return _classify_operation(
                    existing,
                    owner_id=owner,
                    kind=normalized_kind,
                    operation_id=opaque_operation_id,
                    quota_period=period,
                    payload_digest=digest,
                    counter_key=counter_key,
                    requested_limit=limit,
                )
            (
                counter_value,
                stored_expiry,
                count_exists,
                expiry_exists,
            ) = _counter_state(target, counter_key)
        except _RateDependencyFailure:
            break
        if counter_value >= limit:
            return _result(
                RateAdmissionDisposition.LIMIT_EXCEEDED,
                owner_id=owner,
                kind=normalized_kind,
                operation_id=opaque_operation_id,
                quota_period=period,
                counter_key=counter_key,
                counter_value=counter_value,
                limit=limit,
                expires_at=stored_expiry,
            )

        next_counter_value = counter_value + 1
        receipt_expiry = stored_expiry if expiry_exists else expires_at_value
        operation = {
            **operation_key,
            "entity_type": "rate_admission_operation",
            "schema_version": _OPERATION_SCHEMA_VERSION,
            "operation_id": opaque_operation_id,
            "owner_id": owner,
            "kind": normalized_kind,
            "quota_period": period,
            "payload_digest": digest,
            "status": "admitted",
            "decision": RateAdmissionDisposition.ADMITTED.value,
            "counter_value_after": next_counter_value,
            "limit": limit,
            "receipt_expires_at": receipt_expiry,
            "account_fence_generation": generation,
            "created_at": observed_now.astimezone(timezone.utc).isoformat(),
            "expires_at": expires_at_value,
        }
        counter_condition = (
            "#count = :expected" if count_exists else "attribute_not_exists(#count)"
        )
        operations = [
            account_deletion_repo.active_fence_condition(owner, generation),
            {
                "Put": {
                    "Item": operation,
                    "ConditionExpression": (
                        "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                    ),
                }
            },
            {
                "Update": {
                    "Key": counter_key,
                    "UpdateExpression": (
                        "SET #count=:next, #ttl=if_not_exists(#ttl,:expires), "
                        "entity_type=if_not_exists(entity_type,:counter_type), "
                        "owner_id=if_not_exists(owner_id,:owner), "
                        "quota_period=if_not_exists(quota_period,:period), "
                        "account_fence_generation=:generation"
                    ),
                    "ConditionExpression": counter_condition,
                    "ExpressionAttributeNames": {
                        "#count": "count",
                        "#ttl": "expires_at",
                    },
                    "ExpressionAttributeValues": {
                        ":expected": counter_value,
                        ":next": next_counter_value,
                        ":limit": limit,
                        ":expires": expires_at_value,
                        ":counter_type": "rate_counter",
                        ":owner": owner,
                        ":period": period,
                        ":generation": generation,
                    },
                }
            },
        ]
        try:
            account_deletion_repo.transact(operations, table=target)
        except Exception:
            try:
                raced_operation = _get_item(target, operation_key)
            except _RateDependencyFailure:
                break
            if raced_operation is not None:
                return _classify_operation(
                    raced_operation,
                    owner_id=owner,
                    kind=normalized_kind,
                    operation_id=opaque_operation_id,
                    quota_period=period,
                    payload_digest=digest,
                    counter_key=counter_key,
                    requested_limit=limit,
                )
            continue
        return _result(
            RateAdmissionDisposition.ADMITTED,
            owner_id=owner,
            kind=normalized_kind,
            operation_id=opaque_operation_id,
            quota_period=period,
            counter_key=counter_key,
            counter_value=next_counter_value,
            limit=limit,
            expires_at=receipt_expiry,
            decision=RateAdmissionDisposition.ADMITTED.value,
        )

    return _result(
        RateAdmissionDisposition.RETRYABLE,
        owner_id=owner,
        kind=normalized_kind,
        operation_id=opaque_operation_id,
        quota_period=period,
        counter_key=counter_key,
        counter_value=counter_value,
        limit=limit,
        expires_at=stored_expiry,
    )


def _counter_receipt_or_raise(result: RateAdmissionResult, label: str) -> dict[str, Any]:
    if result.disposition in {
        RateAdmissionDisposition.ADMITTED,
        RateAdmissionDisposition.REPLAYED,
    }:
        return result.counter_receipt()
    if result.disposition is RateAdmissionDisposition.LIMIT_EXCEEDED:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily {label} limit ({result.limit}) reached. Try again tomorrow.",
        )
    if result.disposition is RateAdmissionDisposition.IDEMPOTENCY_CONFLICT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "rate_operation_conflict",
                "message": "This idempotency key was already used for another request.",
            },
        )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "rate_limit_unavailable",
            "message": "Usage admission is temporarily unavailable. Please try again.",
        },
        headers={"Retry-After": "30"},
    )


def check_and_record_chat(
    student_id: str,
    operation_id: str,
    payload_digest: str,
    limit: int | None = None,
) -> dict[str, Any]:
    """Legacy adapter; conversation commands remain the authoritative chat path."""
    period = _today_utc()
    result = check_and_record_operation(
        owner_id=student_id,
        kind="chat",
        operation_id=build_rate_operation_id(
            "chat", student_id, operation_id, period
        ),
        payload_digest=payload_digest,
        quota_period=period,
        limit=limit if limit is not None else settings.daily_chat_message_limit,
    )
    return _counter_receipt_or_raise(result, "chat message")


def check_and_record_hint(
    student_id: str,
    challenge_id: str,
    operation_id: str,
    limit: int | None = None,
) -> dict[str, Any]:
    """Admit one explicit hint idempotency identity for one challenge payload."""
    period = _today_utc()
    result = check_and_record_operation(
        owner_id=student_id,
        kind="hint",
        operation_id=build_rate_operation_id(
            "hint", student_id, operation_id, period
        ),
        payload_digest=_payload_digest("hint", challenge_id),
        quota_period=period,
        limit=limit if limit is not None else settings.daily_hint_limit,
    )
    return _counter_receipt_or_raise(result, "hint")
