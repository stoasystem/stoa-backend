"""When a question should come back.

A question answered correctly is worth less the second time and more after a
week, so the gap before it returns has to grow with each success and collapse
after a lapse. This is the FSRS scheduler, which models a card by how long the
memory of it lasts (stability) and how hard it is for this student
(difficulty), then asks for the card again when the chance of recall has fallen
to a target.

The module is deliberately free of storage and clocks: everything it needs
arrives as arguments so the behaviour can be tested exactly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

# FSRS-5 defaults, from the algorithm's published fit over a large review log.
DEFAULT_WEIGHTS: tuple[float, ...] = (
    0.40255, 1.18385, 3.173, 15.69105, 7.1949, 0.5345, 1.4604, 0.0046, 1.54575,
    0.1192, 1.01925, 1.9395, 0.11, 0.29605, 2.2698, 0.2315, 2.9898, 0.51655, 0.6621,
)

DECAY = -0.5
FACTOR = 19 / 81

MIN_DIFFICULTY = 1.0
MAX_DIFFICULTY = 10.0
MIN_STABILITY = 0.01
MAX_INTERVAL_DAYS = 365

# A missed question is due again at once. A student answering three questions
# in two minutes would never reach a delayed one, and the due list is ordered
# oldest-first, so the question just missed arrives at the end of the round
# rather than immediately after itself. Answering it again the same day earns
# little, which is what keeps the second look from inflating the schedule.
RELEARNING_DELAY = timedelta(0)

AGAIN = 1
HARD = 2
GOOD = 3
EASY = 4


@dataclass(frozen=True)
class CardState:
    """What is remembered about one question for one student."""

    stability: float
    difficulty: float
    due_at: datetime
    last_reviewed_at: datetime | None
    reps: int
    lapses: int

    @property
    def is_new(self) -> bool:
        return self.last_reviewed_at is None


def retrievability(state: CardState, *, now: datetime) -> float:
    """The modelled chance of recalling the card right now."""
    if state.last_reviewed_at is None:
        return 1.0
    elapsed_days = max((now - state.last_reviewed_at).total_seconds() / 86400.0, 0.0)
    stability = max(state.stability, MIN_STABILITY)
    return (1 + FACTOR * elapsed_days / stability) ** DECAY


def _clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def _initial_stability(grade: int, weights: tuple[float, ...]) -> float:
    return max(weights[grade - 1], MIN_STABILITY)


def _initial_difficulty(grade: int, weights: tuple[float, ...]) -> float:
    difficulty = weights[4] - math.exp(weights[5] * (grade - 1)) + 1
    return _clamp(difficulty, MIN_DIFFICULTY, MAX_DIFFICULTY)


def _next_difficulty(difficulty: float, grade: int, weights: tuple[float, ...]) -> float:
    delta = -weights[6] * (grade - GOOD)
    damped = difficulty + delta * (10 - difficulty) / 9
    # Difficulty drifts back towards the value an easy first answer implies, so
    # a single bad day does not mark a question hard forever.
    reverted = weights[7] * _initial_difficulty(EASY, weights) + (1 - weights[7]) * damped
    return _clamp(reverted, MIN_DIFFICULTY, MAX_DIFFICULTY)


def _stability_after_recall(
    stability: float, difficulty: float, retention: float, grade: int, weights: tuple[float, ...]
) -> float:
    hard_penalty = weights[15] if grade == HARD else 1.0
    easy_bonus = weights[16] if grade == EASY else 1.0
    growth = (
        math.exp(weights[8])
        * (11 - difficulty)
        * (stability ** -weights[9])
        * (math.exp(weights[10] * (1 - retention)) - 1)
        * hard_penalty
        * easy_bonus
    )
    return max(stability * (1 + growth), MIN_STABILITY)


def _stability_after_lapse(
    stability: float, difficulty: float, retention: float, weights: tuple[float, ...]
) -> float:
    lapsed = (
        weights[11]
        * (difficulty ** -weights[12])
        * (((stability + 1) ** weights[13]) - 1)
        * math.exp(weights[14] * (1 - retention))
    )
    # Forgetting must never leave the memory stronger than it already was.
    return max(min(lapsed, stability), MIN_STABILITY)


def _stability_same_day(stability: float, grade: int, weights: tuple[float, ...]) -> float:
    adjusted = stability * math.exp(weights[17] * (grade - 3 + weights[18]))
    return max(adjusted, MIN_STABILITY)


def interval_days(stability: float, *, requested_retention: float) -> int:
    """How many days until recall decays to the retention we are willing to accept."""
    raw = (stability / FACTOR) * ((requested_retention ** (1 / DECAY)) - 1)
    return int(_clamp(round(raw), 1, MAX_INTERVAL_DAYS))


def new_card(*, now: datetime) -> CardState:
    """A question this student has not answered yet, due immediately."""
    return CardState(
        stability=MIN_STABILITY,
        difficulty=_initial_difficulty(GOOD, DEFAULT_WEIGHTS),
        due_at=now,
        last_reviewed_at=None,
        reps=0,
        lapses=0,
    )


def review(
    state: CardState,
    grade: int,
    *,
    now: datetime,
    requested_retention: float = 0.9,
    weights: tuple[float, ...] = DEFAULT_WEIGHTS,
) -> CardState:
    """Fold one answer into the card and say when it should come back."""
    if grade not in (AGAIN, HARD, GOOD, EASY):
        raise ValueError(f"grade must be 1-4, got {grade}")

    if state.is_new:
        stability = _initial_stability(grade, weights)
        difficulty = _initial_difficulty(grade, weights)
    else:
        retention = retrievability(state, now=now)
        difficulty = _next_difficulty(state.difficulty, grade, weights)
        same_day = state.last_reviewed_at is not None and (
            now - state.last_reviewed_at
        ) < timedelta(days=1)
        if same_day:
            # A second look within the day rehearses the card rather than
            # testing it, so it earns far less than a spaced success.
            stability = _stability_same_day(state.stability, grade, weights)
        elif grade == AGAIN:
            stability = _stability_after_lapse(
                state.stability, difficulty, retention, weights
            )
        else:
            stability = _stability_after_recall(
                state.stability, difficulty, retention, grade, weights
            )

    if grade == AGAIN:
        due_at = now + RELEARNING_DELAY
    else:
        due_at = now + timedelta(days=interval_days(stability, requested_retention=requested_retention))

    return CardState(
        stability=stability,
        difficulty=difficulty,
        due_at=due_at,
        last_reviewed_at=now,
        reps=state.reps + 1,
        lapses=state.lapses + (1 if grade == AGAIN and not state.is_new else 0),
    )


def grade_for_answer(*, correct: bool) -> int:
    """The platform asks for an answer, not for how hard it felt."""
    return GOOD if correct else AGAIN
