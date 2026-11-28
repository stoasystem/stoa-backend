"""The rows the account machinery reaches into, without importing the store (#686).

Account deletion takes a closing account's name out of notifications other
people own; authorization loads the one event or device a route acts on. These are those few calls,
passed straight to the notification store when they are made (so a test that
replaces the store's function replaces it here too).
"""

from __future__ import annotations

from collections.abc import Mapping

from stoa.db.repositories import notification_repo

DELIVERY_INTENT_ENTITY = notification_repo.DELIVERY_INTENT_ENTITY


def scrub_notification_identity_references(
    item: Mapping[str, object],
    *,
    owner_id: str,
    generation: int,
    table: object | None = None,
) -> None:
    """Take the account's name out of a notification another person owns."""
    notification_repo.scrub_notification_identity_references(
        item, owner_id=owner_id, generation=generation, table=table
    )


def get_event(event_id: str) -> dict[str, object] | None:
    """One stored notification, for authorizing a route on it."""
    return notification_repo.get_event(event_id)


def get_push_token(user_id: str, token_reference: str) -> dict[str, object] | None:
    """One person's registered push device, for authorizing a route on it."""
    return notification_repo.get_push_token(user_id, token_reference)
