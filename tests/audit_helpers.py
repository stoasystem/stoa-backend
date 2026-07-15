"""Injected authorization-audit doubles; never access AWS."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import hmac

from stoa.db.repositories.security_audit_repo import AuthorizationAuditRecord


class MemoryAuthorizationAuditSink:
    def __init__(self, *, secret: bytes = b"test-authorization-audit-key", fail: bool = False):
        self.secret = secret
        self.fail = fail
        self.events: dict[str, dict[str, object]] = {}
        self.aggregates: dict[tuple[str, ...], dict[str, object]] = {}

    def persist_authorization_decision(self, **values):
        if self.fail:
            raise RuntimeError("audit-outage-canary")
        raw = "\x00".join(
            str(values.get(key) or "")
            for key in ("resource_type", "resource_id", "student_id", "owner_id", "scope_discriminator")
        ).encode()
        fingerprint = hmac.new(self.secret, raw, hashlib.sha256).hexdigest()
        event_material = "\x00".join(
            str(values.get(key) or "")
            for key in (
                "correlation_id", "actor_id", "policy_version", "resource_type",
                "action", "purpose", "result", "decision_kind",
            )
        ) + "\x00" + fingerprint
        event_id = hashlib.sha256(event_material.encode()).hexdigest()
        actor_fingerprint = hmac.new(
            self.secret, str(values["actor_id"]).encode(), hashlib.sha256
        ).hexdigest()
        replayed = event_id in self.events
        self.events.setdefault(
            event_id,
            {
                "event_id": event_id,
                "event_type": "authorization_sensitive_allowed"
                if values["result"] == "allowed"
                else "authorization_denied",
                "actor_fingerprint": actor_fingerprint,
                "actor_role": values["actor_role"],
                "resource_type": values["resource_type"],
                "action": values["action"],
                "purpose": values["purpose"],
                "result_code": values["result"],
                "version": values["policy_version"],
                "decision_kind": values["decision_kind"],
                "resource_fingerprint": fingerprint,
                "audit_key_id": "test-v1",
                "correlation_id": values["correlation_id"],
            },
        )
        return AuthorizationAuditRecord(event_id, fingerprint, "test-v1", replayed)

    def aggregate_authorization_probe(self, *, record, **values):
        if self.fail:
            raise RuntimeError("audit-outage-canary")
        bucket = str(int(datetime.now(UTC).timestamp()) // 300)
        actor_fingerprint = hmac.new(
            self.secret, str(values["actor_id"]).encode(), hashlib.sha256
        ).hexdigest()
        key = (actor_fingerprint,) + tuple(
            str(values[name])
            for name in ("resource_type", "action", "purpose", "result", "policy_version")
        ) + (record.audit_key_id, bucket)
        row = self.aggregates.setdefault(key, {"count": 0, "event_ids": set()})
        if record.event_id not in row["event_ids"]:
            row["event_ids"].add(record.event_id)
            row["count"] = min(int(row["count"]) + 1, 100)
        return row
