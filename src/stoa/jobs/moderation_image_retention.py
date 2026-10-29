"""Scheduled deletion of refused images 90 days after their case is handled (#139).

Runs on the account-deletion function, which already holds the table and the
images bucket; its schedule sends `{"job": "moderation_image_retention"}`.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import boto3

from stoa.config import Settings, settings
from stoa.services import moderation_service


def _now() -> datetime:
    return datetime.now(UTC)


def run(
    *,
    s3: Any,
    settings_obj: Settings,
    now: datetime | None = None,
    limit: int = 100,
) -> moderation_service.CaseImageRetentionSummary:
    return moderation_service.delete_handled_case_images(
        s3=s3, settings=settings_obj, now=now or _now(), limit=limit
    )


class CaseImageRetentionIncomplete(RuntimeError):
    """Some image due for deletion is still kept; the run counts as failed."""


def handler(event: dict[str, Any] | None, _context: Any) -> dict[str, int]:
    event = event or {}
    s3 = boto3.client("s3", region_name=settings.aws_region)
    summary = run(
        s3=s3,
        settings_obj=settings,
        now=_now(),
        limit=min(max(int(event.get("limit", 100)), 1), 500),
    )
    if summary.retryable:
        # A failed run, not a quiet success: the schedule retries it, and what
        # still fails lands in the dead-letter queue and its alarm.
        raise CaseImageRetentionIncomplete(f"retention incomplete: {asdict(summary)}")
    return asdict(summary)
