"""Judge one answer to one exercise, and record what that answer leads to (#213).

Every route that judges a student's answer comes through here, so an answer is
read the same way wherever it is given: the raw answer is normalized, the
exercise is put into the reader's language, the answer is judged against that
localized exercise (`answer_judging.judge_challenge`), and the feedback is taken
from the same localized exercise, in the reader's language where the exercise
brings none of its own (#128).

What an answer leads to depends on where it was given, the mode:

* **practice** (`answer_practice`): the immutable receipt, the curriculum
  analytics signal, the review card, the usage event, and the feedback.
* **quiz answer** (`judge`, then `record_quiz_answer`): only the usage event.
  A quiz answer is not an attempt; the quiz keeps its own log. The event is
  written once the quiz has taken the answer, because it carries the quiz's
  outcome and an answer the quiz refused leaves no event.
* **star quiz pass** (`record_star_quiz_pass`): every answer of the passed paper
  scheduled for review, right or wrong, as ordinary practice would have.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Any

from stoa.db.repositories import practice_repo
from stoa.models.practice import PracticeAttemptResult
from stoa.services import (
    answer_judging,
    curriculum_analytics_service,
    exercise_localization,
    practice_projection_service,
    review_service,
    usage_ledger_service,
)

logger = logging.getLogger(__name__)


class AnswerInvalid(ValueError):
    """The submitted answer is not something an answer can be (wrong type, too big)."""


class ReceiptUnavailable(RuntimeError):
    """The practice answer was judged, but its receipt could not be written."""


@dataclass(frozen=True)
class Judgement:
    """One answer judged against the exercise as the reader saw it."""

    #: The stored exercise row, unchanged: its version is what a receipt records.
    challenge: Mapping[str, Any]
    #: The exercise in the reader's language, the one judged and the one quoted.
    shown: Mapping[str, Any]
    #: The submitted answer, normalized.
    answer: str | list[str]
    correct: bool
    correct_feedback: str
    incorrect_feedback: str

    @property
    def feedback(self) -> str:
        return self.correct_feedback if self.correct else self.incorrect_feedback


def judge(challenge: Mapping[str, Any], raw_answer: object, *, locale: str) -> Judgement:
    """Normalize, localize, judge and find the feedback. Records nothing.

    Raises `AnswerInvalid` for an answer that cannot be one.
    """
    try:
        answer = practice_projection_service.normalize_submitted_answer(raw_answer)
    except ValueError as error:
        raise AnswerInvalid(str(error)) from error
    shown = exercise_localization.localized(challenge, locale)
    correct_feedback, incorrect_feedback = practice_projection_service.answer_feedback(
        shown, locale
    )
    return Judgement(
        challenge=challenge,
        shown=shown,
        answer=answer,
        correct=answer_judging.judge_challenge(answer, shown),
        correct_feedback=correct_feedback,
        incorrect_feedback=incorrect_feedback,
    )


def answer_practice(
    student_id: str, challenge: Mapping[str, Any], raw_answer: object, *, locale: str
) -> PracticeAttemptResult:
    """Practice mode: judge the answer and record everything it leads to.

    The receipt is written first and is the one write that must succeed: the
    standard answer is revealed only once the answer is on record. Raises
    `AnswerInvalid` before anything is written, and `ReceiptUnavailable` when
    the receipt could not be written; the analytics signal, the review card and
    the usage event are best-effort after it.
    """
    judgement = judge(challenge, raw_answer, locale=locale)
    challenge_id = str(challenge.get("challenge_id") or "")
    shown = judgement.shown
    versioned = practice_repo.version_challenge(dict(challenge))
    lesson_id = str(versioned.get("lesson_id") or "")
    next_challenge_id = _next_challenge_id(challenge_id, lesson_id)
    created_at = datetime.now(timezone.utc).isoformat()
    try:
        receipt = practice_repo.put_attempt(
            student_id,
            challenge_id,
            judgement.answer,
            judgement.correct,
            subject_id=_text(challenge, "subject_id"),
            topic_id=_text(challenge, "topic_id"),
            lesson_id=lesson_id,
            unit_id=_text(challenge, "unit_id"),
            challenge_version=versioned["challenge_version"],
            challenge_content_hash=versioned["challenge_content_hash"],
            standard_answer=str(shown.get("correct_answer", shown.get("answer_key")) or ""),
            explanation=str(shown.get("explanation") or ""),
            correct_feedback=judgement.correct_feedback,
            incorrect_feedback=judgement.incorrect_feedback,
            feedback=judgement.feedback,
            next_challenge_id=next_challenge_id,
            prompt=str(shown.get("prompt") or ""),
            options=shown.get("options") if isinstance(shown.get("options"), list) else None,
            challenge_type=str(challenge.get("type") or ""),
            created_at=created_at,
        )
        result = practice_projection_service.build_attempt_result(receipt)
    except Exception as error:  # noqa: BLE001
        logger.warning("Practice attempt persistence failed")
        raise ReceiptUnavailable from error

    curriculum_analytics_service.record_practice_attempt(
        student_id=student_id, challenge=dict(challenge), correct=judgement.correct
    )
    review_service.record_answer(
        student_id=student_id,
        challenge=challenge,
        correct=judgement.correct,
        answered_at=datetime.fromisoformat(created_at),
    )
    fence = receipt.get("account_fence_generation")
    record_practice_usage(
        student_id=student_id,
        action=usage_ledger_service.PRACTICE_ANSWER_ACTION,
        resource_id=challenge_id,
        metadata={"status": "submitted"},
        account_fence_generation=fence if type(fence) is int else None,
    )
    return result


def record_quiz_answer(
    student_id: str,
    judgement: Judgement,
    *,
    resource_id: str,
    metadata: Mapping[str, Any],
) -> None:
    """Quiz-answer mode: the one trace a quiz answer leaves is its usage event.

    `metadata` is what the quiz says about itself (its id, its status after
    this answer); whether the answer was right is added here.
    """
    record_practice_usage(
        student_id=student_id,
        action=usage_ledger_service.PRACTICE_QUIZ_ANSWER_ACTION,
        resource_id=resource_id,
        metadata={**metadata, "correct": judgement.correct},
        account_fence_generation=None,
    )


def record_star_quiz_pass(student_id: str, answers: Iterable[Mapping[str, Any]]) -> None:
    """Star-quiz-pass mode: schedule every answer of the passed paper for review.

    `answers` is the paper's log, one `{exerciseId, correct, answeredAt}` per
    answer. An exercise that no longer resolves is skipped.
    """
    for answer in answers:
        challenge = practice_repo.get_challenge(str(answer.get("exerciseId") or ""))
        if challenge:
            review_service.record_answer(
                student_id=student_id,
                challenge=challenge,
                correct=bool(answer.get("correct")),
                answered_at=datetime.fromisoformat(str(answer.get("answeredAt"))),
            )


def record_practice_usage(
    *,
    student_id: str,
    action: str,
    resource_id: str,
    metadata: Mapping[str, Any],
    usage_counter: Mapping[str, Any] | None = None,
    account_fence_generation: int | None = None,
) -> None:
    """One practice usage event; a ledger failure never costs the student the answer."""
    try:
        usage_ledger_service.record_usage_event(
            student_id=student_id,
            action=action,
            quota_period=(usage_counter or {}).get("quotaPeriod")
            or usage_ledger_service.today_period(),
            idempotency_key=usage_ledger_service.build_usage_idempotency_key(
                action=action,
                resource_id=resource_id,
                qualifier=student_id,
            ),
            counter_key=(usage_counter or {}).get("counterKey"),
            counter_value=(usage_counter or {}).get("counterValue"),
            request_correlation_id=None,
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata=dict(metadata),
            account_fence_generation=account_fence_generation,
        )
    except Exception:  # noqa: BLE001
        logger.warning("Practice usage ledger write failed", exc_info=True)


def _next_challenge_id(challenge_id: str, lesson_id: str) -> str | None:
    challenge_ids = [
        challenge["challenge_id"] for challenge in practice_repo.get_challenges(lesson_id)
    ]
    try:
        index = challenge_ids.index(challenge_id)
    except ValueError:
        return None
    return challenge_ids[index + 1] if index + 1 < len(challenge_ids) else None


def _text(item: Mapping[str, Any], field: str) -> str:
    value = item.get(field)
    return value if isinstance(value, str) else ""
