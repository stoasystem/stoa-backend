"""Commit a question, answer it, replay it; its allowance goes through `_admission`.

Moved from `routers/conversations.py` (#218). Function bodies are as they were
there; the router now reaches them through the package's entry points.
"""
import functools
import json
import logging
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from stoa import aws
from stoa.aws import Kind
from stoa import config
from stoa.db import table as db_table
from stoa.db.dynamodb import stored_int
from stoa.db.repositories import (
    asked_knowledge_repo,
    knowledge_gap_repo,
    user_repo,
)
from stoa.models.attachment import AttachmentSummary
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.security.identity import Actor
from stoa.security.private_telemetry import emit_private_event
from stoa.services import (
    adaptive_learning_service,
    ai_service,
    ask_answer,
    attachment_service,
    curriculum_service,
    learning_profile_service,
    locale_service,
    runtime_budget_service,
)
from stoa.services.adaptive_learning_service import actor_projection
from stoa.services.ask_question import _admission
from stoa.services.ask_question import _store as ask_question_store
from stoa.services.ask_question._admission import AdmissionError, UsageEvidence
from stoa.services.ask_question._replay import (
    _conversation_repository_call,
    _stored_student_message,
)
from stoa.services.ask_question_errors import AskQuestionErrorCode, parse_error_code
from stoa.services.ask_question.models import (
    ChatMessage,
    GenerationProgressResponse,
    MessageQuote,
    SendMessageRequest,
    SendMessageResponse,
    _quote_payload,
    structured_payload,
    target_unit,
)
from stoa.services import learning_session
from stoa.services.learning_session import (
    DynamoConversationTable,
    active_conversation_generation,
    conversation_grade,
)

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── AI message allowance ──────────────────────────────────────────────────────
# Admission and what the answer is charged are `_admission`'s (#240, #241);
# what stays here is where the usage evidence is kept beside the answer.

def _message_result_json(
    response: SendMessageResponse,
    evidence: UsageEvidence | None,
) -> str:
    payload = response.model_dump(mode="json", by_alias=True)
    if evidence is not None:
        payload["_allowance"] = evidence.to_json()
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _usage_evidence_from_command(
    command: Mapping[str, object],
) -> UsageEvidence | None:
    result_json = command.get("result_json")
    if not isinstance(result_json, str) or not result_json:
        return None
    try:
        payload = json.loads(result_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, Mapping):
        return None
    return UsageEvidence.from_json(payload.get("_allowance"))


GENERATION_PROGRESS_TTL_SECONDS = 3600


def _publish_generation_step(
    conv_id: str,
    student_id: str,
    *,
    command_id: str | None = None,
    attempt: int | None = None,
):
    """Publish each finished step so the student can read the answer forming.

    Progress is held per conversation and carries when it was written and which
    command and attempt wrote it, so a reader can tell this answer's steps from
    the previous answer's.
    """
    delivered: list[str] = []

    def publish(index: int, step: str) -> None:
        if index != len(delivered):
            return
        delivered.append(step)
        ask_question_store.record_generation_progress(
            conv_id,
            owner_id=student_id,
            steps=list(delivered),
            now_iso=_now(),
            expires_at=int(datetime.now(timezone.utc).timestamp())
            + GENERATION_PROGRESS_TTL_SECONDS,
            command_id=command_id,
            attempt=attempt,
        )

    return publish


def _command_generation_state(
    conv_id: str, command: Mapping[str, object]
) -> GenerationProgressResponse | None:
    """Project a stored command onto the four states a reader is told about.

    `claimed` reads as `message_committed`: both are waiting for an answer, and
    the student's message becomes visible in the same transaction that leaves
    `claimed`. Commands written before E19 carry none of the failure fields and
    read the same way.
    """
    stored_status = command.get("status")
    state = GenerationProgressResponse(
        conversationId=conv_id,
        commandId=str(command.get("command_id") or ""),
        attempt=stored_int(command.get("attempt")) or 0,
    )
    if stored_status == "claimed" and (
        stored_int(command.get("expires_at")) or 0
    ) <= int(datetime.now(timezone.utc).timestamp()):
        stored_status = "expired"
    if stored_status in {"claimed", "message_committed"}:
        state.status = "message_committed"
    elif stored_status == "ai_running":
        state.status = "ai_running"
    elif stored_status == "completed":
        state.status = "completed"
        state.assistantMessageId = str(command.get("assistant_message_id") or "")
    elif stored_status == "failed":
        state.status = "failed"
        state.failureCategory = str(command.get("failure_category") or "unknown")
        state.retryable = ask_question_store.failed_command_can_retry(command)
    elif stored_status in {"terminal_failed", "rejected", "expired"}:
        state.status = "failed"
        state.failureCategory = {
            "terminal_failed": "attempts_exhausted",
            "rejected": str(command.get("error_code") or "rejected"),
            "expired": "expired",
        }[str(stored_status)]
        state.retryable = False
    else:
        return None
    return state


_MESSAGE_POLL_ATTEMPTS = 20
_MESSAGE_POLL_SECONDS = 0.05
# No shorter than the generation sweep's 5-minute period: a lease that ran out
# between two runs would otherwise be taken over while its attempt still runs.
_AI_LEASE_SECONDS = 300
_AI_INVOCATION_DEADLINE_SECONDS = 90
# Kept back from the Lambda's remaining time to store the answer and respond.
_AI_PERSIST_RESERVE_SECONDS = 4


def _answer_subject(stored: object) -> str:
    """The subject an answer is generated for: the canonical id, read through
    the one subject entry point (#354).

    A conversation's subject is checked when it is opened; one stored before
    that, naming a subject the platform does not teach, is "" - answered as no
    particular subject - never guessed as math, and its text never reaches
    the prompt.
    """
    return curriculum_service.subject_id(stored) or ""

_MAX_MEMORY_TOPICS = 8


