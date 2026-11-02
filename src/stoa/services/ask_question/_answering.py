"""Commit a question, answer it, settle its allowance, replay it.

Moved from `routers/conversations.py` (#218). Function bodies are as they were
there; the router now reaches them through the package's entry points.
"""
import json
import hashlib
import logging
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

import boto3
from fastapi import status

from stoa.config import settings
from stoa.db.dynamodb import get_table, stored_int
from stoa.db.repositories import (
    account_deletion_repo,
    allowance_repo,
    asked_knowledge_repo,
    knowledge_gap_repo,
    user_repo,
)
from stoa.models.allowance import ProviderUsageEvidence
from stoa.models.attachment import AttachmentSummary
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.security.identity import Actor
from stoa.security.private_telemetry import emit_private_event
from stoa.services import (
    adaptive_learning_service,
    ai_service,
    allowance_service,
    ask_answer,
    attachment_service,
    bedrock_token_count_service,
    entitlement_service,
    locale_service,
    runtime_budget_service,
)
from stoa.services.adaptive_learning_service import actor_projection
from stoa.services.ask_question import _store as ask_question_store
from stoa.services.ask_question._transcript import (
    _DynamoConversationTable,
    _conv_pk,
    _conversation_grade,
    _conversation_repository_call,
    _get_conversation,
    _get_messages,
    _history_snapshot_fingerprint,
    _load_anchored_message_history,
    _msg_sk,
    _stored_student_message,
)
from stoa.services.ask_question.errors import AskQuestionErrorCode, parse_error_code
from stoa.services.ask_question.models import (
    ChatMessage,
    GenerationProgressResponse,
    MessageQuote,
    SendMessageRequest,
    SendMessageResponse,
    _quote_payload,
    _structured_payload,
    _target_unit,
)

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── AI message allowance and settlement ───────────────────────────────────────
# 「AI 消息准入」#206 replaces this whole block, from here to its end marker:
# eligibility, the reservation before the model is called, the provider usage
# observed after, and finalizing or restoring it. Moved as it stood (#218).

class _ConversationAllowanceFailure(Exception):
    """Stable public failure for conversation allowance convergence."""

    def __init__(self, code: str, message: str, action: str, http_status: int):
        self.code = code
        self.message = message
        self.action = action
        self.http_status = http_status
        super().__init__(code)


