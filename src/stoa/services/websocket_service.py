"""The WebSocket connections: connect, subscribe, disconnect, clean up, read their state.

Only connections (#686). What a notification is and who may see it belongs to
the notification package, whose realtime channel asks here for a reader's
connections and posts through `post_to_connection`; this module never imports
notifications (`tests/test_notification_package_boundary.py`).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse

from botocore.exceptions import ClientError
from stoa import aws
from stoa.aws import Kind
from stoa import config
from stoa.db.repositories import websocket_repo
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.services.notification_errors import NotificationErrorCode as _N, NotificationViolation


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
        raise NotificationViolation(_N.WEBSOCKET_CONNECTION_ID_REQUIRED)
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
        "expires_at": now_epoch() + max(int(config.settings().websocket_connection_ttl_seconds), 1),
        "endpoint_url": endpoint_url or config.settings().websocket_api_endpoint or None,
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
        "expires_at": now_epoch() + max(int(config.settings().websocket_connection_ttl_seconds), 1),
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
            "expires_at": now_epoch() + max(int(config.settings().websocket_connection_ttl_seconds), 1),
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


def readiness_status() -> dict[str, Any]:
    endpoint = str(config.settings().websocket_api_endpoint or "").strip()
    routes_configured = bool(config.settings().websocket_live_routes_configured)
    deployed = bool(config.settings().websocket_live_deployed)
    live_smoke_passed = bool(config.settings().websocket_live_smoke_passed)
    stale_cleanup_enabled = bool(config.settings().websocket_stale_cleanup_enabled)
    active_connection_count = 0
    stale_connection_count = 0
    connection_status_error: str | None = None

    try:
        connections = websocket_repo.list_site_connections()
    except Exception:
        connections = []
        connection_status_error = "connection_repository_unavailable"

    for connection in connections:
        if is_expired(connection):
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
            "connect": config.settings().websocket_live_connect_route,
            "disconnect": config.settings().websocket_live_disconnect_route,
            "message": config.settings().websocket_live_message_route,
        },
        "deployed": deployed,
        "liveSmokePassed": live_smoke_passed,
        "connectionTtlSeconds": max(int(config.settings().websocket_connection_ttl_seconds), 1),
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
        raise NotificationViolation(_N.WEBSOCKET_CHANNEL_REQUIRED)
    unauthorized = sorted(requested - allowed)
    if unauthorized:
        raise SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED)
    return sorted(requested)


def _owned_connection(connection_id: str, user: dict[str, Any]) -> dict[str, Any]:
    item = _existing(connection_id)
    if str(item.get("user_id") or "") != _user_id(user):
        raise SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED)
    return item


def _existing(connection_id: str) -> dict[str, Any]:
    item = websocket_repo.get_connection(connection_id)
    if not item:
        raise NotificationViolation(_N.WEBSOCKET_CONNECTION_NOT_FOUND)
    return item


def _user_id(user: dict[str, Any]) -> str:
    user_id = str(user.get("sub") or user.get("username") or "")
    if not user_id:
        raise SecurityDecisionError(SecurityErrorCode.AUTHENTICATION_REQUIRED)
    return user_id


def _role(user: dict[str, Any]) -> str:
    role = str(user.get("role") or "")
    if not role:
        raise SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED)
    return role


def _role_channels(role: str) -> set[str]:
    return {role}


def user_connections(user_id: str) -> list[dict[str, Any]]:
    """One person's connections, read from the connection index (#624)."""
    return websocket_repo.list_user_connections(user_id)


def role_connections(role: str) -> list[dict[str, Any]]:
    """Every connection of one role, read from the connection index (#624)."""
    return websocket_repo.list_role_connections(role)


def drop_connection(connection_id: str) -> None:
    """Forget a connection found stale or gone while posting to it."""
    websocket_repo.delete_connection(connection_id)


def is_expired(connection: dict[str, Any]) -> bool:
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


def post_to_connection(endpoint_url: str, connection_id: str, envelope: dict[str, Any]) -> None:
    client = aws.client(Kind.WEBSOCKET_MANAGEMENT, endpoint_url=endpoint_url)
    client.post_to_connection(
        ConnectionId=connection_id,
        Data=json.dumps(envelope, separators=(",", ":")).encode("utf-8"),
    )


def is_gone_exception(exc: ClientError) -> bool:
    error = exc.response.get("Error", {})
    metadata = exc.response.get("ResponseMetadata", {})
    return error.get("Code") == "GoneException" or metadata.get("HTTPStatusCode") == 410
