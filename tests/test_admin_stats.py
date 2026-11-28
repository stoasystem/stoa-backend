"""`/admin/stats`: how fast teachers answer help requests, over the last 30 days (#697).

The totals it answered before had no reader, and the question counts among them
counted only legacy question rows nothing writes any more. What is left is the
teacher reply card, from the help requests asked in the period. What it reads
follows the requests of the period: not the rest of the table, not the accounts,
not the legacy question rows, not the requests asked before.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from fakes.dynamodb import FakeTable
from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo, question_repo
from stoa.routers import admin
from stoa.routers.admin import stats
from stoa.services import help_requests

NOW = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)


def _at(delta: timedelta) -> str:
    return (NOW - delta).isoformat()


class MeteredTable(FakeTable):
    """Counts the items each read went through, besides the calls."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.items_read = 0

    def query(self, **kwargs: Any) -> dict[str, Any]:
        page = super().query(**kwargs)
        self.items_read += int(page.get("ScannedCount", 0))
        return page

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        page = super().scan(**kwargs)
        self.items_read += int(page.get("ScannedCount", 0))
        return page


def _request(conversation_id: str, asked: timedelta, status: str, **times: timedelta) -> dict[str, Any]:
    record = {
        **help_requests.key(conversation_id),
        "entity_type": help_requests.ENTITY_TYPE,
        "conversation_id": conversation_id,
        "escalation_request_id": conversation_id,
        "student_id": "student-1",
        "version": 1,
        "escalation_status": status,
        "created_at": _at(asked),
        "escalated_at": _at(asked),
        **{field: _at(moment) for field, moment in times.items()},
    }
    return {**record, **help_requests.index_fields(record), **help_requests.listing_fields(record)}


def _in_period(table: FakeTable) -> None:
    table.seed(
        # Answered in 10 minutes: within target.
        _request(
            "c-resolved", timedelta(days=2), help_requests.RESOLVED,
            accepted_at=timedelta(days=2, minutes=-5),
            first_teacher_action_at=timedelta(days=2, minutes=-10),
            escalation_resolved_at=timedelta(days=2, minutes=-20),
        ),
        # Answered in 35 minutes: breached. Asked on the period's first second.
        _request(
            "c-in-progress", timedelta(days=30), help_requests.IN_PROGRESS,
            accepted_at=timedelta(days=30, minutes=-30),
            first_teacher_action_at=timedelta(days=30, minutes=-35),
        ),
        # Withdrawn: never a teacher's to answer.
        _request("c-withdrawn", timedelta(days=5), help_requests.WITHDRAWN),
    )


def _noise(table: FakeTable, rows: int) -> None:
    """What grows beside the requests of the period, none of it the card's."""
    for index in range(rows):
        table.seed({"PK": f"AAA#filler-{index:04d}", "SK": "ROW", "entity_type": "filler"})
        profile = {
            "PK": f"USER#student-{index:04d}", "SK": "PROFILE", "role": "student",
            "created_at": _at(timedelta(days=400)),
        }
        table.seed({**profile, **account_deletion_repo.account_listing_fields(profile)})
        # Legacy question rows from early test accounts, still in their list.
        question = {
            "PK": f"QUESTION#q-{index:04d}", "SK": "META", "entity_type": "question",
            "status": "resolved", "created_at": _at(timedelta(days=3)),
            "teacher_requested_at": _at(timedelta(days=3)),
            "sla_request_to_first_reply_seconds": 7200,
            "teacher_first_reply_sla_bucket": "breached",
        }
        table.seed({**question, **question_repo.listing_fields(question)})
        # Requests asked before the period, one second before it included.
        table.seed(
            _request(
                f"c-old-{index:04d}", timedelta(days=30, seconds=1 + index), help_requests.RESOLVED,
                first_teacher_action_at=timedelta(days=30, seconds=index - 60),
            )
        )


def _admin() -> TestClient:
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    install_actor_overrides(app, {"sub": "admin-1", "role": "admin"})
    return TestClient(app)


@pytest.fixture(autouse=True)
def _frozen_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stats, "_now", lambda: NOW)


def _stats(table: FakeTable) -> dict[str, Any]:
    db_table.install(table)
    response = _admin().get("/admin/stats")
    assert response.status_code == 200, response.text
    return response.json()


def test_the_card_counts_the_requests_asked_in_the_last_30_days() -> None:
    table = MeteredTable()
    _in_period(table)
    _noise(table, 3)

    body = _stats(table)

    assert set(body) == {"teacher_sla", "period_days"}
    assert body["period_days"] == 30
    sla = body["teacher_sla"]
    assert sla["tracked_questions"] == 2
    assert sla["first_reply"] == {"count": 2, "average_seconds": 1350, "max_seconds": 2100}
    assert sla["buckets"] == {"within_target": 1, "at_risk": 0, "breached": 1, "unknown": 0}
    assert sla["resolved"] == {"count": 1, "average_seconds": 1200, "max_seconds": 1200}


def test_the_retired_totals_are_gone_from_the_contract() -> None:
    assert set(stats.StatsResponse.model_fields) == {"teacher_sla", "period_days"}


def test_what_it_reads_does_not_grow_with_the_table() -> None:
    """Accounts, legacy questions, older requests and other rows: none is read."""
    small = MeteredTable(page_item_cap=2)
    _in_period(small)
    before = _stats(small)

    large = MeteredTable(page_item_cap=2)
    _in_period(large)
    _noise(large, 200)
    after = _stats(large)

    assert after == before
    assert dict(large.calls) == dict(small.calls)
    assert set(large.calls) == {"query"}
    assert large.items_read == small.items_read == 3


def test_reading_from_the_beginning_would_read_the_older_requests() -> None:
    """Negative control: the bound the test above holds is the period's."""
    table = MeteredTable(page_item_cap=2)
    _in_period(table)
    _noise(table, 200)

    every_request = help_requests.list_asked_since(datetime(2000, 1, 1, tzinfo=timezone.utc), table=table)

    assert len(every_request) == 203
    assert table.items_read == 203
