"""The rows the account machinery reaches into, without importing the store (#686).

Account deletion pages through every family's rows and scrubs them; the owner
registry sweep asks the same scan which rows are an account's; authorization
loads the one event or device a route acts on. These are those few calls,
passed straight to the notification store when they are made (so a test that
replaces the store's function replaces it here too).
"""

from __future__ import annotations

from collections.abc import Mapping

from stoa.db.repositories import notification_repo

DELIVERY_INTENT_ENTITY = notification_repo.DELIVERY_INTENT_ENTITY


def scan_notification_private_rows(
    owner_id: str,
    *,
    cursor: Mapping[str, str] | None = None,
    maximum_pages: int = 1,
    table: object | None = None,
) -> notification_repo.NotificationPrivatePage:
    """One page of the notification rows that are an account's or name it."""
    return notification_repo.scan_notification_private_rows(
        owner_id, cursor=cursor, maximum_pages=maximum_pages, table=table
    )


def scrub_notification_private_row(
    item: Mapping[str, object],
    *,
    owner_id: str,
    generation: int,
    now_iso: str,
    table: object | None = None,
) -> None:
    """Tombstone a row the account owns, or scrub the account out of one that names it."""
    notification_repo.scrub_notification_private_row(
        item, owner_id=owner_id, generation=generation, now_iso=now_iso, table=table
    )


def get_event(event_id: str) -> dict[str, object] | None:
    """One stored notification, for authorizing a route on it."""
    return notification_repo.get_event(event_id)


def get_push_token(user_id: str, token_reference: str) -> dict[str, object] | None:
    """One person's registered push device, for authorizing a route on it."""
    return notification_repo.get_push_token(user_id, token_reference)