def _allowance_recoverable_failure() -> _ConversationAllowanceFailure:
    return _ConversationAllowanceFailure(
        "allowance_finalization_recoverable",
        "This answer is safely recoverable while token accounting finishes.",
        "retry_same_message",
        status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def _chat_limit_for_student(student_id: str) -> int:
    entitlement = entitlement_service.resolve_student_entitlement(student_id, settings=settings)
    limits = entitlement.get("limits") or {}
    return int(limits.get("dailyChatMessageLimit") or settings.daily_chat_message_limit)


def _attachment_plan_for_student(student_id: str) -> str:
    entitlement = entitlement_service.resolve_student_entitlement(student_id, settings=settings)
    return str(entitlement.get("effectivePlan") or "free_trial")


def _conversation_entitlement_snapshot(
    student_id: str,
    *,
    table: object,
) -> Mapping[str, object]:
    entitlement = entitlement_service.resolve_student_entitlement(
        student_id,
        settings=settings,
    )
    if not isinstance(entitlement, Mapping):
        raise _allowance_recoverable_failure()
    return entitlement


def _conversation_allowance_command_fields(
    command: Mapping[str, object],
    entitlement: Mapping[str, object],
) -> dict[str, object]:
    """Bind one allowance identity to the durable message command snapshot."""
    command_id = str(command.get("command_id") or "")
    assistant_message_id = str(command.get("assistant_message_id") or "")
    student_id = str(command.get("student_id") or command.get("owner_id") or "")
    created_at = str(command.get("created_at") or "")
    if not command_id or not assistant_message_id or not student_id or not created_at:
        raise _allowance_recoverable_failure()
    try:
        observed_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        raise _allowance_recoverable_failure() from None
    if observed_at.tzinfo is None:
        raise _allowance_recoverable_failure()
    plan_id = str(
        entitlement.get("effectivePlan")
        or entitlement.get("effective_plan")
        or "free_trial"
    )
    # The entitlement and the command both come off the table, which returns
    # every stored number as Decimal, and the identity payload below is JSON.
    raw_version = stored_int(
        entitlement.get("allowanceVersion")
        or entitlement.get("allowance_version")
        or entitlement.get("planVersion")
        or 1
    )
    if raw_version is None or raw_version < 1:
        raise _allowance_recoverable_failure()
    grant_id = str(
        entitlement.get("grantId")
        or entitlement.get("grant_id")
        or entitlement.get("source")
        or "student-local"
    )
    week = allowance_service.zurich_week(observed_at)
    week_identity = f"{week.iso_year:04d}-W{week.iso_week:02d}"
    payload = json.dumps(
        {
            "command_id": command_id,
            "assistant_message_id": assistant_message_id,
            "student_id": student_id,
            "plan_id": plan_id,
            "grant_id": grant_id,
            "allowance_version": raw_version,
            "week": week_identity,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    effect_id = hashlib.sha256(
        b"stoa.conversation.allowance-effect.v1\x00" + payload
    ).hexdigest()
    return {
        "allowance_effect_id": effect_id,
        "allowance_plan_id": plan_id,
        "allowance_grant_id": grant_id,
        "allowance_version": raw_version,
        "allowance_week_identity": week_identity,
    }


def _conversation_allowance_coordinates(
    command: Mapping[str, object],
) -> tuple[str, str, int, int]:
    effect_id = command.get("allowance_effect_id")
    plan_id = command.get("allowance_plan_id")
    grant_id = command.get("allowance_grant_id")
    week_identity = command.get("allowance_week_identity")
    # The table returns both numbers as Decimal, and everything downstream of
    # here takes whole `int` only.
    allowance_version = stored_int(command.get("allowance_version"))
    generation = stored_int(command.get("account_fence_generation"))
    if (
        not isinstance(effect_id, str)
        or len(effect_id) != 64
        or any(character not in "0123456789abcdef" for character in effect_id)
        or not isinstance(plan_id, str)
        or not plan_id
        or not isinstance(grant_id, str)
        or not grant_id
        or not isinstance(week_identity, str)
        or not week_identity
        or allowance_version is None
        or allowance_version < 1
        or generation is None
        or generation < 1
    ):
        raise _allowance_recoverable_failure()
    expected = _conversation_allowance_command_fields(
        command,
        {
            "effectivePlan": plan_id,
            "grantId": grant_id,
            "allowanceVersion": allowance_version,
        },
    )
    if (
        expected["allowance_effect_id"] != effect_id
        or expected["allowance_week_identity"] != week_identity
    ):
        raise _allowance_recoverable_failure()
    return effect_id, plan_id, allowance_version, generation


class _ConversationAllowanceBedrockClient:
    """Count and reserve the durable message effect before InvokeModel."""

    def __init__(self, command: Mapping[str, object]) -> None:
        self._deadline_monotonic: float | None = None
        self._clock: Callable[[], float] = time.monotonic
        (
            self.allowance_effect_id,
            self.plan_id,
            self.allowance_version,
            self.account_fence_generation,
        ) = _conversation_allowance_coordinates(command)
        self._command = dict(command)
        created_at = str(command.get("created_at") or "")
        try:
            self._observed_at = datetime.fromisoformat(
                created_at.replace("Z", "+00:00")
            )
        except ValueError:
            raise _allowance_recoverable_failure() from None
        if self._observed_at.tzinfo is None:
            raise _allowance_recoverable_failure()
        self._runtime_client: object | None = None
        self._invocation_method = "invoke_model"
        # Records that the model is about to be called; False means the call
        # may not be made. Set by `generate_for_command` for the leased attempt.
        self.on_invocation: Callable[[], bool] | None = None

    def mark_invocation(self) -> None:
        """Record the call before it is made; refuse one that was not recorded.

        Nothing has been paid for at this point, so the failures raised here
        leave the command free to be generated again.
        """
        if self.on_invocation is None:
            return
        try:
            recorded = self.on_invocation()
        except Exception:
            raise ai_service.AIInvocationFailure("invocation_not_recorded") from None
        if not recorded:
            raise ai_service.AIInvocationFailure("lease_lost")

    def bind_deadline(self, deadline_monotonic: float, clock: Callable[[], float]) -> None:
        """Take the answer's deadline from `ai_service.invoke_answer`, its one source."""
        self._deadline_monotonic = deadline_monotonic
        self._clock = clock

    def invoke_model(self, **kwargs: object) -> object:
        model_id = kwargs.get("modelId")
        request_body = kwargs.get("body")
        if not isinstance(model_id, str) or not isinstance(request_body, str):
            raise _ConversationAllowanceFailure(
                "provider_token_count_unavailable",
                "Token admission is temporarily unavailable. Retry this message.",
                "retry_same_message",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        remaining = (
            None
            if self._deadline_monotonic is None
            else self._deadline_monotonic - self._clock()
        )
        runtime_client = self._runtime_client or ai_service.boto3.client(
            "bedrock-runtime",
            region_name=ai_service.settings.aws_region,
            config=ai_service.bedrock_runtime_config(remaining),
        )
        self._runtime_client = runtime_client
        try:
            foundation_model_id = (
                bedrock_token_count_service.foundation_model_id_for_profile(
                    model_id
                )
            )
            inference_profile_id: str | None = model_id
        except bedrock_token_count_service.ProviderTokenCountUnavailable:
            foundation_model_id = model_id
            inference_profile_id = None
        try:
            input_tokens = bedrock_token_count_service.count_input_tokens(
                request_body,
                model_id=foundation_model_id,
                inference_profile_id=inference_profile_id,
                region=ai_service.settings.aws_region,
                runtime_client=runtime_client,
            )
            parsed_body = json.loads(request_body)
            max_output_tokens = parsed_body.get("max_tokens")
            if type(max_output_tokens) is not int or max_output_tokens < 1:
                raise bedrock_token_count_service.ProviderTokenCountUnavailable()
        except (
            bedrock_token_count_service.ProviderTokenCountUnavailable,
            json.JSONDecodeError,
        ):
            raise _ConversationAllowanceFailure(
                "provider_token_count_unavailable",
                "Token admission is temporarily unavailable. Retry this message.",
                "retry_same_message",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from None

        reservation = allowance_service.reserve_token_allowance(
            beneficiary_id=str(self._command["student_id"]),
            effect_id=self.allowance_effect_id,
            plan_id=self.plan_id,
            allowance_version=self.allowance_version,
            input_tokens=input_tokens,
            max_output_tokens=max_output_tokens,
            observed_at=self._observed_at,
            account_fence_generation=self.account_fence_generation,
        )
        if reservation.disposition is allowance_repo.ReservationDisposition.LIMIT_EXCEEDED:
            raise _ConversationAllowanceFailure(
                "allowance_exhausted",
                "Weekly AI token allowance is exhausted.",
                "view_allowance",
                status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if reservation.disposition not in {
            allowance_repo.ReservationDisposition.ADMITTED,
            allowance_repo.ReservationDisposition.REPLAYED,
        }:
            raise _allowance_recoverable_failure()

        # Counting and reserving can take the time up. Starting a generation
        # now would only be cut off by the Lambda; fail recoverably instead.
        # The reservation is kept on purpose: the ledger restores only after
        # provider usage, and the student's retry of this message reuses it.
        if (
            self._deadline_monotonic is not None
            and self._clock() >= self._deadline_monotonic
        ):
            raise ai_service.AIInvocationFailure("deadline_exceeded")

        invoke = getattr(runtime_client, self._invocation_method, None)
        if not callable(invoke):
            raise RuntimeError("Bedrock invocation dependency unavailable")
        self.mark_invocation()
        return invoke(**kwargs)

    def invoke_model_with_response_stream(self, **kwargs: object) -> object:
        """Admit the same way, then stream. Admission does not depend on how
        the answer is delivered."""
        self._invocation_method = "invoke_model_with_response_stream"
        try:
            return self.invoke_model(**kwargs)
        finally:
            self._invocation_method = "invoke_model"


_MESSAGE_ALLOWANCE_FIELDS = frozenset(
    {
        "allowance_effect_id",
        "provider_usage_evidence_id",
        "allowance_finalization_status",
        "provider_request_id_digest",
        "provider_model_id_digest",
        "provider_input_tokens",
        "provider_output_tokens",
    }
)


def _validated_message_allowance_metadata(
    value: object,
) -> dict[str, object] | None:
    if not isinstance(value, Mapping) or not _MESSAGE_ALLOWANCE_FIELDS.issubset(value):
        return None
    metadata = {field: value[field] for field in _MESSAGE_ALLOWANCE_FIELDS}
    digest_fields = (
        "allowance_effect_id",
        "provider_request_id_digest",
        "provider_model_id_digest",
    )
    if any(
        not isinstance(metadata[field], str)
        or len(str(metadata[field])) != 64
        or any(
            character not in "0123456789abcdef"
            for character in str(metadata[field])
        )
        for field in digest_fields
    ):
        return None
    if (
        not isinstance(metadata["provider_usage_evidence_id"], str)
        or not metadata["provider_usage_evidence_id"]
        or metadata["allowance_finalization_status"] != "durable_result_boundary"
        or stored_int(metadata["provider_input_tokens"]) is None
        or int(metadata["provider_input_tokens"]) < 0
        or stored_int(metadata["provider_output_tokens"]) is None
        or int(metadata["provider_output_tokens"]) < 0
    ):
        return None
    return metadata


def _message_allowance_metadata_from_provider(
    provider_result: ai_service.AIProviderResult[dict[str, object]],
    *,
    allowance_effect_id: str,
) -> dict[str, object]:
    if provider_result.invocation_class is not ai_service.AIInvocationClass.USER_ALLOWANCE:
        raise _allowance_recoverable_failure()
    return _message_allowance_metadata_from_usage(
        provider_result.usage,
        allowance_effect_id=allowance_effect_id,
    )


def _message_allowance_metadata_from_failure(
    failure: BaseException,
    *,
    allowance_effect_id: str,
) -> dict[str, object] | None:
    """The allowance metadata for a paid reply that could not be used, if any."""
    usage = getattr(failure, "usage", None)
    if not isinstance(failure, ai_service.AIInvocationFailure) or usage is None:
        return None
    return _message_allowance_metadata_from_usage(
        usage,
        allowance_effect_id=allowance_effect_id,
    )


def _message_allowance_metadata_from_usage(
    usage: ProviderUsageEvidence,
    *,
    allowance_effect_id: str,
) -> dict[str, object]:
    metadata = {
        "allowance_effect_id": allowance_effect_id,
        "provider_usage_evidence_id": usage.evidence_id,
        "allowance_finalization_status": "durable_result_boundary",
        "provider_request_id_digest": usage.provider_request_id_digest,
        "provider_model_id_digest": usage.model_id_digest,
        "provider_input_tokens": usage.input_tokens,
        "provider_output_tokens": usage.output_tokens,
    }
    validated = _validated_message_allowance_metadata(metadata)
    if validated is None:
        raise _allowance_recoverable_failure()
    return validated


def _observe_message_provider_usage(
    *,
    beneficiary_id: str,
    metadata: object,
) -> bool:
    validated = _validated_message_allowance_metadata(metadata)
    if validated is None:
        return metadata is None
    # The counts go on to an allowance service that takes whole `int` only.
    input_tokens = stored_int(validated["provider_input_tokens"])
    output_tokens = stored_int(validated["provider_output_tokens"])
    if input_tokens is None or output_tokens is None:
        return False
    observed = allowance_service.record_provider_usage(
        beneficiary_id=beneficiary_id,
        effect_id=str(validated["allowance_effect_id"]),
        provider_request_id=str(validated["provider_request_id_digest"]),
        model_id=str(validated["provider_model_id_digest"]),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    return (
        observed.disposition
        in {
            allowance_repo.ProviderUsageDisposition.RECORDED,
            allowance_repo.ProviderUsageDisposition.REPLAYED,
        }
        and observed.evidence is not None
    )


def _finalize_message_allowance(
    *,
    beneficiary_id: str,
    metadata: object,
) -> bool:
    validated = _validated_message_allowance_metadata(metadata)
    if validated is None:
        return metadata is None
    finalized = allowance_service.finalize_token_allowance(
        beneficiary_id=beneficiary_id,
        effect_id=str(validated["allowance_effect_id"]),
        technical_validation_passed=True,
        safety_check_passed=True,
        durable_result_stored=True,
        stable_replay_readable=True,
    )
    return (
        finalized.disposition
        in {
            allowance_repo.FinalizationDisposition.FINALIZED,
            allowance_repo.FinalizationDisposition.REPLAYED,
        }
        and finalized.finalization is not None
    )


def _restore_message_allowance(
    *,
    beneficiary_id: str,
    metadata: object,
) -> bool:
    validated = _validated_message_allowance_metadata(metadata)
    if validated is None:
        return metadata is None
    restored = allowance_service.restore_user_allowance(
        beneficiary_id=beneficiary_id,
        effect_id=str(validated["allowance_effect_id"]),
        technical_validation_passed=False,
        safety_check_passed=True,
        durable_result_stored=False,
        stable_replay_readable=False,
    )
    return (
        restored.disposition
        in {
            allowance_repo.FinalizationDisposition.RESTORED,
            allowance_repo.FinalizationDisposition.REPLAYED,
        }
        and restored.finalization is not None
    )


def _message_result_json(
    response: SendMessageResponse,
    metadata: object,
) -> str:
    payload = response.model_dump(mode="json", by_alias=True)
    validated = _validated_message_allowance_metadata(metadata)
    if validated is not None:
        payload["_allowance"] = validated
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _message_allowance_metadata_from_command(
    command: Mapping[str, object],
) -> dict[str, object] | None:
    result_json = command.get("result_json")
    if not isinstance(result_json, str) or not result_json:
        return None
    try:
        payload = json.loads(result_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, Mapping):
        return None
    return _validated_message_allowance_metadata(payload.get("_allowance"))


# ── end of the AI message allowance block (#206) ──────────────────────────────


def _active_conversation_generation(owner_id: str, table: Any) -> int:
    """Resolve one exact active generation before a private conversation effect."""
    try:
        fence = account_deletion_repo.require_active_account_fence(owner_id, table=table)
    except account_deletion_repo.AccountDeletionConflict:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND) from None
    return int(fence["generation"])


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

_SUBJECT_ALIASES = {
    "Mathematics": "math", "Mathematik": "math", "math": "math",
    "Physics": "physics", "Physik": "physics", "physics": "physics",
    "German": "german", "Deutsch": "german", "german": "german",
    "English": "english", "english": "english",
    "French": "french", "Französisch": "french", "french": "french",
}

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
            subject=_SUBJECT_ALIASES.get(subject, "math"),
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
    metadata = _message_allowance_metadata_from_command(command)
    if metadata is not None:
        owner_id = command.get("owner_id")
        command_effect_id = command.get("allowance_effect_id")
        if (
            not isinstance(owner_id, str)
            or not owner_id
            or (
                command_effect_id is not None
                and metadata["allowance_effect_id"] != command_effect_id
            )
        ):
            raise _allowance_recoverable_failure()
        if not _finalize_message_allowance(
            beneficiary_id=owner_id,
            metadata=metadata,
        ):
            raise _allowance_recoverable_failure()
    return response


def _coerce_command_result(
    value,
    *,
    false_disposition: ask_question_store.MessageCommandDisposition,
) -> ask_question_store.MessageCommandResult:
    """Accept inherited test doubles while production repositories stay typed."""
    if isinstance(value, ask_question_store.MessageCommandResult):
        return value
    if isinstance(value, tuple) and len(value) == 2:
        success, counter = value
        return ask_question_store.MessageCommandResult(
            (
                ask_question_store.MessageCommandDisposition.CLAIMED
                if success
                else false_disposition
            ),
            counter_value=int(counter),
            attempt=int(counter),
        )
    if isinstance(value, bool):
        return ask_question_store.MessageCommandResult(
            (
                ask_question_store.MessageCommandDisposition.COMPLETED
                if value
                else false_disposition
            )
        )
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
    the question was asked.
    """
    return {
        "schema_version": "generation-context.v1",
        "locale": _student_locale(student_id),
        "subject": _SUBJECT_ALIASES.get(subject, "math"),
        "grade": grade,
        "memory_context": _memory_context_for_student(student_id, actor, subject),
        "practice_context": practice_context,
    }


def _generation_context_without_request(
    student_id: str, conversation: Mapping[str, object] | None
) -> dict[str, object]:
    """The context for a command committed before it was stored with one.

    The worker has no request: the language is the student's stored
    preference, and the weak topics are left out, because reading them needs
    the student's own authorisation.
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
        "subject": _SUBJECT_ALIASES.get(str(conversation.get("subject") or ""), "math"),
        "grade": _conversation_grade(conversation),
        "memory_context": None,
        "practice_context": None,
    }


def load_committed_message(command: dict) -> CommittedMessage:
    """Rebuild a committed command from the store alone, for the worker.

    The same checks a resuming request makes, without the request: the
    command's identity, its history snapshot, the stored student message and
    its attachments. A command without its generation context is given one.
    """
    table = cast(_DynamoConversationTable, get_table())
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
        lambda: _load_anchored_message_history(
            conversation_id=conv_id,
            owner_id=student_id,
            expected_message_ids=command["history_message_ids"],
            expected_fingerprint=command["history_fingerprint"],
            table=table,
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
            student_id, _conversation_repository_call(lambda: _get_conversation(conv_id))
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
) -> tuple[ask_answer.AskAnswer, dict[str, object] | None] | None:
    """The answer a lost attempt kept on the command, and its allowance, if it kept one."""
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
    metadata = payload.get("allowance")
    validated = _validated_message_allowance_metadata(metadata)
    if metadata is not None and validated is None:
        return None
    return answer, validated


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
    table = cast(_DynamoConversationTable, get_table())
    existing = command_context.get("existing")
    account_fence_generation = int(
        command_context.get("account_fence_generation")
        or (existing or {}).get("account_fence_generation")
        or _active_conversation_generation(student_id, table)
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
            lambda: _load_anchored_message_history(
                conversation_id=conv_id,
                owner_id=student_id,
                expected_message_ids=command["history_message_ids"],
                expected_fingerprint=command["history_fingerprint"],
                table=table,
            )
        )
    else:
        prior_messages = _conversation_repository_call(lambda: _get_messages(conv_id))
        command["history_message_ids"] = [
            item["message_id"] for item in prior_messages
        ]
        command["history_fingerprint"] = _history_snapshot_fingerprint(prior_messages)

    quota_limit = _conversation_repository_call(
        lambda: _chat_limit_for_student(student_id)
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
            effective_plan = _conversation_repository_call(
                lambda: _attachment_plan_for_student(student_id)
            )
            _conversation_repository_call(
                lambda: attachment_service.ensure_message_attachment_capacity(
                    prepared, student_id, effective_plan
                )
            )
        if not existing:
            entitlement = _conversation_repository_call(
                lambda: _conversation_entitlement_snapshot(
                    student_id,
                    table=table,
                )
            )
            command.update(
                _conversation_allowance_command_fields(command, entitlement)
            )
            claim_result = _coerce_command_result(
                _conversation_repository_call(
                lambda: ask_question_store.claim_message_command_and_quota(
                    command=command,
                    owner_id=student_id,
                    quota_period=quota_period,
                        limit=quota_limit,
                        expires_at=command_expires_at,
                        account_fence_generation=account_fence_generation,
                        table=table,
                )
                ),
                false_disposition=ask_question_store.MessageCommandDisposition.RETRYABLE,
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
        student_item = {
            "PK": _conv_pk(conv_id),
            "SK": _msg_sk(student_msg_id),
            "entity_type": "conversation_message",
            "schema_version": "conversation-message.v1",
            "message_id": student_msg_id,
            "conversation_id": conv_id,
            "student_id": student_id,
            "owner_id": student_id,
            "account_fence_generation": account_fence_generation,
            "role": "student",
            "content": body.content,
            "created_at": created_at,
        }
        if body.quote is not None:
            # Stored beside the message, so reading the conversation back shows
            # the quote above the question exactly as it was asked.
            student_item["quote"] = _quote_payload(body.quote)
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
                    message=student_item,
                    conversation_id=conv_id,
                    actor=actor,
                    prepared=prepared,
                    effective_plan=effective_plan,
                    command=command,
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

    if not all(
        field in command
        for field in (
            "allowance_effect_id",
            "allowance_plan_id",
            "allowance_grant_id",
            "allowance_version",
            "allowance_week_identity",
        )
    ):
        entitlement = _conversation_repository_call(
            lambda: _conversation_entitlement_snapshot(
                student_id,
                table=table,
            )
        )
        command.update(
            _conversation_allowance_command_fields(command, entitlement)
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
    table = cast(_DynamoConversationTable, get_table())
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
        false_disposition=ask_question_store.MessageCommandDisposition.LEASE_HELD,
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
                    false_disposition=ask_question_store.MessageCommandDisposition.RETRYABLE,
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

    allowance_metadata: dict[str, object] | None = None
    answer: ask_answer.AskAnswer
    if recovered is not None:
        answer, allowance_metadata = recovered
    else:
        _active_conversation_generation(student_id, table)
        attachment_context = ""
        attachment_images: tuple[ai_service.PromptImage, ...] = ()
        if prepared:
            s3 = _conversation_repository_call(
                lambda: boto3.client("s3", region_name=settings.aws_region)
            )
            context_result = _conversation_repository_call(
                lambda: attachment_service.extract_message_attachment_context(
                    prepared,
                    s3=s3,
                    settings=settings,
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
        _active_conversation_generation(student_id, table)
        allowance_client = _ConversationAllowanceBedrockClient(command)
        allowance_client.on_invocation = lambda: _conversation_repository_call(
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
                ),
                ask_answer.ModelCall(
                    model=allowance_client,
                    deadline_monotonic=ai_deadline,
                    correlation_id=command_id,
                    effect_id=allowance_client.allowance_effect_id,
                    on_step=_publish_generation_step(
                        conv_id, student_id, command_id=command_id, attempt=lease_result.attempt
                    ),
                ),
            )
            provider_answered = True
            assert answer.provider is not None
            allowance_metadata = _message_allowance_metadata_from_provider(
                answer.provider,
                allowance_effect_id=allowance_client.allowance_effect_id,
            )
        except _ConversationAllowanceFailure as failure:
            # Refused at counting, admission or the allowance itself, before the
            # model was paid for, the same message may be sent again. Refused over
            # the evidence of an answer that did come back, it may not.
            record_failure(failure.code, retryable=not provider_answered)
            raise
        except Exception as exc:
            if allowance_metadata is None:
                # A reply that was cut off or garbled was still paid for; its usage
                # rides on the failure so the reservation can be released here.
                allowance_metadata = _message_allowance_metadata_from_failure(
                    exc,
                    allowance_effect_id=allowance_client.allowance_effect_id,
                )
            if allowance_metadata is not None:
                observed = _observe_message_provider_usage(
                    beneficiary_id=student_id,
                    metadata=allowance_metadata,
                )
                restored = observed and _restore_message_allowance(
                    beneficiary_id=student_id,
                    metadata=allowance_metadata,
                )
                if not restored:
                    raise _allowance_recoverable_failure() from None
            # A reply that was paid for is a known result: generating the same
            # command again would call the model for an effect already settled.
            record_failure(
                exc.category
                if isinstance(exc, ai_service.AIInvocationFailure)
                else "provider_error",
                retryable=allowance_metadata is None,
            )
            emit_private_event(
                "conversation_ai_failed",
                exception=exc,
                input_size=len(committed.content),
                attachment_count=len(prepared),
                correlation_id=command_id,
                level=logging.ERROR,
            )
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
                    {"answer": answer.to_json(), "allowance": allowance_metadata},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                table=table,
            )
        except Exception:
            logger.warning("provider_result_not_kept", exc_info=True)
    if allowance_metadata is not None and not _observe_message_provider_usage(
        beneficiary_id=student_id,
        metadata=allowance_metadata,
    ):
        raise _allowance_recoverable_failure()

    _active_conversation_generation(student_id, table)
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
        targetUnit=_target_unit(answer.target_unit_id),
    )
    result = SendMessageResponse(
        studentMessage=student_message, assistantMessage=assistant_message
    )
    assistant_item = {
        "PK": _conv_pk(conv_id),
        "SK": _msg_sk(assistant_msg_id),
        "entity_type": "conversation_message",
        "schema_version": "conversation-message.v1",
        "message_id": assistant_msg_id,
        "conversation_id": conv_id,
        "student_id": student_id,
        "owner_id": student_id,
        "account_fence_generation": account_fence_generation,
        "role": "assistant",
        "content": answer.content,
        "created_at": assistant_created_at,
        "structured": _structured_payload(answer.structured),
        **({"target_unit_id": answer.target_unit_id} if answer.target_unit_id else {}),
        **(allowance_metadata or {}),
    }
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
                assistant_message=assistant_item,
                result_json=_message_result_json(result, allowance_metadata),
                completed_at=assistant_created_at,
                account_fence_generation=account_fence_generation,
                knowledge_gap_updates=knowledge_gaps,
                asked_knowledge_put=asked_knowledge,
                table=table,
            )
        ),
        false_disposition=ask_question_store.MessageCommandDisposition.RETRYABLE,
    )
    if completion.disposition is ask_question_store.MessageCommandDisposition.COMPLETED:
        if completion.command is not None:
            stored = _result_response(completion)
            assert stored is not None
            return stored
        if not _finalize_message_allowance(
            beneficiary_id=student_id,
            metadata=allowance_metadata,
        ):
            raise _allowance_recoverable_failure()
        return result
    raise AttachmentDecisionError(_command_error_code(completion))
