"""The push channel, and the devices a reader registers for it.

Inside the notification package (#686). A device is registered and revoked
through the reader door; a send happens only from `_bell.create_event`, after
the bell row is stored, and crosses the only-once ledger (`_ledger`).
"""

from __future__ import annotations

import json
from typing import Any, Mapping
from urllib import request

from stoa import config
from stoa.db.repositories import notification_repo
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.security.identity import Actor
from stoa.services.notification_errors import NotificationErrorCode as _N, NotificationViolation
from stoa.services.notifications import _ledger
from stoa.services.notifications._common import (
    hash_value as _hash_value,
    now_iso,
    safe_text as _safe_text,
    user_id_of as _user_id,
    user_role_of as _user_role,
)

PUSH_TOKEN_STATUSES = {"active", "revoked"}
PUSH_TOKEN_PLATFORMS = {"ios", "android", "web"}


def register_push_token(
    user: dict[str, Any] | Actor,
    *,
    platform: str,
    token: str | None = None,
    provider_token_reference: str | None = None,
    device_id: str | None = None,
) -> dict[str, Any]:
    normalized_platform = _safe_text(platform).lower()
    if normalized_platform not in PUSH_TOKEN_PLATFORMS:
        raise NotificationViolation(_N.PUSH_PLATFORM_UNSUPPORTED)
    clean_token = _safe_text(token)
    clean_provider_reference = _safe_text(provider_token_reference)
    if not clean_token and not clean_provider_reference:
        raise NotificationViolation(_N.PUSH_TOKEN_REQUIRED)
    user_id = _user_id(user)
    if not user_id:
        raise SecurityDecisionError(SecurityErrorCode.AUTHENTICATION_REQUIRED)

    token_hash = _hash_value(clean_token or clean_provider_reference)
    token_reference = f"push-{token_hash[:16]}"
    # A provider/body alias is itself an ownership coordinate.  Resolve any
    # existing canonical token before the put so one actor cannot adopt or
    # rotate another actor's device reference. The candidates are every
    # registration of the device the token or the reference names (#624).
    for existing in notification_repo.list_device_push_tokens(
        notification_repo.push_token_lookup_keys(
            token_hash=token_hash,
            provider_token_reference=clean_provider_reference or None,
        )
    ):
        same_material = (
            existing.get("token_hash") == token_hash
            or (
                clean_provider_reference
                and existing.get("provider_token_reference") == clean_provider_reference
            )
        )
        if same_material and existing.get("user_id") != user_id:
            raise SecurityDecisionError(SecurityErrorCode.RESOURCE_NOT_FOUND)
    now = now_iso()
    item: dict[str, object] = {
        "entity_type": notification_repo.PUSH_TOKEN_ENTITY,
        "user_id": user_id,
        "role": _user_role(user),
        "platform": normalized_platform,
        "token_reference": token_reference,
        "token_hash": token_hash,
        "provider_token_reference": clean_provider_reference or None,
        "device_id_hash": _hash_value(device_id) if _safe_text(device_id) else None,
        "status": "active",
        "created_at": now,
        "last_seen_at": now,
        "revoked_at": None,
        "owner_id": user_id,
    }
    persisted = notification_repo.put_push_token(item)
    if isinstance(persisted, dict):
        item = persisted
    return push_token_response(item)


def revoke_authorized_push_token(item: Mapping[str, object]) -> dict[str, Any]:
    updated = notification_repo.update_push_token(
        str(item.get("user_id") or ""),
        str(item.get("token_reference") or ""),
        {"status": "revoked", "revoked_at": now_iso()},
    )
    if not updated:
        raise NotificationViolation(_N.PUSH_TOKEN_NOT_FOUND)
    return push_token_response(updated)


def attempt_push_delivery_safe(item: dict[str, Any]) -> dict[str, Any] | None:
    try:
        return attempt_push_delivery(item)
    except Exception:
        return None


