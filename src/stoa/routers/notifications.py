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


class NotificationListResponse(BaseModel):
    items: list[NotificationEventResponse]
    count: int


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    items = notification_service.list_user_events(user, status=status_filter, limit=limit)
    return NotificationListResponse(items=items, count=len(items))


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
