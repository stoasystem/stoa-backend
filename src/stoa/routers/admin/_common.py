"""What every admin domain module shares: page tokens, scopes and item coercion."""

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

from stoa.db import table as db_table
from stoa.services.account_errors import AccountErrorCode, AccountViolation


type AdminItem = dict[str, object]


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _admin_mapping(value: object) -> AdminItem:
    if not isinstance(value, Mapping):
        raise RuntimeError("admin data dependency unavailable")
    result: AdminItem = {}
    for key, member in value.items():
        if not isinstance(key, str):
            raise RuntimeError("admin data dependency unavailable")
        result[key] = member
    return result


def _admin_items(response: Mapping[str, object]) -> list[AdminItem]:
    raw_items = response.get("Items", [])
    if not isinstance(raw_items, list):
        raise RuntimeError("admin data dependency unavailable")
    return [_admin_mapping(item) for item in raw_items]


def _admin_cursor(response: Mapping[str, object]) -> AdminItem | None:
    raw_cursor = response.get("LastEvaluatedKey")
    if raw_cursor is None:
        return None
    return _admin_mapping(raw_cursor)


def _next_token(scope: str, response: Mapping[str, object]) -> str | None:
    """Where the listing goes on, as a token only this listing reads back."""
    cursor = _admin_cursor(response)
    return db_table.page_token(scope, cursor) if cursor else None


def _start_key(
    token: str | None,
    scope: str,
    *,
    key: tuple[str, ...] = db_table.BASE_KEY,
    within: Callable[[dict[str, Any]], bool] | None = None,
) -> AdminItem | None:
    if not token:
        return None
    try:
        return db_table.read_page_token(token, scope, key=key, within=within)
    except db_table.PageTokenInvalid as exc:
        raise AccountViolation(AccountErrorCode.PAGE_TOKEN_INVALID) from exc


# A listing's scope names its partition when it reads one, so a token made for
# one report's timeline or one job's results continues no other.
ADMIN_REPORTS_SCAN_SCOPE = "admin_reports"


ADMIN_REPORTS_PARENT_KEY = ("PK", "SK", "parent_id", "week_start")


RECOVERY_JOBS_SCOPE = "recovery_jobs"


def _admin_reports_scope(parent_id: str | None) -> str:
    return f"admin_reports:parent:{parent_id}" if parent_id else ADMIN_REPORTS_SCAN_SCOPE


def _in_partition(partition: str, sort_prefix: str = "") -> Callable[[dict[str, Any]], bool]:
    def holds(key: dict[str, Any]) -> bool:
        sort_key = key["SK"]
        return (
            key["PK"] == partition
            and isinstance(sort_key, str)
            and sort_key.startswith(sort_prefix)
        )

    return holds


def _admin_required_text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeError("admin data dependency unavailable")
    return value
