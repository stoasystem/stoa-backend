"""Which topics a student is weak in: one projection, one rule (#632, #673).

Every reader of a student's weak topics - the learning profile, adaptive
memory, the hint an Ask answer gets and the practice recommendations - asks
`for_student` and nothing else. The rule lives here alone:

- **The same topic** is what the curriculum says it is
  (`curriculum_names.resolve`): the unit, or the topic where no single unit is
  meant, whichever spelling a row used - the unit or lesson id an answer
  carries first, then its topic id, a title in any language or an old slug.
  A name the curriculum does not know, one an answer wrote freely, is one
  topic per subject and name compared without case, shown as written.
- **A corrected mistake does not count.** Once an exercise has been answered
  right, every earlier wrong answer to it is put right; any later right answer
  counts, self-reported ones too, however long ago. A mistake on an exercise
  never answered right since still counts.
- **Score**: each mistake that still counts weighs `MISTAKE_POINTS`, each
  knowledge point an Ask answer named `ASKED_POINTS` (a question row from the
  retired flow counts as an Ask record). `count` is how many of those pieces
  of evidence there are.
- **Window**: evidence from the last `WINDOW` before the evidence's `now`,
  unless the reader passes its own `since` / `until`. Evidence whose moment
  cannot be read falls in no window.

Topics come out heaviest first, then most recent, then by name. Names are in
the reader's language, as `curriculum_names` gives them; this module names
nothing itself.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from stoa.services import curriculum_names, curriculum_service, student_evidence

#: What one wrong answer that still counts weighs.
MISTAKE_POINTS = 2
#: What one knowledge point an Ask answer named weighs.
ASKED_POINTS = 1
#: How far back evidence counts unless a reader says otherwise.
WINDOW = timedelta(days=90)


@dataclass(frozen=True, slots=True)
class WeakTopic:
    """One weak topic, as every reader is given it."""

    #: The canonical subject id (`math`, `physics`, ...).
    subject: str
    #: The unit or topic id the curriculum knows it by, or the free name compared without case.
    topic_id: str
    #: Its name in the reader's language, or the free name as written.
    name: str
    score: int
    #: Mistakes that still count, plus knowledge points named.
    count: int
    #: When the newest piece of evidence was recorded, as it was stored.
    latest_evidence_at: str
    #: The retired flow's questions behind it, if any.
    evidence_question_ids: tuple[str, ...] = ()


def for_student(
    evidence: student_evidence.StudentEvidence,
    asked: Iterable[Mapping[str, Any]],
    *,
    locale: str,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[WeakTopic]:
    """The student's weak topics in `[since, until)`, heaviest first.

    `evidence` gives the wrong answers, every answer (for corrections) and the
    catalog the topics are resolved against; `asked` are the student's Ask
    records (`asked_knowledge_repo.list_for_student`), and any question rows of
    the retired flow, which count the same. `since` defaults to `WINDOW` before
    `evidence.now`; `until` to no end.
    """
    start = since if since is not None else evidence.now - WINDOW
    tally = _Tally(
        curriculum_names.for_reader(
            locale, catalog=evidence.content.catalog, rows=evidence.content.named_rows
        ),
        _subjects_of(evidence.content.catalog),
    )
    corrected = evidence.last_answered_right

    for mistake in evidence.mistakes:
        moment = _moment(mistake.get("created_at"))
        if not _within(moment, start, until):
            continue
        exercise = str(mistake.get("challenge_id") or mistake.get("exercise_id") or "")
        right_at = corrected.get(exercise) if exercise else None
        if right_at is not None and moment is not None and right_at > moment:
            continue
        tally.add(
            subject=mistake.get("subject_id") or mistake.get("subject"),
            spelling=mistake.get("topic_id"),
            unit_id=mistake.get("unit_id"),
            lesson_id=mistake.get("lesson_id"),
            points=MISTAKE_POINTS,
            at=str(mistake.get("created_at") or ""),
            moment=moment,
        )

    for record in asked:
        for seed in _named(record):
            moment = _moment(seed["at"])
            if not _within(moment, start, until):
                continue
            tally.add(
                subject=seed["subject"],
                spelling=seed["spelling"],
                label=seed["label"],
                points=ASKED_POINTS,
                at=seed["at"],
                moment=moment,
                question_ids=seed["question_ids"],
            )

    return tally.ranked()


@dataclass(slots=True)
class _Topic:
    subject: str
    topic_id: str
    name: str
    score: int = 0
    count: int = 0
    latest: datetime | None = None
    latest_at: str = ""
    question_ids: set[str] = field(default_factory=set)


class _Tally:
    def __init__(self, names: curriculum_names.Names, subjects: Mapping[str, object]) -> None:
        self._names = names
        self._subjects = subjects
        self._topics: dict[tuple[str, str], _Topic] = {}

    def add(
        self,
        *,
        subject: object,
        spelling: object,
        points: int,
        at: str,
        moment: datetime | None,
        label: object = None,
        unit_id: object = None,
        lesson_id: object = None,
        question_ids: Iterable[str] = (),
    ) -> None:
        written = _written(label) or _written(spelling)
        content_id = self._names.resolve(spelling, label, unit_id=unit_id, lesson_id=lesson_id)
        if content_id is not None:
            subject_id = curriculum_service.counted_subject(self._subjects.get(content_id) or subject)
            key = (subject_id, content_id)
            name = self._names.name(content_id) or written or content_id
        elif written:
            subject_id = curriculum_service.counted_subject(subject)
            key = (subject_id, written.casefold())
            name = written
        else:
            return
        topic = self._topics.setdefault(key, _Topic(subject_id, key[1], name))
        topic.score += points
        topic.count += 1
        topic.question_ids.update(question_ids)
        if moment is not None and (topic.latest is None or moment > topic.latest):
            topic.latest, topic.latest_at = moment, at
            if content_id is None:
                # A free name is shown as its newest evidence wrote it.
                topic.name = name

    def ranked(self) -> list[WeakTopic]:
        never = datetime.min.replace(tzinfo=UTC)
        ordered = sorted(
            self._topics.values(),
            key=lambda topic: (
                -topic.score,
                -(topic.latest or never).timestamp(),
                topic.name.casefold(),
                topic.subject,
                topic.topic_id,
            ),
        )
        return [
            WeakTopic(
                subject=topic.subject,
                topic_id=topic.topic_id,
                name=topic.name,
                score=topic.score,
                count=topic.count,
                latest_evidence_at=topic.latest_at,
                evidence_question_ids=tuple(sorted(topic.question_ids)),
            )
            for topic in ordered
        ]


def _named(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The knowledge points one Ask record (or retired question row) named.

    A question row of the retired flow may carry `topic_seeds`, each with its
    own id, label and moment; it then counts those and not its plain names.
    """
    subject = record.get("subject")
    created_at = str(record.get("created_at") or "")
    question_id = record.get("question_id")
    own = [str(question_id)] if question_id else []
    seeds = record.get("topic_seeds")
    if isinstance(seeds, list) and seeds:
        return [
            {
                "subject": seed.get("subject") or subject,
                "spelling": seed.get("topic_id"),
                "label": seed.get("label"),
                "at": str(seed.get("last_seen_at") or created_at),
                "question_ids": [
                    str(item) for item in seed.get("evidence_question_ids") or own if item
                ],
            }
            for seed in seeds
            if isinstance(seed, Mapping)
        ]
    return [
        {"subject": subject, "spelling": point, "label": point, "at": created_at, "question_ids": own}
        for point in record.get("knowledge_points") or ()
        if isinstance(point, str) and point.strip()
    ]


def _subjects_of(catalog: Mapping[str, Any]) -> dict[str, object]:
    """The subject each unit and topic of the catalog is filed under; a unit's first."""
    subjects: dict[str, object] = {}
    for key in ("units", "topics"):
        for row in catalog.get(key) or ():
            if isinstance(row, Mapping) and row.get("id"):
                subjects.setdefault(str(row["id"]), row.get("subjectId"))
    return subjects


def _written(value: object) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _moment(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _within(moment: datetime | None, start: datetime, until: datetime | None) -> bool:
    return moment is not None and moment >= start and (until is None or moment < until)
