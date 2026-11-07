"""One quiz module: the lesson quiz and the star quiz are two kinds of one paper (#213).

A **paper** is one row in the student's `QUIZ#` partition (`practice_repo`
`put_quiz_paper`): its kind, the exercises it asks in order, the answer log
(`{exerciseId, correct, answeredAt}`, one per answer), the answer count every
write is conditional on, the exercises dropped because they no longer resolve,
its status and its expiry (30 minutes). What it asks next is never stored: the
kind's rule derives it from the order and the log (`rules.lesson_standing`,
`rules.star_standing`).

The two kinds, `LESSON` and `STAR`, differ in:

* the rule for the next exercise: a lesson quiz sends a wrong answer to the back
  of the queue and takes a heart; a star quiz asks every exercise once, in order;
* what passing does: a lesson quiz issues the credential `complete_lesson`
  spends (10 minutes); a star quiz records its pass row, lights the star with
  the source `quiz` and replays every answer into the review schedule
  (`answer_recording.record_star_quiz_pass`);
* what losing does: a star quiz writes the cooldown row (24 hours); a lost
  lesson quiz does nothing;
* what the client is shown (`view`), unchanged from before the merge.

Every answer, of either kind, goes down the same ladder (`answer`):

1. **unknown** - no paper of this student with this id for this lesson or star;
2. **replay** - the exercise named was already answered (and is not the one
   asked now): the first result is handed back and nothing changes;
3. **finished** - the paper was passed or lost;
4. **expired** - past its 30 minutes;
5. **gone** - an exercise that no longer resolves is dropped from the paper
   and the next one is asked; if the one named was dropped, or nothing is left
   to ask, the answer is refused (a paper with nothing left ends as lost, with
   none of a loss's consequences);
6. **out of order** - the exercise named is not the one asked now;
7. judged (`answer_recording.judge`) and written, on condition the answer count
   did not move. When it did, the paper is read again: the same exercise
   answered in between is a replay, anything else is out of order.

An answer that does not name its exercise (an old lesson-quiz client, before
stoa-frontend#589) answers the exercise asked now and has no replay protection.

Every accepted answer leaves one usage event, `{quiz_id}:{n}` for the n-th
answer (`answer_recording.record_quiz_answer`). Refusals are `Refused`, with a
`Reason` the route maps to its kind's error code.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from stoa.db.repositories import practice_repo
from stoa.services import (
    answer_recording,
    knowledge_mastery_service,
    practice_projection_service,
    student_evidence,
)
from stoa.services.quiz import rules

logger = logging.getLogger(__name__)

__all__ = [
    "LESSON",
    "STAR",
    "QuizKind",
    "Reason",
    "Refused",
    "answer",
    "rules",
    "spend_credential",
    "start_lesson_quiz",
    "start_star_quiz",
]


class Reason(StrEnum):
    """Why the quiz module refused; the route names it in its kind's error code."""

    # Answering.
    UNKNOWN = "unknown"
    FINISHED = "finished"
    EXPIRED = "expired"
    GONE = "gone"
    OUT_OF_ORDER = "out_of_order"
    ANSWER_INVALID = "answer_invalid"
    # Starting.
    NOTHING_TO_ASK = "nothing_to_ask"
    NO_SUCH_STAR = "no_such_star"
    ALREADY_LIT = "already_lit"
    COOLING_DOWN = "cooling_down"
    # Spending a lesson quiz's credential.
    CREDENTIAL_INVALID = "credential_invalid"
    CREDENTIAL_EXPIRED = "credential_expired"


class Refused(Exception):
    def __init__(self, reason: Reason, *, retry_at: str | None = None) -> None:
        super().__init__(reason.value)
        self.reason = reason
        #: When a star still cooling down can be taken again.
        self.retry_at = retry_at


Standing = rules.Standing
Paper = Mapping[str, Any]


