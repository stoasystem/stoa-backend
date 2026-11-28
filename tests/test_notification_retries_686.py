"""The same happening told twice reaches everyone once (#686, #638 decision 3).

A happening's id is derived from what happened, never random, so a retry - a
write retried after a timeout, a job that runs again - is refused by the store
the second time: the bell keeps one row, and realtime and push each send once.
Before #686 a moderation case update or a subscription request change got a
random `notif-…` id, so a retry stored and sent it twice.

The world (four people with an open connection, a push device and every
channel on) is the snapshot test's.
"""

from __future__ import annotations

import pytest

from stoa.db.repositories import notification_repo
from stoa.services import notifications

import notification_happenings_686 as tell
from test_notification_happenings_686 import SCENARIOS
from test_notification_happenings_686 import world as world  # noqa: F401 - the fixture


def _events(table) -> list[dict]:
    return [
        row for row in table.rows.values()
        if row.get("entity_type") == notification_repo.NOTIFICATION_ENTITY
    ]


def _intents(table) -> list[dict]:
    return [
        row for row in table.rows.values()
        if row.get("entity_type") == notification_repo.DELIVERY_INTENT_ENTITY
    ]


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_a_happening_told_twice_is_stored_and_sent_once(world, scenario: str) -> None:
    table, recorder = world
    happen, _random_before = SCENARIOS[scenario]
    happen()
    once = (len(_events(table)), len(_intents(table)), len(recorder.posts), len(recorder.pushes), len(recorder.ses))

    happen()

    twice = (len(_events(table)), len(_intents(table)), len(recorder.posts), len(recorder.pushes), len(recorder.ses))
    # The dispatch reminder email is not yet a channel of the package (#687):
    # it still goes out with each offer told, as before.
    if scenario.startswith(("help_offered", "offer_closed")) and scenario != "help_offered_standing":
        assert twice[:4] == once[:4]
        assert twice[4] == once[4] * 2
    else:
        assert twice == once


@pytest.mark.parametrize(
    ("happen", "event_id"),
    [
        (tell.moderation_opened, "moderation-case-opened-case-686"),
        (
            tell.moderation_updated,
            "moderation-case-update-case-686-"
            + notifications._happenings._short_digest(tell.CHANGE_ID),
        ),
        (tell.subscription_requested, "subscription-request-subreq-686-requested"),
        (tell.subscription_approved, "subscription-request-subreq-686-approved"),
    ],
)
def test_moderation_and_subscription_notifications_have_fixed_ids(world, happen, event_id) -> None:
    table, _recorder = world

    happen()

    assert [row["event_id"] for row in _events(table)] == [event_id]


def test_each_moderation_update_still_reaches_the_reporter(world) -> None:
    # An update and a note on the same case, at the same status, are two
    # changes: the reporter hears each once, as before #686.
    table, _recorder = world
    for change_id in ("2026-11-28T10:00:00+00:00#aaaa", "2026-11-28T10:05:00+00:00#bbbb"):
        notifications.happened(
            notifications.ModerationCaseUpdated(
                case=dict(tell.CASE),
                actor_id=tell.ADMIN,
                actor_role="admin",
                owner_id=tell.STUDENT,
                privacy_generation=tell.GENERATION,
                change_id=change_id,
            )
        )

    assert len(_events(table)) == 2
    assert all("#" not in row["event_id"] for row in _events(table))


def test_a_subscription_request_reaching_each_status_is_told_once_per_status(world) -> None:
    table, _recorder = world
    for status in ("requested", "in_review", "approved", "applied"):
        notifications.happened(
            notifications.SubscriptionRequestChanged(
                request={**tell.REQUEST, "status": status},
                recipient_id=tell.PARENT,
                recipient_role="parent",
                actor_id=tell.ADMIN,
                actor_role="admin",
            )
        )
        notifications.happened(
            notifications.SubscriptionRequestChanged(
                request={**tell.REQUEST, "status": status},
                recipient_id=tell.PARENT,
                recipient_role="parent",
                actor_id=tell.ADMIN,
                actor_role="admin",
            )
        )

    assert len(_events(table)) == 4
