"""Append-only, allowlisted security lifecycle and authorization evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import hmac
from typing import Any, Mapping, Protocol, Sequence

from botocore.exceptions import ClientError

from stoa.config import validate_authorization_audit_keyring
from stoa.db.dynamodb import get_table


AUTHORIZATION_EVENT_TYPES = frozenset(
    {
        "authorization_denied",
        "authorization_sensitive_allowed",
        "authorization_probe_aggregated",
        "break_glass_notification_recorded",
        "break_glass_review_required",
    }
)


SAFE_AUDIT_FIELDS = frozenset(
    {
        "event_id",
        "event_type",
        "actor_id",
        "actor_fingerprint",
        "actor_role",
        "target_id",
        "target_type",
        "resource_type",
        "action",
        "purpose",
        "result_code",
        "version",
        "reason_code",
        "evidence_reference",
        "correlation_id",
        "command_id",
        "created_at",
        "decision_kind",
        "resource_fingerprint",
        "audit_key_id",
        "probe_bucket",
        "probe_count",
        "threshold_reached",
        "first_seen_at",
        "last_seen_at",
        "expires_at",
    }
)


class DuplicateSecurityAuditEvent(RuntimeError):
    """An immutable audit event identifier has already been used."""


class AuthorizationAuditUnavailable(RuntimeError):
    """Durable authorization evidence cannot currently be recorded."""


@dataclass(frozen=True, slots=True)
class AuthorizationAuditKey:
    key_id: str
    secret: bytes


@dataclass(frozen=True, slots=True)
class AuthorizationAuditRecord:
    event_id: str
    resource_fingerprint: str
    audit_key_id: str
    replayed: bool = False


class AuthorizationAuditSink(Protocol):
    """Minimal durable boundary used by the authorization gateway."""

    def persist_authorization_decision(
        self,
        *,
        correlation_id: str,
        actor_id: str,
        actor_role: str,
        policy_version: str,
        resource_type: str,
        resource_id: str,
        student_id: str,
        owner_id: str | None,
        scope_discriminator: str,
        action: str,
        purpose: str,
        result: str,
        decision_kind: str,
        evidence_reference: str | None,
        created_at: datetime | None = None,
    ) -> AuthorizationAuditRecord: ...

    def aggregate_authorization_probe(
        self,
        *,
        record: AuthorizationAuditRecord,
        actor_id: str,
        resource_type: str,
        action: str,
        purpose: str,
        result: str,
        policy_version: str,
        created_at: datetime | None = None,
    ) -> Mapping[str, Any]: ...


class UnavailableAuthorizationAuditSink:
    """Injected fail-closed boundary for absent or invalid key configuration."""

    def persist_authorization_decision(self, **_values):
        raise AuthorizationAuditUnavailable("authorization_audit_key_unavailable")

    def aggregate_authorization_probe(self, **_values):
        raise AuthorizationAuditUnavailable("authorization_audit_key_unavailable")


def _canonical_parts(parts: Sequence[str]) -> bytes:
    encoded = bytearray()
    for part in parts:
        value = str(part).encode("utf-8")
        encoded.extend(len(value).to_bytes(4, "big"))
        encoded.extend(value)
    return bytes(encoded)


def _keyed_fingerprint(key: AuthorizationAuditKey, parts: Sequence[str]) -> str:
    return hmac.new(key.secret, _canonical_parts(parts), hashlib.sha256).hexdigest()


def _decision_event_id(
    key: AuthorizationAuditKey,
    *,
    correlation_id: str,
    actor_id: str,
    policy_version: str,
    resource_type: str,
    action: str,
    purpose: str,
    result: str,
    decision_kind: str,
    resource_fingerprint: str,
) -> str:
    material = _canonical_parts(
        (
            correlation_id,
            actor_id,
            policy_version,
            resource_type,
            action,
            purpose,
            result,
            decision_kind,
            resource_fingerprint,
            key.key_id,
        )
    )
    return hashlib.sha256(material).hexdigest()


class DynamoAuthorizationAuditSink:
    """DynamoDB-backed evidence sink with keyed identities and bounded probes."""

    def __init__(
        self,
        *,
        active_key_id: str,
        active_secret: str,
        previous_keys: Mapping[str, str] | None = None,
        allow_development_default: bool = False,
        probe_window_seconds: int = 300,
        probe_ttl_seconds: int = 86400,
        probe_count_cap: int = 100,
        probe_id_cap: int = 256,
    ) -> None:
        try:
            active, previous = validate_authorization_audit_keyring(
                active_key_id,
                active_secret,
                dict(previous_keys or {}),
                allow_development_default=allow_development_default,
            )
        except (TypeError, ValueError) as exc:
            raise AuthorizationAuditUnavailable("authorization_audit_key_unavailable") from exc
        self._active = AuthorizationAuditKey(active.key_id, active.secret)
        self._previous = tuple(
            AuthorizationAuditKey(key.key_id, key.secret) for key in previous
        )
        self._window = probe_window_seconds
        self._ttl = probe_ttl_seconds
        self._count_cap = probe_count_cap
        self._id_cap = probe_id_cap

    @property
    def keys(self) -> tuple[AuthorizationAuditKey, ...]:
        return (self._active, *self._previous)

    def _identity_for_key(
        self,
        key: AuthorizationAuditKey,
        *,
        correlation_id: str,
        actor_id: str,
        policy_version: str,
        resource_type: str,
        resource_id: str,
        student_id: str,
        owner_id: str | None,
        scope_discriminator: str,
        action: str,
        purpose: str,
        result: str,
        decision_kind: str,
    ) -> tuple[str, str, str]:
        actor_fingerprint = _keyed_fingerprint(key, ("actor", actor_id))
        fingerprint = _keyed_fingerprint(
            key,
            (resource_type, resource_id, student_id, owner_id or "", scope_discriminator),
        )
        return fingerprint, _decision_event_id(
            key,
            correlation_id=correlation_id,
            actor_id=actor_id,
            policy_version=policy_version,
            resource_type=resource_type,
            action=action,
            purpose=purpose,
            result=result,
            decision_kind=decision_kind,
            resource_fingerprint=fingerprint,
        ), actor_fingerprint

    def persist_authorization_decision(
        self,
        *,
        correlation_id: str,
        actor_id: str,
        actor_role: str,
        policy_version: str,
        resource_type: str,
        resource_id: str,
        student_id: str,
        owner_id: str | None,
        scope_discriminator: str,
        action: str,
        purpose: str,
        result: str,
        decision_kind: str,
        evidence_reference: str | None,
        created_at: datetime | None = None,
    ) -> AuthorizationAuditRecord:
        now = created_at or datetime.now(UTC)
        candidates = [
            (*self._identity_for_key(
                key,
                correlation_id=correlation_id,
                actor_id=actor_id,
                policy_version=policy_version,
                resource_type=resource_type,
                resource_id=resource_id,
                student_id=student_id,
                owner_id=owner_id,
                scope_discriminator=scope_discriminator,
                action=action,
                purpose=purpose,
                result=result,
                decision_kind=decision_kind,
            ), key)
            for key in self.keys
        ]
        table = get_table()
        for fingerprint, event_id, actor_fingerprint, key in candidates[1:]:
            existing = table.get_item(
                Key={"PK": f"SECURITY_AUDIT#{actor_fingerprint}", "SK": f"EVENT#{event_id}"},
                ConsistentRead=True,
            ).get("Item")
            if existing:
                return AuthorizationAuditRecord(event_id, fingerprint, key.key_id, True)
        fingerprint, event_id, actor_fingerprint, key = candidates[0]
        event_type = "authorization_sensitive_allowed" if result == "allowed" else "authorization_denied"
        event = {
            "event_id": event_id,
            "event_type": event_type,
            "actor_fingerprint": actor_fingerprint,
            "actor_role": actor_role,
            "resource_type": resource_type,
            "action": action,
            "purpose": purpose,
            "result_code": result,
            "version": policy_version,
            "decision_kind": decision_kind,
            "resource_fingerprint": fingerprint,
            "audit_key_id": key.key_id,
            "evidence_reference": evidence_reference,
            "correlation_id": correlation_id,
            "created_at": now.isoformat(),
        }
        try:
            append_authorization_event(actor_fingerprint, event)
        except DuplicateSecurityAuditEvent:
            return AuthorizationAuditRecord(event_id, fingerprint, key.key_id, True)
        return AuthorizationAuditRecord(event_id, fingerprint, key.key_id)

    def aggregate_authorization_probe(
        self,
        *,
        record: AuthorizationAuditRecord,
        actor_id: str,
        resource_type: str,
        action: str,
        purpose: str,
        result: str,
        policy_version: str,
        created_at: datetime | None = None,
    ) -> Mapping[str, Any]:
        now = created_at or datetime.now(UTC)
        epoch = int(now.timestamp())
        bucket = epoch - (epoch % self._window)
        aggregate_id = hashlib.sha256(
            _canonical_parts(
                (
                    actor_id,
                    resource_type,
                    action,
                    purpose,
                    result,
                    policy_version,
                    record.audit_key_id,
                    str(bucket),
                )
            )
        ).hexdigest()
        audit_key = next(key for key in self.keys if key.key_id == record.audit_key_id)
        actor_fingerprint = _keyed_fingerprint(audit_key, ("actor", actor_id))
        key = {"PK": f"SECURITY_AUDIT#{actor_fingerprint}", "SK": f"PROBE#{aggregate_id}"}
        table = get_table()
        for _attempt in range(3):
            existing = table.get_item(Key=key, ConsistentRead=True).get("Item") or {}
            seen = set(existing.get("decision_event_ids") or ())
            if (
                record.event_id in seen
                or len(seen) >= self._id_cap
                or int(existing.get("probe_count") or 0) >= self._count_cap
            ):
                return existing
            count = min(int(existing.get("probe_count") or 0) + 1, self._count_cap)
            seen.add(record.event_id)
            version = int(existing.get("probe_version") or 0) + 1
            safe = project_audit_event(
                {
                    "event_id": aggregate_id,
                    "event_type": "authorization_probe_aggregated",
                    "actor_fingerprint": actor_fingerprint,
                    "resource_type": resource_type,
                    "action": action,
                    "purpose": purpose,
                    "result_code": result,
                    "version": policy_version,
                    "audit_key_id": record.audit_key_id,
                    "probe_bucket": str(bucket),
                    "probe_count": count,
                    "threshold_reached": count >= min(10, self._count_cap),
                    "first_seen_at": existing.get("first_seen_at") or now.isoformat(),
                    "last_seen_at": now.isoformat(),
                    "expires_at": bucket + self._ttl,
                }
            )
            row = {
                "PK": key["PK"],
                "SK": key["SK"],
                "entity_type": "authorization_probe_aggregate",
                **safe,
                "probe_version": version,
                "decision_event_ids": sorted(seen),
            }
            condition = "attribute_not_exists(PK) AND attribute_not_exists(SK)"
            values = None
            if existing:
                condition = "probe_version = :expected_version"
                values = {":expected_version": version - 1}
            try:
                kwargs: dict[str, Any] = {
                    "Item": row,
                    "ConditionExpression": condition,
                }
                if values:
                    kwargs["ExpressionAttributeValues"] = values
                table.put_item(**kwargs)
                return row
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                    raise
        raise AuthorizationAuditUnavailable("authorization_probe_concurrent_update")


def project_audit_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """Construct an audit row from safe scalar fields, never by redacting a payload."""
    projected = {
        key: event[key]
        for key in SAFE_AUDIT_FIELDS
        if key in event and event[key] is not None
    }
    if not str(projected.get("event_id") or "").strip():
        raise ValueError("event_id is required")
    if not str(projected.get("event_type") or "").strip():
        raise ValueError("event_type is required")
    return projected


def append_event(stream_id: str, event: Mapping[str, Any]) -> dict[str, Any]:
    safe = project_audit_event(event)
    row = {
        "PK": f"SECURITY_AUDIT#{stream_id}",
        "SK": f"EVENT#{safe['event_id']}",
        "entity_type": "security_audit_event",
        **safe,
    }
    try:
        get_table().put_item(
            Item=row,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            raise DuplicateSecurityAuditEvent("security audit event already exists") from exc
        raise
    return row


def append_authorization_event(stream_id: str, event: Mapping[str, Any]) -> dict[str, Any]:
    """Append one allowlisted policy decision or aggregate probe event."""
    if event.get("event_type") not in AUTHORIZATION_EVENT_TYPES:
        raise ValueError("unsupported authorization event type")
    return append_event(stream_id, event)


def append_break_glass_evidence(
    *,
    stream_id: str,
    event_id: str,
    actor_id: str,
    resource_type: str,
    action: str,
    purpose: str,
    incident_id: str,
    notification_reference: str,
    review_reference: str,
    correlation_id: str,
    created_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Record immediate notification and independent-review obligations safely."""
    required = (
        event_id,
        actor_id,
        resource_type,
        action,
        purpose,
        incident_id,
        notification_reference,
        review_reference,
        correlation_id,
        created_at,
    )
    if any(not str(value).strip() for value in required):
        raise ValueError("complete break-glass evidence is required")
    common = {
        "actor_id": actor_id,
        "resource_type": resource_type,
        "action": action,
        "purpose": purpose,
        "reason_code": "incident_break_glass",
        "correlation_id": correlation_id,
        "created_at": created_at,
    }
    notification = append_authorization_event(
        stream_id,
        {
            **common,
            "event_id": f"{event_id}:notification",
            "event_type": "break_glass_notification_recorded",
            "target_id": incident_id,
            "evidence_reference": notification_reference,
        },
    )
    review = append_authorization_event(
        stream_id,
        {
            **common,
            "event_id": f"{event_id}:review",
            "event_type": "break_glass_review_required",
            "target_id": incident_id,
            "evidence_reference": review_reference,
        },
    )
    return notification, review