# The hint label is added around the model output, so it has to be translated here
# or the answer comes back with one German word in it.
def _memory_context_for_student(student_id: str, actor: Actor, subject: str) -> str | None:
    """Summarise the student's weak topics for AI personalisation.

    Returns None when there is nothing to personalise on, or when the lookup
    fails — an answer without memory is far better than no answer at all.
    """
    try:
        memory_summary = adaptive_learning_service.get_memory_summary(
            student_id=student_id,
            user=actor_projection(actor),
            subject=_answer_subject(subject),
            persist=False,
        )
        labels: list[str] = []
        for topic in memory_summary.get("weakTopics", []):
            if not isinstance(topic, Mapping):
                continue
            label = str(topic.get("label") or topic.get("topicId") or "").strip()
            if label:
                labels.append(label)
        if not labels:
            return None
        unique_topics = list(dict.fromkeys(labels))[:_MAX_MEMORY_TOPICS]
        return "Known weak topics for this student: " + ", ".join(unique_topics) + "."
    except (AttributeError, TypeError, KeyError):
        # A bad call signature or response shape is a defect, not a runtime
        # condition — surface it instead of silently dropping personalisation.
        logger.exception("memory_context_contract_error")
        return None
    except Exception:
        logger.warning("memory_context_fetch_failed", exc_info=True)
        return None


def _student_locale(student_id: str) -> str:
    """Resolve the student's display language, defaulting to German on lookup failure.

    The language the student is reading the app in right now arrives on the
    request, so it wins over the stored preference. For an Ask answer it is only
    the default: the model answers in the language the student writes in, or
    asks for, and falls back to this one when it cannot tell (#174).

    The policy itself lives in `locale_service.reader_locale`; this keeps the
    name the rest of the module calls it by (#124).
    """
    return locale_service.reader_locale(student_id)


def _student_answer_style(student_id: str) -> str:
    """The answer style on the student's profile now, `standard` on lookup failure.

    Read afresh for every question, unlike the grade, which a conversation
    keeps from its start: a student who changes their style has the very next
    question answered in it (#314). A style is never worth a failed question.
    """
    try:
        profile = user_repo.get_user(student_id)
    except Exception:  # noqa: BLE001 - an answer in the standard style beats none
        logger.warning("student_answer_style_fetch_failed", exc_info=True)
        profile = None
    return learning_profile_service.answer_style_code((profile or {}).get("answer_style"))


def _completed_command_response(command: dict) -> SendMessageResponse | None:
    if command.get("status") != "completed" or not command.get("result_json"):
        return None
    try:
        response = SendMessageResponse.model_validate_json(str(command["result_json"]))
    except (ValueError, TypeError):
        return None
    if (
        response.studentMessage.id != command.get("student_message_id")
        or response.assistantMessage.id != command.get("assistant_message_id")
        or response.studentMessage.conversationId != command.get("conversation_id")
        or response.assistantMessage.conversationId != command.get("conversation_id")
        or response.studentMessage.role != "student"
        or response.assistantMessage.role != "assistant"
    ):
        return None
    return response


def _command_error_code(
    result: ask_question_store.MessageCommandResult,
) -> AskQuestionErrorCode | AttachmentErrorCode:
    disposition = result.disposition
    if disposition is ask_question_store.MessageCommandDisposition.REJECTED:
        try:
            code = parse_error_code(str(result.error_code))
        except ValueError:
            return AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
        if code in {
            AskQuestionErrorCode.MESSAGE_IN_PROGRESS,
            AskQuestionErrorCode.MESSAGE_IDEMPOTENCY_CONFLICT,
            AskQuestionErrorCode.MESSAGE_DAILY_LIMIT,
        }:
            return AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
        return code
    return {
        ask_question_store.MessageCommandDisposition.QUOTA_EXCEEDED: (
            AskQuestionErrorCode.MESSAGE_DAILY_LIMIT
        ),
        ask_question_store.MessageCommandDisposition.IDEMPOTENCY_CONFLICT: (
            AskQuestionErrorCode.MESSAGE_IDEMPOTENCY_CONFLICT
        ),
        ask_question_store.MessageCommandDisposition.RETRYABLE: (
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
        ),
        ask_question_store.MessageCommandDisposition.TERMINAL: (
            AskQuestionErrorCode.MESSAGE_FAILED
        ),
        ask_question_store.MessageCommandDisposition.EXPIRED: (
            AskQuestionErrorCode.MESSAGE_COMMAND_EXPIRED
        ),
        ask_question_store.MessageCommandDisposition.MISSING: (
            AskQuestionErrorCode.MESSAGE_COMMAND_NOT_FOUND
        ),
    }.get(disposition, AskQuestionErrorCode.MESSAGE_IN_PROGRESS)


def _result_response(
    result: ask_question_store.MessageCommandResult,
) -> SendMessageResponse | None:
    if result.disposition is not ask_question_store.MessageCommandDisposition.COMPLETED:
        return None
    command = result.command or {}
    response = _completed_command_response(command)
    if response is None:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    evidence = _usage_evidence_from_command(command)
    if evidence is not None:
        _admission.meter(command).finalize(evidence)
    return response


def _coerce_command_result(value: object) -> ask_question_store.MessageCommandResult:
    """A command transition's result; anything that is not one is retryable."""
    if isinstance(value, ask_question_store.MessageCommandResult):
        return value
    return ask_question_store.MessageCommandResult(
        ask_question_store.MessageCommandDisposition.RETRYABLE
    )


def _wait_for_message_command(
    conversation_id: str,
    idempotency_key: str,
    fingerprint: str,
    *,
    table,
    owner_id: str | None = None,
) -> SendMessageResponse:
    last = ask_question_store.MessageCommandResult(
        ask_question_store.MessageCommandDisposition.MISSING
    )
    for _ in range(_MESSAGE_POLL_ATTEMPTS):
        command = _conversation_repository_call(
            lambda: ask_question_store.get_message_command(
                conversation_id, idempotency_key, table=table
            )
        )
        last = ask_question_store.classify_message_command(
            command,
            owner_id=owner_id or str((command or {}).get("owner_id") or ""),
            fingerprint=fingerprint,
            now_epoch=int(datetime.now(timezone.utc).timestamp()),
        )
        if response := _result_response(last):
            return response
        if last.disposition not in {
            ask_question_store.MessageCommandDisposition.CLAIMED,
            ask_question_store.MessageCommandDisposition.RESUME,
            ask_question_store.MessageCommandDisposition.LEASE_HELD,
        }:
            raise AttachmentDecisionError(_command_error_code(last))
        time.sleep(_MESSAGE_POLL_SECONDS)
    emit_private_event(
        "message_replay_wait_exhausted",
        correlation_id=str((last.command or {}).get("command_id") or "message-command"),
        level=logging.WARNING,
    )
    raise AttachmentDecisionError(AskQuestionErrorCode.MESSAGE_IN_PROGRESS)


