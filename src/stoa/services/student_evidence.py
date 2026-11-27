"""One student's evidence, read once for one request (#214).

Every page that judges a student - the star map, the mastery behind it, the
stars an Ask answer may name, the practice context, the lesson pages, the
review page, and around them the student's history, the parent pages, the
weekly report and the adaptive memory - asks the same few questions: which
lessons are finished, which exercises were answered right, what went wrong,
when they last worked, which stars are lit, what is due. Each used to read its
own answer, so one star map
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
from types import MappingProxyType
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from stoa.db.repositories import practice_repo, review_repo
from stoa.services import (
    curriculum_cache,
    curriculum_service,
    error_causes,
    knowledge_mastery_service,
    practice_projection_service,
)

logger = logging.getLogger(__name__)

#: The streak and "today" are counted in Zurich days.
ZURICH = ZoneInfo("Europe/Zurich")


def _cooling_down(retry: str, now: datetime) -> bool:
    """Whether a star lost at some point still cannot be taken at `now`."""
    if not retry:
        return False
    try:
        moment = datetime.fromisoformat(retry)
    except ValueError:
        return False
    return now < moment


def _retry_times(rows: Sequence[Mapping[str, object]], now: datetime) -> dict[str, str]:
    """Per unit, when a lost star can be taken again; only the ones not yet open."""
    return {
        str(row.get("unit_id") or ""): str(row.get("retry_at") or "")
        for row in rows
        if row.get("unit_id") and _cooling_down(str(row.get("retry_at") or ""), now)
    }


# ── the half every student shares ──────────────────────────────────────────


def indexed_lessons(
    lesson_rows: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """The exercise index of every lesson row that carries one, in one read.

    The lesson rows carry it (`practice_repo.exercise_index`); a row written
    before that is read through its challenges instead (`Content.exercises`).
    `lesson_rows` are every lesson row, when they have been read already.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for row in practice_repo.get_lessons() if lesson_rows is None else lesson_rows:
        index = practice_repo.indexed_exercises(row)
        if index is not None:
            out[str(row.get("lesson_id") or "")] = index
    return out


