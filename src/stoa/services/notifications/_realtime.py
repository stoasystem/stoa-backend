"""The realtime channel: a stored notification posted to its reader's open connections.

Inside the notification package (#686). `websocket_service` keeps the
connections (connect, subscribe, disconnect, clean up, read their state) and
knows nothing of notifications; this module decides which connections a
notification goes to and posts it through the only-once ledger, one intent
per connection.
"""

from __future__ import annotations

import hashlib
from typing import Any

from botocore.exceptions import ClientError

from stoa import config
from stoa.services import websocket_service
from stoa.services.notification_errors import NotificationErrorCode as _N, NotificationViolation
from stoa.services.notifications import _ledger
from stoa.services.notifications._common import now_iso
from stoa.db.repositories import notification_repo

PostConnection = websocket_service.PostConnection


def fanout_notification_event_safe(item: dict[str, Any]) -> dict[str, Any] | None:
    try:
        return fanout_notification_event(item)
    except Exception:
        return None


def fanout_notification_event(
    item: dict[str, Any],
    *,
    post_func: PostConnection | None = None,
) -> dict[str, Any]:
    event_id = str(item.get("event_id") or "")
    if not event_id:
        raise NotificationViolation(_N.NOTIFICATION_EVENT_ID_REQUIRED)

    try:
        batch = _ledger.load_authoritative_delivery_events([event_id])
    except _ledger.DeliveryOwnershipError as exc:
        return {"deliveryId": None, "status": exc.status, "results": []}
    canonical = batch.events[0]
    delivery_id = f"websocket-{batch.event_set_digest[:40]}"
    attempted_at = now_iso()
    target_channels = _target_channels(canonical)
    results: list[dict[str, Any]] = []

    for connection in _reachable_connections(canonical):
        connection_id = str(connection.get("connection_id") or "")
        if not connection_id:
            continue
        connection_ref = _connection_evidence_ref(connection_id)
        if websocket_service.is_expired(connection):
            websocket_service.drop_connection(connection_id)
            results.append(
                {"connection_id": connection_ref, "status": "stale_removed"}
            )
            continue
        raw_channels = connection.get("subscribed_channels")
        if not isinstance(raw_channels, list) or not all(
            isinstance(channel, str) for channel in raw_channels
        ):
            continue
        if not target_channels.intersection(raw_channels):
            continue

        endpoint_url = str(connection.get("endpoint_url") or config.settings().websocket_api_endpoint or "")
        if not endpoint_url and post_func is None:
            results.append(
                {"connection_id": connection_ref, "status": "skipped_no_endpoint"}
            )
            continue
        discriminator = hashlib.sha256(
            (
                "stoa.websocket-connection.v1\x00" + connection_id
            ).encode("utf-8")
        ).hexdigest()
        effect_id = _ledger.authoritative_delivery_operation_id(
            channel="websocket",
            batch=batch,
            discriminator=discriminator,
        )
        envelope = event_envelope(
            canonical, delivery_id=effect_id, delivery_attempt=1
        )
        provider_state = {"gone": False}

        def post() -> None:
            if post_func is not None:
                post_func(connection, envelope)
            else:
                try:
                    websocket_service.post_to_connection(endpoint_url, connection_id, envelope)
                except ClientError as exc:
                    provider_state["gone"] = websocket_service.is_gone_exception(exc)
                    raise

        result = _ledger.run_authoritative_delivery(
            channel="websocket",
            batch=batch,
            payload=envelope,
            discriminator=discriminator,
            provider_call=post,
        )
        status = str(result.get("status") or "")
        if provider_state["gone"]:
            websocket_service.drop_connection(connection_id)
            results.append(
                {"connection_id": connection_ref, "status": "gone_removed"}
            )
            continue
        projected = {
            "accepted": "delivered",
            "provider_acceptance_unknown": "provider_acceptance_unknown",
            "canceled_account_deletion": "canceled_account_deletion",
            "retryable_claim_conflict": "retryable",
        }.get(status, "retryable")
        results.append({"connection_id": connection_ref, "status": projected})
        if projected in {
            "provider_acceptance_unknown",
            "canceled_account_deletion",
            "retryable",
        }:
            break

    _record_delivery_attempt(
        canonical,
        {
            "delivery_id": delivery_id,
            "attempted_at": attempted_at,
            "target_channels": sorted(target_channels),
            "target_count": len(results),
            "results": results,
        },
    )
    return {"deliveryId": delivery_id, "status": "completed", "results": results}


def event_envelope(
    item: dict[str, Any],
    *,
    delivery_id: str,
    delivery_attempt: int,
) -> dict[str, Any]:
    return {
        "eventId": item.get("event_id"),
        "eventType": item.get("event_type"),
        "recipientId": item.get("recipient_id"),
        "recipientRole": item.get("recipient_role"),
        "targetType": item.get("target_type"),
        "targetId": item.get("target_id"),
        "title": item.get("title"),
        "summary": item.get("summary"),
        "createdAt": item.get("created_at"),
        "metadata": item.get("metadata") or {},
        "deliveryId": delivery_id,
        "deliveryAttempt": delivery_attempt,
    }


def _target_channels(item: dict[str, Any]) -> set[str]:
    """The one channel a notification goes out on: its person's, else its role's.

    Who may see it, as the bell reads it (`_common.visible_to_user`): a
    notification with a `recipient_id` is that person's alone, and one without
    is for everyone in its `recipient_role`. A person's notification is not sent
    to their role's channel, which every connection of the role subscribes to.
    """
    recipient_id = str(item.get("recipient_id") or "")
    if recipient_id:
        return {websocket_service.user_channel(recipient_id)}
    recipient_role = str(item.get("recipient_role") or "")
    if recipient_role:
        return {websocket_service.role_channel(recipient_role)}
    return set()


def _reachable_connections(item: dict[str, Any]) -> list[dict[str, Any]]:
    """The connections that can subscribe to the notification's channel (#624).

    A connection subscribes only to its own person's channel and its own role's,
    so these are the recipient's connections, or the role's: one query of an
    index, whatever the size of the table.
    """
    recipient_id = str(item.get("recipient_id") or "")
    if recipient_id:
        return websocket_service.user_connections(recipient_id)
    recipient_role = str(item.get("recipient_role") or "")
    if recipient_role:
        return websocket_service.role_connections(recipient_role)
    return []


def _record_delivery_attempt(item: dict[str, Any], attempt: dict[str, Any]) -> None:
    if item.get("owner_classification") == "global_nonprivate":
        return
    metadata = dict(item.get("metadata") or {})
    attempts = list(metadata.get("websocket_delivery_attempts") or [])
    attempts.append(attempt)
    metadata["websocket_delivery_attempts"] = attempts[-5:]
    notification_repo.update_event(str(item["event_id"]), {"metadata": metadata})


def _connection_evidence_ref(connection_id: str) -> str:
    digest = hashlib.sha256(
        ("stoa.websocket-evidence.v1\x00" + connection_id).encode("utf-8")
    ).hexdigest()
    return f"connection-{digest[:16]}"
