"""Which topics a student is weak in, by one rule (#632, #673).

The rule is `weak_topics.for_student`'s alone; see its module docstring. The
first half locks the top ten of five typical students
(`fakes.weak_topic_students`), the check the user chose in place of a
production comparison: production has no real students yet. The second half
holds each part of the rule on its own.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from fakes import student_evidence as fake_evidence
from fakes.weak_topic_students import NOW, STUDENTS, Student, answer, asked, at, catalog, question
from stoa.services import adaptive_learning_service, learning_profile_service, weak_topics

BY_KEY = {student.key: student for student in STUDENTS}


def _top(student: Student, **kwargs: Any) -> list[tuple[str, str, str, int, int]]:
    found = weak_topics.for_student(
        student.evidence(), [*student.questions, *student.asked], locale="de", **kwargs
    )
    return [(t.subject, t.topic_id, t.name, t.score, t.count) for t in found[:10]]


# ── Five typical students ────────────────────────────────────────────────────

TOP_TEN: dict[str, list[tuple[str, str, str, int, int]]] = {
    # Ask alone: every point weighs 1; a tie goes to the newer evidence.
    "ask-only": [
        ("math", "brueche-u2", "Brüche rechnen", 3, 3),
        ("math", "kürzen mit dem ggt", "Kürzen mit dem ggT", 2, 2),
        ("physics", "kraefte-u1", "Kräfte", 2, 2),
        ("math", "gleichungen-u1", "Einfache Gleichungen lösen", 2, 2),
        ("math", "prozent-u1", "Prozentrechnen", 2, 2),
        ("math", "geometrie-u2", "Winkel messen", 1, 1),
        ("physics", "energie-u1", "Energieformen", 1, 1),
        ("math", "geometrie-u1", "Flächen berechnen", 1, 1),
        ("math", "kopfrechnen", "Kopfrechnen", 1, 1),
        ("math", "brueche-u1", "Brüche verstehen und kürzen", 1, 1),
    ],
    # Twelve fraction mistakes, all put right, leave only the one question
    # asked; the area exercise never answered right leads.
    "mostly-corrected": [
        ("math", "geometrie-u1", "Flächen berechnen", 6, 3),
        ("math", "gleichungen-u1", "Einfache Gleichungen lösen", 3, 2),
        ("math", "prozent-u1", "Prozentrechnen", 2, 1),
        ("math", "brueche-u2", "Brüche rechnen", 1, 1),
    ],
    # Unit id, lesson id, the old slug, the title in two cases and a seed of
    # the retired flow are one unit; the bare topic id is the topic.
    "many-spellings": [
        ("math", "brueche-u2", "Brüche rechnen", 10, 7),
        ("math", "bruchrechnen", "Bruchrechnen", 2, 1),
        ("math", "gleichungen-u1", "Einfache Gleichungen lösen", 1, 1),
    ],
    # Eight mistakes and five questions about angles, all older than 90 days,
    # count for nothing; neither does a point named 91 days ago.
    "old-evidence": [
        ("math", "prozent-u1", "Prozentrechnen", 5, 3),
        ("math", "gleichungen-u1", "Einfache Gleichungen lösen", 1, 1),
        ("physics", "kraefte-u1", "Kräfte", 1, 1),
    ],
    # Free names: one per subject and name compared without case (ß is ss),
    # shown as the newest evidence wrote it; never made a slug.
    "free-text": [
        ("math", "brüche", "Brüche", 3, 3),
        ("math", "kopfrechnen", "Kopfrechnen", 2, 2),
        ("math", "grössen umrechnen", "Größen umrechnen", 2, 2),
        ("math", "分数", "分数", 2, 2),
        ("physics", "hebelgesetz", "Hebelgesetz", 1, 1),
        ("math", "hebelgesetz", "Hebelgesetz", 1, 1),
        ("math", "brueche-u2", "Brüche rechnen", 1, 1),
    ],
}


def test_every_typical_student_is_locked() -> None:
    assert set(TOP_TEN) == set(BY_KEY)


@pytest.mark.parametrize("key", sorted(TOP_TEN))
def test_a_typical_student_s_top_ten(key: str) -> None:
    assert _top(BY_KEY[key]) == TOP_TEN[key]


def test_a_merged_unit_keeps_the_retired_flow_s_questions_behind_it() -> None:
    student = BY_KEY["many-spellings"]
    [merged, *_rest] = weak_topics.for_student(
        student.evidence(), [*student.questions, *student.asked], locale="de"
    )

    assert merged.evidence_question_ids == ("q-mia-1", "q-mia-2")
    assert merged.latest_evidence_at == at(3)


# ── The rule, part by part ───────────────────────────────────────────────────


def _student(
    answers: tuple[dict[str, Any], ...] = (),
    records: tuple[dict[str, Any], ...] = (),
    questions: tuple[dict[str, Any], ...] = (),
) -> Student:
    return Student("rule", "", answers=answers, asked=records, questions=questions)


def test_a_later_right_answer_puts_every_earlier_mistake_on_that_exercise_right() -> None:
    student = _student(
        (
            answer("c1", False, 30, unit="prozent-u1"),
            answer("c1", False, 20, unit="prozent-u1"),
            answer("c1", True, 10, unit="prozent-u1"),
            answer("c1", False, 5, unit="prozent-u1"),
        )
    )

    assert _top(student) == [("math", "prozent-u1", "Prozentrechnen", 2, 1)]


def test_a_right_answer_before_the_mistake_puts_nothing_right() -> None:
    student = _student(
        (answer("c1", True, 30, unit="prozent-u1"), answer("c1", False, 5, unit="prozent-u1"))
    )

    assert _top(student) == [("math", "prozent-u1", "Prozentrechnen", 2, 1)]


def test_a_right_answer_at_the_same_moment_puts_nothing_right() -> None:
    student = _student(
        (answer("c1", False, 5, unit="prozent-u1"), answer("c1", True, 5, unit="prozent-u1"))
    )

    assert _top(student) == [("math", "prozent-u1", "Prozentrechnen", 2, 1)]


def test_a_self_reported_right_answer_corrects_too() -> None:
    student = _student(
        (
            answer("c1", False, 5, unit="prozent-u1"),
            answer("c1", True, 4, unit="prozent-u1", self_reported=True),
        )
    )

    assert _top(student) == []


def test_a_right_answer_on_another_exercise_corrects_nothing() -> None:
    student = _student(
        (answer("c1", False, 5, unit="prozent-u1"), answer("c2", True, 4, unit="prozent-u1"))
    )

    assert _top(student) == [("math", "prozent-u1", "Prozentrechnen", 2, 1)]


def test_a_correction_after_the_window_still_counts() -> None:
    """A week read later: the mistake was that week, the correction after it."""
    student = _student(
        (answer("c1", False, 20, unit="prozent-u1"), answer("c1", True, 2, unit="prozent-u1"))
    )
    week = NOW - timedelta(days=21)

    assert _top(student, since=week, until=week + timedelta(days=7)) == []


def test_a_mistake_weighs_two_and_a_named_point_one() -> None:
    assert (weak_topics.MISTAKE_POINTS, weak_topics.ASKED_POINTS) == (2, 1)
    student = _student(
        (answer("c1", False, 5, unit="prozent-u1"),),
        (asked(4, "Winkel messen"), asked(3, "Winkel messen"), asked(2, "Prozentrechnen")),
    )

    assert _top(student) == [
        ("math", "prozent-u1", "Prozentrechnen", 3, 2),
        ("math", "geometrie-u2", "Winkel messen", 2, 2),
    ]


def test_a_retired_question_row_counts_as_an_ask_record() -> None:
    student = _student(
        questions=(question("q-1", 5, knowledge_points=["Winkel messen", "Kopfrechnen"]),)
    )

    found = weak_topics.for_student(student.evidence(), student.questions, locale="de")

    assert [(t.topic_id, t.score, t.evidence_question_ids) for t in found] == [
        ("kopfrechnen", 1, ("q-1",)),
        ("geometrie-u2", 1, ("q-1",)),
    ]


def test_the_window_is_the_last_ninety_days_by_default() -> None:
    assert weak_topics.WINDOW == timedelta(days=90)
    exactly = (NOW - weak_topics.WINDOW).isoformat()
    student = _student(
        records=(
            {**asked(0, "Winkel messen"), "created_at": exactly},
            asked(90.001, "Prozentrechnen"),
        )
    )

    assert _top(student) == [("math", "geometrie-u2", "Winkel messen", 1, 1)]


def test_a_reader_passes_its_own_window_start_inclusive_end_exclusive() -> None:
    student = _student(
        records=(asked(20, "Winkel messen"), asked(14, "Prozentrechnen"), asked(200, "Kopfrechnen"))
    )
    since = NOW - timedelta(days=20)

    assert _top(student, since=since, until=NOW - timedelta(days=14)) == [
        ("math", "geometrie-u2", "Winkel messen", 1, 1)
    ]
    assert [row[1] for row in _top(student, since=NOW - timedelta(days=365))] == [
        "prozent-u1",
        "geometrie-u2",
        "kopfrechnen",
    ]


def test_evidence_whose_moment_cannot_be_read_falls_in_no_window() -> None:
    student = _student(
        (
            {**answer("c1", False, 5, unit="prozent-u1"), "created_at": ""},
            {**answer("c2", False, 5, unit="prozent-u1"), "created_at": "yesterday"},
        ),
        ({**asked(1, "Winkel messen"), "created_at": "x"},),
    )

    assert _top(student) == []


def test_the_unit_an_answer_carries_wins_over_its_topic_spelling() -> None:
    student = _student((answer("c1", False, 5, unit="brueche-u1", topic="Winkel messen"),))

    assert _top(student) == [("math", "brueche-u1", "Brüche verstehen und kürzen", 2, 1)]


def test_a_topic_with_one_unit_is_that_unit_and_one_with_two_stays_the_topic() -> None:
    student = _student(
        (answer("c1", False, 5, topic="prozent"), answer("c2", False, 4, topic="geometrie"))
    )

    assert _top(student) == [
        ("math", "geometrie", "Geometrie", 2, 1),
        ("math", "prozent-u1", "Prozentrechnen", 2, 1),
    ]


def test_a_unit_counts_under_the_subject_the_curriculum_files_it_under() -> None:
    """An Ask in a maths conversation naming a physics star counts in physics."""
    student = _student(records=(asked(2, "Kräfte", subject="math"),))

    assert _top(student) == [("physics", "kraefte-u1", "Kräfte", 1, 1)]


def test_names_are_the_reader_s() -> None:
    english = {
        **catalog(),
        "units": [
            {**unit, "title": "Percentages"} if unit["id"] == "prozent-u1" else unit
            for unit in catalog()["units"]
        ],
    }
    evidence = fake_evidence.evidence(
        "student-en", catalog=english, locale="en", now=NOW,
        attempts=[answer("c1", False, 5, unit="prozent-u1")],
    )

    [topic] = weak_topics.for_student(evidence, [asked(3, "Percentages")], locale="en")

    assert (topic.topic_id, topic.name, topic.score) == ("prozent-u1", "Percentages", 3)


def test_ties_go_to_the_newer_evidence_then_the_name() -> None:
    student = _student(
        records=(asked(3, "Zahlen"), asked(3, "addieren"), asked(1, "Winkel messen"))
    )

    assert [row[2] for row in _top(student)] == ["Winkel messen", "addieren", "Zahlen"]


def test_a_free_name_is_shown_as_its_newest_evidence_wrote_it() -> None:
    student = _student(records=(asked(1, "kopfrechnen"), asked(5, "Kopfrechnen")))

    assert _top(student) == [("math", "kopfrechnen", "kopfrechnen", 2, 2)]


def test_the_latest_evidence_moment_is_kept_as_stored() -> None:
    stored = "2026-11-26T09:30:00Z"
    student = _student(records=({**asked(0, "Kopfrechnen"), "created_at": stored},))

    [topic] = weak_topics.for_student(student.evidence(), student.asked, locale="de")

    assert topic.latest_evidence_at == stored
    assert datetime.fromisoformat(stored.replace("Z", "+00:00")) < NOW.astimezone(UTC)


# ── The readers ──────────────────────────────────────────────────────────────


def test_the_learning_profile_and_the_ask_hint_read_the_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    student = BY_KEY["mostly-corrected"]
    evidence = student.evidence()
    fake_evidence.install(monkeypatch, evidence)
    monkeypatch.setattr(
        adaptive_learning_service, "_question_rows", lambda _student_id: list(student.questions)
    )
    monkeypatch.setattr(
        adaptive_learning_service.asked_knowledge_repo,
        "list_for_student",
        lambda _student_id, **_k: list(student.asked),
    )
    expected = [
        learning_profile_service.weak_topic_response(topic)
        for topic in weak_topics.for_student(evidence, student.asked, locale="de")[:10]
    ]

    profile = learning_profile_service.build_learning_profile(
        student_id=evidence.student_id,
        questions=list(student.questions),
        evidence=evidence,
        asked=list(student.asked),
        locale="de",
    )

    assert profile["weakTopics"] == expected
    assert adaptive_learning_service.weak_topics(evidence.student_id, locale="de") == expected
    assert expected[0] == {
        "subject": "math",
        "topicId": "geometrie-u1",
        "label": "Flächen berechnen",
        "count": 3,
        "score": 6,
        "latestEvidenceAt": at(8),
        "evidenceQuestionIds": [],
    }
