"""Fallback-safe WebSocket connection and notification fanout helpers."""

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException

from stoa.config import settings
from stoa.db.repositories import notification_repo, websocket_repo


PostConnection = Callable[[dict[str, Any], dict[str, Any]], None]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def now_epoch() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def user_channel(user_id: str) -> str:
    return f"user:{user_id}"


def role_channel(role: str) -> str:
    return f"role:{role}"


def register_connection(
    *,
    connection_id: str,
    user: dict[str, Any],
    subscribed_channels: list[str] | None = None,
    endpoint_url: str | None = None,
) -> dict[str, Any]:
    if not connection_id:
        raise HTTPException(status_code=400, detail="WebSocket connection id is required")
    user_id = _user_id(user)
    role = _role(user)
    channels = _authorize_channels(
        user,
        subscribed_channels or sorted(default_channels_for_user(user)),
    )
    connected_at = now_iso()
    item = {
        "entity_type": websocket_repo.CONNECTION_ENTITY,
        "connection_id": connection_id,
        "user_id": user_id,
        "role": role,
        "subscribed_channels": channels,
        "connected_at": connected_at,
        "last_seen_at": connected_at,
        "expires_at": now_epoch() + max(int(settings.websocket_connection_ttl_seconds), 1),
        "endpoint_url": endpoint_url or settings.websocket_api_endpoint or None,
        "owner_id": user_id,
    }
    persisted = websocket_repo.put_connection(item)
    if isinstance(persisted, dict):
        item = persisted
    return connection_response(item)


def refresh_connection(connection_id: str, user: dict[str, Any] | None = None) -> dict[str, Any]:
    item = _owned_connection(connection_id, user) if user is not None else _existing(connection_id)
    refreshed_at = now_iso()
    updates = {
        "last_seen_at": refreshed_at,
        "expires_at": now_epoch() + max(int(settings.websocket_connection_ttl_seconds), 1),
    }
    updated = websocket_repo.update_connection(connection_id, updates)
    return connection_response(updated or {**item, **updates})


def subscribe_connection(
    connection_id: str,
    user: dict[str, Any],
    subscribed_channels: list[str],
) -> dict[str, Any]:
    item = _owned_connection(connection_id, user)
    channels = _authorize_channels(user, subscribed_channels)
    updated = websocket_repo.update_connection(
        connection_id,
        {
            "subscribed_channels": channels,
            "last_seen_at": now_iso(),
            "expires_at": now_epoch() + max(int(settings.websocket_connection_ttl_seconds), 1),
        },
    )
    return connection_response(updated or {**item, "subscribed_channels": channels})


def disconnect_connection(connection_id: str) -> dict[str, Any]:
    existing = websocket_repo.get_connection(connection_id)
    websocket_repo.delete_connection(connection_id)
    return {"connectionId": connection_id, "removed": existing is not None}


def cleanup_stale_connections(*, current_epoch: int | None = None) -> dict[str, Any]:
    removed = websocket_repo.delete_stale_connections(now_epoch=current_epoch or now_epoch())
    return {"removedConnectionIds": removed, "count": len(removed)}