def _validate_replay_command(
    command: Any,
    *,
    conversation_id: str,
    owner_id: str,
    idempotency_key: str,
    fingerprint: str,
) -> dict:
    if not isinstance(command, dict):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    expected_command_id = str(
        uuid5(
            NAMESPACE_URL,
            f"stoa.conversation.send.v1:{conversation_id}:{idempotency_key}",
        )
    )
    expected_student_id = str(uuid5(UUID(expected_command_id), "student-message"))
    expected_assistant_id = str(uuid5(UUID(expected_command_id), "assistant-message"))
    history_ids = command.get("history_message_ids")
    deterministic_ids = command.get("deterministic_attachment_ids")
    requested = command.get("requested_attachments")
    history_fingerprint = command.get("history_fingerprint")
    if (
        command.get("entity_type") != "message_command"
        or command.get("schema_version") != "message-command.v2"
        or command.get("command_id") != expected_command_id
        or command.get("conversation_id") != conversation_id
        or command.get("owner_id") != owner_id
        or command.get("idempotency_key") != idempotency_key
        or command.get("fingerprint") != fingerprint
        or command.get("student_message_id") != expected_student_id
        or command.get("assistant_message_id") != expected_assistant_id
        or command.get("history_anchor_message_id") != expected_student_id
        or command.get("status")
        not in {
            "claimed",
            "message_committed",
            "ai_running",
            "failed",
            "completed",
            "rejected",
            "terminal_failed",
            "expired",
        }
        or not isinstance(history_ids, list)
        or any(not isinstance(value, str) or not value for value in history_ids)
        or len(set(history_ids)) != len(history_ids)
        or not isinstance(history_fingerprint, str)
        or len(history_fingerprint) != 64
        or any(value not in "0123456789abcdef" for value in history_fingerprint)
        or not isinstance(deterministic_ids, list)
        or any(not isinstance(value, str) or not value for value in deterministic_ids)
        or len(set(deterministic_ids)) != len(deterministic_ids)
        or not isinstance(requested, list)
        or (stored_count := stored_int(command.get("attachment_count"))) is None
        or stored_count < 0
        or stored_count != len(requested)
        or not isinstance(command.get("created_at"), str)
        or not command["created_at"]
        or not isinstance(command.get("history_anchor_created_at"), str)
        or command["history_anchor_created_at"] != command["created_at"]
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return command


def _reopen_failed_for_retry(
    conv_id: str, idempotency_key: str, committed: "CommittedMessage"
) -> None:
    """Put a failed command the student sent again back to waiting, before handing it off."""
    command = committed.command
    student_id = str(command["owner_id"])
    if command.get("status") == "failed":
        # The student's retry of a failed answer. Back to waiting before the
        # request returns: the chat reads that while the answer is on its way
        # (not the old failure), and the sweep takes it up if this invoke is
        # lost. Only the student reopens a failure, never a redelivered event.
        attempt = stored_int(command.get("attempt"))
        if attempt is not None:
            _conversation_repository_call(
                lambda: ask_question_store.reopen_failed_message_command(
                    conversation_id=conv_id,
                    idempotency_key=idempotency_key,
                    owner_id=student_id,
                    attempt=attempt,
                    now_iso=_now(),
                )
            )


@dataclass(frozen=True)
class CommittedMessage:
    """A command whose student message and quota claim are stored.

    `command` carries the generation context; the rest was loaded against the
    command while committing, so generating does not read it twice.
    """

    command: dict
    account_fence_generation: int
    content: str
    prior_messages: list[dict]
    prepared: list
    attachments: list[AttachmentSummary]
    quote: MessageQuote | None = None


def _resolve_generation_context(
    student_id: str,
    actor: Actor,
    subject: str,
    grade: str,
    practice_context: dict[str, object] | None = None,
) -> dict[str, object]:
    """What the answer depends on that only the request knows, resolved once.

    The practice context rides here rather than being looked up again when the
    answer is generated: the worker would otherwise read whatever the
    curriculum and the student's attempts say by then, not what they said when
    the question was asked. So does the answer style: a style changed after the
    question was sent does not reach its answer.

    `answer_style` was added without a new schema version: it is optional, and
    every reader takes a missing or unknown one as `standard` (#314).
    """
    return {
        "schema_version": "generation-context.v1",
        "locale": _student_locale(student_id),
        "subject": _answer_subject(subject),
        "grade": grade,
        "memory_context": _memory_context_for_student(student_id, actor, subject),
        "practice_context": practice_context,
        "answer_style": _student_answer_style(student_id),
    }


def _generation_context_without_request(
    student_id: str, conversation: Mapping[str, object] | None
) -> dict[str, object]:
    """The context for a command committed before it was stored with one.

    The worker has no request: the language is the student's stored
    preference, and the weak topics are left out, because reading them needs
    the student's own authorisation. It carries no answer style, so the answer
    is given in `standard`, as it would have been when the command was sent.
    """
    try:
        profile = user_repo.get_user(student_id)
    except Exception:
        logger.warning("student_locale_fetch_failed", exc_info=True)
        profile = None
    conversation = conversation or {}
    return {
        "schema_version": "generation-context.v1",
        "locale": locale_service.effective_locale(profile),
        "subject": _answer_subject(conversation.get("subject")),
        "grade": conversation_grade(conversation),
        "memory_context": None,
        "practice_context": None,
    }


def load_committed_message(command: dict) -> CommittedMessage:
    """Rebuild a committed command from the store alone, for the worker.

    The same checks a resuming request makes, without the request: the
    command's identity, its history snapshot, the stored student message and
    its attachments. A command without its generation context is given one.
    """
    table = cast(DynamoConversationTable, db_table.table())
    conv_id = str(command.get("conversation_id") or "")
    student_id = str(command.get("owner_id") or "")
    command = _validate_replay_command(
        command,
        conversation_id=conv_id,
        owner_id=student_id,
        idempotency_key=str(command.get("idempotency_key") or ""),
        fingerprint=str(command.get("fingerprint") or ""),
    )
    generation = stored_int(command.get("account_fence_generation"))
    if generation is None or generation < 1:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    prior_messages = _conversation_repository_call(
        lambda: learning_session.anchored_history(
            conv_id,
            owner_id=student_id,
            message_ids=command["history_message_ids"],
            fingerprint=command["history_fingerprint"],
        )
    )
    content, prepared, attachments, quote = _stored_student_message(
        conv_id=conv_id,
        student_id=student_id,
        student_msg_id=str(command["student_message_id"]),
        created_at=str(command["created_at"]),
        expected_content=None,
        table=table,
    )
    if not isinstance(command.get("generation_context"), Mapping):
        context = _generation_context_without_request(
            student_id, _conversation_repository_call(lambda: learning_session.read(conv_id))
        )
        command["generation_context"] = _conversation_repository_call(
            lambda: ask_question_store.record_message_generation_context(
                conversation_id=conv_id,
                idempotency_key=str(command["idempotency_key"]),
                owner_id=student_id,
                context=context,
                table=table,
            )
        )
    return CommittedMessage(
        command=command,
        account_fence_generation=generation,
        content=content,
        prior_messages=prior_messages,
        prepared=prepared,
        attachments=attachments,
        quote=quote,
    )


def _stored_provider_result(
    command: Mapping[str, object], attempt: int
) -> tuple[ask_answer.AskAnswer, UsageEvidence | None] | None:
    """The answer a lost attempt kept on the command, and its usage, if it kept any."""
    raw = command.get("provider_result_json")
    if stored_int(command.get("provider_result_attempt")) != attempt or not isinstance(raw, str):
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, Mapping):
        return None
    answer = ask_answer.AskAnswer.from_json(payload.get("answer"))
    if answer is None:
        return None
    stored = payload.get("allowance")
    evidence = UsageEvidence.from_json(stored)
    if stored is not None and evidence is None:
        return None
    return answer, evidence


