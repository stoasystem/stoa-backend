"""Bounded scheduled cleanup for terminal and expired upload intents."""

from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import logging
from typing import Any

import boto3

from stoa.config import Settings, settings
from stoa.services import uploads

logger = logging.getLogger(__name__)

DEFAULT_BATCH_LIMIT = 25
MAX_BATCH_LIMIT = 100
DEFAULT_PAGE_LIMIT = 100
MAX_PAGE_LIMIT = 100
# Pages of the table scanned per run, at most, while looking for a batch.
DEFAULT_MAX_PAGES = 200
MAX_PAGES = 1000
# Stop scanning or cleaning with this much of the Lambda's time left.
MIN_REMAINING_SECONDS = 20.0


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
    max_pages: int = DEFAULT_MAX_PAGES,
    remaining_seconds: Callable[[], float] | None = None,
) -> CleanupSummary:
    """Clean at most one batch, finding it anywhere in the table.

    A scheduled run starts from the top every time, so the scan goes on page
    after page until the batch is full, the table ends, or the page or time
    budget is spent (#250): a run that looked at the first page only would
    never reach most of the table. A run stopped early returns where it got
    to as an opaque continuation, for a run started by hand.
    """
    batch_limit = _bounded_limit(batch_limit, DEFAULT_BATCH_LIMIT, MAX_BATCH_LIMIT)
    page_limit = _bounded_limit(page_limit, DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT)
    max_pages = _bounded_limit(max_pages, DEFAULT_MAX_PAGES, MAX_PAGES)
    try:
        cursor = _decode_cursor(continuation_token)
    except ValueError:
        return CleanupSummary(invalid_continuation=1)
    current = (now or datetime.now(UTC)).astimezone(UTC)

    def out_of_time() -> bool:
        return remaining_seconds is not None and remaining_seconds() < MIN_REMAINING_SECONDS

    candidates: list[Any] = []
    next_cursor: dict[str, Any] | None = cursor
    for _ in range(max_pages):
        page, next_cursor = uploads.cleanup_candidates(
            int(current.timestamp()),
            limit=page_limit,
            exclusive_start_key=next_cursor,
        )
        candidates.extend(page)
        if len(candidates) >= batch_limit or next_cursor is None or out_of_time():
            break
    counts = {
        "deleted": 0,
        "retryable": 0,
        "protected": 0,
        "deferred": 0,
        "skipped": 0,
    }
    selected = candidates[:batch_limit]
    for index, candidate in enumerate(selected):
        if out_of_time():
            # What is left is still a candidate next run; stop before the Lambda does.
            selected = selected[:index]
            break
        try:
            outcome = uploads.cleanup(
                candidate,
                s3=s3,
                settings=settings_obj,
                now=current,
                reference_scan_limit=page_limit,
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
    if len(candidates) > len(selected):
        # Resume after the last selected record without returning raw coordinates;
        # with none cleaned, from where this run started.
        continuation = _candidate_cursor(selected[-1]) if selected else cursor
    return CleanupSummary(
        scanned=len(selected),
        claimed=len(selected) - counts["skipped"],
        continuation_token=_encode_cursor(continuation),
        **counts,
    )


def handler(event: dict[str, Any] | None, context: Any) -> dict[str, int | str | None]:
    """Scheduled Lambda entrypoint returning category counts and an opaque cursor only.

    The schedule sends `{"source": "stoa.scheduler", "job": "upload_cleanup"}`;
    `batchLimit`, `pageLimit`, `maxPages` and `continuationToken` are for a run
    started by hand.
    """
    event = event or {}
    remaining = getattr(context, "get_remaining_time_in_millis", None)
    result = cleanup_expired_uploads(
        s3=boto3.client("s3", region_name=settings.aws_region),
        settings_obj=settings,
        batch_limit=event.get("batchLimit", DEFAULT_BATCH_LIMIT),
        page_limit=event.get("pageLimit", DEFAULT_PAGE_LIMIT),
        max_pages=event.get("maxPages", DEFAULT_MAX_PAGES),
        continuation_token=event.get("continuationToken"),
        remaining_seconds=(lambda: remaining() / 1000) if callable(remaining) else None,
    )
    # The schedule invokes asynchronously and nobody reads the return value, so the
    # counts go to the log. The cursor stays out: it decodes to table keys.
    logger.info(
        "upload_cleanup_run_completed scanned=%s claimed=%s deleted=%s retryable=%s "
        "protected=%s deferred=%s skipped=%s invalid_continuation=%s more_to_do=%s",
        result.scanned,
        result.claimed,
        result.deleted,
        result.retryable,
        result.protected,
        result.deferred,
        result.skipped,
        result.invalid_continuation,
        "true" if result.continuation_token else "false",
    )
    return result.public_dict()


def _bounded_limit(value: Any, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, 1), maximum)


def _candidate_cursor(candidate: Any) -> dict[str, str]:
    """Accept an exact repository cursor without coercing private values."""
    if not isinstance(candidate, dict):
        raise RuntimeError("invalid cleanup candidate page")
    cursor = {"PK": candidate.get("PK"), "SK": candidate.get("SK")}
    if any(not isinstance(value, str) or not value for value in cursor.values()):
        raise RuntimeError("invalid cleanup candidate page")
    return cursor  # type: ignore[return-value]


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
