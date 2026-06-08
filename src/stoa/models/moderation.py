"""Moderation case request and response models."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ModerationSurface(str, Enum):
    QUESTION = "question"
    AI_ANSWER = "ai_answer"
    TEACHER_REPLY = "teacher_reply"


class ModerationReason(str, Enum):
    INCORRECT_ANSWER = "incorrect_answer"
    UNSAFE_CONTENT = "unsafe_content"
    ABUSE = "abuse"
    PRIVACY = "privacy"
    OTHER = "other"


class ModerationSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ModerationStatus(str, Enum):
    OPEN = "open"
    IN_REVIEW = "in_review"
    ACTIONED = "actioned"
    DISMISSED = "dismissed"
    CLOSED = "closed"


class ModerationReportRequest(BaseModel):
    surface: ModerationSurface
    reason: ModerationReason
    severity: ModerationSeverity = ModerationSeverity.MEDIUM
    note: str | None = Field(default=None, max_length=1000)


class ModerationCaseUpdateRequest(BaseModel):
    status: ModerationStatus | None = None
    assigned_admin_id: str | None = Field(default=None, max_length=200)
    resolution_note: str | None = Field(default=None, max_length=1000)


class ModerationCaseNoteRequest(BaseModel):
    note: str = Field(..., min_length=1, max_length=1000)


class ModerationCaseResponse(BaseModel):
    case_id: str
    status: ModerationStatus
    reason: ModerationReason
    severity: ModerationSeverity
    surface: ModerationSurface
    question_id: str
    student_id: str | None = None
    reporter_id: str
    reporter_role: str
    assigned_admin_id: str | None = None
    report_note: str | None = None
    resolution_note: str | None = None
    created_at: str
    updated_at: str
    closed_at: str | None = None
    question_context: dict[str, Any] | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)


class ModerationCaseListResponse(BaseModel):
    items: list[ModerationCaseResponse]
    count: int
    access_pattern: str = "bounded_scan"
