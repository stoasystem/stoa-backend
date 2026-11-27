"""Asking a question reads as much whether the curriculum is small or large (#496).

On 2026-11-17 the English and physics knowledge bases were published, and
`POST /conversations` with a first question began to run into Lambda's 29
seconds. The weak topics the answer is personalised with were read through
`adaptive_learning_service.get_memory_summary`, which also builds practice
recommendations: for every weak topic it listed the subject's exercises, and
each list read every exercise row of the practice partition. For a student
with a handful of weak topics that was some 150,000 rows per question, and two
full-table scans per topic for the student's assignments besides - none of it
used by the answer.

These run the real routes against the shared table double holding the
published curriculum at two sizes (`fakes.published_curriculum`), for a
student with Ask history in two subjects, and compare the rows the table had
to read. Only the model call and the entitlement read are replaced.

Since #673 the weak topics are resolved against the catalog, which a container
keeps (`curriculum_cache`): the table here carries the catalog stamp the seed
writes in production, and each ask runs in a container that has not read the
curriculum yet, so it loads the one stored copy (#669) rather than the
partition.
"""

from __future__ import annotations

from typing import Any

import pytest
import time_machine

from fakes.admission import seed_plan
from fakes.ask_question import QUESTION, STUDENT, _client
from fakes.ask_question import invokes as invokes  # noqa: F401 - the fixture
from fakes.ask_question import model as model  # noqa: F401 - the fixture
from fakes.learning_session import seed_conversation
from fakes.published_curriculum import ReadCountingTable, curriculum_rows
from stoa.db import table as db_table
from stoa.db.repositories import asked_knowledge_repo
from stoa.services import adaptive_learning_service, curriculum_cache

#: A twentieth of production, and five times that.
SMALL, LARGE = 0.05, 0.25
CONV = "conv-asked"


def _asked_before(table: ReadCountingTable) -> None:
    """Twelve earlier Ask answers in each subject, each naming two stars."""
    units: dict[str, list[dict[str, Any]]] = {}
    for row in table.rows.values():
        if str(row["SK"]).startswith("UNIT#"):
            units.setdefault(str(row["subject_id"]), []).append(row)
    for subject, pool in (("mathematics", units["mathematics"][:24]), ("physics", units["physics"][:4])):
        for index in range(12):
            named = [pool[(2 * index + offset) % len(pool)] for offset in range(2)]
            put = asked_knowledge_repo.record_put(
                conversation_id=f"earlier-{subject}-{index}",
                message_id=f"answer-{index}",
                student_id=STUDENT,
                subject=subject,
                points=[(unit["title"], unit["unit_id"]) for unit in named],
                asked_at=f"2026-11-{10 + index % 7:02d}T10:00:00+00:00",
            )
            assert put is not None
            table.seed(put["Put"]["Item"])


def _table(monkeypatch: pytest.MonkeyPatch, scale: float) -> ReadCountingTable:
    table = ReadCountingTable()
    table.seed(*curriculum_rows(scale))
    table.seed_active_account(STUDENT)
    table.seed(
        {
            "PK": f"USER#{STUDENT}",
            "SK": "PROFILE",
            "user_id": STUDENT,
            "role": "student",
            "account_status": "active",
            "grade": "Grade 6",
            "subjects": ["mathematics", "physics"],
        }
    )
    _asked_before(table)
    seed_conversation(table, conversation_id=CONV, student_id=STUDENT)
    table.seed({**curriculum_cache.STAMP_KEY, "stamp": f"seed-{scale}"})
    db_table.install(table)
    seed_plan(monkeypatch)
    # The first container to read the curriculum stores it; the ask runs in another.
    curriculum_cache.current()
    curriculum_cache.forget()
    table.reset_reads()
    return table


def _create_with_a_question() -> None:
    response = _client().post(
        "/conversations",
        json={"subject": "Mathematik", "grade": "Grade 6", "initialMessage": QUESTION},
    )
    assert response.status_code == 201, response.text


def _send_a_message() -> None:
    response = _client().post(
        f"/conversations/{CONV}/messages",
        json={"content": QUESTION, "idempotencyKey": "key-1"},
    )
    assert response.status_code == 202, response.text


@pytest.mark.parametrize("ask", [_create_with_a_question, _send_a_message], ids=["create", "send"])
def test_asking_reads_no_more_of_a_larger_curriculum(
    monkeypatch: pytest.MonkeyPatch, model, invokes, ask
) -> None:
    small = _table(monkeypatch, SMALL)
    ask()
    large = _table(monkeypatch, LARGE)
    ask()

    assert large.item_count() > 3 * small.item_count()
    assert large.total_rows_scanned == small.total_rows_scanned, (
        f"small curriculum:\n{small.report()}\n\nlarge curriculum:\n{large.report()}"
    )
    assert large.total_items_read == small.total_items_read


def test_the_answer_is_given_the_weak_topics_the_memory_summary_reports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reading only the weak topics changes nothing in what the answer is told."""
    _table(monkeypatch, SMALL)
    student = {"sub": STUDENT, "user_id": STUDENT, "role": "student"}

    # A few days after the earlier answers: within the 90 days the weak topics count (#673).
    with time_machine.travel("2026-11-18T12:00:00+00:00", tick=False):
        topics = adaptive_learning_service.weak_topics(STUDENT, locale="de")

        assert topics, "the earlier answers name weak topics"
        assert all(topic.get("label") and topic.get("topicId") for topic in topics)
        for subject in (None, "math", "physics"):
            summary = adaptive_learning_service.get_memory_summary(
                student_id=STUDENT, user=student, subject=subject
            )
            assert topics == summary["weakTopics"]