@dataclass(frozen=True)
class QuizKind:
    """One configuration of the paper: everything the two quizzes do differently."""

    name: str
    #: The `kind` values a paper of this configuration is stored with.
    paper_kinds: frozenset[str]
    #: The attribute naming what the paper is for: `lesson_id` or `unit_id`.
    scope_field: str
    #: The same, as the usage event's metadata names it.
    scope_key: str
    standing_rule: Callable[[Sequence[str], Sequence[Mapping[str, Any]], Sequence[str]], Standing]
    #: Fields stored with the answer that decides the paper: what a replay hands back.
    outcome: Callable[[str, datetime], dict[str, Any]]
    #: What the decided paper leads to, once the answer that decided it is written.
    consequences: Callable[[str, Paper, datetime], None]
    #: What the client is shown of a paper, before and after answers.
    view: Callable[[Paper, Standing, str], dict[str, Any]]
    #: What only an answer's reply carries, beyond `view` and `correct`.
    answer_fields: Callable[[Paper], dict[str, Any]] = field(default=lambda _paper: {})


# ── the paper ───────────────────────────────────────────────────────────────


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _strings(values: Any) -> list[str]:
    return [str(item) for item in values or []]


def _answers(paper: Paper) -> list[dict[str, Any]]:
    return [dict(item) for item in paper.get("answers") or []]


def standing(kind: QuizKind, paper: Paper) -> Standing:
    """Where the paper stands: the kind's rule over the log, the stored status winning once over."""
    derived = kind.standing_rule(
        _strings(paper.get("order")), _answers(paper), _strings(paper.get("dropped"))
    )
    stored = str(paper.get("status") or rules.IN_PROGRESS)
    if stored == rules.IN_PROGRESS:
        return derived
    return Standing(stored, derived.mistakes, ())


def _exercise_preview(remaining: Sequence[str], locale: str) -> dict[str, Any] | None:
    """The exercise asked now, as the client may see it; one gone is passed over."""
    for exercise_id in remaining:
        challenge = practice_repo.get_challenge(exercise_id)
        if challenge:
            return practice_projection_service.build_challenge_preview(challenge, locale)
    return None


def _open(
    kind: QuizKind,
    student_id: str,
    *,
    paper_kind: str,
    scope_id: str,
    order: Sequence[str],
    now: datetime,
) -> dict[str, Any]:
    expires = now + rules.PAPER_TTL
    return practice_repo.put_quiz_paper(
        student_id,
        quiz_id=rules.new_token(),
        kind=paper_kind,
        scope={kind.scope_field: scope_id},
        order=order,
        expires_at=int(expires.timestamp()),
        expires_at_iso=expires.isoformat(),
        created_at=now.isoformat(),
    )


def _view(kind: QuizKind, paper: Paper, locale: str) -> dict[str, Any]:
    return kind.view(paper, standing(kind, paper), locale)


# ── lesson quiz ─────────────────────────────────────────────────────────────


def _lesson_outcome(status: str, now: datetime) -> dict[str, Any]:
    if status != rules.PASSED:
        return {}
    expires = now + rules.CREDENTIAL_TTL
    return {
        "credential_id": rules.new_token(),
        "credential_expires_at": int(expires.timestamp()),
        "credential_expires_at_iso": expires.isoformat(),
    }


def _lesson_consequences(student_id: str, paper: Paper, now: datetime) -> None:
    if paper.get("status") != rules.PASSED or not paper.get("credential_id"):
        return
    practice_repo.put_quiz_credential(
        student_id,
        credential_id=str(paper["credential_id"]),
        lesson_id=str(paper.get("lesson_id") or ""),
        quiz_id=str(paper.get("quiz_id") or ""),
        expires_at=_int(paper.get("credential_expires_at")),
        expires_at_iso=str(paper.get("credential_expires_at_iso") or ""),
        created_at=now.isoformat(),
    )


def _lesson_view(paper: Paper, position: Standing, locale: str) -> dict[str, Any]:
    exercise = (
        _exercise_preview(position.remaining, locale)
        if position.status == rules.IN_PROGRESS
        else None
    )
    return {
        "quizId": str(paper.get("quiz_id") or ""),
        "lessonId": str(paper.get("lesson_id") or ""),
        "kind": str(paper.get("kind") or rules.SKIP_QUIZ),
        "status": position.status,
        "heartsLeft": rules.hearts_left(position.mistakes),
        "mistakesAllowed": rules.MAX_MISTAKES,
        "remaining": len(position.remaining),
        "expiresAt": str(paper.get("expires_at_iso") or ""),
        "exercise": exercise,
    }