def _record_generation_failure(
    command: Mapping[str, object],
    *,
    table: object,
    lease_owner: str,
    lease_attempt: int | None,
    category: str,
    retryable: bool,
) -> None:
    """End the attempt as failed on the command.

    Best effort: if the write is lost the attempt still ends when its lease
    does, which is how every failure ended before.
    """
    try:
        ask_question_store.fail_message_command(
            conversation_id=str(command["conversation_id"]),
            idempotency_key=str(command["idempotency_key"]),
            owner_id=str(command["owner_id"]),
            lease_owner=lease_owner,
            lease_attempt=int(lease_attempt or 0),
            failure_category=category,
            retryable=retryable,
            now_iso=_now(),
            table=table,
        )
    except Exception:
        logger.warning("message_command_failure_not_recorded", exc_info=True)
    # The steps published while it streamed belong to an answer that will not
    # be stored, and may be cut from a broken reply (#389): no reader is shown
    # them, with or without the message's key. Only this attempt's own steps
    # are cleared: the row may still hold an earlier command's answer. Best
    # effort, as publishing is.
    conversation_id = str(command["conversation_id"])
    owner_id = str(command["owner_id"])
    command_id = command.get("command_id")
    if not isinstance(command_id, str) or not command_id or not lease_attempt:
        return
    published, _ = ask_question_store.read_generation_progress(
        conversation_id,
        owner_id=owner_id,
        command_id=command_id,
        attempt=lease_attempt,
        table=table,
    )
    if published:
        ask_question_store.record_generation_progress(
            conversation_id,
            owner_id=owner_id,
            steps=[],
            now_iso=_now(),
            expires_at=int(datetime.now(timezone.utc).timestamp())
            + GENERATION_PROGRESS_TTL_SECONDS,
            command_id=command_id,
            attempt=lease_attempt,
            table=table,
        )


