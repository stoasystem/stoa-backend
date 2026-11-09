"""A question: what a student asks once in a learning session, until its Ask answer is stored.

The package is being moved here from `routers/conversations.py`,
`attachment_repo` and `jobs/conversation_generation.py` in four steps (#204).
Step 1 (#217) moved the rows the question keeps (`_store`); step 2 (#218)
moved the request half and the answering here; step 3 (#219) moved the
worker's sweep (`_sweep`). The entry points:

- `submit` takes a student's message from the route that authorized it and
  returns `Answered` (the answer, generated in the request) or `Accepted` (the
  message is stored and its answer is on its way). A first send and a replay
  of the same key go through it alike.
- `answer` is the worker's: it takes one committed command to its answer, and
  is safe to call again for the same command.
- `progress` is where a command stands, for `GET /conversations/{id}/generation`.
- `sweep` is the Scheduler's: it answers what the direct invocation missed and
  settles what nothing else will, and returns a `SweepSummary`.
- `cancel_for_account_deletion` is account deletion's: it cancels a command
  still active when the account's private rows are scrubbed.

Who answers a committed command is `dispatch`'s to decide. A question's own
failures carry an `AskQuestionErrorCode`.
"""
import logging
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timezone

from stoa.security.attachment_errors import AttachmentDecisionError
from stoa.security.identity import Actor
from stoa.services.ask_question import _answering, _store, _sweep, dispatch
from stoa.services.ask_question._replay import _conversation_repository_call
from stoa.services.ask_question_errors import AskQuestionErrorCode
from stoa.services.ask_question.models import (
    ChatMessage,
    GenerationProgressResponse,
    MessageAcceptedResponse,
    SendMessageRequest,
    SendMessageResponse,
)
from stoa.services.learning_session import conversation_grade, required_conversation_text

logger = logging.getLogger(__name__)

Answered = SendMessageResponse
"""已回答: the answer was generated in the request (200)."""

Accepted = MessageAcceptedResponse
"""已受理: the message is stored and the worker answers it (202)."""

SweepSummary = _sweep.SweepSummary
"""What one `sweep` run did, counted by outcome."""


def submit(
    actor: Actor,
    conversation: Mapping[str, object],
    body: SendMessageRequest,
    fingerprint: str,
    *,
    conversation_id: str,
    student_id: str,
    practice_context: Mapping[str, object] | None = None,
    new_conversation_generation: int | None = None,
) -> Answered | Accepted:
    """Commit the student's message, then answer it here or hand it over.

    `actor` and `conversation` are what the route authorized; `fingerprint` is
    the request's (`message_request_fingerprint`), compared against a stored
    command before anything else is read; `practice_context` is the exercise
    the route already resolved. A command already stored under this key is
    replayed, waited for or resumed instead of claimed again.

    `new_conversation_generation` is set only for the first message of a
    conversation created in the same request, under that account fence
    generation: no command can precede it, so none is read.

    Raises `AttachmentDecisionError` (the weekly allowance's refusals among
    them, as `_admission.AdmissionError`); the route maps it.
    """
    # A record the conversation cannot be read back from is refused before
    # anything is read or written, as reading it would be.
    subject = required_conversation_text(conversation, "subject")
    grade = conversation_grade(conversation)
    command_context: dict[str, object] = {
        "actor": actor,
        "fingerprint": fingerprint,
        "existing": None,
        "practice_context": practice_context,
    }
    if new_conversation_generation is not None:
        command_context["account_fence_generation"] = new_conversation_generation
    else:
        state = _conversation_repository_call(
            lambda: _store.read_message_command_result(
                conversation_id,
                body.idempotencyKey,
                owner_id=actor.user_id,
                fingerprint=fingerprint,
                now_epoch=int(datetime.now(timezone.utc).timestamp()),
            )
        )
        if state.disposition is _store.MessageCommandDisposition.IDEMPOTENCY_CONFLICT:
            raise AttachmentDecisionError(AskQuestionErrorCode.MESSAGE_IDEMPOTENCY_CONFLICT)
        command_context["state"] = state
        command_context["existing"] = state.command
    committed = _answering.commit_message_command(
        conv_id=conversation_id,
        student_id=student_id,
        subject=subject,
        grade=grade,
        body=body,
        command_context=command_context,
    )
    if isinstance(committed, SendMessageResponse):
        return committed
    answered = dispatch.dispatch(conversation_id, body.idempotencyKey, committed)
    if answered is not None:
        return answered
    command = committed.command
    return MessageAcceptedResponse(
        conversationId=conversation_id,
        commandId=str(command["command_id"]),
        idempotencyKey=body.idempotencyKey,
        studentMessage=ChatMessage(
            id=str(command["student_message_id"]),
            conversationId=conversation_id,
            role="student",
            content=committed.content,
            createdAt=str(command["created_at"]),
            status="sent",
            attachments=committed.attachments,
            quote=committed.quote,
        ),
    )


