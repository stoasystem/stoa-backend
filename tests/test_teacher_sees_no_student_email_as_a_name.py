"""A teacher is not shown a student's email in place of their name (#94).

`_get_student_name` fell back to `email` when the profile had no name, so the
help request list and its detail showed every teacher a contact detail nobody
had agreed to share — in the field that answers "what do I call this person".
The user decided on 2026-10-06 that a student without a name is "Student".

Found in the review of #65, and a different thing from what #65 fixed: that
one was the student seeing the teacher's email.
"""

from __future__ import annotations

import pytest

from stoa.routers import teachers

EMAIL = "pupil@example.test"


@pytest.fixture
def profile(monkeypatch):
    held: dict[str, object] = {}
    monkeypatch.setattr(teachers.user_repo, "get_user", lambda student_id: held or None)
    return held


def test_a_student_without_a_name_is_not_shown_by_their_email(profile) -> None:
    profile.update({"user_id": "s-1", "email": EMAIL})

    assert teachers._get_student_name("s-1") == "Student"


def test_a_name_of_spaces_is_no_name(profile) -> None:
    profile.update({"user_id": "s-1", "name": "   ", "email": EMAIL})

    assert teachers._get_student_name("s-1") == "Student"


def test_a_student_who_gave_a_name_is_called_by_it(profile) -> None:
    profile.update({"user_id": "s-1", "name": "  Lena  ", "email": EMAIL})

    assert teachers._get_student_name("s-1") == "Lena"


def test_an_account_that_is_not_there_is_not_an_error(profile) -> None:
    assert teachers._get_student_name("s-missing") == "Student"
