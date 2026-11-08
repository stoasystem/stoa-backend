"""The provider readiness view's "last Stripe event" across the table's pages (#101).

Billing events sit under each parent's partition, so a whole-table scan meets
them in parent order, not time order. Read one page and the answer is the newest
event of the table's first megabyte: a stale time, or none at all, while the
webhook is in fact delivering. Each test puts the newest event behind pages the
scan has to walk through.
"""

from __future__ import annotations

import pytest
from fakes.dynamodb import FakeTable

from stoa.db.table import SCAN_PAGE_BUDGET, TableUnavailable
from stoa.services import subscription_service

PAGE = 2


@pytest.fixture
def table(monkeypatch) -> FakeTable:
    built = FakeTable()
    monkeypatch.setattr(subscription_service, "get_table", lambda: built)
    return built


def _event(parent_id: str, event_at: str, event_type: str = "invoice.paid") -> dict:
    return {
        "PK": f"SUBSCRIPTION_BILLING#{parent_id}",
        "SK": f"EVENT#{event_at}#evt_{parent_id}",
        "entity_type": subscription_service.BILLING_EVENT_ENTITY,
        "parent_id": parent_id,
        "event_id": f"stripe_evt_{parent_id}",
        "event_type": event_type,
        "event_at": event_at,
        "provider": "stripe",
    }


def test_the_newest_event_is_found_on_a_later_page(table) -> None:
    # Parents that sort first hold older events; the newest belongs to a parent
    # whose partition the scan reaches last.
    for index in range(PAGE * 3):
        table.seed(_event(f"parent-a{index:02d}", f"2026-06-0{1 + index % 5}T10:00:00+00:00"))
    table.seed(_event("parent-z", "2026-09-19T08:30:00+00:00", "invoice.payment_failed"))
    table.page_item_cap = PAGE

    latest = subscription_service._last_observed_provider_event()

    assert latest == {
        "eventAt": "2026-09-19T08:30:00+00:00",
        "eventType": "invoice.payment_failed",
    }


def test_pages_with_no_event_on_them_do_not_end_the_read(table) -> None:
    # Between the first event and the newest lie whole pages of other parents'
    # billing rows, so those pages come back empty after the filter but still
    # carry a cursor.
    table.seed(_event("parent-a", "2026-06-01T10:00:00+00:00"))
    for index in range(PAGE * 4):
        table.seed(
            {
                "PK": f"SUBSCRIPTION_BILLING#parent-m{index:02d}",
                "SK": "BILLING",
                "entity_type": subscription_service.BILLING_ENTITY,
            }
        )
    table.seed(_event("parent-z", "2026-09-19T08:30:00+00:00"))
    table.page_item_cap = PAGE

    latest = subscription_service._last_observed_provider_event()

    assert latest["eventAt"] == "2026-09-19T08:30:00+00:00"


def test_a_table_with_no_event_answers_none_after_reading_every_page(table) -> None:
    for index in range(PAGE * 3):
        table.seed({"PK": f"PROFILE#u-{index:02d}", "SK": "META", "entity_type": "user_profile"})
    table.page_item_cap = PAGE

    assert subscription_service._last_observed_provider_event() == {
        "eventAt": None,
        "eventType": None,
    }
    assert table.calls["scan"] == 3


def test_a_read_past_the_page_budget_fails_instead_of_answering(table) -> None:
    # A stale time on this view says the webhook is quiet when it is not; an
    # error says the view could not tell.
    for index in range(SCAN_PAGE_BUDGET + 1):
        table.seed({"PK": f"PROFILE#u-{index:04d}", "SK": "META", "entity_type": "user_profile"})
    table.seed(_event("parent-z", "2026-09-19T08:30:00+00:00"))
    table.page_item_cap = 1

    with pytest.raises(TableUnavailable, match="page_budget_spent"):
        subscription_service._last_observed_provider_event()
