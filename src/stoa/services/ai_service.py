"""The types an Ask answer's model call shares with its callers: failure, result, image.

The Ask prompt, and the checks the model's reply goes through, are
`ask_answer`'s (#176, #437); the model is called through `model_call` (#436).
These are the types the asking and the allowance's admission share with it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from stoa.models.allowance import ProviderUsageEvidence
from stoa.services.model_call import CostClass


class AIInvocationFailure(Exception):
    """Closed model-boundary failure without provider diagnostics.

    `usage` is set when the provider did answer and was paid for, but the
    answer cannot be used, so the caller can still account for the cost and
    release the student's reservation. `retryable` says whether the same
    answer may be asked for again, as the model call decided it: never once a
    reply was paid for. `detail` is for diagnostics only.
    """

    def __init__(
        self,
        category: str,
        *,
        usage: ProviderUsageEvidence | None = None,
        retryable: bool | None = None,
        detail: str | None = None,
    ):
        self.category = category
        self.usage = usage
        self.retryable = (usage is None) if retryable is None else retryable
        self.detail = detail
        super().__init__(category)


@dataclass(frozen=True, slots=True)
class PromptImage:
    """One image the student attached, handed to the model as it is (#135)."""

    media_type: str
    data: bytes


AIContent = TypeVar("AIContent")


@dataclass(frozen=True, slots=True)
class AIProviderResult(Generic[AIContent]):
    """Validated content separated from immutable, content-free usage evidence."""

    content: AIContent
    usage: ProviderUsageEvidence
    model_id: str
    inference_profile_id: str
    provider_message_id_digest: str
    stop_reason: str
    # Whether the answer was admitted against an allowance (#439).
    invocation_class: CostClass
