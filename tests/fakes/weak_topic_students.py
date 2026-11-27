"""Five made-up students whose weak topics are locked in tests (#673).

There are no real students in production yet, so the new weak-topic rule is
checked on typical students instead: one who only asks, one who corrects most
of their mistakes, one whose evidence spells one unit several ways, one whose
evidence is mostly older than 90 days, and one whose Ask answers name topics
the curriculum does not know. `tests/test_weak_topics.py` locks each one's
top ten; the PR for #673 put them beside what main's learning profile made of
the same rows.

Each student is rows as stored - wrong and right answers, Ask records, the
retired flow's question rows - read on `NOW` against one small catalog.
Nothing here imports `weak_topics`, so the same rows can be given to the
algorithm it replaced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from fakes import student_evidence as fake_evidence
from stoa.services import student_evidence

#: When every student's weak topics are read.
NOW = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)

_UNITS = {
    # unit id: (subject, topic id, title)
    "brueche-u1": ("math", "bruchrechnen", "Brüche verstehen und kürzen"),
    "brueche-u2": ("math", "bruchrechnen", "Brüche rechnen"),
    "gleichungen-u1": ("math", "gleichungen", "Einfache Gleichungen lösen"),
    "geometrie-u1": ("math", "geometrie", "Flächen berechnen"),
    "geometrie-u2": ("math", "geometrie", "Winkel messen"),
    "prozent-u1": ("math", "prozent", "Prozentrechnen"),
    "kraefte-u1": ("physics", "mechanik", "Kräfte"),
    "bewegung-u1": ("physics", "mechanik", "Bewegung"),
    "energie-u1": ("physics", "energie", "Energieformen"),
}
_TOPICS = {
    "bruchrechnen": ("math", "Bruchrechnen"),
    "gleichungen": ("math", "Gleichungen"),
    "geometrie": ("math", "Geometrie"),
    "prozent": ("math", "Prozent"),
    "mechanik": ("physics", "Mechanik"),
    "energie": ("physics", "Energie"),
}
#: lesson id: unit id
_LESSONS = {
    "brueche-l1": "brueche-u1",
    "brueche-l3": "brueche-u2",
    "gleichungen-l1": "gleichungen-u1",
    "geometrie-l1": "geometrie-u1",
    "geometrie-l4": "geometrie-u2",
    "prozent-l1": "prozent-u1",
    "kraefte-l1": "kraefte-u1",
    "bewegung-l1": "bewegung-u1",
    "energie-l1": "energie-u1",
}


def catalog() -> dict[str, Any]:
    """The student catalog, in German, as `curriculum_service.list_catalog` projects it."""
    return {
        "subjects": [{"id": "math", "order": 1}, {"id": "physics", "order": 2}],
        "topics": [
            {"id": topic_id, "subjectId": subject, "title": title, "order": order}
            for order, (topic_id, (subject, title)) in enumerate(_TOPICS.items(), start=1)
        ],
        "units": [
            {"id": unit_id, "subjectId": subject, "topicId": topic_id, "title": title, "order": order}
            for order, (unit_id, (subject, topic_id, title)) in enumerate(_UNITS.items(), start=1)
        ],
        "lessons": [
            {
                "id": lesson_id,
                "unitId": unit_id,
                "topicId": _UNITS[unit_id][1],
                "subjectId": _UNITS[unit_id][0],
            }
            for lesson_id, unit_id in _LESSONS.items()
        ],
    }


def at(days_ago: float) -> str:
    """The stored moment `days_ago` days before `NOW`."""
    return (NOW - timedelta(days=days_ago)).isoformat()


_STORED_SUBJECT = {"math": "mathematics", "physics": "physics"}


def answer(
    challenge: str,
    correct: bool,
    days_ago: float,
    *,
    unit: str | None = None,
    lesson: str | None = None,
    topic: str | None = None,
    self_reported: bool = False,
) -> dict[str, Any]:
    """One answer row as practice stores it.

    A current row names its unit, lesson and topic; an older one only some of
    them, as `lesson` / `topic` alone say. `unit` fills in the lesson and topic
    the catalog files it under, unless they are given.
    """
    subject = "math"
    if unit is not None:
        subject, unit_topic, _title = _UNITS[unit]
        topic = topic or unit_topic
        lesson = lesson or next(lid for lid, uid in _LESSONS.items() if uid == unit)
    elif lesson is not None:
        subject = _UNITS[_LESSONS[lesson]][0]
    row: dict[str, Any] = {
        "attempt_id": f"{challenge}-{'right' if correct else 'wrong'}-{days_ago}",
        "challenge_id": challenge,
        "subject_id": _STORED_SUBJECT[subject],
        "correct": correct,
        "answer": "x",
        "created_at": at(days_ago),
    }
    for key, value in (("unit_id", unit), ("lesson_id", lesson), ("topic_id", topic)):
        if value is not None:
            row[key] = value
    if self_reported:
        row["self_reported"] = True
    return row


def asked(days_ago: float, *names: str, subject: str = "math") -> dict[str, Any]:
    """One Ask record (`asked_knowledge_repo`) naming `names`."""
    return {
        "entity_type": "asked_knowledge_points",
        "subject": subject,
        "knowledge_points": list(names),
        "unit_ids": [],
        "created_at": at(days_ago),
    }


def question(question_id: str, days_ago: float, **fields: Any) -> dict[str, Any]:
    """One question row of the retired 「交一道题」 flow."""
    return {
        "question_id": question_id,
        "subject": "math",
        "status": "ai_answered",
        "created_at": at(days_ago),
        **fields,
    }


@dataclass(frozen=True)
class Student:
    key: str
    #: What the student is like, in the words of #673.
    about: str
    answers: tuple[dict[str, Any], ...] = ()
    asked: tuple[dict[str, Any], ...] = ()
    questions: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def evidence(self) -> student_evidence.StudentEvidence:
        return fake_evidence.evidence(
            f"student-{self.key}", catalog=catalog(), attempts=self.answers, now=NOW
        )


def _ask_only() -> Student:
    return Student(
        "ask-only",
        "只用 Ask、不做练习",
        asked=(
            asked(2, "Brüche rechnen", "Kürzen mit dem ggT"),
            asked(5, "Brüche rechnen"),
            asked(9, "Einfache Gleichungen lösen", "Brüche rechnen"),
            asked(14, "Prozentrechnen"),
            asked(20, "Einfache Gleichungen lösen"),
            asked(30, "Winkel messen", "Kürzen mit dem ggT"),
            asked(45, "Prozentrechnen"),
            asked(61, "Flächen berechnen"),
            asked(70, "Kopfrechnen"),
            asked(80, "Brüche verstehen und kürzen"),
            asked(3, "Kräfte", subject="physics"),
            asked(40, "Energieformen", "Kräfte", subject="physics"),
        ),
    )


def _mostly_corrected() -> Student:
    answers: list[dict[str, Any]] = []
    # Fractions: six exercises, each wrong twice, every one put right since.
    for n in range(1, 7):
        answers += [
            answer(f"b{n}", False, 40, unit="brueche-u2"),
            answer(f"b{n}", False, 38, unit="brueche-u2"),
            answer(f"b{n}", True, 35, unit="brueche-u2"),
        ]
    # Equations: four wrong, three put right; the fourth never.
    for n in range(1, 5):
        answers.append(answer(f"g{n}", False, 20, unit="gleichungen-u1"))
    answers += [answer(f"g{n}", True, 18, unit="gleichungen-u1") for n in range(1, 4)]
    # Areas: one exercise wrong three times and never right; one put right by
    # an answer the student reported themselves.
    answers += [answer("f1", False, days, unit="geometrie-u1") for days in (10, 9, 8)]
    answers += [
        answer("f2", False, 7, unit="geometrie-u1"),
        answer("f2", True, 6, unit="geometrie-u1", self_reported=True),
    ]
    # Percentages: one right long before it went wrong, which puts nothing
    # right; one wrong and right again an hour later.
    answers += [
        answer("p1", True, 50, unit="prozent-u1"),
        answer("p1", False, 5, unit="prozent-u1"),
        answer("p2", False, 4, unit="prozent-u1"),
        answer("p2", True, 4 - 1 / 24, unit="prozent-u1"),
    ]
    return Student(
        "mostly-corrected",
        "错题很多但大部分已订正",
        answers=tuple(answers),
        asked=(asked(3, "Brüche rechnen"), asked(12, "Einfache Gleichungen lösen")),
    )


def _one_unit_many_spellings() -> Student:
    return Student(
        "many-spellings",
        "同一个单元有好几种写法（单元 id、课时 id、旧 slug、德语标题）",
        answers=(
            # The unit id a current answer carries.
            answer("m1", False, 10, unit="brueche-u2"),
            # An older one names only its lesson and topic.
            answer("m2", False, 9, lesson="brueche-l3", topic="bruchrechnen"),
            # The slug the old code made of the unit's title, dropping the ü.
            answer("m3", False, 8, topic="br-che-rechnen"),
            # The bare topic id: a topic with two units is not one of them.
            answer("m4", False, 7, topic="bruchrechnen"),
        ),
        asked=(
            asked(6, "Brüche rechnen"),
            asked(5, "BRÜCHE RECHNEN"),
            asked(2, "Einfache Gleichungen lösen"),
        ),
        questions=(
            question(
                "q-mia-1",
                4,
                topic_seeds=[
                    {
                        "subject": "math",
                        "topic_id": "brueche-u2",
                        "label": "Brüche rechnen",
                        "evidence_question_ids": ["q-mia-1"],
                        "last_seen_at": at(4),
                    }
                ],
            ),
            question(
                "q-mia-2",
                3,
                topic_seeds=[
                    {"subject": "math", "topic_id": "br-che-rechnen", "label": "br-che-rechnen"}
                ],
            ),
        ),
    )


def _old_evidence() -> Student:
    answers = [answer(f"w{n}", False, 100 + 10 * n, unit="geometrie-u2") for n in range(1, 9)]
    answers += [
        answer("e1", False, 10, unit="prozent-u1"),
        answer("e2", False, 11, unit="prozent-u1"),
    ]
    return Student(
        "old-evidence",
        "有超过 90 天的证据",
        answers=tuple(answers),
        asked=(
            *(asked(150 + n, "Winkel messen") for n in range(4)),
            *(asked(95 + n, "Energieformen", subject="physics") for n in range(3)),
            asked(3, "Prozentrechnen"),
            asked(20, "Einfache Gleichungen lösen"),
            # Just inside the 90 days, and just outside.
            asked(89, "Kräfte", subject="physics"),
            asked(91, "Bewegung", subject="physics"),
        ),
        questions=(question("q-elias-1", 200, knowledge_points=["Winkel messen"]),),
    )


def _free_text() -> Student:
    return Student(
        "free-text",
        "AI 写了目录里没有的自由文本主题（含变音字母）",
        asked=(
            asked(1, "Brüche", "Kopfrechnen"),
            asked(3, "brüche"),
            asked(4, " BRÜCHE "),
            asked(6, "Größen umrechnen", "分数"),
            asked(8, "Grössen umrechnen"),
            asked(10, "分数"),
            asked(12, "Brüche rechnen"),
            asked(15, "Kopfrechnen"),
            asked(7, "Hebelgesetz"),
            asked(5, "Hebelgesetz", subject="physics"),
        ),
    )


STUDENTS: tuple[Student, ...] = (
    _ask_only(),
    _mostly_corrected(),
    _one_unit_many_spellings(),
    _old_evidence(),
    _free_text(),
)