def answer(conversation_id: str, idempotency_key: str) -> str:
    """Take one command to its answer if it still needs one.

    Returns `completed`, `failed` (the command says why), `held` (another
    delivery holds its lease), `settled` (it needs nothing) or `missing`.
    Safe on redelivery: the lease is claimed conditionally, so a duplicate
    finds it held or the answer stored and leaves.
    """
    command = _store.get_message_command(conversation_id, idempotency_key)
    if not isinstance(command, dict):
        return "missing"
    if command.get("status") == "failed":
        # Whether it may be tried again is the student's to act on, with the
        # same key (the request reopens it); a late or repeated delivery must
        # not spend their attempts.
        return "settled"
    fingerprint = command.get("fingerprint")
    owner_id = command.get("owner_id")
    if not isinstance(fingerprint, str) or not isinstance(owner_id, str):
        return "settled"
    state = _store.classify_message_command(
        command,
        owner_id=owner_id,
        fingerprint=fingerprint,
        now_epoch=int(datetime.now(UTC).timestamp()),
    )
    if state.disposition is _store.MessageCommandDisposition.LEASE_HELD:
        return "held"
    if state.disposition is not _store.MessageCommandDisposition.RESUME:
        return "settled"
    try:
        committed = _answering.load_committed_message(command)
        _answering.generate_for_command(committed)
    except AttachmentDecisionError as error:
        if error.code is AskQuestionErrorCode.MESSAGE_IN_PROGRESS:
            return "held"
        logger.warning("conversation_generation_failed code=%s", error.code.value)
        return "failed"
    return "completed"


def progress(
    conversation_id: str, idempotency_key: str | None, student_id: str
) -> GenerationProgressResponse:
    """Where an answer stands, for the student who asked.

    Without a key, the conversation's latest steps. With one, the command it
    names too, with only the steps its current attempt wrote; a key that names
    no command of this student raises `AttachmentDecisionError`
    (`MESSAGE_COMMAND_NOT_FOUND`).
    """
    if idempotency_key is None:
        steps, updated_at = _store.read_generation_progress(
            conversation_id, owner_id=student_id
        )
        return GenerationProgressResponse(
            conversationId=conversation_id, steps=steps, updatedAt=updated_at
        )
    command = _conversation_repository_call(
        lambda: _store.get_message_command(conversation_id, idempotency_key)
    )
    state = (
        _answering._command_generation_state(conversation_id, command)
        if isinstance(command, dict) and command.get("owner_id") == student_id
        else None
    )
    if state is None:
        raise AttachmentDecisionError(AskQuestionErrorCode.MESSAGE_COMMAND_NOT_FOUND)
    state.steps, state.updatedAt = _store.read_generation_progress(
        conversation_id,
        owner_id=student_id,
        command_id=state.commandId,
        attempt=state.attempt,
    )
    return state


def sweep(remaining_seconds: Callable[[], float | None]) -> SweepSummary:
    """Answer what nobody claimed and what a dead attempt left; settle what is due.

    `remaining_seconds` returns how much of the invocation is left (`None`
    when unknown). It is read again before each command, and each answer's
    runtime budget is bound to it; each command is answered through `answer`.
    """
    return _sweep.sweep(remaining_seconds, answer)


def cancel_for_account_deletion(
    row: dict[str, object],
    *,
    owner_id: str,
    deletion_generation: int,
    now_iso: str,
) -> bool:
    """Cancel `row` if it is a command still active, as account deletion scans it.

    Returns whether it was canceled; any other private row is the caller's.
    A command of another owner is refused (`AttachmentRepositoryConflict`).
    """
    if (
        row.get("entity_type") != "message_command"
        or row.get("status") not in _store.CONVERSATION_ACTIVE_COMMAND_STATES
    ):
        return False
    _store.cancel_stale_message_command(
        row,
        owner_id=owner_id,
        deletion_generation=deletion_generation,
        now_iso=now_iso,
    )
    return True
