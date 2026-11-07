"""One student's evidence, read once for one request (#214).

Every page that judges a student - the star map, the mastery behind it, the
stars an Ask answer may name, the practice context, the lesson pages, the
review page - asks the same few questions: which lessons are finished, which
exercises were answered right, what went wrong, when they last worked, which
stars are lit, what is due. Each used to read its own answer, so one star map
queried the same student partitions about seventeen times and some of those
reads stopped at DynamoDB's first 1 MB page without saying so.

`StudentEvidence` is the one value that answers them. It is lazy: a fact is
read the first time somebody asks for it, and the partition behind it is read
at most once however many facts come out of it. A page that needs three facts
pays for the partitions behind those three and no others.

Every read here follows every page. Where a fact is cut short, the cut is the
caller's and is named where it is made (`RECENT_MISTAKES`, the review page's
`limit`), never a page boundary that happened to fall somewhere.

The catalog and the lesson index (`Content`) are the half every student shares.
They are built once per value too, or handed in by a caller that keeps them
longer (`star_map_candidates`).

Tests build the value from facts (`tests/fakes/student_evidence.py`) rather
than standing up a table: the derivations below then run on rows made from
those facts, exactly as they run in production.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from stoa.db.repositories import practice_repo, review_repo
from stoa.services import (
    curriculum_service,
    knowledge_mastery_service,
    practice_projection_service,
    star_quiz_service,
)

logger = logging.getLogger(__name__)

#: The streak and "today" are counted in Zurich days.
ZURICH = ZoneInfo("Europe/Zurich")


# ── the half every student shares ──────────────────────────────────────────


def indexed_lessons() -> dict[str, list[dict[str, Any]]]:
    """The exercise index of every lesson row that carries one, in one read.

    The lesson rows carry it (`practice_repo.exercise_index`); a row written
    before that is read through its challenges instead (`Content.exercises`).
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for row in practice_repo.get_lessons():
        index = practice_repo.indexed_exercises(row)
        if index is not None:
            out[str(row.get("lesson_id") or "")] = index
    return out


def _active_exercise_entries(lesson_id: str) -> list[dict[str, Any]]:
    """A lesson's live exercises read through its challenges, for a row with no index."""
    return practice_repo.exercise_index(
        challenge
        for challenge in practice_repo.get_challenges(lesson_id)
        if practice_projection_service.content_state(challenge) != "archived"
    )


class Content:
    """The student catalog and its lesson index, each built at most once.

    Either may be handed in already built. A lesson the index does not carry
    is read through its challenges, once.
    """

    def __init__(
        self,
        *,
        locale: str = "de",
        catalog: Mapping[str, Any] | None = None,
        indexed: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    ) -> None:
        self.locale = locale
        self._catalog = catalog
        self._indexed = indexed
        self._read_through: dict[str, list[dict[str, Any]]] = {}

    @property
    def catalog(self) -> Mapping[str, Any]:
        if self._catalog is None:
            self._catalog = curriculum_service.list_catalog(locale=self.locale)
        return self._catalog

    @property
    def indexed(self) -> Mapping[str, Sequence[Mapping[str, Any]]]:
        if self._indexed is None:
            self._indexed = indexed_lessons()
        return self._indexed

    def rows(self, key: str) -> list[Mapping[str, Any]]:
        return [item for item in self.catalog.get(key) or () if isinstance(item, Mapping)]

    @property
    def lessons(self) -> list[Mapping[str, Any]]:
        return self.rows("lessons")

    @property
    def units(self) -> list[Mapping[str, Any]]:
        return self.rows("units")

    def exercises(self, lesson_id: str) -> list[Mapping[str, Any]]:
        """One lesson's live exercises: id, skills, knowledge point."""
        if lesson_id in self.indexed:
            return list(self.indexed[lesson_id])
        if lesson_id not in self._read_through:
            self._read_through[lesson_id] = _active_exercise_entries(lesson_id)
        return self._read_through[lesson_id]

    def exercise_ids(self, lesson_id: str) -> list[str]:
        return [str(entry["id"]) for entry in self.exercises(lesson_id)]

    def unit_of_lesson(self) -> dict[str, str]:
        return {
            str(lesson.get("id") or ""): str(lesson.get("unitId") or "")
            for lesson in self.lessons
        }


