"""Conditional weekly token allowance persistence and provider-cost evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
import hashlib
import json
from typing import Any

from stoa.db.dynamodb import get_table
from stoa.db.repositories import account_deletion_repo
from stoa.models.allowance import (
    MAX_EXACT_COUNT,
    AllowanceFinalization,
    AllowanceReservation,
    PlanAllowanceBudget,
    ProviderUsageEvidence,
    ZurichWeek,
)
from stoa.models.billing import BillingPlanId


ALLOWANCE_COUNTER_SCHEMA_VERSION = "allowance_counter.v1"
ALLOWANCE_EFFECT_SCHEMA_VERSION = "allowance_effect.v1"
PROVIDER_USAGE_EVIDENCE_SCHEMA_VERSION = "provider_usage_evidence.v1"
_PROVIDER_EVIDENCE_DOMAIN = b"stoa.allowance.provider-evidence.v1"


type AllowanceItem = dict[str, object]


class ReservationDisposition(StrEnum):
    ADMITTED = "admitted"
    REPLAYED = "replayed"
    LIMIT_EXCEEDED = "limit_exceeded"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    RETRYABLE = "retryable"


class ProviderUsageDisposition(StrEnum):
    RECORDED = "recorded"
    REPLAYED = "replayed"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    INVALID_STATE = "invalid_state"
    RETRYABLE = "retryable"


class FinalizationDisposition(StrEnum):
    FINALIZED = "finalized"
    RESTORED = "restored"
    REPLAYED = "replayed"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    INVALID_STATE = "invalid_state"
    RETRYABLE = "retryable"


@dataclass(frozen=True, slots=True)
class ReservationResult:
    disposition: ReservationDisposition
    reservation: AllowanceReservation | None = None


@dataclass(frozen=True, slots=True)
class ProviderUsageResult:
    disposition: ProviderUsageDisposition
    evidence: ProviderUsageEvidence | None = None


@dataclass(frozen=True, slots=True)
class FinalizationResult:
    disposition: FinalizationDisposition
    finalization: AllowanceFinalization | None = None


class _AllowanceDependencyFailure(RuntimeError):
    pass


def _required_text(value: object, field: str, *, maximum: int = 200) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not 1 <= len(value) <= maximum
    ):
        raise ValueError(f"{field} is invalid")
    return value


def _sha256(value: object, field: str) -> str:
    digest = _required_text(value, field, maximum=64)
    if (
        len(digest) != 64
        or digest != digest.lower()
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return digest


def _exact_count(value: object, field: str, *, positive: bool = False) -> int:
    minimum = 1 if positive else 0
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} is invalid")
    if not minimum <= value <= MAX_EXACT_COUNT:
        raise ValueError(f"{field} is invalid")
    return value


def _stored_count(value: object, field: str, *, positive: bool = False) -> int:
    if isinstance(value, bool):
        raise _AllowanceDependencyFailure(f"malformed {field}")
    if isinstance(value, int):
        parsed = value
    elif (
        isinstance(value, Decimal)
        and value.is_finite()
        and value == value.to_integral_value()
    ):
        parsed = int(value)
    else:
        raise _AllowanceDependencyFailure(f"malformed {field}")
    minimum = 1 if positive else 0
    if not minimum <= parsed <= MAX_EXACT_COUNT:
        raise _AllowanceDependencyFailure(f"malformed {field}")
    return parsed


def _stored_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise _AllowanceDependencyFailure(f"malformed {field}")
    return value


def _aware_timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value


def _timestamp_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _payload_digest(kind: str, values: Mapping[str, object]) -> str:
    payload = json.dumps(
        {"kind": kind, **dict(values)},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(b"stoa.allowance.payload.v1\x00" + payload).hexdigest()


def _week_identity(week: ZurichWeek) -> str:
    return f"{week.iso_year:04d}-W{week.iso_week:02d}"


def _partition(beneficiary_id: str) -> str:
    return f"ALLOWANCE#{_required_text(beneficiary_id, 'beneficiary_id')}"


def _counter_key(beneficiary_id: str, week_identity: str) -> dict[str, str]:
    return {
        "PK": _partition(beneficiary_id),
        "SK": f"WEEK#{_required_text(week_identity, 'week_identity', maximum=8)}",
    }


def _effect_key(beneficiary_id: str, effect_id: str) -> dict[str, str]:
    return {
        "PK": _partition(beneficiary_id),
        "SK": f"EFFECT#{_sha256(effect_id, 'effect_id')}",
    }


def _evidence_id(effect_id: str) -> str:
    return hashlib.sha256(_PROVIDER_EVIDENCE_DOMAIN + b"\x00" + effect_id.encode()).hexdigest()


def _evidence_key(beneficiary_id: str, evidence_id: str) -> dict[str, str]:
    return {
        "PK": _partition(beneficiary_id),
        "SK": f"PROVIDER_USAGE#{_sha256(evidence_id, 'evidence_id')}",
    }


def _mapping(value: object) -> AllowanceItem | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise _AllowanceDependencyFailure("allowance dependency returned malformed data")
    return {str(key): member for key, member in value.items()}


def _strong_get(table: object, key: Mapping[str, str]) -> AllowanceItem | None:
    getter = getattr(table, "get_item", None)
    if not callable(getter):
        raise _AllowanceDependencyFailure("allowance persistence is unavailable")
    try:
        response = getter(Key=dict(key), ConsistentRead=True)
    except Exception:
        raise _AllowanceDependencyFailure("allowance persistence is unavailable") from None
    if not isinstance(response, Mapping):
        raise _AllowanceDependencyFailure("allowance dependency returned malformed data")
    return _mapping(response.get("Item"))


def _query_evidence(table: object, beneficiary_id: str) -> list[AllowanceItem]:
    query = getattr(table, "query", None)
    if not callable(query):
        raise _AllowanceDependencyFailure("allowance persistence is unavailable")
    request: dict[str, object] = {
        "KeyConditionExpression": "PK=:pk AND begins_with(SK,:prefix)",
        "ExpressionAttributeValues": {
            ":pk": _partition(beneficiary_id),
            ":prefix": "PROVIDER_USAGE#",
        },
        "ConsistentRead": True,
    }
    items: list[AllowanceItem] = []
    for _ in range(20):
        try:
            response = query(**request)
        except Exception:
            raise _AllowanceDependencyFailure(
                "allowance persistence is unavailable"
            ) from None
        if not isinstance(response, Mapping) or not isinstance(response.get("Items"), list):
            raise _AllowanceDependencyFailure(
                "allowance dependency returned malformed data"
            )
        items.extend(
            item
            for raw in response["Items"]
            if (item := _mapping(raw)) is not None
        )
        cursor = response.get("LastEvaluatedKey")
        if cursor is None:
            return items
        if (
            not isinstance(cursor, Mapping)
            or set(cursor) != {"PK", "SK"}
            or any(not isinstance(cursor[field], str) for field in ("PK", "SK"))
        ):
            raise _AllowanceDependencyFailure(
                "allowance dependency returned malformed data"
            )
        request["ExclusiveStartKey"] = dict(cursor)
    raise _AllowanceDependencyFailure("allowance evidence exceeds the read bound")


def _put_create(item: Mapping[str, object]) -> dict[str, Any]:
    return {
        "Put": {
            "Item": dict(item),
            "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
        }
    }


def _put_replace(
    item: Mapping[str, object],
    *,
    expected_state_version: int,
    expected_state: str | None = None,
) -> dict[str, Any]:
    expression = "state_version=:expected_state_version"
    names: dict[str, str] = {}
    values: dict[str, object] = {":expected_state_version": expected_state_version}
    if expected_state is not None:
        expression += " AND #state=:expected_state"
        names["#state"] = "state"
        values[":expected_state"] = expected_state
    payload: dict[str, Any] = {
        "Item": dict(item),
        "ConditionExpression": expression,
        "ExpressionAttributeValues": values,
    }
    if names:
        payload["ExpressionAttributeNames"] = names
    return {"Put": payload}


def _put_initial_counter(item: Mapping[str, object]) -> dict[str, Any]:
    return {
        "Put": {
            "Item": dict(item),
            "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
        }
    }


def _transact(operations: list[dict[str, Any]], *, table: object) -> None:
    account_deletion_repo.transact(operations, table=table)


_COUNTER_FIELDS = (
    "finalized_input_tokens",
    "finalized_output_tokens",
    "reserved_input_tokens",
    "reserved_output_tokens",
    "provider_cost_input_tokens",
    "provider_cost_output_tokens",
)


def _empty_counter(
    *,
    beneficiary_id: str,
    week: ZurichWeek,
    budget: PlanAllowanceBudget,
    account_fence_generation: int,
    observed_at: datetime,
) -> AllowanceItem:
    identity = _week_identity(week)
    return {
        **_counter_key(beneficiary_id, identity),
        "entity_type": "allowance_counter",
        "schema_version": ALLOWANCE_COUNTER_SCHEMA_VERSION,
        "beneficiary_id": beneficiary_id,
        "week_identity": identity,
        "window_start": _timestamp_text(week.window_start),
        "window_end": _timestamp_text(week.window_end),
        "plan_id": str(budget.plan_id),
        "allowance_version": budget.allowance_version,
        "budget_input_tokens": budget.input_tokens,
        "budget_output_tokens": budget.output_tokens,
        "finalized_input_tokens": 0,
        "finalized_output_tokens": 0,
        "reserved_input_tokens": 0,
        "reserved_output_tokens": 0,
        "provider_cost_input_tokens": 0,
        "provider_cost_output_tokens": 0,
        "state_version": 0,
        "account_fence_generation": account_fence_generation,
        "created_at": _timestamp_text(observed_at),
        "updated_at": _timestamp_text(observed_at),
    }


def _validated_counter(
    item: Mapping[str, object],
    *,
    beneficiary_id: str,
    week: ZurichWeek,
) -> AllowanceItem:
    identity = _week_identity(week)
    if (
        item.get("entity_type") != "allowance_counter"
        or item.get("schema_version") != ALLOWANCE_COUNTER_SCHEMA_VERSION
        or item.get("beneficiary_id") != beneficiary_id
        or item.get("week_identity") != identity
        or item.get("PK") != _partition(beneficiary_id)
        or item.get("SK") != f"WEEK#{identity}"
        or item.get("window_start") != _timestamp_text(week.window_start)
        or item.get("window_end") != _timestamp_text(week.window_end)
    ):
        raise _AllowanceDependencyFailure("malformed allowance counter")
    normalized = dict(item)
    try:
        for field in _COUNTER_FIELDS:
            normalized[field] = _stored_count(item.get(field), field)
        normalized["budget_input_tokens"] = _stored_count(
            item.get("budget_input_tokens"), "budget_input_tokens", positive=True
        )
        normalized["budget_output_tokens"] = _stored_count(
            item.get("budget_output_tokens"), "budget_output_tokens", positive=True
        )
        normalized["state_version"] = _stored_count(
            item.get("state_version"), "state_version", positive=True
        )
        normalized["allowance_version"] = _stored_count(
            item.get("allowance_version"), "allowance_version", positive=True
        )
        normalized["account_fence_generation"] = _stored_count(
            item.get("account_fence_generation"),
            "account_fence_generation",
            positive=True,
        )
        normalized["plan_id"] = str(
            BillingPlanId(_required_text(item.get("plan_id"), "plan_id"))
        )
        _required_text(item.get("created_at"), "created_at")
        _required_text(item.get("updated_at"), "updated_at")
    except ValueError as exc:
        raise _AllowanceDependencyFailure("malformed allowance counter") from exc
    return normalized


def _checked_add(left: int, right: int) -> int:
    value = left + right
    if value > MAX_EXACT_COUNT:
        raise _AllowanceDependencyFailure("allowance count overflow")
    return value


def _reservation_from_effect(item: Mapping[str, object]) -> AllowanceReservation:
    try:
        return AllowanceReservation.model_validate(
            {
                "reservation_id": item.get("reservation_id"),
                "effect_id": item.get("effect_id"),
                "beneficiary_id": item.get("beneficiary_id"),
                "plan_id": item.get("plan_id"),
                "allowance_version": _stored_count(
                    item.get("allowance_version"), "allowance_version", positive=True
                ),
                "week": {
                    "iso_year": _stored_count(
                        item.get("iso_year"), "iso_year", positive=True
                    ),
                    "iso_week": _stored_count(
                        item.get("iso_week"), "iso_week", positive=True
                    ),
                    "window_start": item.get("window_start"),
                    "window_end": item.get("window_end"),
                },
                "input_tokens": _stored_count(
                    item.get("reservation_input_tokens"), "reservation_input_tokens"
                ),
                "output_tokens": _stored_count(
                    item.get("reservation_output_tokens"), "reservation_output_tokens"
                ),
                "state_version": _stored_count(
                    item.get("reservation_state_version"),
                    "reservation_state_version",
                    positive=True,
                ),
                "expires_at": item.get("expires_at"),
            }
        )
    except (TypeError, ValueError) as exc:
        raise _AllowanceDependencyFailure("malformed allowance effect") from exc


def _validated_effect(
    item: Mapping[str, object],
    *,
    beneficiary_id: str,
    effect_id: str,
) -> AllowanceItem:
    if (
        item.get("entity_type") != "allowance_effect"
        or item.get("schema_version") != ALLOWANCE_EFFECT_SCHEMA_VERSION
        or item.get("beneficiary_id") != beneficiary_id
        or item.get("effect_id") != effect_id
        or item.get("PK") != _partition(beneficiary_id)
        or item.get("SK") != f"EFFECT#{effect_id}"
        or item.get("state") not in {"reserved", "observed", "finalized", "restored"}
    ):
        raise _AllowanceDependencyFailure("malformed allowance effect")
    normalized = dict(item)
    normalized["state_version"] = _stored_count(
        item.get("state_version"), "state_version", positive=True
    )
    normalized["account_fence_generation"] = _stored_count(
        item.get("account_fence_generation"),
        "account_fence_generation",
        positive=True,
    )
    _sha256(item.get("reservation_payload_digest"), "reservation_payload_digest")
    _reservation_from_effect(normalized)
    return normalized


def _classify_reservation(
    item: Mapping[str, object],
    *,
    beneficiary_id: str,
    effect_id: str,
    payload_digest: str,
) -> ReservationResult:
    try:
        effect = _validated_effect(
            item, beneficiary_id=beneficiary_id, effect_id=effect_id
        )
        reservation = _reservation_from_effect(effect)
    except _AllowanceDependencyFailure:
        return ReservationResult(ReservationDisposition.RETRYABLE)
    disposition = (
        ReservationDisposition.REPLAYED
        if effect["reservation_payload_digest"] == payload_digest
        else ReservationDisposition.IDEMPOTENCY_CONFLICT
    )
    return ReservationResult(disposition, reservation=reservation)


def reserve_allowance(
    *,
    beneficiary_id: str,
    effect_id: str,
    week: ZurichWeek,
    budget: PlanAllowanceBudget,
    input_tokens: int,
    output_tokens: int,
    observed_at: datetime,
    account_fence_generation: int | None = None,
    table: object | None = None,
) -> ReservationResult:
    """Conditionally reserve both token dimensions under one payload-bound effect."""
    beneficiary = _required_text(beneficiary_id, "beneficiary_id")
    effect = _sha256(effect_id, "effect_id")
    requested_input = _exact_count(input_tokens, "input_tokens")
    requested_output = _exact_count(output_tokens, "output_tokens")
    if requested_input + requested_output == 0:
        raise ValueError("a reservation must request at least one token")
    if not isinstance(week, ZurichWeek) or not isinstance(budget, PlanAllowanceBudget):
        raise ValueError("validated week and budget are required")
    now = _aware_timestamp(observed_at, "observed_at")
    identity = _week_identity(week)
    digest = _payload_digest(
        "reservation",
        {
            "beneficiary_id": beneficiary,
            "effect_id": effect,
            "week_identity": identity,
            "plan_id": str(budget.plan_id),
            "allowance_version": budget.allowance_version,
            "budget_input_tokens": budget.input_tokens,
            "budget_output_tokens": budget.output_tokens,
            "input_tokens": requested_input,
            "output_tokens": requested_output,
        },
    )
    if (
        requested_input > budget.input_tokens
        or requested_output > budget.output_tokens
    ):
        return ReservationResult(ReservationDisposition.LIMIT_EXCEEDED)

    target = table or get_table()
    effect_key = _effect_key(beneficiary, effect)
    counter_key = _counter_key(beneficiary, identity)
    try:
        existing = _strong_get(target, effect_key)
    except _AllowanceDependencyFailure:
        return ReservationResult(ReservationDisposition.RETRYABLE)
    if existing is not None:
        return _classify_reservation(
            existing,
            beneficiary_id=beneficiary,
            effect_id=effect,
            payload_digest=digest,
        )
    try:
        if account_fence_generation is None:
            fence = account_deletion_repo.require_active_account_fence(
                beneficiary, table=target
            )
            generation = _exact_count(
                fence.get("generation"), "account_fence_generation", positive=True
            )
        else:
            generation = _exact_count(
                account_fence_generation,
                "account_fence_generation",
                positive=True,
            )
    except (account_deletion_repo.AccountDeletionConflict, TypeError, ValueError):
        return ReservationResult(ReservationDisposition.RETRYABLE)

    for _ in range(4):
        try:
            existing = _strong_get(target, effect_key)
            if existing is not None:
                return _classify_reservation(
                    existing,
                    beneficiary_id=beneficiary,
                    effect_id=effect,
                    payload_digest=digest,
                )
            raw_counter = _strong_get(target, counter_key)
            if raw_counter is None:
                counter = _empty_counter(
                    beneficiary_id=beneficiary,
                    week=week,
                    budget=budget,
                    account_fence_generation=generation,
                    observed_at=now,
                )
                counter_exists = False
            else:
                counter = _validated_counter(
                    raw_counter, beneficiary_id=beneficiary, week=week
                )
                counter_exists = True
        except _AllowanceDependencyFailure:
            return ReservationResult(ReservationDisposition.RETRYABLE)

        try:
            input_used = _checked_add(
                int(counter["finalized_input_tokens"]),
                int(counter["reserved_input_tokens"]),
            )
            output_used = _checked_add(
                int(counter["finalized_output_tokens"]),
                int(counter["reserved_output_tokens"]),
            )
        except _AllowanceDependencyFailure:
            return ReservationResult(ReservationDisposition.RETRYABLE)
        stored_allowance_version = int(counter["allowance_version"])
        if budget.allowance_version < stored_allowance_version:
            return ReservationResult(ReservationDisposition.RETRYABLE)
        if (
            budget.allowance_version == stored_allowance_version
            and (
                counter["plan_id"] != str(budget.plan_id)
                or counter["budget_input_tokens"] != budget.input_tokens
                or counter["budget_output_tokens"] != budget.output_tokens
            )
        ):
            return ReservationResult(ReservationDisposition.RETRYABLE)
        if (
            input_used + requested_input > budget.input_tokens
            or output_used + requested_output > budget.output_tokens
        ):
            return ReservationResult(ReservationDisposition.LIMIT_EXCEEDED)

        next_version = int(counter["state_version"]) + 1
        reservation = AllowanceReservation(
            reservationId=effect,
            effectId=effect,
            beneficiaryId=beneficiary,
            planId=budget.plan_id,
            allowanceVersion=budget.allowance_version,
            week=week,
            inputTokens=requested_input,
            outputTokens=requested_output,
            stateVersion=next_version,
            expiresAt=week.window_end,
        )
        next_effect: AllowanceItem = {
            **effect_key,
            "entity_type": "allowance_effect",
            "schema_version": ALLOWANCE_EFFECT_SCHEMA_VERSION,
            "reservation_id": reservation.reservation_id,
            "effect_id": effect,
            "beneficiary_id": beneficiary,
            "plan_id": str(budget.plan_id),
            "allowance_version": budget.allowance_version,
            "week_identity": identity,
            "iso_year": week.iso_year,
            "iso_week": week.iso_week,
            "window_start": _timestamp_text(week.window_start),
            "window_end": _timestamp_text(week.window_end),
            "reservation_input_tokens": requested_input,
            "reservation_output_tokens": requested_output,
            "reservation_state_version": next_version,
            "reservation_payload_digest": digest,
            "state": "reserved",
            "state_version": 1,
            "account_fence_generation": generation,
            "created_at": _timestamp_text(now),
            "updated_at": _timestamp_text(now),
            "expires_at": _timestamp_text(week.window_end),
        }
        next_counter = {
            **counter,
            "plan_id": str(budget.plan_id),
            "allowance_version": budget.allowance_version,
            "budget_input_tokens": budget.input_tokens,
            "budget_output_tokens": budget.output_tokens,
            "reserved_input_tokens": input_used
            - int(counter["finalized_input_tokens"])
            + requested_input,
            "reserved_output_tokens": output_used
            - int(counter["finalized_output_tokens"])
            + requested_output,
            "state_version": next_version,
            "account_fence_generation": generation,
            "updated_at": _timestamp_text(now),
        }
        counter_operation = (
            _put_replace(
                next_counter,
                expected_state_version=int(counter["state_version"]),
            )
            if counter_exists
            else _put_initial_counter(next_counter)
        )
        operations = [
            account_deletion_repo.active_fence_condition(beneficiary, generation),
            _put_create(next_effect),
            counter_operation,
        ]
        try:
            _transact(operations, table=target)
        except Exception:
            try:
                raced = _strong_get(target, effect_key)
            except _AllowanceDependencyFailure:
                return ReservationResult(ReservationDisposition.RETRYABLE)
            if raced is not None:
                return _classify_reservation(
                    raced,
                    beneficiary_id=beneficiary,
                    effect_id=effect,
                    payload_digest=digest,
                )
            continue
        return ReservationResult(
            ReservationDisposition.ADMITTED,
            reservation=_reservation_from_effect(next_effect),
        )
    return ReservationResult(ReservationDisposition.RETRYABLE)


def _evidence_from_item(item: Mapping[str, object]) -> ProviderUsageEvidence:
    if (
        item.get("entity_type") != "provider_usage_evidence"
        or item.get("schema_version") != PROVIDER_USAGE_EVIDENCE_SCHEMA_VERSION
    ):
        raise _AllowanceDependencyFailure("malformed provider usage evidence")
    try:
        provider_cost_retained = _stored_bool(
            item.get("provider_cost_retained"), "provider_cost_retained"
        )
        if provider_cost_retained is not True:
            raise _AllowanceDependencyFailure(
                "malformed provider usage evidence"
            )
        return ProviderUsageEvidence.model_validate(
            {
                "evidence_id": item.get("evidence_id"),
                "effect_id": item.get("effect_id"),
                "provider_request_id_digest": item.get(
                    "provider_request_id_digest"
                ),
                "model_id_digest": item.get("model_id_digest"),
                "input_tokens": _stored_count(
                    item.get("input_tokens"), "input_tokens"
                ),
                "output_tokens": _stored_count(
                    item.get("output_tokens"), "output_tokens"
                ),
                "provider_cost_retained": provider_cost_retained,
                "observed_at": item.get("observed_at"),
            }
        )
    except (TypeError, ValueError) as exc:
        raise _AllowanceDependencyFailure("malformed provider usage evidence") from exc


def _classify_provider_evidence(
    item: Mapping[str, object],
    *,
    payload_digest: str,
) -> ProviderUsageResult:
    try:
        evidence = _evidence_from_item(item)
        stored_digest = _sha256(
            item.get("provider_payload_digest"), "provider_payload_digest"
        )
    except (_AllowanceDependencyFailure, ValueError):
        return ProviderUsageResult(ProviderUsageDisposition.RETRYABLE)
    disposition = (
        ProviderUsageDisposition.REPLAYED
        if stored_digest == payload_digest
        else ProviderUsageDisposition.IDEMPOTENCY_CONFLICT
    )
    return ProviderUsageResult(disposition, evidence=evidence)


def record_provider_usage(
    *,
    beneficiary_id: str,
    effect_id: str,
    provider_request_id_digest: str,
    model_id_digest: str,
    input_tokens: int,
    output_tokens: int,
    observed_at: datetime,
    table: object | None = None,
) -> ProviderUsageResult:
    """Persist one immutable provider observation and increment cost exactly once."""
    beneficiary = _required_text(beneficiary_id, "beneficiary_id")
    effect = _sha256(effect_id, "effect_id")
    request_digest = _sha256(
        provider_request_id_digest, "provider_request_id_digest"
    )
    provider_model_digest = _sha256(model_id_digest, "model_id_digest")
    actual_input = _exact_count(input_tokens, "input_tokens")
    actual_output = _exact_count(output_tokens, "output_tokens")
    now = _aware_timestamp(observed_at, "observed_at")
    evidence_id = _evidence_id(effect)
    evidence_key = _evidence_key(beneficiary, evidence_id)
    effect_key = _effect_key(beneficiary, effect)
    payload_digest = _payload_digest(
        "provider_usage",
        {
            "beneficiary_id": beneficiary,
            "effect_id": effect,
            "provider_request_id_digest": request_digest,
            "model_id_digest": provider_model_digest,
            "input_tokens": actual_input,
            "output_tokens": actual_output,
        },
    )
    target = table or get_table()
    try:
        existing_evidence = _strong_get(target, evidence_key)
        if existing_evidence is not None:
            return _classify_provider_evidence(
                existing_evidence, payload_digest=payload_digest
            )
    except _AllowanceDependencyFailure:
        return ProviderUsageResult(ProviderUsageDisposition.RETRYABLE)

    for _ in range(4):
        try:
            raw_effect = _strong_get(target, effect_key)
            if raw_effect is None:
                return ProviderUsageResult(ProviderUsageDisposition.INVALID_STATE)
            current_effect = _validated_effect(
                raw_effect, beneficiary_id=beneficiary, effect_id=effect
            )
            if current_effect["state"] != "reserved":
                existing_evidence = _strong_get(target, evidence_key)
                if existing_evidence is not None:
                    return _classify_provider_evidence(
                        existing_evidence, payload_digest=payload_digest
                    )
                return ProviderUsageResult(ProviderUsageDisposition.INVALID_STATE)
            week = ZurichWeek.model_validate(
                {
                    "iso_year": current_effect["iso_year"],
                    "iso_week": current_effect["iso_week"],
                    "window_start": current_effect["window_start"],
                    "window_end": current_effect["window_end"],
                }
            )
            raw_counter = _strong_get(
                target, _counter_key(beneficiary, str(current_effect["week_identity"]))
            )
            if raw_counter is None:
                return ProviderUsageResult(ProviderUsageDisposition.RETRYABLE)
            counter = _validated_counter(
                raw_counter, beneficiary_id=beneficiary, week=week
            )
        except (_AllowanceDependencyFailure, TypeError, ValueError, KeyError):
            return ProviderUsageResult(ProviderUsageDisposition.RETRYABLE)

        evidence_item: AllowanceItem = {
            **evidence_key,
            "entity_type": "provider_usage_evidence",
            "schema_version": PROVIDER_USAGE_EVIDENCE_SCHEMA_VERSION,
            "evidence_id": evidence_id,
            "effect_id": effect,
            "beneficiary_id": beneficiary,
            "week_identity": current_effect["week_identity"],
            "provider_request_id_digest": request_digest,
            "model_id_digest": provider_model_digest,
            "input_tokens": actual_input,
            "output_tokens": actual_output,
            "provider_cost_retained": True,
            "provider_payload_digest": payload_digest,
            "observed_at": _timestamp_text(now),
        }
        next_effect = {
            **current_effect,
            "state": "observed",
            "state_version": int(current_effect["state_version"]) + 1,
            "evidence_id": evidence_id,
            "provider_input_tokens": actual_input,
            "provider_output_tokens": actual_output,
            "provider_payload_digest": payload_digest,
            "provider_observed_at": _timestamp_text(now),
            "updated_at": _timestamp_text(now),
        }
        try:
            next_provider_input = _checked_add(
                int(counter["provider_cost_input_tokens"]), actual_input
            )
            next_provider_output = _checked_add(
                int(counter["provider_cost_output_tokens"]), actual_output
            )
        except _AllowanceDependencyFailure:
            return ProviderUsageResult(ProviderUsageDisposition.RETRYABLE)
        next_counter = {
            **counter,
            "provider_cost_input_tokens": next_provider_input,
            "provider_cost_output_tokens": next_provider_output,
            "state_version": int(counter["state_version"]) + 1,
            "updated_at": _timestamp_text(now),
        }
        operations = [
            account_deletion_repo.active_fence_condition(
                beneficiary, int(current_effect["account_fence_generation"])
            ),
            _put_create(evidence_item),
            _put_replace(
                next_effect,
                expected_state_version=int(current_effect["state_version"]),
                expected_state="reserved",
            ),
            _put_replace(
                next_counter,
                expected_state_version=int(counter["state_version"]),
            ),
        ]
        try:
            _transact(operations, table=target)
        except Exception:
            try:
                raced = _strong_get(target, evidence_key)
            except _AllowanceDependencyFailure:
                return ProviderUsageResult(ProviderUsageDisposition.RETRYABLE)
            if raced is not None:
                return _classify_provider_evidence(
                    raced, payload_digest=payload_digest
                )
            continue
        return ProviderUsageResult(
            ProviderUsageDisposition.RECORDED,
            evidence=_evidence_from_item(evidence_item),
        )
    return ProviderUsageResult(ProviderUsageDisposition.RETRYABLE)


def _finalization_from_effect(item: Mapping[str, object]) -> AllowanceFinalization:
    try:
        provider_cost_retained = _stored_bool(
            item.get("provider_cost_retained"), "provider_cost_retained"
        )
        technical_validation_passed = _stored_bool(
            item.get("technical_validation_passed"),
            "technical_validation_passed",
        )
        safety_check_passed = _stored_bool(
            item.get("safety_check_passed"), "safety_check_passed"
        )
        durable_result_stored = _stored_bool(
            item.get("durable_result_stored"), "durable_result_stored"
        )
        stable_replay_readable = _stored_bool(
            item.get("stable_replay_readable"), "stable_replay_readable"
        )
        return AllowanceFinalization.model_validate(
            {
                "reservation_id": item.get("reservation_id"),
                "evidence_id": item.get("evidence_id"),
                "finalized_input_tokens": _stored_count(
                    item.get("finalized_input_tokens"), "finalized_input_tokens"
                ),
                "finalized_output_tokens": _stored_count(
                    item.get("finalized_output_tokens"), "finalized_output_tokens"
                ),
                "restored_input_tokens": _stored_count(
                    item.get("restored_input_tokens"), "restored_input_tokens"
                ),
                "restored_output_tokens": _stored_count(
                    item.get("restored_output_tokens"), "restored_output_tokens"
                ),
                "provider_cost_retained": provider_cost_retained,
                "technical_validation_passed": technical_validation_passed,
                "safety_check_passed": safety_check_passed,
                "durable_result_stored": durable_result_stored,
                "stable_replay_readable": stable_replay_readable,
                "state_version": _stored_count(
                    item.get("state_version"), "state_version", positive=True
                ),
                "finalized_at": item.get("finalized_at"),
            }
        )
    except (TypeError, ValueError) as exc:
        raise _AllowanceDependencyFailure("malformed allowance finalization") from exc


def _classify_finalization(
    item: Mapping[str, object],
    *,
    payload_digest: str,
) -> FinalizationResult:
    try:
        finalization = _finalization_from_effect(item)
        stored_digest = _sha256(
            item.get("finalization_payload_digest"), "finalization_payload_digest"
        )
    except (_AllowanceDependencyFailure, ValueError):
        return FinalizationResult(FinalizationDisposition.RETRYABLE)
    disposition = (
        FinalizationDisposition.REPLAYED
        if stored_digest == payload_digest
        else FinalizationDisposition.IDEMPOTENCY_CONFLICT
    )
    return FinalizationResult(disposition, finalization=finalization)


def _complete_allowance(
    *,
    beneficiary_id: str,
    effect_id: str,
    restore: bool,
    technical_validation_passed: bool,
    safety_check_passed: bool,
    durable_result_stored: bool,
    stable_replay_readable: bool,
    finalized_at: datetime,
    table: object | None,
) -> FinalizationResult:
    beneficiary = _required_text(beneficiary_id, "beneficiary_id")
    effect = _sha256(effect_id, "effect_id")
    flags = (
        technical_validation_passed,
        safety_check_passed,
        durable_result_stored,
        stable_replay_readable,
    )
    if any(not isinstance(flag, bool) for flag in flags):
        raise ValueError("finalization flags must be booleans")
    delivered = all(flags)
    if restore == delivered:
        raise ValueError(
            "delivered results must finalize and undelivered results must restore"
        )
    now = _aware_timestamp(finalized_at, "finalized_at")
    payload_digest = _payload_digest(
        "restoration" if restore else "finalization",
        {
            "beneficiary_id": beneficiary,
            "effect_id": effect,
            "technical_validation_passed": technical_validation_passed,
            "safety_check_passed": safety_check_passed,
            "durable_result_stored": durable_result_stored,
            "stable_replay_readable": stable_replay_readable,
        },
    )
    target = table or get_table()
    effect_key = _effect_key(beneficiary, effect)

    for _ in range(4):
        try:
            raw_effect = _strong_get(target, effect_key)
            if raw_effect is None:
                return FinalizationResult(FinalizationDisposition.INVALID_STATE)
            current_effect = _validated_effect(
                raw_effect, beneficiary_id=beneficiary, effect_id=effect
            )
            if current_effect["state"] in {"finalized", "restored"}:
                return _classify_finalization(
                    current_effect, payload_digest=payload_digest
                )
            if current_effect["state"] != "observed":
                return FinalizationResult(FinalizationDisposition.INVALID_STATE)
            week = ZurichWeek.model_validate(
                {
                    "iso_year": current_effect["iso_year"],
                    "iso_week": current_effect["iso_week"],
                    "window_start": current_effect["window_start"],
                    "window_end": current_effect["window_end"],
                }
            )
            raw_counter = _strong_get(
                target, _counter_key(beneficiary, str(current_effect["week_identity"]))
            )
            evidence_item = _strong_get(
                target,
                _evidence_key(beneficiary, str(current_effect["evidence_id"])),
            )
            if raw_counter is None or evidence_item is None:
                return FinalizationResult(FinalizationDisposition.RETRYABLE)
            counter = _validated_counter(
                raw_counter, beneficiary_id=beneficiary, week=week
            )
            evidence = _evidence_from_item(evidence_item)
        except (
            _AllowanceDependencyFailure,
            TypeError,
            ValueError,
            KeyError,
        ):
            return FinalizationResult(FinalizationDisposition.RETRYABLE)

        reserved_input = _stored_count(
            current_effect.get("reservation_input_tokens"),
            "reservation_input_tokens",
        )
        reserved_output = _stored_count(
            current_effect.get("reservation_output_tokens"),
            "reservation_output_tokens",
        )
        if (
            (
                not restore
                and (
                    evidence.input_tokens > reserved_input
                    or evidence.output_tokens > reserved_output
                )
            )
            or int(counter["reserved_input_tokens"]) < reserved_input
            or int(counter["reserved_output_tokens"]) < reserved_output
        ):
            return FinalizationResult(FinalizationDisposition.INVALID_STATE)

        finalized_input = 0 if restore else evidence.input_tokens
        finalized_output = 0 if restore else evidence.output_tokens
        restored_input = reserved_input if restore else 0
        restored_output = reserved_output if restore else 0
        next_effect = {
            **current_effect,
            "state": "restored" if restore else "finalized",
            "state_version": int(current_effect["state_version"]) + 1,
            "finalized_input_tokens": finalized_input,
            "finalized_output_tokens": finalized_output,
            "restored_input_tokens": restored_input,
            "restored_output_tokens": restored_output,
            "provider_cost_retained": True,
            "technical_validation_passed": technical_validation_passed,
            "safety_check_passed": safety_check_passed,
            "durable_result_stored": durable_result_stored,
            "stable_replay_readable": stable_replay_readable,
            "finalization_payload_digest": payload_digest,
            "finalized_at": _timestamp_text(now),
            "restored_at": _timestamp_text(now) if restore else None,
            "updated_at": _timestamp_text(now),
        }
        try:
            next_finalized_input = _checked_add(
                int(counter["finalized_input_tokens"]), finalized_input
            )
            next_finalized_output = _checked_add(
                int(counter["finalized_output_tokens"]), finalized_output
            )
        except _AllowanceDependencyFailure:
            return FinalizationResult(FinalizationDisposition.RETRYABLE)
        next_counter = {
            **counter,
            "reserved_input_tokens": int(counter["reserved_input_tokens"])
            - reserved_input,
            "reserved_output_tokens": int(counter["reserved_output_tokens"])
            - reserved_output,
            "finalized_input_tokens": next_finalized_input,
            "finalized_output_tokens": next_finalized_output,
            "state_version": int(counter["state_version"]) + 1,
            "updated_at": _timestamp_text(now),
        }
        operations = [
            account_deletion_repo.active_fence_condition(
                beneficiary, int(current_effect["account_fence_generation"])
            ),
            _put_replace(
                next_effect,
                expected_state_version=int(current_effect["state_version"]),
                expected_state="observed",
            ),
            _put_replace(
                next_counter,
                expected_state_version=int(counter["state_version"]),
            ),
        ]
        try:
            _transact(operations, table=target)
        except Exception:
            try:
                raced = _strong_get(target, effect_key)
            except _AllowanceDependencyFailure:
                return FinalizationResult(FinalizationDisposition.RETRYABLE)
            if raced is not None and raced.get("state") in {"finalized", "restored"}:
                return _classify_finalization(raced, payload_digest=payload_digest)
            continue
        return FinalizationResult(
            FinalizationDisposition.RESTORED
            if restore
            else FinalizationDisposition.FINALIZED,
            finalization=_finalization_from_effect(next_effect),
        )
    return FinalizationResult(FinalizationDisposition.RETRYABLE)


def finalize_allowance(
    *,
    beneficiary_id: str,
    effect_id: str,
    technical_validation_passed: bool,
    safety_check_passed: bool,
    durable_result_stored: bool,
    stable_replay_readable: bool,
    finalized_at: datetime,
    table: object | None = None,
) -> FinalizationResult:
    """Finalize actual user debit only after all delivery predicates pass."""
    return _complete_allowance(
        beneficiary_id=beneficiary_id,
        effect_id=effect_id,
        restore=False,
        technical_validation_passed=technical_validation_passed,
        safety_check_passed=safety_check_passed,
        durable_result_stored=durable_result_stored,
        stable_replay_readable=stable_replay_readable,
        finalized_at=finalized_at,
        table=table,
    )


def restore_allowance(
    *,
    beneficiary_id: str,
    effect_id: str,
    technical_validation_passed: bool,
    safety_check_passed: bool,
    durable_result_stored: bool,
    stable_replay_readable: bool,
    restored_at: datetime,
    table: object | None = None,
) -> FinalizationResult:
    """Release user reservation while retaining immutable provider-cost evidence."""
    return _complete_allowance(
        beneficiary_id=beneficiary_id,
        effect_id=effect_id,
        restore=True,
        technical_validation_passed=technical_validation_passed,
        safety_check_passed=safety_check_passed,
        durable_result_stored=durable_result_stored,
        stable_replay_readable=stable_replay_readable,
        finalized_at=restored_at,
        table=table,
    )


def get_allowance_counter(
    *,
    beneficiary_id: str,
    week: ZurichWeek,
    table: object | None = None,
) -> AllowanceItem | None:
    """Load one strict weekly counter; malformed persisted numbers fail closed."""
    beneficiary = _required_text(beneficiary_id, "beneficiary_id")
    target = table or get_table()
    raw = _strong_get(
        target, _counter_key(beneficiary, _week_identity(week))
    )
    return (
        _validated_counter(raw, beneficiary_id=beneficiary, week=week)
        if raw is not None
        else None
    )


def list_provider_usage_evidence(
    *,
    beneficiary_id: str,
    week_identity: str,
    table: object | None = None,
) -> list[ProviderUsageEvidence]:
    """List exact content-free evidence for one beneficiary and week."""
    beneficiary = _required_text(beneficiary_id, "beneficiary_id")
    identity = _required_text(week_identity, "week_identity", maximum=8)
    target = table or get_table()
    evidence: list[ProviderUsageEvidence] = []
    for item in _query_evidence(target, beneficiary):
        if item.get("week_identity") != identity:
            continue
        evidence.append(_evidence_from_item(item))
    return sorted(evidence, key=lambda item: (item.observed_at, item.evidence_id))


__all__ = [
    "ALLOWANCE_COUNTER_SCHEMA_VERSION",
    "ALLOWANCE_EFFECT_SCHEMA_VERSION",
    "PROVIDER_USAGE_EVIDENCE_SCHEMA_VERSION",
    "FinalizationDisposition",
    "FinalizationResult",
    "ProviderUsageDisposition",
    "ProviderUsageResult",
    "ReservationDisposition",
    "ReservationResult",
    "finalize_allowance",
    "get_allowance_counter",
    "list_provider_usage_evidence",
    "record_provider_usage",
    "reserve_allowance",
    "restore_allowance",
]