def commit_message_command(
    *,
    conv_id: str,
    student_id: str,
    subject: str,
    grade: str,
    body: SendMessageRequest,
    command_context: dict,
) -> SendMessageResponse | CommittedMessage:
    """Store the student's message, its quota claim and the command.

    Returns the stored answer when the command already has one. Otherwise the
    command is left `message_committed` (or as a resumable earlier attempt left
    it) carrying the context its answer is generated from, and
    `generate_for_command` takes it from there. This half is the only one that
    reads the request.
    """
    actor: Actor = command_context["actor"]
    fingerprint = str(command_context["fingerprint"])
    table = cast(DynamoConversationTable, db_table.table())
    existing = command_context.get("existing")
    account_fence_generation = int(
        command_context.get("account_fence_generation")
        or (existing or {}).get("account_fence_generation")
        or active_conversation_generation(student_id, table)
    )
    now_epoch = int(datetime.now(timezone.utc).timestamp())
    state = command_context.get("state")
    if not isinstance(state, ask_question_store.MessageCommandResult):
        state = ask_question_store.classify_message_command(
            existing,
            owner_id=student_id,
            fingerprint=fingerprint,
            now_epoch=now_epoch,
        )
    if existing:
        existing = _validate_replay_command(
            existing,
            conversation_id=conv_id,
            owner_id=student_id,
            idempotency_key=body.idempotencyKey,
            fingerprint=fingerprint,
        )
    if response := _result_response(state):
        return response
    if state.disposition is ask_question_store.MessageCommandDisposition.LEASE_HELD:
        return _wait_for_message_command(
            conv_id,
            body.idempotencyKey,
            fingerprint,
            table=table,
            owner_id=student_id,
        )
    if existing and state.disposition in {
        ask_question_store.MessageCommandDisposition.REJECTED,
        ask_question_store.MessageCommandDisposition.QUOTA_EXCEEDED,
        ask_question_store.MessageCommandDisposition.IDEMPOTENCY_CONFLICT,
        ask_question_store.MessageCommandDisposition.RETRYABLE,
        ask_question_store.MessageCommandDisposition.TERMINAL,
        ask_question_store.MessageCommandDisposition.EXPIRED,
        ask_question_store.MessageCommandDisposition.MISSING,
    }:
        raise AttachmentDecisionError(_command_error_code(state))

    command_id = str(
        uuid5(NAMESPACE_URL, f"stoa.conversation.send.v1:{conv_id}:{body.idempotencyKey}")
    )
    student_msg_id = str(uuid5(UUID(command_id), "student-message"))
    assistant_msg_id = str(uuid5(UUID(command_id), "assistant-message"))
    created_at = str(existing.get("created_at")) if existing else _now()
    requested_attachments: list[dict[str, str]] = []
    deterministic_attachment_ids: list[str] = []
    for index, reference in enumerate(body.attachmentIds or []):
        if reference.upload_id is not None:
            attachment_id = str(uuid5(UUID(command_id), f"attachment:{index}"))
            deterministic_attachment_ids.append(attachment_id)
            requested_attachments.append(
                {
                    "kind": "upload",
                    "id": str(reference.upload_id),
                    "attachment_id": attachment_id,
                }
            )
        else:
            requested_attachments.append(
                {
                    "kind": "attachment",
                    "id": str(reference.attachment_id),
                    "attachment_id": str(reference.attachment_id),
                }
            )
    quota_period = (
        str(existing["quota_period"])
        if existing and isinstance(existing.get("quota_period"), str)
        else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    )
    command_expires_at = (
        stored_expiry
        if existing and (stored_expiry := stored_int(existing.get("expires_at"))) is not None
        else now_epoch + 172800
    )
    usage_idempotency_key = f"chat_message:{student_msg_id}"
    # Resolved before the claim: the lookups span several table reads, and the
    # answer's language is the one this request asked in, not whichever request
    # happens to be around when the answer is generated.
    requested_practice_context = command_context.get("practice_context")
    practice_context = (
        dict(requested_practice_context)
        if isinstance(requested_practice_context, Mapping)
        else None
    )
    generation_context = (
        None
        if existing
        else _resolve_generation_context(
            student_id, actor, subject, grade, practice_context
        )
    )
    command = existing or {
        "entity_type": "message_command",
        "schema_version": "message-command.v2",
        "command_id": command_id,
        "conversation_id": conv_id,
        "owner_id": student_id,
        "student_id": student_id,
        "account_fence_generation": account_fence_generation,
        "idempotency_key": body.idempotencyKey,
        "fingerprint": fingerprint,
        "status": "claimed",
        "student_message_id": student_msg_id,
        "assistant_message_id": assistant_msg_id,
        "attachment_count": len(body.attachmentIds or []),
        "requested_attachments": requested_attachments,
        "deterministic_attachment_ids": deterministic_attachment_ids,
        "quota_period": quota_period,
        "usage_action": "chat_message",
        "usage_resource_id": student_msg_id,
        "usage_idempotency_key": usage_idempotency_key,
        "usage_event_id": (
            f"{student_id}:chat_message:{quota_period}:{usage_idempotency_key}"
        ),
        "history_anchor_message_id": student_msg_id,
        "history_anchor_created_at": created_at,
        "attempt": 0,
        "created_at": created_at,
        "expires_at": command_expires_at,
        "generation_context": generation_context,
    }
    if existing:
        prior_messages = _conversation_repository_call(
            lambda: learning_session.anchored_history(
                conv_id,
                owner_id=student_id,
                message_ids=command["history_message_ids"],
                fingerprint=command["history_fingerprint"],
            )
        )
    else:
        prior_messages = _conversation_repository_call(lambda: learning_session.history_rows(conv_id))
        command["history_message_ids"] = [
            item["message_id"] for item in prior_messages
        ]
        command["history_fingerprint"] = learning_session.history_fingerprint(prior_messages)

    # Admitted once, at the first submission; a command already stored carries
    # what that admission decided.
    admitted = (
        None
        if existing
        else _conversation_repository_call(lambda: _admission.admit(student_id, command))
    )
    resume_after_message = bool(
        existing
        and existing.get("status") in {"message_committed", "ai_running", "failed"}
    )
    if resume_after_message:
        _, prepared, attachments, quote = _stored_student_message(
            conv_id=conv_id,
            student_id=student_id,
            student_msg_id=student_msg_id,
            created_at=created_at,
            expected_content=body.content,
            table=table,
            expected_quote=body.quote,
        )
    else:
        quote = body.quote
        # Stage B is entered only for an absent command, or to resume a claimed
        # command lost before its deterministic message transaction.
        prepared = _conversation_repository_call(
            lambda: attachment_service.prepare_message_attachments(
                body.attachmentIds or [], actor, conversation_id=conv_id
            )
        )
        effective_plan = "free_trial"
        if body.attachmentIds:
            effective_plan = (
                admitted.attachment_plan
                if admitted is not None
                else str(command.get("allowance_plan_id") or "free_trial")
            )
            _conversation_repository_call(
                lambda: attachment_service.ensure_message_attachment_capacity(
                    prepared, student_id, effective_plan
                )
            )
        if admitted is not None:
            command.update(admitted.identity)
            claim_result = _coerce_command_result(
                _conversation_repository_call(
                lambda: ask_question_store.claim_message_command_and_quota(
                    command=command,
                    owner_id=student_id,
                    quota_period=quota_period,
                        limit=admitted.daily_limit,
                        expires_at=command_expires_at,
                        account_fence_generation=account_fence_generation,
                        table=table,
                )
                ),
            )
            if claim_result.disposition is not ask_question_store.MessageCommandDisposition.CLAIMED:
                if response := _result_response(claim_result):
                    return response
                if claim_result.disposition in {
                    ask_question_store.MessageCommandDisposition.RESUME,
                    ask_question_store.MessageCommandDisposition.LEASE_HELD,
                }:
                    return _wait_for_message_command(
                        conv_id,
                        body.idempotencyKey,
                        fingerprint,
                        table=table,
                        owner_id=student_id,
                    )
                raise AttachmentDecisionError(_command_error_code(claim_result))
            command = claim_result.command or {
                **command,
                "counter_value": int(claim_result.counter_value or 0),
            }
        # The message is the actor's, written under the fence generation and
        # with the attachment ids that binding decides. The quote is stored
        # beside it, so reading the conversation back shows the quote above the
        # question exactly as it was asked.
        student_quote = _quote_payload(body.quote) if body.quote is not None else None

        def student_message_put(
            attachment_ids: list[str], generation: int
        ) -> dict[str, object]:
            return learning_session.append(
                conv_id,
                role="student",
                message_id=student_msg_id,
                student_id=actor.user_id,
                generation=generation,
                content=body.content,
                created_at=created_at,
                attachment_ids=attachment_ids,
                quote=student_quote,
            )

        command_attachment_ids = command.get("deterministic_attachment_ids")
        if not isinstance(command_attachment_ids, list) or any(
            not isinstance(value, str) or not value
            for value in command_attachment_ids
        ):
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            )
        try:
            attachments = _conversation_repository_call(
                lambda: attachment_service.bind_message_attachments(
                    message_id=student_msg_id,
                    message_put=student_message_put,
                    conversation_id=conv_id,
                    actor=actor,
                    prepared=prepared,
                    effective_plan=effective_plan,
                    command_operations=functools.partial(
                        ask_question_store.message_committed_operations, command
                    ),
                    deterministic_attachment_ids=command_attachment_ids,
                )
            )
        except AttachmentDecisionError as bind_error:
            bind_error_code = bind_error.code
            deterministic = bind_error_code in {
                AttachmentErrorCode.STORAGE_QUOTA_EXCEEDED,
                AttachmentErrorCode.UPLOAD_NOT_FOUND,
                AttachmentErrorCode.UPLOAD_EXPIRED,
                AttachmentErrorCode.UPLOAD_TOO_LARGE,
                AttachmentErrorCode.UPLOAD_TYPE_NOT_SUPPORTED,
                AttachmentErrorCode.UPLOAD_CONTENT_MISMATCH,
                AttachmentErrorCode.UPLOAD_INVALID,
                AttachmentErrorCode.UPLOAD_CHUNK_CONFLICT,
            }
            if deterministic:
                rejection = _conversation_repository_call(
                    lambda: ask_question_store.reject_message_command_and_compensate(
                        conversation_id=conv_id,
                        idempotency_key=body.idempotencyKey,
                        owner_id=student_id,
                        fingerprint=fingerprint,
                        error_code=bind_error_code.value,
                        now_iso=_now(),
                        table=table,
                    )
                )
                if rejection.disposition is ask_question_store.MessageCommandDisposition.REJECTED:
                    raise bind_error
                if response := _result_response(rejection):
                    return response
                if rejection.disposition not in {
                    ask_question_store.MessageCommandDisposition.RESUME,
                    ask_question_store.MessageCommandDisposition.LEASE_HELD,
                }:
                    raise AttachmentDecisionError(_command_error_code(rejection))
                raced = rejection.command
            else:
                reread = _conversation_repository_call(
                    lambda: ask_question_store.read_message_command_result(
                        conv_id,
                        body.idempotencyKey,
                        owner_id=student_id,
                        fingerprint=fingerprint,
                        now_epoch=int(datetime.now(timezone.utc).timestamp()),
                        table=table,
                    )
                )
                if response := _result_response(reread):
                    return response
                if reread.disposition not in {
                    ask_question_store.MessageCommandDisposition.RESUME,
                    ask_question_store.MessageCommandDisposition.LEASE_HELD,
                }:
                    raise AttachmentDecisionError(
                        AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
                    )
                raced = reread.command
            return commit_message_command(
                conv_id=conv_id,
                student_id=student_id,
                subject=subject,
                grade=grade,
                body=body,
                command_context={
                    "actor": actor,
                    "fingerprint": fingerprint,
                    "existing": raced,
                    "practice_context": practice_context,
                },
            )

    if not all(field in command for field in _admission.ALLOWANCE_IDENTITY_FIELDS):
        command.update(
            _conversation_repository_call(
                lambda: _admission.identity_of_unstamped(command)
            )
        )

    if not isinstance(command.get("generation_context"), Mapping):
        # A command claimed before its context was stored with it (E19) takes
        # the context of the request resuming it.
        resumed_context = _resolve_generation_context(
            student_id, actor, subject, grade, practice_context
        )
        command["generation_context"] = _conversation_repository_call(
            lambda: ask_question_store.record_message_generation_context(
                conversation_id=conv_id,
                idempotency_key=body.idempotencyKey,
                owner_id=student_id,
                context=resumed_context,
                table=table,
            )
        )
    return CommittedMessage(
        command=command,
        account_fence_generation=account_fence_generation,
        content=body.content,
        prior_messages=prior_messages,
        prepared=prepared,
        attachments=attachments,
        quote=quote,
    )


