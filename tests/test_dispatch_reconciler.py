"""Nobody should be left waiting on a teacher who is not coming.

Dispatch happens inside the request that asks for a teacher. These cover what
happens afterwards, when that request left the student waiting on nobody: the
scheduled job runs `help_requests.sweep` over every help request (#189).
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from boto3.dynamodb.conditions import Attr
import pytest

from stoa.services import help_requests

NOW = datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc)


def stamp(offset_minutes: int = 0) -> str:
    return (NOW + timedelta(minutes=offset_minutes)).isoformat()


def request(conversation_id: str, **overrides: Any) -> dict[str, Any]:
    base = {
        "PK": f"CONV#{conversation_id}",
        "SK": "HELP",
        "entity_type": "help_request",
        "conversation_id": conversation_id,
        "escalation_request_id": conversation_id,
        "student_id": "student-1",
        "escalation_status": "pending",
        "escalated_at": stamp(-5),
        "version": 1,
    }
    base.update(overrides)
    return base


class ScanPages:
    """A table whose scan answers page by page, remembering what it was asked."""

    def __init__(self, *pages: list[dict[str, Any]]) -> None:
        self.pages = list(pages)
        self.requests: list[dict[str, Any]] = []

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        self.requests.append(kwargs)
        index = len(self.requests) - 1
        response: dict[str, Any] = {"Items": self.pages[index]}
        if index + 1 < len(self.pages):
            response["LastEvaluatedKey"] = {"PK": f"page-{index}", "SK": "HELP"}
        return response


def test_the_scheduled_job_reports_what_it_did(monkeypatch):
    from stoa.jobs import dispatch_reconciler

    monkeypatch.setattr(
        dispatch_reconciler.help_requests, "sweep",
        lambda: {"reassigned": 2, "conversationSweep": "completed",
                 "conversationsWaiting": 1,
                 "conversationsDispatched": [{"conversationId": "c-1", "status": "dispatched"}],
                 "conversationsExpired": [],
                 "generatedAt": stamp()},
    )

    result = dispatch_reconciler.handler({"job": "dispatch_reconcile"}, None)

    assert result == {
        "status": "completed", "reassigned": 2,
        "conversationSweep": "completed",
        "conversationsWaiting": 1, "conversationsDispatched": 1, "conversationsExpired": 0,
        "generatedAt": stamp(),
    }


def test_a_failed_sweep_is_not_swallowed(monkeypatch):
    """A silent failure here is how the gap it closes went unnoticed."""
    from stoa.jobs import dispatch_reconciler

    def explode():
        raise RuntimeError("dynamo is having a day")

    monkeypatch.setattr(dispatch_reconciler.help_requests, "sweep", explode)

    with pytest.raises(RuntimeError):
        dispatch_reconciler.handler({}, None)


def test_a_chat_escalation_nobody_took_is_swept_too(monkeypatch):
    """The chat lane is the one a student actually uses."""
    taken: list[str] = []

    monkeypatch.setattr(
        help_requests, "list_all",
        lambda **_kwargs: [
            request("c-1"),
            request("c-2", escalation_status="in_progress", teacher_id="teacher-2"),
        ],
    )

    def fake_dispatch(record, *, now=None, table=None):
        taken.append(record["conversation_id"])
        return {**record, "dispatch_status": "dispatched", "version": record["version"] + 1}

    monkeypatch.setattr(help_requests, "dispatch", fake_dispatch)

    result = help_requests.sweep(now=stamp(), table=object())

    # Only the one still waiting; a teacher is already working on the other.
    assert taken == ["c-1"]
    assert result["conversationsWaiting"] == 1
    assert result["conversationsDispatched"] == [{"conversationId": "c-1", "status": "dispatched"}]


def test_a_chat_escalation_with_a_live_teacher_is_left_alone(monkeypatch):
    monkeypatch.setattr(
        help_requests, "list_all",
        lambda **_kwargs: [request(
            "c-1", dispatch_status="dispatched", dispatched_teacher_id="teacher-3",
            dispatch_deadline_at=stamp(9),
        )],
    )
    monkeypatch.setattr(
        help_requests, "dispatch",
        lambda *a, **k: pytest.fail("a teacher already has this conversation"),
    )

    result = help_requests.sweep(now=stamp(), table=object())

    assert result["conversationsWaiting"] == 0


def test_a_failed_chat_sweep_says_so_rather_than_reporting_nobody_waiting(monkeypatch):
    """Reporting zero for a sweep that never ran is how a broken sweep hides."""
    def explode(**_kwargs):
        raise RuntimeError("scan is having a day")

    monkeypatch.setattr(help_requests, "list_all", explode)

    result = help_requests.sweep(now=stamp(), table=object())

    assert result["conversationSweep"] == "failed"
    assert result["conversationsWaiting"] == 0


def test_a_healthy_chat_sweep_says_it_completed(monkeypatch):
    monkeypatch.setattr(help_requests, "list_all", lambda **_kwargs: [])

    result = help_requests.sweep(now=stamp(), table=object())

    assert result["conversationSweep"] == "completed"


def test_the_lister_asks_for_help_requests_and_reads_every_page():
    """It was once called with the wrong arguments and the failure swallowed;
    and a filtered scan stops at a page of the table, not at the matches (#95)."""
    table = ScanPages(
        [request("c-1"), {"PK": "CONV#c-x", "SK": "HELP", "entity_type": "help_request"}],
        [],
        [request("c-2", escalation_status="resolved")],
    )

    rows = help_requests.list_all(table=table)

    assert [row["conversation_id"] for row in rows] == ["c-1", "c-2"]
    assert len(table.requests) == 3
    assert table.requests[0]["FilterExpression"] == Attr("entity_type").eq("help_request")
    assert table.requests[1]["ExclusiveStartKey"] == {"PK": "page-0", "SK": "HELP"}
    assert table.requests[2]["ExclusiveStartKey"] == {"PK": "page-1", "SK": "HELP"}


def test_the_lister_of_waiting_requests_leaves_out_requests_that_have_ended():
    # The sweep works through what is waiting; an ended request listed there
    # would be offered again, or stand in the place of a waiting one.
    ended = [
        request(f"c-{status}", escalation_status=status)
        for status in ("expired", "withdrawn", "resolved", "in_progress")
    ]
    waiting = request("c-waiting")
    table = ScanPages([*ended, waiting])

    assert help_requests.list_open(table=table) == [waiting]
