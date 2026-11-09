"""Scheduled archive of the authorization allow stream, 90 days on (card 129).

Runs on the account-deletion function, which already holds the table and may
write under the evidence bucket's audit prefix; its schedule sends
`{"job": "security_audit_retention"}`.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import boto3

from stoa.config import Settings, settings
from stoa.services import security_audit_retention


def _now() -> datetime:
    return datetime.now(UTC)


def run(
    *,
    s3: Any,
    settings_obj: Settings,
    now: datetime | None = None,
    limit: int = security_audit_retention.ROWS_PER_RUN,
) -> security_audit_retention.AuditArchiveSummary:
    return security_audit_retention.archive_due_events(
        s3=s3, settings=settings_obj, now=now or _now(), limit=limit
    )


def handler(event: dict[str, Any] | None, _context: Any) -> dict[str, Any]:
    event = event or {}
    s3 = boto3.client("s3", region_name=settings.aws_region)
    summary = run(
        s3=s3,
        settings_obj=settings,
        now=_now(),
        limit=min(
            max(int(event.get("limit", security_audit_retention.ROWS_PER_RUN)), 1),
            2_000,
        ),
    )
    return asdict(summary)
