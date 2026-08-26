"""What the scheduler promises a student.

These test the behaviour someone would notice - a question they keep getting
right stops appearing, a question they miss comes straight back - rather than
the arithmetic, which is the algorithm's business.
"""

from datetime import datetime, timedelta, timezone

import pytest

from stoa.services.review_scheduler import (
    AGAIN,
    EASY,
    GOOD,
    HARD,
    MAX_INTERVAL_DAYS,
    CardState,
    grade_for_answer,
    interval_days,
    new_card,
    retrievability,
    review,
)

NOW = datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc)


def answer_correctly(state: CardState, *, at: datetime) -> CardState:
    return review(state, GOOD, now=at)


def test_a_new_question_is_due_at_once():
    card = new_card(now=NOW)

    assert card.due_at == NOW
    assert card.is_new
    assert card.reps == 0


def test_getting_it_right_pushes_it_into_the_future():
    card = answer_correctly(new_card(now=NOW), at=NOW)

    assert card.due_at > NOW
    assert card.reps == 1
    assert card.lapses == 0


def test_each_success_waits_longer_than_the_last():
    card = new_card(now=NOW)
    at = NOW
    gaps: list[timedelta] = []

    for _ in range(5):
        reviewed = answer_correctly(card, at=at)
        gaps.append(reviewed.due_at - at)
        at = reviewed.due_at
        card = reviewed

    assert gaps == sorted(gaps), f"intervals should grow, got {gaps}"
    assert gaps[-1] > gaps[0] * 2, f"five correct answers should more than double the gap: {gaps}"


def test_a_missed_question_is_due_again_at_once():
    card = answer_correctly(new_card(now=NOW), at=NOW)
    later = card.due_at

    lapsed = review(card, AGAIN, now=later)

    assert lapsed.due_at <= later
    assert lapsed.lapses == 1


def test_the_question_just_missed_comes_last_in_the_round():
    """Ordering, not a delay, is what stops a question following itself."""
    missed_earlier = review(answer_correctly(new_card(now=NOW), at=NOW), AGAIN, now=NOW)
    missed_now = review(
        answer_correctly(new_card(now=NOW), at=NOW), AGAIN, now=NOW + timedelta(minutes=3)
    )

    assert missed_earlier.due_at < missed_now.due_at


def test_forgetting_undoes_the_progress_that_was_earned():
    card = new_card(now=NOW)
    at = NOW
    for _ in range(4):
        card = answer_correctly(card, at=at)
        at = card.due_at
    settled = card.stability

    lapsed = review(card, AGAIN, now=at)

    assert lapsed.stability < settled
    # The next success starts from the reduced memory, so the card is not
    # instantly back where it was.
    recovered = answer_correctly(lapsed, at=lapsed.due_at)
    assert recovered.due_at - lapsed.due_at < timedelta(days=MAX_INTERVAL_DAYS)


def test_answering_again_the_same_day_earns_far_less_than_waiting():
    first = answer_correctly(new_card(now=NOW), at=NOW)

    crammed = answer_correctly(first, at=NOW + timedelta(minutes=5))
    spaced = answer_correctly(first, at=first.due_at)

    assert crammed.stability < spaced.stability


def test_a_question_the_student_finds_hard_comes_back_sooner():
    card = answer_correctly(new_card(now=NOW), at=NOW)
    at = card.due_at

    hard = review(card, HARD, now=at)
    good = review(card, GOOD, now=at)
    easy = review(card, EASY, now=at)

    assert hard.due_at < good.due_at < easy.due_at
    assert hard.difficulty > good.difficulty > easy.difficulty


def test_recall_decays_as_the_days_pass():
    card = answer_correctly(new_card(now=NOW), at=NOW)

    same_day = retrievability(card, now=NOW)
    a_month_on = retrievability(card, now=NOW + timedelta(days=30))

    assert same_day > a_month_on
    assert 0 < a_month_on < 1


def test_a_card_never_disappears_for_more_than_a_year():
    card = CardState(
        stability=10_000.0,
        difficulty=1.0,
        due_at=NOW,
        last_reviewed_at=NOW - timedelta(days=1),
        reps=99,
        lapses=0,
    )

    reviewed = answer_correctly(card, at=NOW)

    assert reviewed.due_at - NOW <= timedelta(days=MAX_INTERVAL_DAYS)


def test_the_gap_never_collapses_to_nothing():
    assert interval_days(0.0001, requested_retention=0.9) >= 1


def test_asking_for_stronger_recall_shortens_the_gap():
    strict = interval_days(50.0, requested_retention=0.95)
    relaxed = interval_days(50.0, requested_retention=0.8)

    assert strict < relaxed


def test_a_wrong_answer_is_graded_as_a_lapse():
    assert grade_for_answer(correct=False) == AGAIN
    assert grade_for_answer(correct=True) == GOOD


def test_an_unknown_grade_is_refused():
    with pytest.raises(ValueError):
        review(new_card(now=NOW), 7, now=NOW)


def test_difficulty_stays_within_its_bounds_under_repeated_failure():
    card = new_card(now=NOW)
    at = NOW
    for _ in range(30):
        card = review(card, AGAIN, now=at)
        at = card.due_at + timedelta(days=1)

    assert 1.0 <= card.difficulty <= 10.0
    assert card.stability > 0
