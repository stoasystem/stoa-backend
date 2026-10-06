"""Each teacher message names the teacher who wrote it (#65).

The student's conversation showed every teacher reply under the name of the
teacher holding the current request: a second request's teacher took over the
first one's replies, and a reply read while a new request waited showed the
generic label. The name is now written with the message, the profile's name
only, never the email.
"""

from __future__ import annotations

from test_chat_help_request_lifecycle import (
    CONV,
    TEACHER,
    _client,
    _dispatch_to,
    _reply,
    _student_client,
)
from test_chat_help_request_lifecycle import table as table  # noqa: F401 - the fixture


def _teacher_messages(student) -> list[dict]:
    response = student.get(f"/conversations/{CONV}")
    assert response.status_code == 200, response.text
    return [message for message in response.json()["messages"] if message["role"] == "teacher"]


def test_a_reply_carries_its_teachers_name_as_written(table) -> None:
    table.rows[(f"USER#{TEACHER}", "PROFILE")]["name"] = "Frau Keller"
    _dispatch_to(table, TEACHER)
    assert _reply(_client(), "Probier jetzt 15 : 5.").status_code in {200, 201}

    # The name is the one at the time of writing, not looked up afterwards.
    table.rows[(f"USER#{TEACHER}", "PROFILE")]["name"] = "Someone Else"
    [message] = _teacher_messages(_student_client())

    assert message["authorName"] == "Frau Keller"


def test_a_teacher_without_a_name_is_not_named_by_email(table) -> None:
    profile = table.rows[(f"USER#{TEACHER}", "PROFILE")]
    profile["name"] = "  "
    profile["email"] = "frau.keller@example.com"
    _dispatch_to(table, TEACHER)
    assert _reply(_client()).status_code in {200, 201}

    student = _student_client()
    [message] = _teacher_messages(student)

    assert message["authorName"] is None
    assert "frau.keller@example.com" not in student.get(f"/conversations/{CONV}").text
