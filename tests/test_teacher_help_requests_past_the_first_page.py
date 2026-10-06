"""A teacher finds a help request wherever its row falls in the table (#95).

The teacher's list, detail, reply and status change all find a chat help
request by a filtered scan of the whole table, and it read one page only. In
production on 2026-10-06 the first page stopped after 1604 rows, and a request
dispatched to the test teacher a minute earlier was on a later page: the
teacher could not see it, take it or answer it.
"""

from __future__ import annotations

from test_chat_help_request_lifecycle import (
    CONV,
    REQUEST,
    TEACHER,
    _client,
    _conv,
    _dispatch_to,
    _reply,
    _set_status,
)
from test_chat_help_request_lifecycle import table as table  # noqa: F401 - the fixture


def _push_past_the_first_page(table) -> None:
    # Rows that sort before the conversation, and pages of three rows: the
    # request is several pages in, as a new one is in production.
    for index in range(12):
        table.seed({"PK": f"AAA#filler-{index:02d}", "SK": "ROW", "entity_type": "filler"})
    table.page_item_cap = 3


def test_the_teacher_lists_a_request_beyond_the_first_page(table) -> None:
    _dispatch_to(table, TEACHER)
    _push_past_the_first_page(table)

    response = _client().get("/teachers/me/help-requests")

    assert response.status_code == 200, response.text
    assert CONV in [item["conversationId"] for item in response.json()["items"]]


def test_the_teacher_opens_and_answers_a_request_beyond_the_first_page(table) -> None:
    _dispatch_to(table, TEACHER)
    _push_past_the_first_page(table)
    teacher = _client()

    assert teacher.get(f"/teachers/me/help-requests/{REQUEST}").status_code == 200
    assert _reply(teacher).status_code in {200, 201}
    assert _set_status(teacher, "resolved").status_code == 200
    assert _conv(table)["escalation_status"] == "resolved"
