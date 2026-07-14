"""Notification routes."""

from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from stoa.security.admin_authorization import admin_operation
from stoa.security.authorization import AuthorizationAction, AuthorizedResource, ResourceType
from stoa.security.identity import Actor
from stoa.security.route_authorization import (
    authorized_notification_event_dependency,
    authorized_notification_push_token_dependency,
    notification_self_dependency,
)
from stoa.services import notification_service

router = APIRouter()


class NotificationEventResponse(BaseModel):
    eventId: str
    recipientId: str | None = None
    recipientRole: str
    eventType: str
    targetType: str
    targetId: str
    title: str
    summary: str
    status: str
    createdAt: str
    readAt: str | None = None
    archivedAt: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    actorId: str | None = None
    actorRole: str | None = None
    deliveryCategory: str | None = None
    deliveryChannels: dict[str, Any] = Field(default_factory=dict)


class NotificationListResponse(BaseModel):
    items: list[NotificationEventResponse]
    count: int


class NotificationPreferenceUpdate(BaseModel):
    preferences: dict[str, dict[str, bool]]


class NotificationDigestSendRequest(BaseModel):
    category: str | None = None
    since: str | None = None
    until: str | None = None
    limit: int = Field(default=25, ge=1, le=100)


class NotificationDigestSendResponse(BaseModel):
    deliveryId: str
    status: str
    providerMode: str
    template: str
    itemCount: int
    eventIds: list[str]
    recipient: dict[str, Any]
    providerResult: dict[str, Any] = Field(default_factory=dict)


class NotificationPushTokenRegisterRequest(BaseModel):
    platform: str
    token: str | None = None
    providerTokenReference: str | None = None
    deviceId: str | None = None


class NotificationPushTokenResponse(BaseModel):
    tokenReference: str
    platform: str
    status: str
    tokenHashPrefix: str
    hasProviderReference: bool
    createdAt: str
    lastSeenAt: str
    revokedAt: str | None = None


class NotificationPreferenceResponse(BaseModel):
    userId: str
    preferences: dict[str, dict[str, bool]]
    supportedCategories: list[str]
    supportedChannels: list[str]
    updatedAt: str | None = None


class NotificationDeliveryStatusResponse(BaseModel):
    websocketConfigured: bool
    websocketMode: str
    websocketReadiness: dict[str, Any] = Field(default_factory=dict)
    emailProvider: dict[str, Any] = Field(default_factory=dict)
    pushProvider: dict[str, Any] = Field(default_factory=dict)
    preferenceCategories: list[str]
    preferenceChannels: list[str]
    recentEventCount: int
    categoryCounts: dict[str, int]
    realtimeDecisionCounts: dict[str, int]
    deliveryAttemptCounts: dict[str, int] = Field(default_factory=dict)
    recentDeliveryAttempts: list[dict[str, Any]] = Field(default_factory=list)


class NotificationDigestItem(BaseModel):
    eventId: str
    eventType: str
    category: str
    targetType: str
    targetId: str
    title: str
    summary: str
    createdAt: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class NotificationDigestPreviewResponse(BaseModel):
    userId: str
    category: str | None = None
    window: dict[str, str | None]
    count: int
    items: list[NotificationDigestItem]
    deliveryMode: str
    emailProviderConfigured: bool
    pushProviderConfigured: bool
    pushPreferencesSupported: bool


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    actor: Actor = Depends(notification_self_dependency(ResourceType.NOTIFICATION_COLLECTION, AuthorizationAction.READ)),
):
    items = notification_service.list_user_events(actor, status=status_filter, limit=limit)
    return NotificationListResponse(items=items, count=len(items))


@router.get("/preferences", response_model=NotificationPreferenceResponse)
async def get_notification_preferences(
    actor: Actor = Depends(notification_self_dependency(ResourceType.NOTIFICATION_PREFERENCE, AuthorizationAction.READ)),
):
    return notification_service.preferences_response(actor.user_id)


@router.patch("/preferences", response_model=NotificationPreferenceResponse)
async def update_notification_preferences(
    body: NotificationPreferenceUpdate,
    actor: Actor = Depends(notification_self_dependency(ResourceType.NOTIFICATION_PREFERENCE, AuthorizationAction.UPDATE)),
):
    return notification_service.update_preferences(actor.user_id, body.preferences)


@router.get("/digest-preview", response_model=NotificationDigestPreviewResponse)
async def preview_notification_digest(
    category: str | None = Query(default=None),
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    actor: Actor = Depends(notification_self_dependency(ResourceType.NOTIFICATION_DIGEST, AuthorizationAction.READ)),
):
    return notification_service.digest_preview(
        actor,
        category=category,
        since=since,
        until=until,
        limit=limit,
    )


@router.post("/digest-send", response_model=NotificationDigestSendResponse)
async def send_notification_digest(
    body: NotificationDigestSendRequest,
    actor: Actor = Depends(notification_self_dependency(ResourceType.NOTIFICATION_DIGEST, AuthorizationAction.CREATE)),
):
    return notification_service.send_digest(
        actor,
        category=body.category,
        since=body.since,
        until=body.until,
        limit=body.limit,
    )


@router.post("/push-tokens", response_model=NotificationPushTokenResponse)
async def register_notification_push_token(
    body: NotificationPushTokenRegisterRequest,
    actor: Actor = Depends(notification_self_dependency(ResourceType.NOTIFICATION_PUSH_TOKEN, AuthorizationAction.CREATE)),
):
    return notification_service.register_push_token(
        actor,
        platform=body.platform,
        token=body.token,
        provider_token_reference=body.providerTokenReference,
        device_id=body.deviceId,
    )


@router.delete("/push-tokens/{token_reference}", response_model=NotificationPushTokenResponse)
async def revoke_notification_push_token(
    token_reference: str,
    authorized: AuthorizedResource = Depends(
        authorized_notification_push_token_dependency(AuthorizationAction.DELETE)
    ),
):
    return notification_service.revoke_authorized_push_token(authorized.value)


@router.post("/{event_id}/read", response_model=NotificationEventResponse, status_code=status.HTTP_200_OK)
async def mark_notification_read(
    event_id: str,
    authorized: AuthorizedResource = Depends(
        authorized_notification_event_dependency(AuthorizationAction.UPDATE)
    ),
):
    return notification_service.mark_authorized_event(authorized.value, "read")


@router.post("/{event_id}/archive", response_model=NotificationEventResponse, status_code=status.HTTP_200_OK)
async def archive_notification(
    event_id: str,
    authorized: AuthorizedResource = Depends(
        authorized_notification_event_dependency(AuthorizationAction.UPDATE)
    ),
):
    return notification_service.mark_authorized_event(authorized.value, "archived")


admin_router = APIRouter()


@admin_router.get("/notifications", response_model=NotificationListResponse)
async def list_admin_notifications(
    status_filter: str | None = Query(default=None, alias="status"),
    event_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    user: dict = Depends(admin_operation),
):
    items = notification_service.list_admin_events(
        status=status_filter,
        event_type=event_type,
        limit=limit,
    )
    return NotificationListResponse(items=items, count=len(items))


@admin_router.get("/notifications/delivery-status", response_model=NotificationDeliveryStatusResponse)
async def get_notification_delivery_status(
    limit: int = Query(default=100, ge=1, le=500),
    user: dict = Depends(admin_operation),
):
    return notification_service.delivery_status(limit=limit)
