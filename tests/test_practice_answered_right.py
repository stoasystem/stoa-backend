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


class _LaggingReplicaTable(FakeTable):
    """A table whose newest writes only a strongly consistent read sees yet.

    DynamoDB reads are eventually consistent unless asked otherwise: the last
    exercise's right answer, saved a moment before completion is requested,
    may still be missing from the replica an ordinary query reads.
    """

    def __init__(self, *, fresh: set[tuple[str, str]], **kwargs) -> None:
        super().__init__(**kwargs)
        self.fresh = fresh

    def query(self, **kwargs):
        if kwargs.get("ConsistentRead") is True:
            return super().query(**kwargs)
        hidden = {key: self.rows.pop(key) for key in list(self.rows) if key in self.fresh}
        try:
            return super().query(**kwargs)
        finally:
            self.rows.update(hidden)


def test_a_right_answer_saved_just_before_completion_is_read(monkeypatch) -> None:
    # Review of 5aa22b80: without a strongly consistent read the last right
    # answer could be missed and the lesson refused with 409.
    last = _attempt("student-1", 2, lesson="lesson-1", challenge="c-2", correct=True)
    table = _LaggingReplicaTable(fresh={(last["PK"], last["SK"])})
    table.seed(
        _attempt("student-1", 0, lesson="lesson-1", challenge="c-0", correct=True),
        _attempt("student-1", 1, lesson="lesson-1", challenge="c-1", correct=True),
        last,
    )
    monkeypatch.setattr(practice_repo, "get_table", lambda: table)

    assert practice_repo.challenges_answered_right("student-1", "lesson-1") == {"c-0", "c-1", "c-2"}
