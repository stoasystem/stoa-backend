"""The review loop.

Answering a question anywhere in the platform schedules when it should come
back; this collects the ones whose time has come and presents them with enough
of the question to attempt again.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from stoa.db.repositories import practice_repo, review_repo
from stoa.models.practice import DEFAULT_CHALLENGE_TYPE
from stoa.services import curriculum_service, review_scheduler

logger = logging.getLogger(__name__)

DEFAULT_DUE_LIMIT = 20


def _text(value: Any) -> str:
    return str(value) if value not in (None, "") else ""


def record_answer(
    *,
    student_id: str,
    challenge: Mapping[str, Any],
    correct: bool,
    answered_at: datetime | None = None,
) -> dict[str, Any] | None:
    """Fold an answer into the question's schedule.

    A failure here must not cost the student their answer, which is already
    recorded, so the schedule is best-effort.
    """
    challenge_id = _text(challenge.get("challenge_id"))
    if not challenge_id:
        return None
    now = answered_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    try:
        # Answering is study, whatever the answer was, and the streak is the
        # reason a student comes back to clear a review.
        practice_repo.record_study_day(
            student_id,
            now.astimezone(curriculum_service.ZURICH).date().isoformat(),
            kind="practice",
            at=now.isoformat(),
        )
    except Exception:  # noqa: BLE001
        logger.warning("Study day not recorded", exc_info=True)

    try:
        stored = review_repo.get_card(student_id, challenge_id)
        state = (
            review_repo.state_from_item(stored, now=now)
            if stored
            else review_scheduler.new_card(now=now)
        )
        updated = review_scheduler.review(
            state, review_scheduler.grade_for_answer(correct=correct), now=now
        )
        return review_repo.save_card(
            student_id,
            challenge_id,
            updated,
            lesson_id=_text(challenge.get("lesson_id")),
            subject_id=_text(challenge.get("subject_id")),
            topic_id=_text(challenge.get("topic_id")),
        )
    except Exception:  # noqa: BLE001
        logger.warning("Review schedule update failed", exc_info=True)
        return None


def _unit_of_lesson() -> dict[str, str]:
    """Which unit each lesson of the active curriculum sits under."""
    catalog = curriculum_service.list_catalog()
    return {
        _text(lesson.get("id")): _text(lesson.get("unitId"))
        for lesson in catalog.get("lessons") or ()
        if isinstance(lesson, Mapping)
    }


def _card_unit(card: Mapping[str, Any], unit_of_lesson: Mapping[str, str]) -> str:
    """The unit a card belongs to, by the rule the star map's reviewDue uses.

    The card's own `lesson_id` decides; only a card that carries none is placed
    through its question. A card that lands outside the active curriculum
    belongs to no unit and is counted nowhere.
    """
    lesson_id = _text(card.get("lesson_id"))
    if not lesson_id:
        challenge = practice_repo.get_challenge(_text(card.get("challenge_id")))
        lesson_id = _text(challenge.get("lesson_id")) if challenge else ""
    return unit_of_lesson.get(lesson_id, "") if lesson_id else ""


def due_review(
    *,
    student_id: str,
    now: datetime | None = None,
    limit: int = DEFAULT_DUE_LIMIT,
    unit_id: str | None = None,
) -> dict[str, Any]:
    """The questions waiting for this student, with the content to attempt them."""
    moment = now or datetime.now(timezone.utc)
    selected: list[dict[str, Any]] | None = None
    if unit_id:
        # Before the page is cut, not after: a knowledge point whose cards sort
        # behind a fuller one would otherwise hand back an empty session while
        # its badge on the map says there is work.
        unit_of_lesson = _unit_of_lesson()
        selected = [
            card
            for card in review_repo.due_cards(student_id, now=moment)
            if _card_unit(card, unit_of_lesson) == unit_id
        ]
        cards = selected[:limit]
    else:
        cards = review_repo.list_due_cards(student_id, now=moment, limit=limit)

    items: list[dict[str, Any]] = []
    for card in cards:
        challenge_id = _text(card.get("challenge_id"))
        challenge = practice_repo.get_challenge(challenge_id) if challenge_id else None
        if not challenge:
            # The question was withdrawn from the curriculum since it was
            # answered; there is nothing to review.
            continue
        items.append(
            {
                "challengeId": challenge_id,
                "lessonId": _text(card.get("lesson_id")) or _text(challenge.get("lesson_id")),
                "subjectId": _text(card.get("subject_id")) or _text(challenge.get("subject_id")),
                "topicId": _text(card.get("topic_id")) or _text(challenge.get("topic_id")),
                "prompt": _text(challenge.get("prompt")),
                "options": [str(option) for option in (challenge.get("options") or [])],
                # The same default as the lesson stage, from the same
                # definition: a question with no stored type must be the same
                # kind of question on both pages (#124).
                "type": _text(challenge.get("type")) or DEFAULT_CHALLENGE_TYPE,
                "dueAt": _text(card.get("due_at")),
                "lapses": review_repo.as_int(card.get("lapses")),
                "reps": review_repo.as_int(card.get("reps")),
            }
        )

    return {
        "items": items,
        # For a selected unit this is the whole set, so it matches the map's
        # reviewDue even when a question has since been withdrawn and cannot be
        # offered. Unselected, it stays the page count it has always been.
        "dueCount": len(items) if selected is None else len(selected),
        "generatedAt": moment.astimezone(timezone.utc).isoformat(),
    }


def review_summary(*, student_id: str, now: datetime | None = None) -> dict[str, Any]:
    """How much is waiting, without the cost of loading the questions."""
    moment = now or datetime.now(timezone.utc)
    try:
        cards = review_repo.list_cards(student_id)
    except Exception:  # noqa: BLE001
        logger.warning("Review summary unavailable", exc_info=True)
        return {"dueCount": 0, "scheduledCount": 0, "nextDueAt": ""}

    stamp = moment.astimezone(timezone.utc).isoformat()
    due = [card for card in cards if str(card.get("due_at", "")) <= stamp]
    upcoming = sorted(
        (str(card.get("due_at", "")) for card in cards if str(card.get("due_at", "")) > stamp)
    )
    return {
        "dueCount": len(due),
        "scheduledCount": len(cards),
        "nextDueAt": upcoming[0] if upcoming else "",
    }