def generate_for_command(committed: CommittedMessage) -> SendMessageResponse:
    """Generate, store and settle the answer to one committed command.

    Reads only the command and the store: the language, subject, grade and
    weak topics come from the context stored at commit, never from a request.
    An attempt that fails ends the command `failed` with its category, and says
    whether the same command may be tried again.
    """
    command = committed.command
    conv_id = str(command["conversation_id"])
    student_id = str(command["owner_id"])
    idempotency_key = str(command["idempotency_key"])
    fingerprint = str(command["fingerprint"])
    command_id = str(command["command_id"])
    student_msg_id = str(command["student_message_id"])
    assistant_msg_id = str(command["assistant_message_id"])
    created_at = str(command["created_at"])
    account_fence_generation = committed.account_fence_generation
    prepared = committed.prepared
    attachments = committed.attachments
    prior_messages = committed.prior_messages
    table = cast(DynamoConversationTable, db_table.table())
    context = command.get("generation_context")
    if (
        not isinstance(context, Mapping)
        or not isinstance(context.get("locale"), str)
        or not isinstance(context.get("subject"), str)
        or not isinstance(context.get("grade"), str)
        or not isinstance(context.get("memory_context"), (str, type(None)))
        or not isinstance(context.get("practice_context"), (Mapping, type(None)))
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    memory_context = context["memory_context"]
    # Missing on a command stored before styles existed (#314): `standard`.
    answer_style = learning_profile_service.answer_style_code(context.get("answer_style"))
    # A question about a part of an earlier answer is a follow-up whatever the
    # model makes of it: it is shown no star map, and counts no gaps (#142).
    follow_up = committed.quote is not None and committed.quote.source.part is not None
    stored_practice_context = context.get("practice_context")
    practice_context = (
        dict(stored_practice_context)
        if isinstance(stored_practice_context, Mapping)
        else None
    )

    lease_owner = str(uuid.uuid4())
    now_epoch = int(datetime.now(timezone.utc).timestamp())
    lease_result = _coerce_command_result(
        _conversation_repository_call(
            lambda: ask_question_store.claim_message_ai_lease(
                conversation_id=conv_id,
                idempotency_key=idempotency_key,
                owner_id=student_id,
                lease_owner=lease_owner,
                now_epoch=now_epoch,
                expires_at=now_epoch + _AI_LEASE_SECONDS,
                account_fence_generation=account_fence_generation,
                table=table,
            )
        ),
    )
    if lease_result.disposition is not ask_question_store.MessageCommandDisposition.CLAIMED:
        if response := _result_response(lease_result):
            return response
        if lease_result.attempt is not None and lease_result.attempt >= 3:
            current = _conversation_repository_call(
                lambda: ask_question_store.read_message_command_result(
                    conv_id,
                    idempotency_key,
                    owner_id=student_id,
                    fingerprint=fingerprint,
                    now_epoch=now_epoch,
                    table=table,
                )
            )
            if current.disposition in {
                ask_question_store.MessageCommandDisposition.TERMINAL,
                ask_question_store.MessageCommandDisposition.RESUME,
            }:
                terminal = _conversation_repository_call(
                    lambda: ask_question_store.mark_message_command_terminal(
                        conversation_id=conv_id,
                        idempotency_key=idempotency_key,
                        owner_id=student_id,
                        now_iso=_now(),
                        table=table,
                    )
                )
                terminal = _coerce_command_result(
                    terminal,
                )
                if terminal.previous_status == "ai_running":
                    # Its last attempt died; whatever it reserved is still held
                    # (ticket 15). Counted once, by the write that ended it.
                    emit_private_event(
                        "conversation_ai_attempts_exhausted",
                        correlation_id=command_id,
                        level=logging.WARNING,
                    )
                raise AttachmentDecisionError(_command_error_code(terminal))
            lease_result = current
        if lease_result.disposition in {
            ask_question_store.MessageCommandDisposition.LEASE_HELD,
            ask_question_store.MessageCommandDisposition.RESUME,
        }:
            return _wait_for_message_command(
                conv_id,
                idempotency_key,
                fingerprint,
                table=table,
                owner_id=student_id,
            )
        raise AttachmentDecisionError(_command_error_code(lease_result))

    def record_failure(category: str, *, retryable: bool) -> None:
        _record_generation_failure(
            command,
            table=table,
            lease_owner=lease_owner,
            lease_attempt=lease_result.attempt,
            category=category,
            retryable=retryable,
        )

    lease_attempt_number = int(lease_result.attempt or 0)
    # An attempt whose lease ran out is recovered by what it left behind (ticket
    # 08, constraint 2): not yet called, generate again; answer kept, finish
    # storing it; called with nothing kept, never call again. The mark is
    # cleared only when an outcome is settled, so one still present belongs to
    # whichever earlier attempt called, however many attempts died since.
    leased = lease_result.command or {}
    invoked_attempt = stored_int(leased.get("provider_invoked_attempt"))
    recovered: tuple[ask_answer.AskAnswer, dict[str, object] | None] | None = None
    if lease_result.previous_status == "ai_running" and invoked_attempt is not None:
        recovered = _stored_provider_result(leased, invoked_attempt)
        if recovered is None:
            record_failure("needs_reconciliation", retryable=False)
            emit_private_event(
                "conversation_ai_needs_reconciliation",
                correlation_id=command_id,
                level=logging.WARNING,
            )
            raise AttachmentDecisionError(AskQuestionErrorCode.MESSAGE_FAILED)

    allowance = _admission.meter(command)
    evidence: UsageEvidence | None = None
    answer: ask_answer.AskAnswer
    if recovered is not None:
        answer, evidence = recovered
    else:
        active_conversation_generation(student_id, table)
        attachment_context = ""
        attachment_images: tuple[ai_service.PromptImage, ...] = ()
        if prepared:
            s3 = _conversation_repository_call(
                lambda: aws.client(Kind.S3)
            )
            context_result = _conversation_repository_call(
                lambda: attachment_service.extract_message_attachment_context(
                    prepared,
                    s3=s3,
                    settings=config.settings(),
                )
            )
            if (
                not isinstance(context_result, attachment_service.AttachmentContextResult)
                or context_result.disposition
                is not attachment_service.AttachmentContextDisposition.READY
            ):
                code = (
                    context_result.error_code
                    if isinstance(context_result, attachment_service.AttachmentContextResult)
                    and context_result.error_code is not None
                    else AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
                )
                transient = code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
                record_failure(
                    "attachment_unavailable" if transient else "attachment_invalid",
                    retryable=transient,
                )
                raise AttachmentDecisionError(code)
            attachment_context = context_result.context
            attachment_images = context_result.images
        ai_deadline = runtime_budget_service.ai_deadline(
            fixed_seconds=_AI_INVOCATION_DEADLINE_SECONDS,
            reserve_seconds=_AI_PERSIST_RESERVE_SECONDS,
        )
        active_conversation_generation(student_id, table)
        metered = allowance.model(
            on_invocation=lambda: _conversation_repository_call(
                lambda: ask_question_store.record_provider_invocation(
                    conversation_id=conv_id,
                    idempotency_key=idempotency_key,
                    owner_id=student_id,
                    lease_owner=lease_owner,
                    lease_attempt=lease_attempt_number,
                    now_epoch=int(datetime.now(timezone.utc).timestamp()),
                    table=table,
                )
            )
        )
        provider_answered = False

        try:
            answer = ask_answer.answer(
                ask_answer.Asked(
                    content=committed.content,
                    history=prior_messages,
                    attachment_context=attachment_context,
                    images=attachment_images,
                    quote=_quote_payload(committed.quote),
                    practice_context=practice_context,
                    follow_up=follow_up,
                ),
                ask_answer.Asker(
                    student_id=student_id,
                    subject=context["subject"],
                    grade=context["grade"],
                    locale=context["locale"],
                    memory_context=memory_context,
                    answer_style=answer_style,
                ),
                ask_answer.ModelCall(
                    model=metered,
                    deadline_monotonic=ai_deadline,
                    correlation_id=command_id,
                    effect_id=metered.effect_id,
                    on_step=_publish_generation_step(
                        conv_id, student_id, command_id=command_id, attempt=lease_result.attempt
                    ),
                ),
            )
            provider_answered = True
            assert answer.provider is not None
            evidence = UsageEvidence.from_provider(
                answer.provider, effect_id=metered.effect_id
            )
        except AdmissionError as failure:
            # Refused at counting, admission or the allowance itself, before the
            # model was paid for, the same message may be sent again. Refused over
            # the evidence of an answer that did come back, it may not.
            record_failure(failure.code.value, retryable=not provider_answered)
            raise
        except Exception as exc:
            if evidence is None:
                # A reply that was cut off or garbled was still paid for; its usage
                # rides on the failure so the reservation can be released here.
                evidence = UsageEvidence.from_failure(exc, effect_id=metered.effect_id)
            if evidence is not None:
                try:
                    allowance.observe(evidence)
                    allowance.restore(evidence)
                except AdmissionError as failure:
                    raise failure from None
            # A reply that was paid for is a known result: generating the same
            # command again would call the model for an effect already settled.
            record_failure(
                exc.category
                if isinstance(exc, ai_service.AIInvocationFailure)
                else "provider_error",
                retryable=evidence is None,
            )
            emit_private_event(
                "conversation_ai_failed",
                exception=exc,
                input_size=len(committed.content),
                attachment_count=len(prepared),
                correlation_id=command_id,
                level=logging.ERROR,
            )
            if evidence is not None:
                # A reply that came back and cannot be used (`malformed_response`,
                # `incomplete_output`) failed the message for good, as the command
                # now says; it has nothing to do with an upload (#412).
                raise AttachmentDecisionError(AskQuestionErrorCode.MESSAGE_FAILED) from None
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            ) from None
        # Kept until the answer is stored for good, so an attempt that dies on
        # the way is finished by the next one without a second model call.
        try:
            ask_question_store.record_provider_result(
                conversation_id=conv_id,
                idempotency_key=idempotency_key,
                owner_id=student_id,
                lease_owner=lease_owner,
                lease_attempt=lease_attempt_number,
                now_epoch=int(datetime.now(timezone.utc).timestamp()),
                result_json=json.dumps(
                    {
                        "answer": answer.to_json(),
                        "allowance": None if evidence is None else evidence.to_json(),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                table=table,
            )
        except Exception:
            logger.warning("provider_result_not_kept", exc_info=True)
    if evidence is not None:
        allowance.observe(evidence)

    active_conversation_generation(student_id, table)
    completed_epoch = int(datetime.now(timezone.utc).timestamp())
    renewed = _conversation_repository_call(
        lambda: ask_question_store.renew_message_ai_lease(
            conversation_id=conv_id,
            idempotency_key=idempotency_key,
            owner_id=student_id,
            lease_owner=lease_owner,
            now_epoch=completed_epoch,
            expires_at=completed_epoch + _AI_LEASE_SECONDS,
            account_fence_generation=account_fence_generation,
            table=table,
        )
    )
    if renewed is not True:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    lease_attempt = lease_result.attempt
    if (
        isinstance(lease_attempt, bool)
        or not isinstance(lease_attempt, int)
        or lease_attempt <= 0
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)

    assistant_created_at = _now()
    student_message = ChatMessage(
        id=student_msg_id,
        conversationId=conv_id,
        role="student",
        content=committed.content,
        createdAt=created_at,
        status="sent",
        attachments=attachments,
        quote=committed.quote,
    )
    assistant_message = ChatMessage(
        id=assistant_msg_id,
        conversationId=conv_id,
        role="assistant",
        content=answer.content,
        createdAt=assistant_created_at,
        status="sent",
        structured=answer.structured,
        targetUnit=target_unit(answer.target_unit_id),
    )
    result = SendMessageResponse(
        studentMessage=student_message, assistantMessage=assistant_message
    )
    assistant_message_put = learning_session.append(
        conv_id,
        role="assistant",
        message_id=assistant_msg_id,
        student_id=student_id,
        generation=account_fence_generation,
        content=answer.content,
        created_at=assistant_created_at,
        structured=structured_payload(answer.structured),
        target_unit_id=answer.target_unit_id,
        allowance=None if evidence is None else evidence.to_json(),
    )
    # What the answer counts on the knowledge-base gap list (#142) and records
    # as asked knowledge points (#143), once per question; which those are is
    # the answer's to say (`ask_answer`).
    knowledge_gaps = knowledge_gap_repo.count_updates(
        context["subject"], answer.knowledge_gaps, seen_at=assistant_created_at
    )
    asked_knowledge = asked_knowledge_repo.record_put(
        conversation_id=conv_id,
        message_id=assistant_msg_id,
        student_id=student_id,
        subject=context["subject"],
        points=[(point.name, point.unitId) for point in answer.asked_points],
        asked_at=assistant_created_at,
    )
    completion = _coerce_command_result(
        _conversation_repository_call(
            lambda: ask_question_store.complete_message_command(
                conversation_id=conv_id,
                idempotency_key=idempotency_key,
                owner_id=student_id,
                lease_owner=lease_owner,
                lease_attempt=lease_attempt,
                completed_epoch=completed_epoch,
                assistant_message_put=assistant_message_put,
                result_json=_message_result_json(result, evidence),
                completed_at=assistant_created_at,
                account_fence_generation=account_fence_generation,
                knowledge_gap_updates=knowledge_gaps,
                asked_knowledge_put=asked_knowledge,
                table=table,
            )
        ),
    )
    if completion.disposition is ask_question_store.MessageCommandDisposition.COMPLETED:
        if completion.command is not None:
            stored = _result_response(completion)
            assert stored is not None
            return stored
        if evidence is not None:
            allowance.finalize(evidence)
        return result
    raise AttachmentDecisionError(_command_error_code(completion))
