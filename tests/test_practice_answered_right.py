"""Which exercises of a lesson a student has answered right (#83).

Completing a lesson asks this of every attempt the student ever made, so the
read must page to the end: a student with many attempts must not be told an
exercise was never answered because its right answer sat on a later page.
"""

from __future__ import annotations

from fakes.dynamodb import FakeTable

from stoa.db.repositories import practice_repo


def _attempt(student: str, index: int, *, lesson: str, challenge: str, correct: bool) -> dict:
    return {
        "PK": f"ATTEMPTS#{student}",
        "SK": f"ATTEMPT#{index:04d}",
        "attempt_id": f"{index:04d}",
        "student_id": student,
        "challenge_id": challenge,
        "lesson_id": lesson,
        "correct": correct,
    }


def test_the_right_answers_of_a_lesson_are_read_across_every_page(monkeypatch) -> None:
    table = FakeTable(page_item_cap=3)
    rows = []
    # Many attempts first, the one right answer to c-2 last of all.
    for index in range(20):
        rows.append(_attempt("student-1", index, lesson="lesson-1", challenge="c-0", correct=index == 4))
    rows.append(_attempt("student-1", 20, lesson="lesson-1", challenge="c-1", correct=False))
    rows.append(_attempt("student-1", 21, lesson="lesson-2", challenge="c-1", correct=True))
    rows.append(_attempt("student-2", 22, lesson="lesson-1", challenge="c-1", correct=True))
    rows.append(_attempt("student-1", 23, lesson="lesson-1", challenge="c-2", correct=True))
    table.seed(*rows)
    monkeypatch.setattr(practice_repo, "get_table", lambda: table)

    assert practice_repo.challenges_answered_right("student-1", "lesson-1") == {"c-0", "c-2"}
