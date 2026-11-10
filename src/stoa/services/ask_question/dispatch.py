"""Hand a committed question to whatever answers it (#204, decision 2).

`dispatch` is the seam. Two adapters sit behind it: `LambdaWorker` invokes the
generation worker asynchronously (production, E21), and `in_process` answers
right away in the request (the rollback). A configured, non-blank
`settings.conversation_generation_function_name` picks the worker; without
one the answer is generated in the request, as before the worker existed. This
module is the only place that choice is made.

An adapter returns the answer when it answered now, and `None` when the
question was accepted for answering elsewhere; `submit` reads that and nothing
else.

`override` is the one injection point for tests: set it with `monkeypatch` to
any adapter, for example `LambdaWorker(invoke=recorder)` to record what would
have been sent to the worker.
"""
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from stoa import aws
from stoa.aws import Kind
from stoa import config
from stoa.services.ask_question import _answering
from stoa.services.ask_question._answering import CommittedMessage
from stoa.services.ask_question.models import SendMessageResponse

logger = logging.getLogger(__name__)


class Adapter(Protocol):
    def __call__(
        self, conversation_id: str, idempotency_key: str, committed: CommittedMessage
    ) -> SendMessageResponse | None: ...


override: Adapter | None = None
"""When set, every dispatch goes to this adapter instead of the configured one."""


def dispatch(
    conversation_id: str, idempotency_key: str, committed: CommittedMessage
) -> SendMessageResponse | None:
    """Hand one committed command to whatever answers it.

    The ids are what crosses to an answerer in another process; `committed` is
    what the request already loaded and checked, so the in-process adapter
    answers it without reading it again. Returns the answer when it was given
    now, `None` when the command was accepted for answering elsewhere.
    """
    adapter = override if override is not None else _configured_adapter()
    return adapter(conversation_id, idempotency_key, committed)


def _configured_adapter() -> Adapter:
    return LambdaWorker() if _generation_worker_name() else in_process


def in_process(
    conversation_id: str, idempotency_key: str, committed: CommittedMessage
) -> SendMessageResponse:
    """Generate the answer here, in the request; the rollback (E19)."""
    return _answering.generate_for_command(committed)


def _generation_worker_name() -> str:
    return config.settings().conversation_generation_function_name.strip()


def _invoke_generation_worker(event: dict[str, object]) -> None:
    """Hand one command to the worker; returns once Lambda has queued it."""
    # Bounded well inside the request's 29 seconds (`aws.GENERATION_INVOKE_CONFIG`).
    client = aws.client(Kind.LAMBDA_GENERATION)
    client.invoke(
        FunctionName=_generation_worker_name(),
        InvocationType="Event",
        Payload=json.dumps(event).encode(),
    )


@dataclass(frozen=True)
class LambdaWorker:
    """Accept the question here and have the generation worker answer it (E21).

    The request returns as soon as the message is stored: an answer that takes
    longer than API Gateway's 29 seconds is no longer cut off. `invoke` sends
    the event; left unset it is the asynchronous Lambda invoke.
    """

    invoke: Callable[[dict[str, object]], None] | None = None

    def __call__(
        self, conversation_id: str, idempotency_key: str, committed: CommittedMessage
    ) -> None:
        event: dict[str, object] = {
            "conversation_id": conversation_id,
            "idempotency_key": idempotency_key,
        }
        _answering._reopen_failed_for_retry(conversation_id, idempotency_key, committed)
        try:
            (self.invoke or _invoke_generation_worker)(event)
        except Exception:
            # Not rolled back: the message and its command are stored, and the
            # sweep takes up a command nobody claimed within a minute.
            logger.warning("conversation_generation_invoke_failed", exc_info=True)
        return None
