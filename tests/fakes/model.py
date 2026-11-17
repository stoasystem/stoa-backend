"""The model the Ask tests run on (#176, #436).

`FakeModel` is the in-memory model-call adapter (`model_call.fake.FakeAdapter`,
which holds every request to the rules measured against Bedrock) answering with
an Ask answer by default, `ANSWER`. `install(model)` puts it where the model
call finds it. See `FakeAdapter` for the outcomes a test can script.

Only the provider is stood in for: the prompt, the request, the reply's checks
and the allowance's admission run as production runs them.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from stoa.services import ask_answer, model_call
from stoa.services.model_call.fake import INPUT_TOKENS, FakeAdapter, Prose, Reply, Unsent

ANSWER: dict[str, Any] = {
    "language": "de",
    "steps": ["Zähler und Nenner durch den ggT teilen"],
    "answer": "So kürzt man einen Bruch.",
    "hints": ["Was ist der ggT von 6 und 8?"],
    "similar_exercises": [],
    "knowledge_points": ["Brüche kürzen"],
    "suggest_teacher": False,
}


class FakeModel(FakeAdapter):
    def __init__(self, *outcomes: Any, answer: Any = None, **kwargs: Any) -> None:
        super().__init__(*outcomes, answer=ANSWER if answer is None else answer, **kwargs)


def install(model: FakeAdapter) -> FakeAdapter:
    """Install `model` as the model-call adapter and hand it back."""
    model_call.install(model)
    return model


def asking(model: FakeAdapter, **call: Any) -> ask_answer.ModelCall:
    """Install `model` and say how an answer is asked of it: 90 seconds from now, unless `call` says."""
    install(model)
    call.setdefault("deadline_monotonic", time.monotonic() + 90)
    return ask_answer.ModelCall(**call)


def not_sent(monkeypatch: pytest.MonkeyPatch, *categories: str) -> None:
    """The next model calls end unsent, retryably, under `categories`, one per call.

    Each is admitted first, as a call that ran out of time after admission is;
    once they are used up, calls reach the installed model again.
    """
    real = model_call.call
    left = list(categories)

    def call(**kwargs: Any) -> model_call.Result:
        if not left:
            return real(**kwargs)
        category = left.pop(0)
        admission = kwargs.get("admission")
        if admission is not None:
            decision = admission(INPUT_TOKENS, kwargs["max_tokens"])
            if isinstance(decision, model_call.Refuse):
                return model_call.NotSent(decision.category, retryable=True, detail=decision.detail)
        return model_call.NotSent(category, retryable=True)

    monkeypatch.setattr(model_call, "call", call)


__all__ = [
    "ANSWER",
    "FakeModel",
    "Prose",
    "Reply",
    "Unsent",
    "asking",
    "install",
    "not_sent",
]