# ── where the rows come from ───────────────────────────────────────────────


class Source(Protocol):
    """The five student partitions the evidence is made of, each read whole."""

    def progress(self, student_id: str) -> list[dict[str, Any]]: ...
    def attempts(self, student_id: str) -> list[dict[str, Any]]: ...
    def activity(self, student_id: str) -> list[dict[str, Any]]: ...
    def star_quiz_outcomes(self, student_id: str) -> list[dict[str, Any]]: ...
    def review_cards(self, student_id: str) -> list[dict[str, Any]]: ...


class _Repositories:
    """The table, through the repositories; every page of every partition."""

    def progress(self, student_id: str) -> list[dict[str, Any]]:
        return practice_repo.get_progress(student_id)

    def attempts(self, student_id: str) -> list[dict[str, Any]]:
        return practice_repo.list_attempts(student_id)

    def activity(self, student_id: str) -> list[dict[str, Any]]:
        return practice_repo.list_activity(student_id)

    def star_quiz_outcomes(self, student_id: str) -> list[dict[str, Any]]:
        return practice_repo.list_star_quiz_outcomes(student_id)

    def review_cards(self, student_id: str) -> list[dict[str, Any]]:
        return review_repo.list_cards(student_id)


REPOSITORIES: Source = _Repositories()


# ── pure rules over rows ───────────────────────────────────────────────────


