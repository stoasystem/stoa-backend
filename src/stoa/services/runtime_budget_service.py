"""How much of the request's life is left for work that must finish inside it.

The API runs in a Lambda that API Gateway stops waiting on at 29 seconds. A
budget counted from the moment a piece of work starts, rather than from when the
request arrived, overruns that without anyone noticing; so the start of the
request and the time the Lambda reported left at that moment are bound here for
the length of the request, the way `locale_service` binds the answer language.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class _RequestBudget:
    started_monotonic: float | None
    remaining_seconds: float | None


_REQUEST_BUDGET: ContextVar[_RequestBudget] = ContextVar(
    "stoa_request_budget", default=_RequestBudget(None, None)
)


def begin_request(
    *, started_monotonic: float | None, remaining_seconds: float | None
) -> None:
    """Bind when the request started and what the Lambda had left then."""
    _REQUEST_BUDGET.set(_RequestBudget(started_monotonic, remaining_seconds))


def ai_deadline(
    *,
    fixed_seconds: float,
    reserve_seconds: float,
    clock: Callable[[], float] = time.monotonic,
) -> float:
    """The monotonic time an AI call must be done by.

    Never later than the fixed budget, and never later than the Lambda's own
    end less the time kept back to store the result. Without a Lambda context
    - locally, in tests - the fixed budget applies, from the request's start
    when that is known and from now otherwise.
    """
    bound = _REQUEST_BUDGET.get()
    started = bound.started_monotonic if bound.started_monotonic is not None else clock()
    budget = fixed_seconds
    if bound.remaining_seconds is not None:
        budget = min(budget, bound.remaining_seconds - reserve_seconds)
    return started + max(budget, 0.0)