def attempt_push_delivery(
    item: dict[str, Any],
    *,
    send_func: Any | None = None,
) -> dict[str, Any]:
    readiness = push_provider_readiness()
    event_id = str(item.get("event_id") or "")
    # Under the event's own fixed id (#686): a refused attempt is recorded under
    # it, a send under the ledger's operation id derived from the stored event.
    delivery_id = f"push-{event_id}"
    batch: _ledger.AuthoritativeDeliveryBatch | None = None
    ownership_error: _ledger.DeliveryOwnershipError | None = None
    try:
        batch = _ledger.load_authoritative_delivery_events([event_id])
    except _ledger.DeliveryOwnershipError as exc:
        ownership_error = exc
    canonical = batch.events[0] if batch is not None else {}
    recipient_id = str(canonical.get("recipient_id") or "")
    tokens = (
        notification_repo.list_user_push_tokens(recipient_id, status="active")
        if batch is not None and recipient_id
        else []
    )
    token_refs = [
        str(token.get("provider_token_reference") or token.get("token_reference") or "")
        for token in tokens
        if str(token.get("provider_token_reference") or token.get("token_reference") or "").strip()
    ]
    attempt = {
        "delivery_id": delivery_id,
        "attempted_at": now_iso(),
        "channel": "push",
        "provider": readiness["provider"],
        "provider_mode": readiness["mode"],
        "template": config.settings().notification_push_template,
        "token_count": len(token_refs),
        "token_references": [_redacted_reference(token_ref) for token_ref in token_refs],
        "status": "pending",
        "provider_result": {},
    }

    if ownership_error is not None:
        attempt["status"] = ownership_error.status
    elif not recipient_id:
        attempt["status"] = "refused_missing_recipient_id"
    elif not token_refs:
        attempt["status"] = "refused_missing_token"
    elif readiness["mode"] == "disabled" or readiness["blockers"]:
        attempt["status"] = "refused_provider_not_ready"
    elif not config.settings().notification_push_send_enabled and send_func is None:
        attempt["status"] = "refused_provider_send_disabled"
    else:
        assert batch is not None
        discriminator = _ledger.canonical_payload_digest(
            {
                "token_references": token_refs,
                "template": config.settings().notification_push_template,
            }
        )
        delivery_id = _ledger.authoritative_delivery_operation_id(
            channel="push", batch=batch, discriminator=discriminator
        )
        attempt["delivery_id"] = delivery_id
        payload = {
            "deliveryId": delivery_id,
            "tokenReferences": token_refs,
            "title": canonical.get("title"),
            "body": canonical.get("summary"),
            "data": {
                "eventId": canonical.get("event_id"),
                "eventType": canonical.get("event_type"),
                "targetType": canonical.get("target_type"),
                "targetId": canonical.get("target_id"),
            },
            "template": config.settings().notification_push_template,
        }
        result = _ledger.run_authoritative_delivery(
            channel="push",
            batch=batch,
            payload=payload,
            discriminator=discriminator,
            provider_call=lambda: (
                send_func(payload)
                if send_func is not None
                else _send_push_provider(payload)
            ),
        )
        attempt["status"] = {
            "accepted": "sent",
            "provider_acceptance_unknown": "provider_acceptance_unknown",
            "canceled_account_deletion": "canceled_account_deletion",
        }.get(str(result.get("status") or ""), "retryable")

    _record_event_attempts([event_id], "push_delivery_attempts", attempt)
    return {
        "deliveryId": delivery_id,
        "status": attempt["status"],
        "providerMode": readiness["mode"],
        "tokenCount": len(token_refs),
        "providerResult": attempt["provider_result"],
    }


def push_provider_readiness() -> dict[str, Any]:
    provider = _safe_text(config.settings().notification_push_provider)
    template = _safe_text(config.settings().notification_push_template)
    api_key = _safe_text(config.settings().notification_push_provider_api_key)
    endpoint = _safe_text(config.settings().notification_push_provider_endpoint_url)
    blockers = []
    if not provider:
        blockers.append("missing_notification_push_provider")
    if provider and not config.settings().notification_push_provider_approved:
        blockers.append("notification_push_provider_not_approved")
    if provider and not template:
        blockers.append("missing_notification_push_template")
    if provider and config.settings().notification_push_send_enabled and not endpoint:
        blockers.append("missing_notification_push_provider_endpoint_url")
    mode = "disabled"
    if provider:
        mode = "provider_ready" if not blockers and config.settings().notification_push_send_enabled else "configured"
    return {
        "provider": provider or "disabled",
        "mode": mode,
        "configured": bool(provider and not blockers),
        "approved": bool(config.settings().notification_push_provider_approved),
        "sendEnabled": bool(config.settings().notification_push_send_enabled),
        "credentials": "configured" if api_key else "missing",
        "endpointConfigured": bool(endpoint),
        "template": template,
        "blockers": blockers,
    }


def push_token_response(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "tokenReference": item.get("token_reference"),
        "platform": item.get("platform"),
        "status": item.get("status"),
        "tokenHashPrefix": str(item.get("token_hash") or "")[:12],
        "hasProviderReference": bool(item.get("provider_token_reference")),
        "createdAt": item.get("created_at"),
        "lastSeenAt": item.get("last_seen_at"),
        "revokedAt": item.get("revoked_at"),
    }


def _record_event_attempts(event_ids: list[str], metadata_key: str, attempt: dict[str, Any]) -> None:
    for event_id in [event_id for event_id in event_ids if event_id]:
        item = notification_repo.get_event(event_id)
        if not item:
            continue
        if item.get("owner_classification") == "global_nonprivate":
            continue
        raw_metadata = item.get("metadata")
        metadata: dict[str, object] = (
            dict(raw_metadata) if isinstance(raw_metadata, Mapping) else {}
        )
        raw_attempts = metadata.get(metadata_key)
        attempts = list(raw_attempts) if isinstance(raw_attempts, list) else []
        attempts.append(attempt)
        metadata[metadata_key] = attempts[-5:]
        notification_repo.update_event(event_id, {"metadata": metadata})


def _send_push_provider(payload: dict[str, Any]) -> dict[str, Any]:
    endpoint = _safe_text(config.settings().notification_push_provider_endpoint_url)
    if not endpoint:
        raise RuntimeError("notification push provider endpoint is not configured")
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    api_key = _safe_text(config.settings().notification_push_provider_api_key)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = request.Request(endpoint, data=body, headers=headers, method="POST")
    with request.urlopen(req, timeout=5) as response:
        raw = response.read().decode("utf-8")
    return {"statusCode": response.status, "bodyHash": _hash_value(raw) if raw else None}



def _redacted_reference(value: str) -> str:
    text = _safe_text(value)
    if not text:
        return ""
    digest = _hash_value(text)
    return f"ref-{digest[:12]}"
