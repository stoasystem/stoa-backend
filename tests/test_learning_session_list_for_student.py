"""`learning_session.list_for_student`: one student's sessions, within a budget (#431)."""

from boto3.dynamodb.conditions import Attr

from stoa.db import table as db_table
from stoa.services import learning_session


class _StudentIndex:
    """GSI-StudentId double that cuts each page before the filter, as DynamoDB does.

    A page is `Limit` rows when the query passes one and `default_rows`
    otherwise (standing in for the table's 1 MB). The filter then drops every
    row that is not a conversation record, so a page can come back empty with
    records still behind its key.
    """

    def __init__(self, rows, *, default_rows=50):
        self.rows = rows
        self.default_rows = default_rows
        self.query_calls = []

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        assert kwargs["IndexName"] == "GSI-StudentId"
        assert kwargs["ScanIndexForward"] is False
        assert kwargs["FilterExpression"] == Attr("entity_type").eq("conversation")
        student_id = kwargs["KeyConditionExpression"].get_expression()["values"][1]
        partition = [row for row in self.rows if row["student_id"] == student_id]
        start = 0
        cursor = kwargs.get("ExclusiveStartKey")
        if cursor is not None:
            start = 1 + next(
                index
                for index, row in enumerate(partition)
                if (row["PK"], row["SK"]) == (cursor["PK"], cursor["SK"])
            )
        size = kwargs.get("Limit", self.default_rows)
        evaluated = partition[start : start + size]
        response = {
            "Items": [dict(row) for row in evaluated if row["entity_type"] == "conversation"]
        }
        if start + len(evaluated) < len(partition):
            last = evaluated[-1]
            response["LastEvaluatedKey"] = {
                key: last[key] for key in ("PK", "SK", "student_id", "created_at")
            }
        return response


def _rows(*, messages, conversations, student_id="student-1"):
    """Newest first, as the descending index returns them: messages, then records."""
    rows = [
        {
            "PK": f"CONV#noise-{index}",
            "SK": f"MSG#{index}",
            "student_id": student_id,
            "created_at": f"2026-07-20T00:00:{index:06d}Z",
            "entity_type": "message",
        }
        for index in range(messages)
    ]
    rows += [
        {
            "PK": f"CONV#history-{index}",
            "SK": "CONV",
            "student_id": student_id,
            "created_at": f"2026-07-15T00:00:{index:06d}Z",
            "entity_type": "conversation",
            "conversation_id": f"history-{index}",
        }
        for index in range(conversations)
    ]
    return rows


def _ids(listed):
    return [item["conversation_id"] for item in listed.items]


def test_lists_every_record_when_the_index_ends_within_the_limit():
    table = _StudentIndex(_rows(messages=3, conversations=4))
    db_table.install(table)

    listed = learning_session.list_for_student("student-1", limit=10)

    assert _ids(listed) == ["history-0", "history-1", "history-2", "history-3"]
    assert listed.truncated is False
    assert len(table.query_calls) == 1
    assert "Limit" not in table.query_calls[0]


def test_follows_the_key_past_pages_the_filter_emptied():
    table = _StudentIndex(_rows(messages=120, conversations=2))
    db_table.install(table)

    listed = learning_session.list_for_student("student-1", limit=10)

    assert _ids(listed) == ["history-0", "history-1"]
    assert listed.truncated is False
    assert len(table.query_calls) == 3


def test_only_the_students_own_rows_are_listed():
    table = _StudentIndex(
        _rows(messages=0, conversations=2) + _rows(messages=0, conversations=1, student_id="other")
    )
    db_table.install(table)

    listed = learning_session.list_for_student("student-1", limit=10)

    assert len(listed.items) == 2
    assert all(item["student_id"] == "student-1" for item in listed.items)


def test_stops_at_the_limit_and_says_so():
    table = _StudentIndex(_rows(messages=0, conversations=250))
    db_table.install(table)

    listed = learning_session.list_for_student("student-1", limit=120)

    assert len(listed.items) == 120
    assert _ids(listed)[0] == "history-0"
    assert listed.truncated is True
    assert len(table.query_calls) == 3


def test_more_records_than_the_limit_on_the_last_page_is_truncated():
    table = _StudentIndex(_rows(messages=0, conversations=30))
    db_table.install(table)

    listed = learning_session.list_for_student("student-1", limit=20)

    assert len(listed.items) == 20
    assert listed.truncated is True
    assert len(table.query_calls) == 1


def test_exactly_the_limit_on_the_last_page_is_not_truncated():
    table = _StudentIndex(_rows(messages=0, conversations=20))
    db_table.install(table)

    listed = learning_session.list_for_student("student-1", limit=20)

    assert len(listed.items) == 20
    assert listed.truncated is False


def test_a_spent_page_budget_stops_the_read_and_says_so():
    """A heavy history is bounded, and the caller is told it was cut short."""
    table = _StudentIndex(_rows(messages=400, conversations=2))
    db_table.install(table)

    listed = learning_session.list_for_student("student-1", limit=10, page_budget=3)

    assert listed.items == []
    assert listed.truncated is True
    assert len(table.query_calls) == 3


def test_the_default_page_budget_is_twenty_five_pages():
    table = _StudentIndex(_rows(messages=2000, conversations=1), default_rows=10)
    db_table.install(table)

    listed = learning_session.list_for_student("student-1", limit=10)

    assert listed.items == []
    assert listed.truncated is True
    assert len(table.query_calls) == learning_session.STUDENT_LIST_PAGE_BUDGET == 25


def test_page_size_is_the_querys_limit_and_changes_how_far_a_budget_reaches():
    """`Limit` counts rows looked at, so a small page reaches fewer rows per budget."""
    rows = _rows(messages=30, conversations=1)

    without = _StudentIndex(rows)
    db_table.install(without)
    reached = learning_session.list_for_student("student-1", limit=5, page_budget=2)

    with_size = _StudentIndex(rows)
    db_table.install(with_size)
    cut = learning_session.list_for_student("student-1", limit=5, page_budget=2, page_size=5)

    assert _ids(reached) == ["history-0"]
    assert reached.truncated is False
    assert cut.items == []
    assert cut.truncated is True
    assert [call["Limit"] for call in with_size.query_calls] == [5, 5]