def _moment(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def completed_days(progress: Iterable[Mapping[str, Any]]) -> set[date]:
    """The Zurich calendar days on which a lesson was completed."""
    days: set[date] = set()
    for item in progress:
        if item.get("status") != "completed":
            continue
        moment = _moment(item.get("completed_at"))
        if moment is not None:
            days.add(moment.astimezone(ZURICH).date())
    return days


def _parse_day(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def study_streak(
    progress: Iterable[Mapping[str, Any]],
    *,
    today: date | None = None,
    study_days: Iterable[str] | None = None,
) -> int:
    """Count consecutive days of study ending today.

    A streak survives the day after the last one, because a student who has not
    practised yet today has not broken anything. It is only lost once a day
    passes with nothing done.

    Recorded study days carry any work that counts - clearing a review as much
    as finishing a lesson - and are joined with the lesson completions that
    were the only record before, so streaks earned then still stand.
    """
    days = completed_days(progress)
    for raw in study_days or ():
        parsed = _parse_day(raw)
        if parsed:
            days.add(parsed)
    if not days:
        return 0
    current = today or datetime.now(ZURICH).date()
    if current not in days:
        current -= timedelta(days=1)
        if current not in days:
            return 0
    streak = 0
    while current in days:
        streak += 1
        current -= timedelta(days=1)
    return streak


def stored_lit_facts(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, knowledge_mastery_service.LitFact]:
    """The lightings kept for a student, by unit."""
    facts: dict[str, knowledge_mastery_service.LitFact] = {}
    for row in rows:
        unit_id = str(row.get("unit_id") or "")
        if not unit_id:
            continue
        try:
            source = knowledge_mastery_service.LitSource(str(row.get("lit_at_source") or ""))
        except ValueError:
            # A row whose source cannot be read is treated as history. Guessing
            # `observed` here would celebrate a lighting nobody watched happen.
            source = knowledge_mastery_service.LitSource.BACKFILLED
        facts[unit_id] = knowledge_mastery_service.LitFact(
            unit_id=unit_id,
            lit_at=str(row.get("lit_at") or ""),
            source=source,
            acknowledged=bool(row.get("acknowledged_at")),
        )
    return facts


def _judged(attempt: Mapping[str, Any]) -> bool:
    """An answer the backend judged. A self-reported one was never checked (#93)."""
    return attempt.get("self_reported") is not True


def _attempt_exercise(attempt: Mapping[str, Any]) -> str:
    return str(attempt.get("challenge_id") or attempt.get("exercise_id") or "")


def _newest_first(attempt: Mapping[str, Any]) -> tuple[str, str]:
    return (str(attempt.get("created_at") or ""), str(attempt.get("attempt_id") or ""))


@dataclass(frozen=True, slots=True)
class Completion:
    """One finished lesson."""

    lesson_id: str
    unit_id: str
    subject_id: str
    completed_at: str


# ── the value ──────────────────────────────────────────────────────────────


class _Failed:
    """A read that failed, kept so asking again does not read again."""

    __slots__ = ("error",)

    def __init__(self, error: BaseException) -> None:
        self.error = error


class StudentEvidence:
    """What one student has done, each fact read the first time it is asked for.

    One value per request. Facts that come out of the same partition share one
    read of it; a read that fails is not retried within the value, and the
    facts that degrade rather than fail (study days, star quiz cooldowns) say
    so where they are defined.
    """

    def __init__(
        self,
        student_id: str,
        *,
        content: Content,
        source: Source = REPOSITORIES,
        now: datetime | None = None,
    ) -> None:
        self.student_id = student_id
        self.content = content
        self.now = (now or datetime.now(UTC)).astimezone(UTC)
        self.source = source
        self._partitions: dict[str, object] = {}
        self._derived: dict[str, object] = {}

    # -- reading ----------------------------------------------------------

    def _rows(self, partition: str) -> list[dict[str, Any]]:
        """Every row of one partition, read on first use and then kept."""
        if partition not in self._partitions:
            reader: Callable[[str], list[dict[str, Any]]] = getattr(self.source, partition)
            try:
                self._partitions[partition] = [
                    dict(row) for row in reader(self.student_id) if isinstance(row, Mapping)
                ]
            except Exception as error:  # noqa: BLE001
                self._partitions[partition] = _Failed(error)
        kept = self._partitions[partition]
        if isinstance(kept, _Failed):
            raise kept.error
        return kept  # type: ignore[return-value]

    def _once(self, name: str, build: Callable[[], Any]) -> Any:
        if name not in self._derived:
            self._derived[name] = build()
        return self._derived[name]

    # -- lessons (PROGRESS#) ------------------------------------------------

    @property
    def completions(self) -> tuple[Completion, ...]:
        """Every finished lesson, oldest first."""

        def build() -> tuple[Completion, ...]:
            done = [
                Completion(
                    lesson_id=str(row.get("lesson_id") or ""),
                    unit_id=str(row.get("unit_id") or ""),
                    subject_id=str(row.get("subject_id") or ""),
                    completed_at=str(row.get("completed_at") or ""),
                )
                for row in self._rows("progress")
                if row.get("status") == "completed" and row.get("lesson_id")
            ]
            return tuple(sorted(done, key=lambda item: (item.completed_at, item.lesson_id)))

        return self._once("completions", build)

    @property
    def completed_lesson_ids(self) -> frozenset[str]:
        return self._once(
            "completed_lesson_ids",
            lambda: frozenset(item.lesson_id for item in self.completions),
        )

    def completed_lesson_ids_in(self, subject_id: str | None) -> frozenset[str]:
        """The finished lessons of one subject, under any spelling of it; all without one."""
        if not subject_id:
            return self.completed_lesson_ids
        return frozenset(
            item.lesson_id
            for item in self.completions
            if practice_repo.same_subject(item.subject_id, subject_id)
        )

    def lessons_completed_on(self, day: date) -> int:
        """How many lessons were finished on this Zurich day."""
        return sum(
            1
            for item in self.completions
            if (moment := _moment(item.completed_at)) is not None
            and moment.astimezone(ZURICH).date() == day
        )

    @property
    def subjects_taken(self) -> frozenset[str]:
        """The subjects this student has progress in, in canonical form.

        Progress rows copy their lesson's subject, `mathematics`; the catalog
        says `math`. Compared raw, a student taking maths was told they do not.
        """
        return self._once(
            "subjects_taken",
            lambda: frozenset(
                practice_repo.normal_subject_id(row.get("subject_id"))
                for row in self._rows("progress")
                if row.get("subject_id")
            ),
        )

    # -- answers (ATTEMPTS#) -------------------------------------------------

    @property
    def answered_right(self) -> frozenset[str]:
        """Every exercise this student has answered right at least once, judged.

        From every page: a truncated read puts out stars the student earned,
        and does so more the more they practise.
        """
        return self._once(
            "answered_right",
            lambda: frozenset(
                exercise
                for attempt in self._rows("attempts")
                if attempt.get("correct") is True
                and _judged(attempt)
                and (exercise := _attempt_exercise(attempt))
            ),
        )

    @property
    def mistakes(self) -> tuple[dict[str, Any], ...]:
        """Every wrong answer, newest first.

        All of them, self-reported ones too, as the mistake pages always showed
        them; a caller that shows a few takes the first few and says how many.
        """
        return self._once(
            "mistakes",
            lambda: tuple(
                sorted(
                    (attempt for attempt in self._rows("attempts") if not attempt.get("correct")),
                    key=_newest_first,
                    reverse=True,
                )
            ),
        )

    def mistakes_by_topic(self, subject_id: str | None = None) -> Counter[str]:
        """Wrong answers per topic, of one subject or of all."""
        return Counter(
            str(item.get("topic_id"))
            for item in self.mistakes
            if item.get("topic_id")
            and (not subject_id or practice_repo.same_subject(item.get("subject_id", ""), subject_id))
        )

    @property
    def last_activity_by_unit(self) -> dict[str, str]:
        """When the student last did something in each knowledge point (#164).

        A judged answer, right or wrong, or a finished lesson.
        """

        def build() -> dict[str, str]:
            latest: dict[str, str] = {}

            def note(unit_id: object, moment: object) -> None:
                if unit_id and moment and str(moment) > latest.get(str(unit_id), ""):
                    latest[str(unit_id)] = str(moment)

            for attempt in self._rows("attempts"):
                if _judged(attempt):
                    note(attempt.get("unit_id"), attempt.get("created_at"))
            for item in self.completions:
                note(item.unit_id, item.completed_at)
            return latest

        return self._once("last_activity_by_unit", build)

    # -- days and lightings (ACTIVITY#) ------------------------------------

    @property
    def study_days(self) -> frozenset[str]:
        """Every Zurich day this student did some work.

        Degrades to none if the partition cannot be read: the streak then
        counts lesson completions, which is what it was before, rather than
        failing the page it is on.
        """

        def build() -> frozenset[str]:
            try:
                rows = self._rows("activity")
            except Exception:  # noqa: BLE001
                logger.warning("Study days unavailable; streak falls back to lessons")
                return frozenset()
            return frozenset(
                str(row.get("day"))
                for row in rows
                if str(row.get("SK") or "").startswith(practice_repo.STUDY_DAY_PREFIX)
                and row.get("day")
            )

        return self._once("study_days", build)

    def _completed_rows(self) -> list[dict[str, Any]]:
        return [
            {"status": "completed", "completed_at": item.completed_at} for item in self.completions
        ]

    @property
    def today(self) -> date:
        return self.now.astimezone(ZURICH).date()

    @property
    def study_streak(self) -> int:
        return self._once(
            "study_streak",
            lambda: study_streak(
                self._completed_rows(), today=self.today, study_days=self.study_days
            ),
        )

    @property
    def practised_today(self) -> bool:
        return self.today in completed_days(self._completed_rows()) or (
            self.today.isoformat() in self.study_days
        )

    def _lit_rows(self) -> list[dict[str, Any]]:
        return [
            row
            for row in self._rows("activity")
            if str(row.get("SK") or "").startswith(practice_repo.LIT_SK_PREFIX)
        ]

    @property
    def lit_ledger_open(self) -> bool:
        """Whether lightings are recorded as they happen yet (#71)."""
        return any(row.get("entity_type") == "lit_ledger" for row in self._lit_rows())

    @property
    def lit_facts(self) -> dict[str, knowledge_mastery_service.LitFact]:
        """The lightings already kept for this student, by unit."""
        return self._once(
            "lit_facts",
            lambda: stored_lit_facts(
                row for row in self._lit_rows() if row.get("entity_type") == "lit_unit"
            ),
        )

    # -- star quizzes (QUIZ#, the outcome rows) -----------------------------

    @property
    def star_quiz_passed(self) -> frozenset[str]:
        """Every star this student lit by passing its quiz (#165)."""
        return self._once(
            "star_quiz_passed",
            lambda: frozenset(
                str(row.get("unit_id"))
                for row in self._rows("star_quiz_outcomes")
                if row.get("entity_type") == practice_repo.STAR_QUIZ_PASS_ENTITY
                and row.get("unit_id")
            ),
        )

    @property
    def star_quiz_retry_at(self) -> dict[str, str]:
        """Per star, when a lost star quiz can be taken again (#165).

        Degrades to none if it cannot be read: the quiz route refuses a star
        still cooling down whatever a page drew.
        """

        def build() -> dict[str, str]:
            try:
                rows = self._rows("star_quiz_outcomes")
            except Exception:  # noqa: BLE001
                logger.warning("Star quiz cooldowns unavailable", exc_info=True)
                return {}
            cooldowns = [
                row
                for row in rows
                if str(row.get("SK") or "").startswith(practice_repo.STAR_QUIZ_COOLDOWN_PREFIX)
            ]
            return star_quiz_service.retry_times(cooldowns, self.now)

        return self._once("star_quiz_retry_at", build)

    # -- review (REVIEW#) ----------------------------------------------------

    @property
    def due_cards(self) -> tuple[dict[str, Any], ...]:
        """Every review card whose time has come, soonest first. Every page, no ceiling."""

        def build() -> tuple[dict[str, Any], ...]:
            moment = self.now.isoformat()
            due = [card for card in self._rows("review_cards") if str(card.get("due_at", "")) <= moment]
            due.sort(key=lambda card: str(card.get("due_at", "")))
            return tuple(due)

        return self._once("due_cards", build)

    def card_unit(self, card: Mapping[str, Any]) -> str:
        """The one rule for where a card counts: the unit of its own lesson.

        A card without a lesson, or whose lesson is outside the active
        curriculum, belongs to no unit and is counted nowhere.
        """
        lesson_id = str(card.get("lesson_id") or "")
        unit_of_lesson = self._once("unit_of_lesson", self.content.unit_of_lesson)
        return unit_of_lesson.get(lesson_id, "") if lesson_id else ""

    def due_cards_in(self, unit_id: str) -> tuple[dict[str, Any], ...]:
        return tuple(card for card in self.due_cards if self.card_unit(card) == unit_id)

    @property
    def review_due_by_unit(self) -> dict[str, int]:
        """How many cards are due in each unit, by `card_unit`."""

        def build() -> dict[str, int]:
            counts: dict[str, int] = {}
            for card in self.due_cards:
                unit_id = self.card_unit(card)
                if unit_id:
                    counts[unit_id] = counts.get(unit_id, 0) + 1
            return counts

        return self._once("review_due_by_unit", build)


def for_student(
    student_id: str,
    *,
    locale: str = "de",
    content: Content | None = None,
    now: datetime | None = None,
) -> StudentEvidence:
    """The evidence of one student for one request. Reads nothing yet."""
    return StudentEvidence(
        student_id,
        content=content if content is not None else Content(locale=locale),
        now=now,
    )
