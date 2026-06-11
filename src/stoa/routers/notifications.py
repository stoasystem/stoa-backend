"""Notification routes."""

from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from stoa.deps import get_current_user, require_role
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


class NotificationPreferenceResponse(BaseModel):
    userId: str
    preferences: dict[str, dict[str, bool]]
    supportedCategories: list[str]
    supportedChannels: list[str]
    updatedAt: str | None = None


class NotificationDeliveryStatusResponse(BaseModel):
    websocketConfigured: bool
    preferenceCategories: list[str]
    preferenceChannels: list[str]
    recentEventCount: int
    categoryCounts: dict[str, int]
    realtimeDecisionCounts: dict[str, int]


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
    user: dict = Depends(get_current_user),
):
    items = notification_service.list_user_events(user, status=status_filter, limit=limit)
    return NotificationListResponse(items=items, count=len(items))


@router.get("/preferences", response_model=NotificationPreferenceResponse)
async def get_notification_preferences(
    user: dict = Depends(get_current_user),
):
    return notification_service.preferences_response(str(user.get("sub") or ""))


@router.patch("/preferences", response_model=NotificationPreferenceResponse)
async def update_notification_preferences(
    body: NotificationPreferenceUpdate,
    user: dict = Depends(get_current_user),
):
    return notification_service.update_preferences(str(user.get("sub") or ""), body.preferences)


@router.get("/digest-preview", response_model=NotificationDigestPreviewResponse)
async def preview_notification_digest(
    category: str | None = Query(default=None),
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    return notification_service.digest_preview(
        user,
        category=category,
        since=since,
        until=until,
        limit=limit,
    )


@router.post("/{event_id}/read", response_model=NotificationEventResponse, status_code=status.HTTP_200_OK)
async def mark_notification_read(
    event_id: str,
    user: dict = Depends(get_current_user),
):
    return notification_service.mark_event(event_id, user, "read")


@router.post("/{event_id}/archive", response_model=NotificationEventResponse, status_code=status.HTTP_200_OK)
async def archive_notification(
    event_id: str,
    user: dict = Depends(get_current_user),
):
    return notification_service.mark_event(event_id, user, "archived")


admin_router = APIRouter()


@admin_router.get("/notifications", response_model=NotificationListResponse)
async def list_admin_notifications(
    status_filter: str | None = Query(default=None, alias="status"),
    event_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    user: dict = Depends(require_role("admin")),
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
    user: dict = Depends(require_role("admin")),
):
    return notification_service.delivery_status(limit=limit)