def _lesson_answer_fields(paper: Paper) -> dict[str, Any]:
    credential = paper.get("credential_id")
    return {
        "credential": str(credential) if credential else None,
        "credentialExpiresAt": (
            str(paper.get("credential_expires_at_iso")) if credential else None
        ),
    }


LESSON = QuizKind(
    name="lesson",
    paper_kinds=frozenset(rules.LESSON_QUIZ_KINDS),
    scope_field="lesson_id",
    scope_key="lessonId",
    standing_rule=rules.lesson_standing,
    outcome=_lesson_outcome,
    consequences=_lesson_consequences,
    view=_lesson_view,
    answer_fields=_lesson_answer_fields,
)


def start_lesson_quiz(
    student_id: str,
    lesson_id: str,
    *,
    kind: str = rules.SKIP_QUIZ,
    locale: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Draw a new lesson quiz (#92): `skip` or `testOut`. Refused when there is nothing to ask."""
    moment = now or datetime.now(timezone.utc)
    exercise_ids = [
        str(challenge.get("challenge_id"))
        for challenge in practice_repo.get_challenges(lesson_id)
        if challenge.get("challenge_id")
    ]
    order = rules.compose_lesson_quiz(
        kind,
        exercise_ids=exercise_ids,
        answered_right=practice_repo.challenges_answered_right(student_id, lesson_id),
    )
    if not order:
        raise Refused(Reason.NOTHING_TO_ASK)
    paper = _open(
        LESSON, student_id, paper_kind=kind, scope_id=lesson_id, order=order, now=moment
    )
    return _view(LESSON, paper, locale)


def spend_credential(
    student_id: str, lesson_id: str, credential: str, *, now: datetime | None = None
) -> None:
    """Take one passed lesson quiz's credential out of circulation, or refuse it."""
    moment = now or datetime.now(timezone.utc)
    stored = practice_repo.get_quiz_credential(student_id, credential)
    # The quiz it was issued for has to be the one it names: without this the
    # field is decoration, and a credential is a bearer token for a lesson
    # rather than for the paper that earned it.
    if stored and not str(stored.get("quiz_id") or ""):
        stored = None
    if not stored or str(stored.get("lesson_id") or "") != lesson_id:
        raise Refused(Reason.CREDENTIAL_INVALID)
    if _int(stored.get("expires_at")) <= int(moment.timestamp()):
        practice_repo.consume_quiz_credential(student_id, credential, lesson_id=lesson_id)
        raise Refused(Reason.CREDENTIAL_EXPIRED)
    if not practice_repo.consume_quiz_credential(student_id, credential, lesson_id=lesson_id):
        raise Refused(Reason.CREDENTIAL_INVALID)


# ── star quiz ───────────────────────────────────────────────────────────────


def _star_outcome(status: str, now: datetime) -> dict[str, Any]:
    if status != rules.FAILED:
        return {}
    return {"retry_at": (now + rules.COOLDOWN).isoformat()}


def _star_consequences(student_id: str, paper: Paper, now: datetime) -> None:
    unit_id = str(paper.get("unit_id") or "")
    quiz_id = str(paper.get("quiz_id") or "")
    status = paper.get("status")
    if status == rules.FAILED and paper.get("retry_at"):
        retry_at = str(paper["retry_at"])
        practice_repo.put_star_quiz_cooldown(
            student_id,
            unit_id=unit_id,
            quiz_id=quiz_id,
            retry_at=retry_at,
            expires_at=int(datetime.fromisoformat(retry_at).timestamp()),
        )
    elif status == rules.PASSED:
        # The star lit for good, whatever its lessons say later, and every
        # answer of the paper scheduled for review, right or wrong.
        practice_repo.put_star_quiz_pass(
            student_id, unit_id=unit_id, quiz_id=quiz_id, passed_at=now.isoformat()
        )
        try:
            practice_repo.record_lit_unit(
                student_id,
                unit_id,
                lit_at=now.isoformat(),
                source=knowledge_mastery_service.LitSource.QUIZ.value,
            )
        except Exception:  # noqa: BLE001
            # Lit once before, by its lessons: that lighting keeps its moment.
            logger.info("Star quiz lighting already recorded", extra={"unit_id": unit_id})
        answer_recording.record_star_quiz_pass(student_id, _answers(paper))


def _star_view(paper: Paper, position: Standing, locale: str) -> dict[str, Any]:
    order = _strings(paper.get("order"))
    dropped = set(_strings(paper.get("dropped")))
    exercise = (
        _exercise_preview(position.remaining, locale)
        if position.status == rules.IN_PROGRESS
        else None
    )
    retry_at = paper.get("retry_at")
    return {
        "quizId": str(paper.get("quiz_id") or ""),
        "unitId": str(paper.get("unit_id") or ""),
        "status": position.status,
        "total": len([item for item in order if item not in dropped]),
        "answered": len(paper.get("answers") or []),
        "mistakes": position.mistakes,
        "mistakesAllowed": rules.MAX_MISTAKES,
        "expiresAt": str(paper.get("expires_at_iso") or ""),
        "exercise": exercise,
        "retryAt": str(retry_at) if retry_at else None,
    }


STAR = QuizKind(
    name="star",
    paper_kinds=frozenset({rules.STAR_QUIZ}),
    scope_field="unit_id",
    scope_key="unitId",
    standing_rule=rules.star_standing,
    outcome=_star_outcome,
    consequences=_star_consequences,
    view=_star_view,
)


def start_star_quiz(
    student_id: str,
    unit_id: str,
    *,
    locale: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Open the star quiz of one knowledge point, or hand back the one already open (#165).

    Every star not lit can be taken, in progress or not, whatever its
    prerequisites, unless one of its papers was lost less than 24 hours ago.
    """
    moment = now or datetime.now(timezone.utc)
    evidence = student_evidence.for_student(student_id, locale=locale, now=moment)
    judged = knowledge_mastery_service.unit_states(evidence).get(unit_id)
    if judged is None or judged.lesson_count == 0:
        raise Refused(Reason.NO_SUCH_STAR)
    if judged.state is knowledge_mastery_service.LearningState.LIT:
        raise Refused(Reason.ALREADY_LIT)
    retry = evidence.star_quiz_retry_at.get(unit_id)
    if retry:
        raise Refused(Reason.COOLING_DOWN, retry_at=retry)

    for paper in practice_repo.list_quiz_papers(student_id):
        if (
            str(paper.get("kind") or "") in STAR.paper_kinds
            and str(paper.get("unit_id") or "") == unit_id
            and str(paper.get("status") or "") == rules.IN_PROGRESS
            and _int(paper.get("expires_at")) > int(moment.timestamp())
        ):
            return _view(STAR, paper, locale)

    order = rules.compose_star_quiz(
        knowledge_mastery_service.star_quiz_exercises(unit_id, evidence)
    )
    if not order:
        raise Refused(Reason.NOTHING_TO_ASK)
    paper = _open(
        STAR, student_id, paper_kind=rules.STAR_QUIZ, scope_id=unit_id, order=order, now=moment
    )
    return _view(STAR, paper, locale)


# ── answering: one ladder for both kinds ────────────────────────────────────


def _replay(
    kind: QuizKind, paper: Paper, exercise_id: str, locale: str
) -> dict[str, Any] | None:
    """The first result for `exercise_id`, if it was answered and is not the one asked now."""
    logged = [item for item in _answers(paper) if str(item.get("exerciseId") or "") == exercise_id]
    if not logged:
        return None
    now = standing(kind, paper)
    if now.status == rules.IN_PROGRESS and now.remaining and now.remaining[0] == exercise_id:
        # A lesson quiz asks a wrongly answered exercise again: naming it now is
        # a new answer to it, not a retry of the old one.
        return None
    return _reply(kind, paper, correct=bool(logged[-1].get("correct")), locale=locale)


def _reply(kind: QuizKind, paper: Paper, *, correct: bool, locale: str) -> dict[str, Any]:
    return {**_view(kind, paper, locale), "correct": correct, **kind.answer_fields(paper)}


def _drop(student_id: str, paper: Paper, gone: Sequence[str], *, exhausted: bool) -> None:
    """Record exercises that no longer resolve; a paper left with nothing to ask ends."""
    updates: dict[str, Any] = {"dropped": [*_strings(paper.get("dropped")), *gone]}
    if exhausted:
        updates["status"] = rules.FAILED
    for exercise_id in gone:
        logger.warning("Quiz dropped an exercise it could not resolve", extra={"challenge_id": exercise_id})
    try:
        practice_repo.update_quiz_paper(
            student_id,
            str(paper.get("quiz_id") or ""),
            answered=_int(paper.get("answered")),
            updates=updates,
        )
    except practice_repo.QuizPaperConflict:
        # Somebody answered in between; the next request finds the exercise gone again.
        pass


def answer(
    kind: QuizKind,
    student_id: str,
    quiz_id: str,
    *,
    scope_id: str,
    exercise_id: str | None,
    raw_answer: object,
    locale: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Judge one answer to a paper of `kind` and record it; see the module docstring's ladder."""
    moment = now or datetime.now(timezone.utc)
    paper = practice_repo.get_quiz_paper(student_id, quiz_id)
    if (
        not paper
        or str(paper.get("kind") or "") not in kind.paper_kinds
        or str(paper.get(kind.scope_field) or "") != scope_id
    ):
        raise Refused(Reason.UNKNOWN)

    if exercise_id is not None:
        replayed = _replay(kind, paper, exercise_id, locale)
        if replayed is not None:
            return replayed
    now_standing = standing(kind, paper)
    if now_standing.status != rules.IN_PROGRESS:
        raise Refused(Reason.FINISHED)
    if _int(paper.get("expires_at")) <= int(moment.timestamp()):
        raise Refused(Reason.EXPIRED)

    # An exercise the catalog no longer resolves is dropped rather than asked:
    # asking it again would hold the paper shut for good (independent audit of #92).
    remaining = list(now_standing.remaining)
    gone: list[str] = []
    challenge = None
    while remaining:
        challenge = practice_repo.get_challenge(remaining[0])
        if challenge:
            break
        gone.append(remaining.pop(0))
    asking = remaining[0] if remaining else None
    if asking is None or (exercise_id is not None and exercise_id in gone):
        _drop(student_id, paper, gone, exhausted=asking is None)
        raise Refused(Reason.GONE)
    if exercise_id is not None and exercise_id != asking:
        if gone:
            _drop(student_id, paper, gone, exhausted=False)
        raise Refused(Reason.OUT_OF_ORDER)
    if challenge is None:  # pragma: no cover - `asking` resolved above
        raise Refused(Reason.GONE)

    try:
        judgement = answer_recording.judge(challenge, raw_answer, locale=locale)
    except answer_recording.AnswerInvalid as error:
        raise Refused(Reason.ANSWER_INVALID) from error

    answers = [
        *_answers(paper),
        {"exerciseId": asking, "correct": judgement.correct, "answeredAt": moment.isoformat()},
    ]
    dropped = [*_strings(paper.get("dropped")), *gone]
    after = kind.standing_rule(_strings(paper.get("order")), answers, dropped)
    updates = {
        "answers": answers,
        "answered": len(answers),
        "dropped": dropped,
        "status": after.status,
        **kind.outcome(after.status, moment),
    }
    try:
        practice_repo.update_quiz_paper(
            student_id, quiz_id, answered=_int(paper.get("answered")), updates=updates
        )
    except practice_repo.QuizPaperConflict:
        # Another answer was written since this one read the paper. If it
        # answered the same exercise, this one is its retry: hand back that result.
        current = practice_repo.get_quiz_paper(student_id, quiz_id) or paper
        before = [item for item in _answers(paper) if item.get("exerciseId") == asking]
        since = [item for item in _answers(current) if item.get("exerciseId") == asking]
        if len(since) > len(before):
            return _reply(kind, current, correct=bool(since[-1].get("correct")), locale=locale)
        raise Refused(Reason.OUT_OF_ORDER) from None

    written = {**paper, **updates}
    kind.consequences(student_id, written, moment)
    answer_recording.record_quiz_answer(
        student_id,
        judgement,
        resource_id=f"{quiz_id}:{len(answers)}",
        metadata={"quizId": quiz_id, kind.scope_key: scope_id, "status": after.status},
    )
    return _reply(kind, written, correct=judgement.correct, locale=locale)
