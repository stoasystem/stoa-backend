"""The types an Ask answer's model call shares with its callers: failure, result, image.

The Ask prompt, and the checks the model's reply goes through, are
`ask_answer`'s (#176, #437); the model is called through `model_call` (#436).
These are the types the asking and the allowance's admission share with it,
and the inventory of who calls InvokeModel under which cost class.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeVar

from stoa.models.allowance import ProviderUsageEvidence


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


class AIInvocationClass(StrEnum):
    """Closed cost attribution class for each direct InvokeModel caller."""

    USER_ALLOWANCE = "user_allowance"
    PROVIDER_COST_ONLY = "provider_cost_only"


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
    invocation_class: AIInvocationClass


def inventory_ai_invocation_classes() -> dict[str, AIInvocationClass]:
    """Return the exhaustive direct InvokeModel caller inventory."""
    return {
        # The Ask answer, through 模型调用 under the allowance's admission (#436).
        # The weekly report goes through it too, without an admission hook, so
        # at provider cost only (#438); the hook decides the class per call.
        "src/stoa/services/model_call/bedrock.py:invoke_model_with_response_stream": (
            AIInvocationClass.USER_ALLOWANCE
        ),
    }
