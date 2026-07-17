"""Bounded scheduled cleanup for terminal and expired upload intents."""

from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from typing import Any

import boto3

from stoa.config import Settings, settings
from stoa.db.repositories import attachment_repo
from stoa.services.attachment_service import cleanup_upload_intent

DEFAULT_BATCH_LIMIT = 25
MAX_BATCH_LIMIT = 100
DEFAULT_PAGE_LIMIT = 100
MAX_PAGE_LIMIT = 100


@dataclass(frozen=True, slots=True)
class CleanupSummary:
    scanned: int = 0
    claimed: int = 0
    deleted: int = 0
    retryable: int = 0
    protected: int = 0
    deferred: int = 0
    skipped: int = 0
    invalid_continuation: int = 0
    continuation_token: str | None = None

    def public_dict(self) -> dict[str, int | str | None]:
        return asdict(self)


def cleanup_expired_uploads(
    *,
    s3: Any,
    settings_obj: Settings,
    now: datetime | None = None,
    batch_limit: int = DEFAULT_BATCH_LIMIT,
    page_limit: int = DEFAULT_PAGE_LIMIT,
    continuation_token: str | None = None,
    repository: Any = attachment_repo,
) -> CleanupSummary:
    """Process at most one page and one explicit batch without exposing coordinates."""
    batch_limit = _bounded_limit(batch_limit, DEFAULT_BATCH_LIMIT, MAX_BATCH_LIMIT)
    page_limit = _bounded_limit(page_limit, DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT)
    try:
        cursor = _decode_cursor(continuation_token)
    except ValueError:
        return CleanupSummary(invalid_continuation=1)
    current = (now or datetime.now(UTC)).astimezone(UTC)
    candidates, next_cursor = repository.list_upload_cleanup_candidates(
        int(current.timestamp()),
        limit=page_limit,
        exclusive_start_key=cursor,
    )
    counts = {
        "deleted": 0,
        "retryable": 0,
        "protected": 0,
        "deferred": 0,
        "skipped": 0,
    }
    selected = candidates[:batch_limit]
    for candidate in selected:
        try:
            outcome = cleanup_upload_intent(
                candidate,
                s3=s3,
                settings=settings_obj,
                now=current,
                reference_scan_limit=page_limit,
                repository=repository,
            )
            if outcome not in counts:
                outcome = "retryable"
        except Exception:
            # Candidate diagnostics and coordinates are intentionally discarded.
            # The global listing call remains outside this boundary so a page
            # failure cannot be misreported as successful empty work.
            outcome = "retryable"
        counts[outcome] += 1
    continuation = next_cursor
    if len(candidates) > batch_limit:
        # Resume after the last selected record without returning raw coordinates.
        last = selected[-1]
        continuation = (
            {"PK": str(last["PK"]), "SK": str(last["SK"])}
            if isinstance(last, dict) and last.get("PK") and last.get("SK")
            else cursor
        )
    return CleanupSummary(
        scanned=len(selected),
        claimed=len(selected) - counts["skipped"],
        continuation_token=_encode_cursor(continuation),
        **counts,
    )


def handler(event: dict[str, Any] | None, context: Any) -> dict[str, int | str | None]:
    """Scheduled Lambda entrypoint returning category counts and an opaque cursor only."""
    event = event or {}
    result = cleanup_expired_uploads(
        s3=boto3.client("s3", region_name=settings.aws_region),
        settings_obj=settings,
        batch_limit=event.get("batchLimit", DEFAULT_BATCH_LIMIT),
        page_limit=event.get("pageLimit", DEFAULT_PAGE_LIMIT),
        continuation_token=event.get("continuationToken"),
    )
    return result.public_dict()


def _bounded_limit(value: Any, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, 1), maximum)


def _encode_cursor(cursor: dict[str, Any] | None) -> str | None:
    if not cursor:
        return None
    payload = json.dumps(cursor, sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(token: str | None) -> dict[str, Any] | None:
    if token is None:
        return None
    if not isinstance(token, str) or not token or len(token) > 2048:
        raise ValueError("invalid cleanup continuation")
    try:
        padding = "=" * (-len(token) % 4)
        value = json.loads(base64.b64decode(token + padding, altchars=b"-_", validate=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid cleanup continuation") from exc
    if not isinstance(value, dict) or set(value) - {"PK", "SK"}:
        raise ValueError("invalid cleanup continuation")
    if not all(isinstance(item, str) and len(item) <= 256 for item in value.values()):
        raise ValueError("invalid cleanup continuation")
    return value