def _active_exercise_entries(
    lesson_id: str, challenges: Sequence[Mapping[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """A lesson's live exercises read through its challenges, for a row with no index."""
    return practice_repo.exercise_index(
        challenge
        for challenge in (practice_repo.get_challenges(lesson_id) if challenges is None else challenges)
        if practice_projection_service.content_state(challenge) != "archived"
    )


class Content:
    """The student catalog and its lesson index, each built at most once.

    Either may be handed in already built. Both come from the kept student
    curriculum (`curriculum_cache`), asked for once for the two. A lesson the
    index does not carry is read through its challenges, once - kept with the
    curriculum when it was read with it.
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
        self._snapshot: curriculum_cache.Snapshot | None = None

    def _kept(self) -> curriculum_cache.Snapshot:
        if self._snapshot is None:
            self._snapshot = curriculum_cache.current()
        return self._snapshot

    def built(self) -> Content:
        """This content with the catalog and the lesson index both built now."""
        self.catalog  # noqa: B018 - built on first use
        self.indexed  # noqa: B018
        return self

    @property
    def catalog(self) -> Mapping[str, Any]:
        if self._catalog is None:
            self._catalog = curriculum_service.list_catalog(
                locale=self.locale, snapshot=self._kept()
            )
        return self._catalog

    @property
    def indexed(self) -> Mapping[str, Sequence[Mapping[str, Any]]]:
        if self._indexed is None:
            kept = self._kept()
            self._indexed = MappingProxyType(
                kept.once(("indexed",), lambda: indexed_lessons(kept.lessons))
            )
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
            kept = (
                self._snapshot.lesson_challenges(lesson_id) if self._snapshot is not None else None
            )
            self._read_through[lesson_id] = _active_exercise_entries(lesson_id, kept)
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
    """The five student partitions the evidence is made of, each read whole.

    And the lighter reads of two of them a page can ask for instead: the
    answer rollups and the answers' facts (`ATTEMPTS#`), the cards' due times
    (`REVIEW#`).
    """

    def progress(self, student_id: str) -> list[dict[str, Any]]: ...
    def attempts(self, student_id: str) -> list[dict[str, Any]]: ...
    def activity(self, student_id: str) -> list[dict[str, Any]]: ...
    def star_quiz_outcomes(self, student_id: str) -> list[dict[str, Any]]: ...
    def review_cards(self, student_id: str) -> list[dict[str, Any]]: ...
    def attempt_rollups(self, student_id: str) -> list[dict[str, Any]]: ...
    def attempt_facts(self, student_id: str) -> list[dict[str, Any]]: ...
    def review_due(self, student_id: str) -> list[dict[str, Any]]: ...
    def mark_attempt_rollups_complete(self, student_id: str) -> None: ...


class _Repositories:
    """The table, through the repositories; every page of every partition.

    Read on a worker thread (`StudentEvidence.read_all`), each through that
    thread's own table.
    """

    def progress(self, student_id: str) -> list[dict[str, Any]]:
        return curriculum_cache.with_table(practice_repo.get_progress, student_id)

    def attempts(self, student_id: str) -> list[dict[str, Any]]:
        return curriculum_cache.with_table(practice_repo.list_attempts, student_id)

    def activity(self, student_id: str) -> list[dict[str, Any]]:
        return curriculum_cache.with_table(practice_repo.list_activity, student_id)

    def star_quiz_outcomes(self, student_id: str) -> list[dict[str, Any]]:
        return curriculum_cache.with_table(practice_repo.list_star_quiz_outcomes, student_id)

    def review_cards(self, student_id: str) -> list[dict[str, Any]]:
        return curriculum_cache.with_table(review_repo.list_cards, student_id)

    def attempt_rollups(self, student_id: str) -> list[dict[str, Any]]:
        return curriculum_cache.with_table(practice_repo.list_attempt_rollups, student_id)

    def attempt_facts(self, student_id: str) -> list[dict[str, Any]]:
        return curriculum_cache.with_table(practice_repo.list_attempt_facts, student_id)

    def review_due(self, student_id: str) -> list[dict[str, Any]]:
        return curriculum_cache.with_table(review_repo.list_card_dues, student_id)

    def mark_attempt_rollups_complete(self, student_id: str) -> None:
        practice_repo.mark_attempt_rollups_complete(student_id)


#: Every partition a `Source` reads.
PARTITIONS = ("progress", "attempts", "activity", "star_quiz_outcomes", "review_cards")


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


@dataclass(frozen=True, slots=True)
class AttemptRollup:
    """What one rollup row holds: a lesson's judged answers in one knowledge point (card 135)."""

    right_alone: frozenset[str] = frozenset()
    right_asked: frozenset[str] = frozenset()
    last_judged_at: str = ""


def _rollup_place(row: Mapping[str, Any]) -> tuple[str, str]:
    return (str(row.get("lesson_id") or ""), str(row.get("unit_id") or ""))


def expected_attempt_rollups(
    attempts: Iterable[Mapping[str, Any]],
) -> dict[tuple[str, str], AttemptRollup]:
    """The rollups these answers make, by (lesson, knowledge point).

    The rules of `answered_right`, `right_answers_by_unit` and
    `last_activity_by_unit`: judged answers only, right ones by exercise,
    split by whether AI was asked first.
    """
    alone: dict[tuple[str, str], set[str]] = {}
    asked: dict[tuple[str, str], set[str]] = {}
    latest: dict[tuple[str, str], str] = {}
    for attempt in attempts:
        if not _judged(attempt):
            continue
        place = _rollup_place(attempt)
        alone.setdefault(place, set())
        asked.setdefault(place, set())
        moment = str(attempt.get("created_at") or "")
        if moment > latest.get(place, ""):
            latest[place] = moment
        exercise = _attempt_exercise(attempt)
        if attempt.get("correct") is True and exercise:
            (asked if attempt.get("asked_ai") is True else alone)[place].add(exercise)
    return {
        place: AttemptRollup(
            right_alone=frozenset(alone[place]),
            right_asked=frozenset(asked[place]),
            last_judged_at=latest.get(place, ""),
        )
        for place in alone
    }


def _strings(value: object) -> frozenset[str]:
    if isinstance(value, (set, frozenset, list, tuple)):
        return frozenset(str(item) for item in value if item)
    return frozenset()


def stored_attempt_rollups(
    rows: Iterable[Mapping[str, Any]],
) -> dict[tuple[str, str], AttemptRollup]:
    """The rollup rows as read, by (lesson, knowledge point); the marker left out."""
    return {
        _rollup_place(row): AttemptRollup(
            right_alone=_strings(row.get("right_alone")),
            right_asked=_strings(row.get("right_asked")),
            last_judged_at=str(row.get("last_judged_at") or ""),
        )
        for row in rows
        if row.get("entity_type") == practice_repo.ATTEMPT_ROLLUP_ENTITY
    }


def attempt_rollups_complete(rows: Iterable[Mapping[str, Any]]) -> bool:
    """Whether the rollups read carry the marker of this version: every answer is in them."""
    return any(
        row.get("SK") == practice_repo.ATTEMPT_ROLLUP_STATE_SK
        and row.get("entity_type") == practice_repo.ATTEMPT_ROLLUP_STATE_ENTITY
        and row.get("rollup_version") == practice_repo.ATTEMPT_ROLLUP_VERSION
        for row in rows
    )


@dataclass(frozen=True, slots=True)
class _RightAnswer:
    exercise: str
    unit_id: str
    lesson_id: str
    asked_ai: bool


def _newest_first(attempt: Mapping[str, Any]) -> tuple[str, str]:
    return (str(attempt.get("created_at") or ""), str(attempt.get("attempt_id") or ""))


#: How many of the newest checked wrong answers the error-cause tally reads (#452).
RECENT_ERROR_CAUSE_ANSWERS = 20


@dataclass(frozen=True, slots=True)
class ErrorCauseCount:
    """One error cause among the recent wrong answers, and how often (#452).

    `misconception` is the sentence per locale, empty for `unclassified`.
    """

    category: str
    misconception: tuple[tuple[str, str], ...]
    count: int

    def misconception_in(self, locale: str) -> str:
        """The misconception in `locale`, else German; empty when it has none."""
        sentences = dict(self.misconception)
        return sentences.get(locale) or sentences.get("de", "")


def _error_cause_key(attempt: Mapping[str, Any]) -> tuple[str, tuple[tuple[str, str], ...]]:
    """A wrong answer's cause as a tally key; one without a whole cause is unclassified."""
    cause = attempt.get("error_cause")
    if isinstance(cause, Mapping) and cause.get("category") in error_causes.CATEGORIES:
        misconception = cause.get("misconception")
        if isinstance(misconception, Mapping):
            return (
                str(cause["category"]),
                tuple(sorted((str(k), str(v)) for k, v in misconception.items())),
            )
    return (error_causes.UNCLASSIFIED, ())


@dataclass(frozen=True, slots=True)
class RightAnswers:
    """One star's exercises answered right, split by how (#449).

    `independent`: answered right at least once without asking Ask about it
    first. `asked_ai`: answered right only after asking. Each exercise is
    counted once, in one of the two, so together they are the exercises of
    this star the student has answered right - the ones the star lights by.
    """

    independent: int = 0
    asked_ai: int = 0


@dataclass(frozen=True, slots=True)
class Completion:
    """One finished lesson.

    `title` is the lesson title an older progress row kept beside it; rows
    written now leave it empty and the reader looks the lesson up.
    """

    lesson_id: str
    unit_id: str
    subject_id: str
    completed_at: str
    topic_id: str = ""
    title: str = ""


def _within(raw: object, start: datetime, end: datetime) -> bool:
    """Whether a stored moment falls in `[start, end)`; one that cannot be read does not."""
    moment = _moment(raw)
    return moment is not None and start <= moment < end


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

    def _read(self, partition: str) -> list[dict[str, Any]] | _Failed:
        reader: Callable[[str], list[dict[str, Any]]] = getattr(self.source, partition)
        try:
            return [dict(row) for row in reader(self.student_id) if isinstance(row, Mapping)]
        except Exception as error:  # noqa: BLE001
            return _Failed(error)

    def _rows(self, partition: str) -> list[dict[str, Any]]:
        """Every row of one partition, read on first use and then kept."""
        if partition not in self._partitions:
            self._partitions[partition] = self._read(partition)
        kept = self._partitions[partition]
        if isinstance(kept, _Failed):
            raise kept.error
        return kept  # type: ignore[return-value]

    def read_all(self, partitions: Sequence[str] = PARTITIONS) -> StudentEvidence:
        """Read these partitions now, side by side, and the content with them.

        What a read would have raised is kept and raised where the partition is
        asked for, exactly as a partition read on first use.
        """
        wanted = [partition for partition in partitions if partition not in self._partitions]
        outcomes = curriculum_cache.run_all(
            [self.content.built, *((lambda p=partition: self._read(p)) for partition in wanted)]
        )
        for partition, outcome in zip(wanted, outcomes[1:], strict=True):
            self._partitions[partition] = outcome
        if isinstance(outcomes[0], Exception):
            raise outcomes[0]
        return self

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
                    topic_id=str(row.get("topic_id") or ""),
                    title=str(row.get("lesson_title") or ""),
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

    def completions_in(
        self, subject_id: str | None, *, topic_id: str | None = None
    ) -> tuple[Completion, ...]:
        """The finished lessons of one subject, under any spelling of it, oldest first.

        All subjects without one; with `topic_id`, only that topic's lessons.
        """
        return tuple(
            item
            for item in self.completions
            if (not subject_id or curriculum_service.same_subject(item.subject_id, subject_id))
            and (topic_id is None or item.topic_id == topic_id)
        )

    def completed_lesson_ids_in(self, subject_id: str | None) -> frozenset[str]:
        """The finished lessons of one subject, under any spelling of it; all without one."""
        if not subject_id:
            return self.completed_lesson_ids
        return frozenset(item.lesson_id for item in self.completions_in(subject_id))

    def completions_between(self, start: datetime, end: datetime) -> tuple[Completion, ...]:
        """The lessons finished in `[start, end)`, oldest first: a week's, say."""
        return tuple(item for item in self.completions if _within(item.completed_at, start, end))

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
                curriculum_service.subject_key(row.get("subject_id"))
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
            lambda: frozenset(item.exercise for item in self._right_answers()),
        )

    def _answers(self) -> tuple[str, list[dict[str, Any]]]:
        """Where the answer facts come from: every answer, or their rollups (card 135).

        The rollups when the page read them (`attempt_rollups` in `read_all`)
        and the answers have not been read whole already. They are trusted only
        under their marker, which the backfill writes once every earlier answer
        is in them; without it every answer is read, as before.

        This rests on the rollup write and this read going out in one deploy,
        with the backfill run after it: an answer saved by code that does not
        write rollups is never behind a marker. A marker this read writes itself
        (`_complete_rollups`) can be written in the seconds a deploy still runs
        the old code; the backfill run after the deploy adds what those missed.
        """

        def build() -> tuple[str, list[dict[str, Any]]]:
            if "attempts" in self._partitions or "attempt_rollups" not in self._partitions:
                return ("attempts", self._rows("attempts"))
            rollups = self._rows("attempt_rollups")
            if attempt_rollups_complete(rollups):
                return ("rollups", rollups)
            facts = self._rows("attempt_facts")
            self._complete_rollups(rollups, facts)
            return ("attempts", facts)

        return self._once("answers", build)

    def _complete_rollups(
        self, rollups: Sequence[Mapping[str, Any]], facts: Sequence[Mapping[str, Any]]
    ) -> None:
        """Write the marker when the rollups read already say what every answer says.

        A student who began after the backfill has no marker and would read
        every answer forever. An answer saved between the two reads makes them
        differ unless its rollup already held it, so agreeing rollups stay right
        once the marker stands. Degrades to no marker.
        """
        if expected_attempt_rollups(facts) != stored_attempt_rollups(rollups):
            return
        try:
            self.source.mark_attempt_rollups_complete(self.student_id)
        except Exception:  # noqa: BLE001
            logger.warning("Answer rollup marker could not be written", exc_info=True)

    def _right_answers(self) -> tuple[_RightAnswer, ...]:
        """Every judged right answer, one per exercise and place, from `_answers`."""

        def build() -> tuple[_RightAnswer, ...]:
            kind, rows = self._answers()
            found: list[_RightAnswer] = []
            if kind == "rollups":
                for place, rollup in stored_attempt_rollups(rows).items():
                    found.extend(
                        _RightAnswer(exercise, place[1], place[0], False)
                        for exercise in rollup.right_alone
                    )
                    found.extend(
                        _RightAnswer(exercise, place[1], place[0], True)
                        for exercise in rollup.right_asked
                    )
                return tuple(found)
            for attempt in rows:
                exercise = _attempt_exercise(attempt)
                if attempt.get("correct") is not True or not _judged(attempt) or not exercise:
                    continue
                found.append(
                    _RightAnswer(
                        exercise,
                        str(attempt.get("unit_id") or ""),
                        str(attempt.get("lesson_id") or ""),
                        attempt.get("asked_ai") is True,
                    )
                )
            return tuple(found)

        return self._once("right_answers", build)

    @property
    def right_answers_by_unit(self) -> dict[str, RightAnswers]:
        """Per star, its exercises answered right independently and after asking AI (#449).

        Judged answers only, as `answered_right`. A receipt without the
        `asked_ai` mark - every one written before it existed - is independent.
        One without its star is counted under its lesson's. For showing only:
        whether a star lights is decided on `answered_right`, as before.
        """

        def build() -> dict[str, RightAnswers]:
            asked: dict[str, set[str]] = {}
            alone: dict[str, set[str]] = {}
            for answer in self._right_answers():
                unit_id = answer.unit_id or self._once(
                    "unit_of_lesson", self.content.unit_of_lesson
                ).get(answer.lesson_id, "")
                if not unit_id:
                    continue
                kind = asked if answer.asked_ai else alone
                kind.setdefault(unit_id, set()).add(answer.exercise)
            return {
                unit_id: RightAnswers(
                    independent=len(alone.get(unit_id, set())),
                    asked_ai=len(asked.get(unit_id, set()) - alone.get(unit_id, set())),
                )
                for unit_id in sorted(set(asked) | set(alone))
            }

        return self._once("right_answers_by_unit", build)

    def right_answers_between(self, start: datetime, end: datetime) -> RightAnswers:
        """The exercises first answered right in `[start, end)`, split as `right_answers_by_unit` (#450).

        A week's newly solved exercises, say: one answered right before `start`
        is not new, and an answer after `end` does not count yet. Independent
        when one of its right answers in the window came without asking first.
        An answer whose moment cannot be read is not placed in any window.
        """
        before: set[str] = set()
        alone: set[str] = set()
        asked: set[str] = set()
        for attempt in self._rows("attempts"):
            exercise = _attempt_exercise(attempt)
            if attempt.get("correct") is not True or not _judged(attempt) or not exercise:
                continue
            moment = _moment(attempt.get("created_at") or attempt.get("createdAt"))
            if moment is None or moment >= end:
                continue
            if moment < start:
                before.add(exercise)
            else:
                (asked if attempt.get("asked_ai") is True else alone).add(exercise)
        alone -= before
        return RightAnswers(independent=len(alone), asked_ai=len(asked - before - alone))

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

    @property
    def last_answered_right(self) -> Mapping[str, datetime]:
        """When each exercise was last answered right, by any answer (#673).

        Self-reported answers count here: this says whether a student went back
        to an exercise they got wrong and got it right, not whether a star is
        earned. From every answer, as `mistakes`; one whose moment cannot be
        read is left out.
        """

        def build() -> Mapping[str, datetime]:
            latest: dict[str, datetime] = {}
            for attempt in self._rows("attempts"):
                exercise = _attempt_exercise(attempt)
                moment = _moment(attempt.get("created_at") or attempt.get("createdAt"))
                if attempt.get("correct") is not True or not exercise or moment is None:
                    continue
                if exercise not in latest or moment > latest[exercise]:
                    latest[exercise] = moment
            return MappingProxyType(latest)

        return self._once("last_answered_right", build)

    @property
    def recent_error_causes(self) -> tuple[ErrorCauseCount, ...]:
        """Why the recent wrong answers were wrong, most common first (#452).

        The newest `RECENT_ERROR_CAUSE_ANSWERS` checked wrong answers - a
        self-reported one was never judged wrong by anyone - each counted under
        the cause its receipt records. One recorded before causes were, or
        with no whole cause, is unclassified. A tie goes to the cause seen
        most recently.
        """

        def build() -> tuple[ErrorCauseCount, ...]:
            checked = [item for item in self.mistakes if _judged(item)]
            counts: Counter[tuple[str, tuple[tuple[str, str], ...]]] = Counter()
            last_seen: dict[tuple[str, tuple[tuple[str, str], ...]], int] = {}
            for position, attempt in enumerate(checked[:RECENT_ERROR_CAUSE_ANSWERS]):
                key = _error_cause_key(attempt)
                counts[key] += 1
                last_seen.setdefault(key, position)
            return tuple(
                ErrorCauseCount(category=category, misconception=misconception, count=count)
                for (category, misconception), count in sorted(
                    counts.items(), key=lambda item: (-item[1], last_seen[item[0]])
                )
            )

        return self._once("recent_error_causes", build)

    @property
    def most_common_error_cause(self) -> ErrorCauseCount | None:
        """The commonest known cause among the recent wrong answers; none when all are unclassified."""
        return next(
            (item for item in self.recent_error_causes if item.category != error_causes.UNCLASSIFIED),
            None,
        )

    def mistakes_between(self, start: datetime, end: datetime) -> tuple[dict[str, Any], ...]:
        """The wrong answers given in `[start, end)`, newest first."""
        return tuple(
            item
            for item in self.mistakes
            if _within(item.get("created_at") or item.get("createdAt"), start, end)
        )

    def mistakes_by_topic(self, subject_id: str | None = None) -> Counter[str]:
        """Wrong answers per topic, of one subject or of all."""
        return Counter(
            str(item.get("topic_id"))
            for item in self.mistakes
            if item.get("topic_id")
            and (not subject_id or curriculum_service.same_subject(item.get("subject_id", ""), subject_id))
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

            kind, rows = self._answers()
            if kind == "rollups":
                for (_lesson, unit_id), rollup in stored_attempt_rollups(rows).items():
                    note(unit_id, rollup.last_judged_at)
            else:
                for attempt in rows:
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
            return _retry_times(cooldowns, self.now)

        return self._once("star_quiz_retry_at", build)

    # -- review (REVIEW#) ----------------------------------------------------

    @property
    def due_cards(self) -> tuple[dict[str, Any], ...]:
        """Every review card whose time has come, soonest first. Every page, no ceiling."""

        return self._once("due_cards", lambda: self._due(self._rows("review_cards")))

    def _due(self, cards: Iterable[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
        moment = self.now.isoformat()
        due = [card for card in cards if str(card.get("due_at", "")) <= moment]
        due.sort(key=lambda card: str(card.get("due_at", "")))
        return tuple(due)

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
        """How many cards are due in each unit, by `card_unit`.

        From the cards' due times alone (`review_due`) unless the cards were
        read whole already.
        """

        def build() -> dict[str, int]:
            counts: dict[str, int] = {}
            due = (
                self.due_cards
                if "review_cards" in self._partitions
                else self._once("due_times", lambda: self._due(self._rows("review_due")))
            )
            for card in due:
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