def readiness_status(*, connection_limit: int = 200) -> dict[str, Any]:
    endpoint = str(settings.websocket_api_endpoint or "").strip()
    routes_configured = bool(settings.websocket_live_routes_configured)
    deployed = bool(settings.websocket_live_deployed)
    live_smoke_passed = bool(settings.websocket_live_smoke_passed)
    stale_cleanup_enabled = bool(settings.websocket_stale_cleanup_enabled)
    active_connection_count = 0
    stale_connection_count = 0
    connection_status_error: str | None = None

    try:
        connections = websocket_repo.list_connections(limit=connection_limit)
    except Exception:
        connections = []
        connection_status_error = "connection_repository_unavailable"

    for connection in connections:
        if _is_expired(connection):
            stale_connection_count += 1
        else:
            active_connection_count += 1

    blockers = _configuration_blockers(
        endpoint=endpoint,
        routes_configured=routes_configured,
        deployed=deployed,
        live_smoke_passed=live_smoke_passed,
        stale_cleanup_enabled=stale_cleanup_enabled,
        connection_status_error=connection_status_error,
    )
    mode = _readiness_mode(
        endpoint=endpoint,
        routes_configured=routes_configured,
        deployed=deployed,
        live_smoke_passed=live_smoke_passed,
        stale_cleanup_enabled=stale_cleanup_enabled,
    )

    return {
        "mode": mode,
        "endpointConfigured": bool(endpoint),
        "endpointHost": _endpoint_host(endpoint),
        "routes": {
            "configured": routes_configured,
            "connect": settings.websocket_live_connect_route,
            "disconnect": settings.websocket_live_disconnect_route,
            "message": settings.websocket_live_message_route,
        },
        "deployed": deployed,
        "liveSmokePassed": live_smoke_passed,
        "connectionTtlSeconds": max(int(settings.websocket_connection_ttl_seconds), 1),
        "connectionStatus": {
            "activeConnectionCount": active_connection_count,
            "staleConnectionCount": stale_connection_count,
            "error": connection_status_error,
        },
        "staleCleanup": {
            "enabled": stale_cleanup_enabled,
            "staleConnectionCount": stale_connection_count,
        },
        "configurationBlockers": blockers,
    }


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
        raise HTTPException(status_code=400, detail="Notification event id is required")

    delivery_id = f"ws-{uuid4().hex}"
    attempted_at = now_iso()
    target_channels = _target_channels(item)
    results: list[dict[str, Any]] = []
    owner_id = str(item.get("owner_id") or item.get("recipient_id") or "")
    generation = item.get("account_fence_generation")
    lease_owner: str | None = None
    leased = bool(owner_id and type(generation) is int and generation > 0)
    if leased:
        payload_digest = hashlib.sha256(
            json.dumps(
                event_envelope(item, delivery_id=delivery_id, delivery_attempt=1),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        intent = notification_repo.register_delivery_intent(
            owner_id=owner_id,
            generation=generation,
            operation_id=delivery_id,
            channel="websocket",
            event_ids=[event_id],
            payload_digest=payload_digest,
            now_iso=attempted_at,
        )
        if str(intent.get("status") or "") in {
            "accepted",
            "provider_acceptance_unknown",
            "canceled_account_deletion",
        }:
            return {"deliveryId": delivery_id, "results": []}
        lease_owner = f"websocket-worker-{uuid4().hex}"
        claim = notification_repo.claim_delivery_intent(
            owner_id=owner_id,
            generation=generation,
            operation_id=delivery_id,
            lease_owner=lease_owner,
            lease_expires_at=now_epoch() + 90,
            now_iso=attempted_at,
        )
        if not claim:
            return {"deliveryId": delivery_id, "results": []}

    completion_status = "rejected"

    for connection in websocket_repo.list_connections(limit=500):
        connection_id = str(connection.get("connection_id") or "")
        if not connection_id:
            continue
        if _is_expired(connection):
            websocket_repo.delete_connection(connection_id)
            results.append({"connection_id": connection_id, "status": "stale_removed"})
            continue
        if not target_channels.intersection(set(connection.get("subscribed_channels") or [])):
            continue

        envelope = event_envelope(item, delivery_id=delivery_id, delivery_attempt=1)
        endpoint_url = str(connection.get("endpoint_url") or settings.websocket_api_endpoint or "")
        if not endpoint_url and post_func is None:
            results.append({"connection_id": connection_id, "status": "skipped_no_endpoint"})
            continue

        try:
            if leased and lease_owner is not None:
                check = {
                    "owner_id": owner_id,
                    "generation": generation,
                    "operation_id": delivery_id,
                    "lease_owner": lease_owner,
                }
                if not notification_repo.delivery_intent_sendable(
                    **check
                ) or not notification_repo.delivery_intent_sendable(**check):
                    completion_status = "canceled_account_deletion"
                    results.append(
                        {"connection_id": connection_id, "status": completion_status}
                    )
                    break
            if post_func is not None:
                post_func(connection, envelope)
            else:
                _post_to_connection(endpoint_url, connection_id, envelope)
            results.append({"connection_id": connection_id, "status": "delivered"})
            completion_status = "accepted"
        except ClientError as exc:
            if _is_gone_exception(exc):
                websocket_repo.delete_connection(connection_id)
                results.append({"connection_id": connection_id, "status": "gone_removed"})
            else:
                results.append({"connection_id": connection_id, "status": "failed"})
        except Exception:
            results.append(
                {"connection_id": connection_id, "status": "provider_acceptance_unknown"}
            )
            completion_status = "provider_acceptance_unknown"
            break

    if leased and lease_owner is not None:
        notification_repo.complete_delivery_intent(
            owner_id=owner_id,
            generation=generation,
            operation_id=delivery_id,
            lease_owner=lease_owner,
            status=completion_status,
            now_iso=now_iso(),
        )

    _record_delivery_attempt(
        item,
        {
            "delivery_id": delivery_id,
            "attempted_at": attempted_at,
            "target_channels": sorted(target_channels),
            "target_count": len(results),
            "results": results,
        },
    )
    return {"deliveryId": delivery_id, "results": results}


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


def connection_response(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "connectionId": item.get("connection_id"),
        "userId": item.get("user_id"),
        "role": item.get("role"),
        "subscribedChannels": item.get("subscribed_channels") or [],
        "connectedAt": item.get("connected_at"),
        "lastSeenAt": item.get("last_seen_at"),
        "expiresAt": item.get("expires_at"),
    }


def default_channels_for_user(user: dict[str, Any]) -> set[str]:
    user_id = _user_id(user)
    return {user_channel(user_id), *{role_channel(role) for role in _role_channels(_role(user))}}


def _authorize_channels(user: dict[str, Any], channels: list[str]) -> list[str]:
    allowed = default_channels_for_user(user)
    requested = {str(channel) for channel in channels if str(channel).strip()}
    if not requested:
        raise HTTPException(status_code=400, detail="At least one subscription channel is required")
    unauthorized = sorted(requested - allowed)
    if unauthorized:
        raise HTTPException(status_code=403, detail="WebSocket subscription is not permitted")
    return sorted(requested)


def _owned_connection(connection_id: str, user: dict[str, Any]) -> dict[str, Any]:
    item = _existing(connection_id)
    if str(item.get("user_id") or "") != _user_id(user):
        raise HTTPException(status_code=403, detail="WebSocket connection is not owned by this user")
    return item


def _existing(connection_id: str) -> dict[str, Any]:
    item = websocket_repo.get_connection(connection_id)
    if not item:
        raise HTTPException(status_code=404, detail="WebSocket connection not found")
    return item


def _user_id(user: dict[str, Any]) -> str:
    user_id = str(user.get("sub") or user.get("username") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authenticated WebSocket user is required")
    return user_id


def _role(user: dict[str, Any]) -> str:
    role = str(user.get("role") or "")
    if not role:
        raise HTTPException(status_code=403, detail="Authenticated WebSocket role is required")
    return role


def _role_channels(role: str) -> set[str]:
    return {role}


def _target_channels(item: dict[str, Any]) -> set[str]:
    channels: set[str] = set()
    recipient_id = str(item.get("recipient_id") or "")
    recipient_role = str(item.get("recipient_role") or "")
    if recipient_id:
        channels.add(user_channel(recipient_id))
    if recipient_role:
        channels.add(role_channel(recipient_role))
    return channels


def _is_expired(connection: dict[str, Any]) -> bool:
    try:
        return int(connection.get("expires_at") or 0) <= now_epoch()
    except (TypeError, ValueError):
        return True


def _configuration_blockers(
    *,
    endpoint: str,
    routes_configured: bool,
    deployed: bool,
    live_smoke_passed: bool,
    stale_cleanup_enabled: bool,
    connection_status_error: str | None,
) -> list[str]:
    blockers = []
    if not endpoint:
        blockers.append("websocket_api_endpoint_missing")
    if endpoint and not routes_configured:
        blockers.append("websocket_live_routes_not_configured")
    if endpoint and routes_configured and not deployed:
        blockers.append("websocket_live_deployment_not_marked_deployed")
    if endpoint and routes_configured and deployed and not live_smoke_passed:
        blockers.append("websocket_live_smoke_not_passed")
    if endpoint and not stale_cleanup_enabled:
        blockers.append("websocket_stale_cleanup_not_enabled")
    if connection_status_error:
        blockers.append(connection_status_error)
    return blockers


def _readiness_mode(
    *,
    endpoint: str,
    routes_configured: bool,
    deployed: bool,
    live_smoke_passed: bool,
    stale_cleanup_enabled: bool,
) -> str:
    if not endpoint:
        return "local_only"
    if not routes_configured or not stale_cleanup_enabled:
        return "provider_blocked"
    if not deployed:
        return "configured"
    if not live_smoke_passed:
        return "deployed"
    return "live_ready"


def _endpoint_host(endpoint: str) -> str | None:
    if not endpoint:
        return None
    parsed = urlparse(endpoint)
    return parsed.netloc or parsed.path or "configured"


def _record_delivery_attempt(item: dict[str, Any], attempt: dict[str, Any]) -> None:
    metadata = dict(item.get("metadata") or {})
    attempts = list(metadata.get("websocket_delivery_attempts") or [])
    attempts.append(attempt)
    metadata["websocket_delivery_attempts"] = attempts[-5:]
    notification_repo.update_event(str(item["event_id"]), {"metadata": metadata})


def _post_to_connection(endpoint_url: str, connection_id: str, envelope: dict[str, Any]) -> None:
    client = boto3.client(
        "apigatewaymanagementapi",
        region_name=settings.aws_region,
        endpoint_url=endpoint_url,
    )
    client.post_to_connection(
        ConnectionId=connection_id,
        Data=json.dumps(envelope, separators=(",", ":")).encode("utf-8"),
    )


def _is_gone_exception(exc: ClientError) -> bool:
    error = exc.response.get("Error", {})
    metadata = exc.response.get("ResponseMetadata", {})
    return error.get("Code") == "GoneException" or metadata.get("HTTPStatusCode") == 410
