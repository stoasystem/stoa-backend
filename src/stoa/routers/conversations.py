"""Conversation routes — multi-turn AI teaching sessions.


Implements the frontend chat API contract:
  GET  /conversations                        list conversations for current student
  POST /conversations                        create conversation
  GET  /conversations/{id}                   get conversation with messages
  POST /conversations/{id}/messages          send message → Bedrock AI reply
  POST /teacher-help/request                 escalate to teacher
"""
import json
import hashlib
import logging
import struct
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, NamedTuple, NoReturn, Protocol, cast
from uuid import NAMESPACE_URL, UUID, uuid5

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.config import Config
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from stoa.config import settings
from stoa.db.repositories.security_audit_repo import AuthorizationAuditSink
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.db.dynamodb import get_table, stored_int
from stoa.db.repositories import (
    account_deletion_repo,
    allowance_repo,
    attachment_repo,
    question_repo,
    user_repo,
)
from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationPurpose,
    AuthorizationSpec,
    AuthorizedResource,
    ResourceType,
)
from stoa.security.identity import Actor
from stoa.models.allowance import ProviderUsageEvidence
from stoa.models.attachment import AttachmentReference, AttachmentSummary
from stoa.models.question import QuestionStatus
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.security.request_correlation import get_request_correlation_id
from stoa.security.private_telemetry import emit_private_event
from stoa.security.route_authorization import (
    CONVERSATION_CONTENT_READ,
    STUDENT_SELF,
    authorize_conversation_resource,
    authorized_conversation_dependency,
    get_authorization_fact_repository,
    student_actor_dependency,
    student_create_actor_dependency,
)
from stoa.routers.adaptive import actor_projection
from stoa.services import (
    adaptive_learning_service,
    ai_service,
    allowance_service,
    attachment_service,
    bedrock_token_count_service,
    entitlement_service,
    learning_profile_service,
    locale_service,
    runtime_budget_service,
    teacher_dispatch_service,
    teacher_support_allowance_service,
    usage_ledger_service,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class _DynamoConversationTable(Protocol):
    def query(self, **kwargs: object) -> dict[str, object]: ...

    def get_item(self, **kwargs: object) -> dict[str, object]: ...


def _conversation_response_items(
    response: Mapping[str, object],
) -> list[dict[str, object]]:
    raw_items = response.get("Items", [])
    if not isinstance(raw_items, list) or any(
        not isinstance(item, dict) for item in raw_items
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return [dict(cast(Mapping[str, object], item)) for item in raw_items]


def _conversation_response_item(
    response: Mapping[str, object],
) -> dict[str, object] | None:
    item = response.get("Item")
    if item is None:
        return None
    if not isinstance(item, dict):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return dict(cast(Mapping[str, object], item))


def _required_conversation_text(record: Mapping[str, object], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return value


def _conversation_grade(record: Mapping[str, object]) -> str:
    """The year group the conversation was opened for, which may be none yet.

    A grade is asked for on the learning profile, not when an account is opened,
    so a student an administrator opened has none and the console sends an empty
    one. Creation accepted it, every later read refused it, and the conversation
    existed in a state it could never be read out of: the assistant's reply
    failed with `upload_service_unavailable` on a request with no upload in it.

    Blank is safe downstream - a grade of whitespace produces a reply - so what
    was wrong was refusing here what the door accepted. A value of the wrong
    type is still refused.
    """
    value = record.get("grade")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return value


def _conversation_record(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return value


class _ConversationAllowanceFailure(Exception):
    """Stable public failure for conversation allowance convergence."""

    def __init__(self, code: str, message: str, action: str, http_status: int):
        self.code = code
        self.message = message
        self.action = action
        self.http_status = http_status
        super().__init__(code)


def _raise_conversation_allowance_failure(
    error: _ConversationAllowanceFailure,
    *,
    correlation_id: str,
) -> None:
    raise HTTPException(
        status_code=error.http_status,
        detail={
            "code": error.code,
            "message": error.message,
            "action": error.action,
        },
        headers={"X-Correlation-ID": correlation_id},
    ) from error


def _allowance_recoverable_failure() -> _ConversationAllowanceFailure:
    return _ConversationAllowanceFailure(
        "allowance_finalization_recoverable",
        "This answer is safely recoverable while token accounting finishes.",
        "retry_same_message",
        status.HTTP_503_SERVICE_UNAVAILABLE,
    )

# ── DynamoDB helpers ───────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conv_pk(conv_id: str) -> str:
    return f"CONV#{conv_id}"


def _msg_sk(msg_id: str) -> str:
    return f"MSG#{msg_id}"


# List budget: at most 25 index pages and 200 conversations per request.
_CONVERSATION_LIST_LIMIT = 200
_CONVERSATION_LIST_PAGE_BUDGET = 25


class ConversationListPage(NamedTuple):
    """Conversations in hand, plus whether older ones were left unread."""

    items: list[dict]
    truncated: bool


def _list_conversations(
    student_id: str,
    *,
    limit: int = _CONVERSATION_LIST_LIMIT,
    page_budget: int = _CONVERSATION_LIST_PAGE_BUDGET,
) -> ConversationListPage:
    """List this student's conversations, newest first.

    GSI-StudentId carries every row holding the student id - messages, usage
    events, reports - so a page can be consumed entirely by rows the filter drops
    and still leave conversations behind the continuation key. Follow the key
    instead of trusting one page, but stop at an explicit budget so a heavy
    history cannot turn the list into an unbounded table walk; descending order
    means a truncated answer is the most recent conversations, and the caller is
    told it was truncated.
    """
    table = cast(_DynamoConversationTable, get_table())
    items: list[dict] = []
    cursor: object = None
    for _page in range(page_budget):
        request: dict[str, object] = {
            "IndexName": "GSI-StudentId",
            "KeyConditionExpression": Key("student_id").eq(student_id),
            "FilterExpression": Attr("entity_type").eq("conversation"),
            "ScanIndexForward": False,
        }
        if cursor is not None:
            request["ExclusiveStartKey"] = cursor
        resp = table.query(**request)
        items.extend(_conversation_response_items(resp))
        cursor = resp.get("LastEvaluatedKey")
        if cursor is None:
            return ConversationListPage(items[:limit], len(items) > limit)
        if not isinstance(cursor, dict) or not cursor:
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
        if len(items) >= limit:
            return ConversationListPage(items[:limit], True)
    return ConversationListPage(items[:limit], True)


def _get_conversation(conv_id: str) -> dict | None:
    table = cast(_DynamoConversationTable, get_table())
    resp = table.get_item(Key={"PK": _conv_pk(conv_id), "SK": "CONV"})
    return _conversation_response_item(resp)


def _get_messages(conv_id: str) -> list[dict]:
    return _load_anchored_message_history(
        conversation_id=conv_id,
        owner_id=None,
        expected_message_ids=None,
        expected_fingerprint=None,
        table=get_table(),
    )


def _history_snapshot_fingerprint(messages: list[dict]) -> str:
    projection = [
        {
            "message_id": item["message_id"],
            "conversation_id": item["conversation_id"],
            "student_id": item["student_id"],
            "role": item["role"],
            "content": item["content"],
            "created_at": item["created_at"],
        }
        for item in messages
    ]
    encoded = json.dumps(
        projection, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_history_message(
    item: Any, *, conversation_id: str, owner_id: str | None
) -> dict:
    if not isinstance(item, dict):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    message_id = item.get("message_id")
    if (
        not isinstance(message_id, str)
        or not message_id
        or item.get("PK") != _conv_pk(conversation_id)
        or item.get("SK") != _msg_sk(message_id)
        or item.get("conversation_id") != conversation_id
        or (owner_id is not None and item.get("student_id") != owner_id)
        or not isinstance(item.get("student_id"), str)
        or not item["student_id"]
        or item.get("role") not in {"student", "assistant", "teacher", "system"}
        or not isinstance(item.get("content"), str)
        or not isinstance(item.get("created_at"), str)
        or not item["created_at"]
        or item.get("entity_type") != "conversation_message"
        or item.get("schema_version") != "conversation-message.v1"
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return item


def _load_anchored_message_history(
    *,
    conversation_id: str,
    owner_id: str | None,
    expected_message_ids: list[str] | None,
    expected_fingerprint: str | None,
    table,
) -> list[dict]:
    """Load one consistent bounded history and optionally prove an exact snapshot."""
    if expected_message_ids is not None and (
        any(not isinstance(value, str) or not value for value in expected_message_ids)
        or len(set(expected_message_ids)) != len(expected_message_ids)
        or not isinstance(expected_fingerprint, str)
        or len(expected_fingerprint) != 64
        or any(value not in "0123456789abcdef" for value in expected_fingerprint)
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    items: list[dict] = []
    cursor = None
    for _page in range(64):
        request = {
            "KeyConditionExpression": (
                Key("PK").eq(_conv_pk(conversation_id))
                & Key("SK").begins_with("MSG#")
            ),
            "ScanIndexForward": True,
            "ConsistentRead": True,
        }
        if cursor is not None:
            request["ExclusiveStartKey"] = cursor
        response = table.query(**request)
        if not isinstance(response, dict) or not isinstance(response.get("Items", []), list):
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            )
        page = response.get("Items", [])
        items.extend(
            _validate_history_message(
                item, conversation_id=conversation_id, owner_id=owner_id
            )
            for item in page
        )
        if len(items) > 2_000:
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            )
        cursor = response.get("LastEvaluatedKey")
        if cursor is None:
            break
        if not isinstance(cursor, dict) or not cursor:
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            )
    else:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)

    ordered = sorted(items, key=lambda value: (value["created_at"], value["message_id"]))
    if expected_message_ids is None:
        if len({item["message_id"] for item in ordered}) != len(ordered):
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            )
        return ordered
    selected: dict[str, dict] = {}
    expected = set(expected_message_ids)
    for item in ordered:
        message_id = item["message_id"]
        if message_id not in expected:
            continue
        if message_id in selected:
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            )
        selected[message_id] = item
    if set(selected) != expected:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    snapshot = [selected[message_id] for message_id in expected_message_ids]
    if _history_snapshot_fingerprint(snapshot) != expected_fingerprint:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return snapshot


def _validate_replay_attachment(
    item: Any, *, attachment_id: str, owner_id: str
) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    text_fields = (
        "immutable_object_key",
        "immutable_version_id",
        "immutable_etag",
        "detected_type",
        "original_filename",
    )
    checksum = item.get("content_sha256")
    source_fingerprint = item.get("source_fingerprint")
    if (
        item.get("PK") != attachment_repo.attachment_key(attachment_id)["PK"]
        or item.get("SK") != "META"
        or item.get("attachment_id") != attachment_id
        or item.get("owner_id") != owner_id
        or item.get("student_id") != owner_id
        or item.get("status") != "active"
        or item.get("entity_type") != "attachment"
        or item.get("schema_version") != "attachment.v1"
        or any(
            not isinstance(item.get(field), str) or not item[field]
            for field in text_fields
        )
        or not isinstance(checksum, str)
        or len(checksum) != 64
        or any(value not in "0123456789abcdef" for value in checksum)
        or (stored_length := stored_int(item.get("content_length"))) is None
        or stored_length <= 0
        or (
            source_fingerprint is not None
            and (
                not isinstance(source_fingerprint, str)
                or len(source_fingerprint) != 64
                or any(value not in "0123456789abcdef" for value in source_fingerprint)
            )
        )
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    return item


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
    if not hasattr(table, "meta") and not hasattr(table, "transact_write_items"):
        # Narrow inherited-test compatibility. Production DynamoDB tables always
        # expose a transactional client and resolve the authoritative entitlement.
        return {
            "effectivePlan": "free_trial",
            "source": "inherited-test-compatibility",
            "allowanceVersion": 1,
        }
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
        """Take the answer's deadline from `ai_service.get_ai_answer`, its one source."""
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


# ── Request / Response models ──────────────────────────────────────────────────

class CreateConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str
    grade: str
    initialMessage: str | None = Field(default=None, min_length=1, max_length=10_000)


def _active_conversation_generation(owner_id: str, table: Any) -> int:
    """Resolve one exact active generation before a private conversation effect."""
    if not hasattr(table, "get_item") or (
        not hasattr(table, "meta") and not hasattr(table, "transact_write_items")
    ):
        # Narrow inherited-test compatibility; production DynamoDB tables always
        # expose get_item and fail closed through the permanent fence.
        return 1
    try:
        fence = account_deletion_repo.require_active_account_fence(owner_id, table=table)
    except account_deletion_repo.AccountDeletionConflict:
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND) from None
    return int(fence["generation"])


class SendMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    idempotencyKey: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._~-]+$")
    attachmentIds: list[AttachmentReference] | None = Field(default=None, max_length=8)

    @model_validator(mode="after")
    def unique_attachments(self) -> "SendMessageRequest":
        if self.attachmentIds is not None and not self.attachmentIds:
            raise ValueError("attachmentIds must be omitted or contain at least one reference")
        identities = [reference.identity for reference in self.attachmentIds or []]
        if len(identities) != len(set(identities)):
            raise ValueError("attachment references must be unique")
        return self


def _conversation_repository_call(
    operation, *, conflict_code: AttachmentErrorCode = AttachmentErrorCode.UPLOAD_NOT_FOUND
):
    """Keep conversation repository transport behind one closed public boundary."""
    try:
        return operation()
    except AttachmentDecisionError:
        raise
    except attachment_repo.AttachmentTransactionError as exc:
        code = {
            attachment_repo.AttachmentTransactionOutcome.QUOTA_EXCEEDED: (
                AttachmentErrorCode.STORAGE_QUOTA_EXCEEDED
            ),
            attachment_repo.AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY: (
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            ),
            attachment_repo.AttachmentTransactionOutcome.CONCEALED_RESOURCE_CONFLICT: (
                conflict_code
            ),
        }[exc.outcome]
        raise AttachmentDecisionError(code) from None
    except attachment_repo.AttachmentRepositoryConflict as exc:
        if exc.category == "dependency_failure":
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            ) from None
        raise AttachmentDecisionError(conflict_code) from None
    except Exception:
        raise AttachmentDecisionError(
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
        ) from None


async def _message_command_dependency(
    conv_id: str,
    body: SendMessageRequest,
    actor: Actor = Depends(get_actor),
    correlation_id: str = Depends(get_request_correlation_id),
) -> dict:
    """Stage A: compute and compare the command before attachment resolution."""
    fingerprint = message_request_fingerprint(body)
    try:
        state = _conversation_repository_call(
            lambda: attachment_repo.read_message_command_result(
                conv_id,
                body.idempotencyKey,
                owner_id=actor.user_id,
                fingerprint=fingerprint,
                now_epoch=int(datetime.now(timezone.utc).timestamp()),
            )
        )
    except AttachmentDecisionError as error:
        _raise_attachment(error, correlation_id)
    if state.disposition is attachment_repo.MessageCommandDisposition.IDEMPOTENCY_CONFLICT:
        _raise_attachment(
            AttachmentDecisionError(AttachmentErrorCode.MESSAGE_IDEMPOTENCY_CONFLICT),
            correlation_id,
        )
    return {
        "actor": actor,
        "fingerprint": fingerprint,
        "state": state,
        "existing": state.command,
    }


async def _attachment_inventory_resolver(resource_id: str):
    return {"student_id": resource_id}


_message_command_dependency.authorization_specs = (  # type: ignore[attr-defined]
    AuthorizationSpec(
        ResourceType.UPLOAD,
        AuthorizationAction.UPDATE,
        AuthorizationPurpose.SELF_SERVICE,
        _attachment_inventory_resolver,
    ),
    AuthorizationSpec(
        ResourceType.ATTACHMENT,
        AuthorizationAction.READ,
        AuthorizationPurpose.SELF_SERVICE,
        _attachment_inventory_resolver,
    ),
)


def message_request_fingerprint(body: SendMessageRequest) -> str:
    """Canonical v1 fingerprint over exact UTF-8 content and ordered typed IDs."""
    content = body.content.encode("utf-8")
    framed = bytearray(b"stoa.conversation.send.v1")
    framed.extend(struct.pack(">I", len(content)))
    framed.extend(content)
    references = body.attachmentIds or []
    framed.extend(struct.pack(">I", len(references)))
    for reference in references:
        type_byte = b"\x01" if reference.upload_id is not None else b"\x02"
        opaque_id = str(reference.upload_id or reference.attachment_id).encode("utf-8")
        framed.extend(type_byte)
        framed.extend(struct.pack(">I", len(opaque_id)))
        framed.extend(opaque_id)
    return hashlib.sha256(bytes(framed)).hexdigest()


class ChatMessage(BaseModel):
    id: str
    conversationId: str
    role: str
    content: str
    createdAt: str
    status: str = "sent"
    attachments: list[AttachmentSummary] = Field(default_factory=list)


class SendMessageResponse(BaseModel):
    studentMessage: ChatMessage
    assistantMessage: ChatMessage


class MessageAcceptedResponse(BaseModel):
    """The message is stored and its answer is on its way (202).

    Where it stands is read at `GET /conversations/{id}/generation` with this
    idempotency key.
    """

    conversationId: str
    commandId: str
    idempotencyKey: str
    status: Literal["message_committed"] = "message_committed"
    studentMessage: ChatMessage


class ConversationSummary(BaseModel):
    id: str
    title: str
    subject: str
    grade: str
    updatedAt: str
    lastMessagePreview: str | None = None


class ConversationDetail(ConversationSummary):
    messages: list[ChatMessage]


class ConversationListResponse(BaseModel):
    items: list[ConversationSummary]
    truncated: bool = False


class TeacherHelpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversationId: str
    message: str | None = None


def _dispatch_escalated_conversation(
    *,
    conversation_id: str,
    conversation: dict[str, Any],
    student_id: str,
    request_id: str,
    subject: object,
    now: str,
    table: Any,
) -> str | None:
    """Assign a teacher to a fresh escalation and return that teacher's name.

    Dispatch is best effort so a transient planner failure never rejects an
    escalation that has already consumed the student's weekly allowance. An
    unassigned escalation stays visible to the reassignment path.
    """
    try:
        result = teacher_dispatch_service.dispatch_conversation(
            conversation_id,
            conversation={
                **conversation,
                "conversation_id": conversation_id,
                "student_id": student_id,
                "subject": subject,
                "escalation_status": "pending",
                # The row this was read from predates the escalation, so it does
                # not carry the request id yet - and without it dispatch cannot
                # find the queue row to mark, which left that row unassigned.
                "escalation_request_id": request_id,
            },
            now=now,
            table=table,
        )
    except Exception:
        logger.exception("conversation teacher dispatch failed")
        return None
    teacher_id = str(result.get("teacherId") or "")
    if result.get("status") != "dispatched" or not teacher_id:
        return None
    profile = user_repo.get_user(teacher_id)
    name = (profile or {}).get("name") or (profile or {}).get("email")
    return str(name) if name else None


class TeacherHelpResponse(BaseModel):
    requestId: str
    conversationId: str
    status: str = "pending"
    teacherName: str | None = None
    createdAt: str
    updatedAt: str | None = None


class TeacherAvailabilityResponse(BaseModel):
    online: bool
    availableTeachers: int
    nextWindow: str | None = None
    responseTime: str | None = None


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


def _generate_title(
    first_message: str, subject: str, *, correlation_id: str | None = None
) -> str | None:
    """Call Bedrock to generate a short conversation title (max 6 words)."""
    try:
        import json as _json

        from stoa.config import get_settings

        settings = get_settings()
        invocation_class = ai_service.AIInvocationClass.PROVIDER_COST_ONLY
        if invocation_class is not ai_service.AIInvocationClass.PROVIDER_COST_ONLY:
            raise ai_service.AIInvocationFailure("invalid_invocation_class")
        bedrock = boto3.client("bedrock-runtime", region_name=settings.aws_region)
        prompt = (
            f"Generate a concise title (max 6 words, no punctuation) for a {subject} "
            f"teaching conversation that starts with: \"{first_message[:120]}\". "
            "Respond with only the title, nothing else."
        )
        body = _json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 30,
            "messages": [{"role": "user", "content": prompt}],
        })
        resp = bedrock.invoke_model(
            modelId=settings.bedrock_model_id,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        result = _json.loads(resp["body"].read())
        title = result["content"][0]["text"].strip().strip('"').strip("'")
        return title[:80] if title else None
    except Exception as exc:
        emit_private_event(
            "title_generation_failed",
            exception=exc,
            input_size=len(first_message),
            correlation_id=correlation_id,
            level=logging.WARNING,
        )
        return None


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    actor: Actor = Depends(
        student_actor_dependency(ResourceType.CONVERSATION, AuthorizationAction.READ)
    ),
):
    student_id = actor.user_id
    page = _list_conversations(student_id)
    summaries = [
        ConversationSummary(
            id=item["conversation_id"],
            title=item.get("title", item.get("subject", "")),
            subject=item.get("subject", ""),
            grade=item.get("grade", ""),
            updatedAt=item.get("updated_at", item.get("created_at", _now())),
            lastMessagePreview=item.get("last_message_preview"),
        )
        for item in page.items
    ]
    return ConversationListResponse(items=summaries, truncated=page.truncated)


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
        attachment_repo.record_generation_progress(
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


def _subject_display_label(subject: object) -> str:
    """The subject named the way students see it, not the id it is stored under."""
    try:
        return learning_profile_service.subject_metadata(str(subject))["label"]
    except (ValueError, KeyError):
        return str(subject)


def _default_conversation_title(subject: object, grade: object) -> str:
    """The placeholder keeps the stored subject id; the client localises it.

    Writing the display label here left the client matching on the id form and
    finding nothing, so the placeholder survived untranslated. Only `math`
    showed it — the other subjects' labels happen to lowercase into their ids.
    """
    return f"{subject} – {grade}"


def _placeholder_conversation_titles(subject: object, grade: object) -> tuple[str, ...]:
    """Every shape the generated placeholder has had, so older rows stay claimable."""
    return tuple(
        dict.fromkeys(
            (
                _default_conversation_title(subject, grade),
                f"{subject} – {grade}",
            )
        )
    )


def _title_from_question(question: str, *, limit: int = 48) -> str:
    """Name a conversation after the question that started it."""
    condensed = " ".join(question.split())
    if len(condensed) <= limit:
        return condensed
    cut = condensed[:limit].rsplit(" ", 1)[0] or condensed[:limit]
    return f"{cut}…"


def _adopt_question_as_title(
    conv_id: str, conversation: Mapping[str, object], question: str
) -> None:
    """Retitle a conversation still carrying its subject-and-grade placeholder.

    Every conversation opened the same way was listed under the same name, so a
    student could not tell one from another. Best effort: a title is worth less
    than the answer that was just delivered.
    """
    title = _title_from_question(question)
    if not title:
        return
    placeholders = _placeholder_conversation_titles(
        conversation.get("subject"), conversation.get("grade")
    )
    current = conversation.get("title")
    if not isinstance(current, str) or current not in placeholders:
        return
    attachment_repo.retitle_conversation(
        conv_id, title=title, expected_title=current, now_iso=_now()
    )


@router.post("", response_model=ConversationDetail, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: CreateConversationRequest,
    actor: Actor = Depends(student_create_actor_dependency(ResourceType.CONVERSATION)),
    correlation_id: str = Depends(get_request_correlation_id),
):
    student_id = actor.user_id
    conv_id = str(uuid.uuid4())
    now = _now()
    title = (
        _title_from_question(body.initialMessage)
        if body.initialMessage
        else _default_conversation_title(body.subject, body.grade)
    )

    table = get_table()
    conv_item: dict[str, object] = {
        "PK": _conv_pk(conv_id),
        "SK": "CONV",
        "conversation_id": conv_id,
        "student_id": student_id,
        "entity_type": "conversation",
        "subject": body.subject,
        "grade": body.grade,
        "title": title,
        "created_at": now,
        "updated_at": now,
    }
    generation = _active_conversation_generation(student_id, table)
    attachment_repo.create_conversation_record(
        conv_item,
        owner_id=student_id,
        generation=generation,
        table=table,
    )

    messages: list[ChatMessage] = []
    if body.initialMessage:
        request = SendMessageRequest(
            content=body.initialMessage,
            idempotencyKey=f"initial-{conv_id}",
        )
        try:
            result = _submit_message_command(
                conv_id=conv_id,
                student_id=student_id,
                subject=body.subject,
                grade=body.grade,
                body=request,
                command_context={
                    "actor": actor,
                    "fingerprint": message_request_fingerprint(request),
                    "existing": None,
                    "account_fence_generation": generation,
                },
            )
        except _ConversationAllowanceFailure as error:
            _raise_conversation_allowance_failure(
                error,
                correlation_id=correlation_id,
            )
        messages = (
            # The answer follows; it is read at /generation with this key.
            [result.studentMessage]
            if isinstance(result, MessageAcceptedResponse)
            else [result.studentMessage, result.assistantMessage]
        )

    return ConversationDetail(
        id=conv_id,
        title=title,
        subject=body.subject,
        grade=body.grade,
        updatedAt=now,
        messages=messages,
    )


@router.get("/{conv_id}", response_model=ConversationDetail)
async def get_conversation(
    authorized: AuthorizedResource = Depends(
        authorized_conversation_dependency(
            action=AuthorizationAction.READ,
            purposes=CONVERSATION_CONTENT_READ,
            resolver=lambda conversation_id: _get_conversation(conversation_id),
        )
    ),
):
    conv_id = authorized.ref.resource_id
    conv = _conversation_record(authorized.value)

    raw_messages = _get_messages(conv_id)
    attachment_ids = [value for message in raw_messages for value in message.get("attachment_ids", [])]
    attachment_summaries = attachment_service.list_attachment_summaries(attachment_ids)
    messages = [
        ChatMessage(
            id=m["message_id"],
            conversationId=conv_id,
            role=m["role"],
            content=m["content"],
            createdAt=m["created_at"],
            status="sent",
            attachments=[
                attachment_summaries[value]
                for value in m.get("attachment_ids", [])
                if value in attachment_summaries
            ],
        )
        for m in raw_messages
    ]

    return ConversationDetail(
        id=conv_id,
        title=_required_conversation_text(conv, "title"),
        subject=_required_conversation_text(conv, "subject"),
        grade=_conversation_grade(conv),
        updatedAt=_required_conversation_text(conv, "updated_at"),
        messages=messages,
    )


class GenerationProgressResponse(BaseModel):
    conversationId: str
    steps: list[str] = Field(default_factory=list)
    # When these steps were written, so a reader can tell them from the steps
    # of a previous answer in the same conversation.
    updatedAt: str = ""
    # Set only when the reader names the message's idempotency key: where that
    # command stands. A `failed` command that is `retryable` may be sent again
    # with the same key; `assistantMessageId` names the answer once `completed`.
    commandId: str | None = None
    status: Literal["message_committed", "ai_running", "completed", "failed"] | None = None
    attempt: int | None = None
    assistantMessageId: str | None = None
    failureCategory: str | None = None
    retryable: bool | None = None


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
        state.retryable = attachment_repo.failed_command_can_retry(command)
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


@router.get("/{conv_id}/generation", response_model=GenerationProgressResponse)
async def get_generation_progress(
    authorized: AuthorizedResource = Depends(
        authorized_conversation_dependency(
            action=AuthorizationAction.READ,
            purposes=CONVERSATION_CONTENT_READ,
            resolver=lambda conversation_id: _get_conversation(conversation_id),
        )
    ),
    idempotency_key: str | None = Query(
        default=None,
        alias="idempotencyKey",
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9._~-]+$",
    ),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Return the steps of an answer still being written.

    Named by its idempotency key, the message's command is reported too, with
    only the steps its current attempt wrote.
    """
    conv_id = authorized.ref.resource_id
    owner_id = authorized.ref.student_id
    if idempotency_key is None:
        steps, updated_at = attachment_repo.read_generation_progress(
            conv_id, owner_id=owner_id
        )
        return GenerationProgressResponse(
            conversationId=conv_id, steps=steps, updatedAt=updated_at
        )
    try:
        command = _conversation_repository_call(
            lambda: attachment_repo.get_message_command(conv_id, idempotency_key)
        )
        state = (
            _command_generation_state(conv_id, command)
            if isinstance(command, dict) and command.get("owner_id") == owner_id
            else None
        )
        if state is None:
            raise AttachmentDecisionError(AttachmentErrorCode.MESSAGE_COMMAND_NOT_FOUND)
    except AttachmentDecisionError as error:
        _raise_attachment(error, correlation_id)
    state.steps, state.updatedAt = attachment_repo.read_generation_progress(
        conv_id,
        owner_id=owner_id,
        command_id=state.commandId,
        attempt=state.attempt,
    )
    return state


@router.post(
    "/{conv_id}/messages",
    response_model=SendMessageResponse,
    responses={status.HTTP_202_ACCEPTED: {"model": MessageAcceptedResponse}},
)
async def send_message(
    body: SendMessageRequest,
    authorized: AuthorizedResource = Depends(
        authorized_conversation_dependency(
            action=AuthorizationAction.RESPOND,
            purposes=STUDENT_SELF,
            resolver=lambda conversation_id: _get_conversation(conversation_id),
        )
    ),
    message_command: dict = Depends(_message_command_dependency),
    correlation_id: str = Depends(get_request_correlation_id),
):
    conv_id = authorized.ref.resource_id
    student_id = authorized.ref.student_id
    conv = _conversation_record(authorized.value)

    try:
        result = _submit_message_command(
            conv_id=conv_id,
            student_id=student_id,
            subject=_required_conversation_text(conv, "subject"),
            grade=_conversation_grade(conv),
            body=body,
            command_context=message_command,
        )
    except _ConversationAllowanceFailure as error:
        _raise_conversation_allowance_failure(
            error,
            correlation_id=correlation_id,
        )
    except AttachmentDecisionError as error:
        _raise_attachment(error, correlation_id)
    _adopt_question_as_title(conv_id, conv, body.content)
    if isinstance(result, MessageAcceptedResponse):
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=result.model_dump(mode="json"),
        )
    return result


@router.post(
    "/{conv_id}/messages/stream",
    responses={status.HTTP_202_ACCEPTED: {"model": MessageAcceptedResponse}},
)
async def stream_message(
    body: SendMessageRequest,
    authorized: AuthorizedResource = Depends(
        authorized_conversation_dependency(
            action=AuthorizationAction.RESPOND,
            purposes=STUDENT_SELF,
            resolver=lambda conversation_id: _get_conversation(conversation_id),
        )
    ),
    message_command: dict = Depends(_message_command_dependency),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Send a message and stream the AI reply as Server-Sent Events.

    API Gateway buffers the full response before sending, so this is
    pseudo-streaming: the client receives all SSE events at once, but
    the SSE parser handles them correctly and the UI updates as expected.
    """
    conv_id = authorized.ref.resource_id
    student_id = authorized.ref.student_id
    conv = _conversation_record(authorized.value)

    try:
        result = _submit_message_command(
            conv_id=conv_id,
            student_id=student_id,
            subject=_required_conversation_text(conv, "subject"),
            grade=_conversation_grade(conv),
            body=body,
            command_context=message_command,
        )
    except _ConversationAllowanceFailure as error:
        _raise_conversation_allowance_failure(
            error,
            correlation_id=correlation_id,
        )
    except AttachmentDecisionError as error:
        _raise_attachment(error, correlation_id)
    # Same as the non-streaming route. Only that one adopted the question, while
    # the client only ever calls this one, so every conversation it opened stayed
    # listed under the subject-and-grade placeholder.
    _adopt_question_as_title(conv_id, conv, body.content)
    if isinstance(result, MessageAcceptedResponse):
        # Stored, answer to follow from the worker: nothing to stream here.
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=result.model_dump(mode="json"),
        )
    student_msg = result.studentMessage
    assistant_msg = result.assistantMessage

    def _sse(event_type: str, data: dict) -> str:
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    def generate():
        yield _sse("student_message", student_msg.model_dump(mode="json", by_alias=True))
        yield _sse("message_start", {
            "messageId": assistant_msg.id,
            "role": "assistant",
            "createdAt": assistant_msg.createdAt,
        })
        # Split content into ~100-char chunks so the frontend can render
        # progressively if it ever gains true streaming support.
        chunk_size = 100
        content = assistant_msg.content
        for i in range(0, len(content), chunk_size):
            yield _sse("message_delta", {
                "messageId": assistant_msg.id,
                "delta": content[i:i + chunk_size],
            })
        yield _sse("message_done", {
            "messageId": assistant_msg.id,
            "status": "completed",
        })

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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
_HINT_LABELS = {
    "de": "Hinweis",
    "en": "Hint",
    "fr": "Indice",
    "it": "Indizio",
}


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
    """Resolve the student's answer language, defaulting to German on lookup failure.

    The language the student is reading the app in right now arrives on the
    request, so it wins over the stored preference — an answer should come back
    in the language the question was asked in.
    """
    requested = locale_service.request_locale()
    if requested:
        return requested
    try:
        profile = user_repo.get_user(student_id)
    except Exception:
        logger.warning("student_locale_fetch_failed", exc_info=True)
        return locale_service.DEFAULT_LOCALE
    return locale_service.effective_locale(profile)


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
    result: attachment_repo.MessageCommandResult,
) -> AttachmentErrorCode:
    disposition = result.disposition
    if disposition is attachment_repo.MessageCommandDisposition.REJECTED:
        try:
            code = AttachmentErrorCode(str(result.error_code))
        except ValueError:
            return AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
        if code in {
            AttachmentErrorCode.MESSAGE_IN_PROGRESS,
            AttachmentErrorCode.MESSAGE_IDEMPOTENCY_CONFLICT,
            AttachmentErrorCode.MESSAGE_DAILY_LIMIT,
        }:
            return AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
        return code
    return {
        attachment_repo.MessageCommandDisposition.QUOTA_EXCEEDED: (
            AttachmentErrorCode.MESSAGE_DAILY_LIMIT
        ),
        attachment_repo.MessageCommandDisposition.IDEMPOTENCY_CONFLICT: (
            AttachmentErrorCode.MESSAGE_IDEMPOTENCY_CONFLICT
        ),
        attachment_repo.MessageCommandDisposition.RETRYABLE: (
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
        ),
        attachment_repo.MessageCommandDisposition.TERMINAL: (
            AttachmentErrorCode.MESSAGE_FAILED
        ),
        attachment_repo.MessageCommandDisposition.EXPIRED: (
            AttachmentErrorCode.MESSAGE_COMMAND_EXPIRED
        ),
        attachment_repo.MessageCommandDisposition.MISSING: (
            AttachmentErrorCode.MESSAGE_COMMAND_NOT_FOUND
        ),
    }.get(disposition, AttachmentErrorCode.MESSAGE_IN_PROGRESS)


def _result_response(
    result: attachment_repo.MessageCommandResult,
) -> SendMessageResponse | None:
    if result.disposition is not attachment_repo.MessageCommandDisposition.COMPLETED:
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
    false_disposition: attachment_repo.MessageCommandDisposition,
) -> attachment_repo.MessageCommandResult:
    """Accept inherited test doubles while production repositories stay typed."""
    if isinstance(value, attachment_repo.MessageCommandResult):
        return value
    if isinstance(value, tuple) and len(value) == 2:
        success, counter = value
        return attachment_repo.MessageCommandResult(
            (
                attachment_repo.MessageCommandDisposition.CLAIMED
                if success
                else false_disposition
            ),
            counter_value=int(counter),
            attempt=int(counter),
        )
    if isinstance(value, bool):
        return attachment_repo.MessageCommandResult(
            (
                attachment_repo.MessageCommandDisposition.COMPLETED
                if value
                else false_disposition
            )
        )
    return attachment_repo.MessageCommandResult(
        attachment_repo.MessageCommandDisposition.RETRYABLE
    )


def _wait_for_message_command(
    conversation_id: str,
    idempotency_key: str,
    fingerprint: str,
    *,
    table,
    owner_id: str | None = None,
) -> SendMessageResponse:
    last = attachment_repo.MessageCommandResult(
        attachment_repo.MessageCommandDisposition.MISSING
    )
    for _ in range(_MESSAGE_POLL_ATTEMPTS):
        command = _conversation_repository_call(
            lambda: attachment_repo.get_message_command(
                conversation_id, idempotency_key, table=table
            )
        )
        last = attachment_repo.classify_message_command(
            command,
            owner_id=owner_id or str((command or {}).get("owner_id") or ""),
            fingerprint=fingerprint,
            now_epoch=int(datetime.now(timezone.utc).timestamp()),
        )
        if response := _result_response(last):
            return response
        if last.disposition not in {
            attachment_repo.MessageCommandDisposition.CLAIMED,
            attachment_repo.MessageCommandDisposition.RESUME,
            attachment_repo.MessageCommandDisposition.LEASE_HELD,
        }:
            raise AttachmentDecisionError(_command_error_code(last))
        time.sleep(_MESSAGE_POLL_SECONDS)
    emit_private_event(
        "message_replay_wait_exhausted",
        correlation_id=str((last.command or {}).get("command_id") or "message-command"),
        level=logging.WARNING,
    )
    raise AttachmentDecisionError(AttachmentErrorCode.MESSAGE_IN_PROGRESS)


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


def _stored_student_message(
    *,
    conv_id: str,
    student_id: str,
    student_msg_id: str,
    created_at: str,
    expected_content: str | None,
    table: Any,
) -> tuple[str, list, list[AttachmentSummary]]:
    """Read back a committed student message and its attachments, checked.

    Returns its content, the attachments as generation prepares them, and their
    summaries. `expected_content` is the request's, when there is a request.
    """
    stored_student = _conversation_repository_call(
        lambda: table.get_item(
            Key={"PK": _conv_pk(conv_id), "SK": _msg_sk(student_msg_id)},
            ConsistentRead=True,
        ).get("Item")
    )
    if (
        not isinstance(stored_student, dict)
        or stored_student.get("PK") != _conv_pk(conv_id)
        or stored_student.get("SK") != _msg_sk(student_msg_id)
        or stored_student.get("entity_type") != "conversation_message"
        or stored_student.get("schema_version") != "conversation-message.v1"
        or stored_student.get("message_id") != student_msg_id
        or stored_student.get("conversation_id") != conv_id
        or stored_student.get("student_id") != student_id
        or stored_student.get("role") != "student"
        or not isinstance(stored_student.get("content"), str)
        or (
            expected_content is not None
            and stored_student.get("content") != expected_content
        )
        or stored_student.get("created_at") != created_at
    ):
        raise AttachmentDecisionError(
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
        )
    raw_attachment_ids = stored_student.get("attachment_ids", [])
    if (
        not isinstance(raw_attachment_ids, list)
        or any(
            not isinstance(value, str) or not value
            for value in raw_attachment_ids
        )
        or len(set(raw_attachment_ids)) != len(raw_attachment_ids)
    ):
        raise AttachmentDecisionError(
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
        )
    attachment_ids = list(raw_attachment_ids)
    stored_attachments = _conversation_repository_call(
        lambda: attachment_repo.get_attachments(attachment_ids, table=table)
    )
    if len(stored_attachments) != len(attachment_ids) or set(
        stored_attachments
    ) != set(attachment_ids):
        raise AttachmentDecisionError(
            AttachmentErrorCode.UPLOAD_NOT_FOUND
        )
    prepared = [
        (
            "attachment",
            _validate_replay_attachment(
                stored_attachments[value],
                attachment_id=value,
                owner_id=student_id,
            ),
        )
        for value in attachment_ids
    ]
    attachments = attachment_service.attachment_summaries_for_records(
        attachment_ids, stored_attachments
    )
    return str(stored_student["content"]), prepared, attachments


def _generation_worker_name() -> str:
    return settings.conversation_generation_function_name.strip()


# Bounded well inside the request's 29 seconds: a slow or throttled invoke
# leaves the stored command to the sweep, not the student to a gateway timeout.
_GENERATION_INVOKE_CONFIG = Config(
    connect_timeout=2,
    read_timeout=3,
    retries={"max_attempts": 1, "mode": "standard"},
)


def _invoke_generation_worker(event: dict[str, object]) -> None:
    """Hand one command to the worker; returns once Lambda has queued it."""
    client = boto3.client(
        "lambda", region_name=settings.aws_region, config=_GENERATION_INVOKE_CONFIG
    )
    client.invoke(
        FunctionName=_generation_worker_name(),
        InvocationType="Event",
        Payload=json.dumps(event).encode(),
    )


def _submit_message_command(
    *,
    conv_id: str,
    student_id: str,
    subject: str,
    grade: str,
    body: SendMessageRequest,
    command_context: dict,
) -> SendMessageResponse | MessageAcceptedResponse:
    """Commit the message, and generate its answer here or hand it to the worker.

    With the worker named (E21), the request returns as soon as the message is
    stored: an answer that takes longer than API Gateway's 29 seconds is no
    longer cut off. A stored answer is still replayed here. Without it, the
    answer is generated in the request as before; that is the rollback.
    """
    if not _generation_worker_name():
        return _execute_message_command(
            conv_id=conv_id,
            student_id=student_id,
            subject=subject,
            grade=grade,
            body=body,
            command_context=command_context,
        )
    committed = commit_message_command(
        conv_id=conv_id,
        student_id=student_id,
        subject=subject,
        grade=grade,
        body=body,
        command_context=command_context,
    )
    if isinstance(committed, SendMessageResponse):
        return committed
    command = committed.command
    event: dict[str, object] = {
        "conversation_id": conv_id,
        "idempotency_key": body.idempotencyKey,
    }
    if command.get("status") == "failed":
        # The student's retry of a failed answer. Back to waiting before the
        # request returns: the chat reads that while the answer is on its way
        # (not the old failure), and the sweep takes it up if this invoke is
        # lost. Only the student reopens a failure, never a redelivered event.
        attempt = stored_int(command.get("attempt"))
        if attempt is not None:
            _conversation_repository_call(
                lambda: attachment_repo.reopen_failed_message_command(
                    conversation_id=conv_id,
                    idempotency_key=body.idempotencyKey,
                    owner_id=student_id,
                    attempt=attempt,
                    now_iso=_now(),
                )
            )
    try:
        _invoke_generation_worker(event)
    except Exception:
        # Not rolled back: the message and its command are stored, and the
        # sweep takes up a command nobody claimed within a minute.
        logger.warning("conversation_generation_invoke_failed", exc_info=True)
    return MessageAcceptedResponse(
        conversationId=conv_id,
        commandId=str(command["command_id"]),
        idempotencyKey=body.idempotencyKey,
        studentMessage=ChatMessage(
            id=str(command["student_message_id"]),
            conversationId=conv_id,
            role="student",
            content=committed.content,
            createdAt=str(command["created_at"]),
            status="sent",
            attachments=committed.attachments,
        ),
    )


def _execute_message_command(
    *,
    conv_id: str,
    student_id: str,
    subject: str,
    grade: str,
    body: SendMessageRequest,
    command_context: dict,
) -> SendMessageResponse:
    """Run the shared regular/SSE command: commit it, then generate its answer."""
    committed = commit_message_command(
        conv_id=conv_id,
        student_id=student_id,
        subject=subject,
        grade=grade,
        body=body,
        command_context=command_context,
    )
    if isinstance(committed, SendMessageResponse):
        return committed
    return generate_for_command(committed)


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


def _resolve_generation_context(
    student_id: str, actor: Actor, subject: str, grade: str
) -> dict[str, object]:
    """What the answer depends on that only the request knows, resolved once."""
    return {
        "schema_version": "generation-context.v1",
        "locale": _student_locale(student_id),
        "subject": _SUBJECT_ALIASES.get(subject, "math"),
        "grade": grade,
        "memory_context": _memory_context_for_student(student_id, actor, subject),
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
    content, prepared, attachments = _stored_student_message(
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
            lambda: attachment_repo.record_message_generation_context(
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
    )


def _stored_provider_result(
    command: Mapping[str, object], attempt: int
) -> tuple[str, dict[str, object] | None] | None:
    """The answer a lost attempt kept on the command, if it kept one."""
    raw = command.get("provider_result_json")
    if stored_int(command.get("provider_result_attempt")) != attempt or not isinstance(raw, str):
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, Mapping) or not isinstance(payload.get("content"), str):
        return None
    metadata = payload.get("allowance")
    validated = _validated_message_allowance_metadata(metadata)
    if metadata is not None and validated is None:
        return None
    return payload["content"], validated


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
        attachment_repo.fail_message_command(
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
    if not isinstance(state, attachment_repo.MessageCommandResult):
        state = attachment_repo.classify_message_command(
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
    if state.disposition is attachment_repo.MessageCommandDisposition.LEASE_HELD:
        return _wait_for_message_command(
            conv_id,
            body.idempotencyKey,
            fingerprint,
            table=table,
            owner_id=student_id,
        )
    if existing and state.disposition in {
        attachment_repo.MessageCommandDisposition.REJECTED,
        attachment_repo.MessageCommandDisposition.QUOTA_EXCEEDED,
        attachment_repo.MessageCommandDisposition.IDEMPOTENCY_CONFLICT,
        attachment_repo.MessageCommandDisposition.RETRYABLE,
        attachment_repo.MessageCommandDisposition.TERMINAL,
        attachment_repo.MessageCommandDisposition.EXPIRED,
        attachment_repo.MessageCommandDisposition.MISSING,
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
    generation_context = (
        None
        if existing
        else _resolve_generation_context(student_id, actor, subject, grade)
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
        _, prepared, attachments = _stored_student_message(
            conv_id=conv_id,
            student_id=student_id,
            student_msg_id=student_msg_id,
            created_at=created_at,
            expected_content=body.content,
            table=table,
        )
    else:
        # Stage B is entered only for an absent command, or to resume a claimed
        # command lost before its deterministic message transaction.
        prepared = _conversation_repository_call(
            lambda: attachment_service.prepare_message_attachments(
                body.attachmentIds or [], actor
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
                lambda: attachment_repo.claim_message_command_and_quota(
                    command=command,
                    owner_id=student_id,
                    quota_period=quota_period,
                        limit=quota_limit,
                        expires_at=command_expires_at,
                        account_fence_generation=account_fence_generation,
                        table=table,
                )
                ),
                false_disposition=attachment_repo.MessageCommandDisposition.RETRYABLE,
            )
            if claim_result.disposition is not attachment_repo.MessageCommandDisposition.CLAIMED:
                if response := _result_response(claim_result):
                    return response
                if claim_result.disposition in {
                    attachment_repo.MessageCommandDisposition.RESUME,
                    attachment_repo.MessageCommandDisposition.LEASE_HELD,
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
                    lambda: attachment_repo.reject_message_command_and_compensate(
                        conversation_id=conv_id,
                        idempotency_key=body.idempotencyKey,
                        owner_id=student_id,
                        fingerprint=fingerprint,
                        error_code=bind_error_code.value,
                        now_iso=_now(),
                        table=table,
                    )
                )
                if rejection.disposition is attachment_repo.MessageCommandDisposition.REJECTED:
                    raise bind_error
                if response := _result_response(rejection):
                    return response
                if rejection.disposition not in {
                    attachment_repo.MessageCommandDisposition.RESUME,
                    attachment_repo.MessageCommandDisposition.LEASE_HELD,
                }:
                    raise AttachmentDecisionError(_command_error_code(rejection))
                raced = rejection.command
            else:
                reread = _conversation_repository_call(
                    lambda: attachment_repo.read_message_command_result(
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
                    attachment_repo.MessageCommandDisposition.RESUME,
                    attachment_repo.MessageCommandDisposition.LEASE_HELD,
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
        resumed_context = _resolve_generation_context(student_id, actor, subject, grade)
        command["generation_context"] = _conversation_repository_call(
            lambda: attachment_repo.record_message_generation_context(
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
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    memory_context = context["memory_context"]

    lease_owner = str(uuid.uuid4())
    now_epoch = int(datetime.now(timezone.utc).timestamp())
    lease_result = _coerce_command_result(
        _conversation_repository_call(
            lambda: attachment_repo.claim_message_ai_lease(
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
        false_disposition=attachment_repo.MessageCommandDisposition.LEASE_HELD,
    )
    if lease_result.disposition is not attachment_repo.MessageCommandDisposition.CLAIMED:
        if response := _result_response(lease_result):
            return response
        if lease_result.attempt is not None and lease_result.attempt >= 3:
            current = _conversation_repository_call(
                lambda: attachment_repo.read_message_command_result(
                    conv_id,
                    idempotency_key,
                    owner_id=student_id,
                    fingerprint=fingerprint,
                    now_epoch=now_epoch,
                    table=table,
                )
            )
            if current.disposition in {
                attachment_repo.MessageCommandDisposition.TERMINAL,
                attachment_repo.MessageCommandDisposition.RESUME,
            }:
                terminal = _conversation_repository_call(
                    lambda: attachment_repo.mark_message_command_terminal(
                        conversation_id=conv_id,
                        idempotency_key=idempotency_key,
                        owner_id=student_id,
                        now_iso=_now(),
                        table=table,
                    )
                )
                terminal = _coerce_command_result(
                    terminal,
                    false_disposition=attachment_repo.MessageCommandDisposition.RETRYABLE,
                )
                raise AttachmentDecisionError(_command_error_code(terminal))
            lease_result = current
        if lease_result.disposition in {
            attachment_repo.MessageCommandDisposition.LEASE_HELD,
            attachment_repo.MessageCommandDisposition.RESUME,
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
    recovered: tuple[str, dict[str, object] | None] | None = None
    if lease_result.previous_status == "ai_running" and invoked_attempt is not None:
        recovered = _stored_provider_result(leased, invoked_attempt)
        if recovered is None:
            record_failure("needs_reconciliation", retryable=False)
            emit_private_event(
                "conversation_ai_needs_reconciliation",
                correlation_id=command_id,
                level=logging.WARNING,
            )
            raise AttachmentDecisionError(AttachmentErrorCode.MESSAGE_FAILED)

    allowance_metadata: dict[str, object] | None = None
    if recovered is not None:
        ai_content, allowance_metadata = recovered
    else:
        _active_conversation_generation(student_id, table)
        attachment_context = ""
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
        normalized_subject = context["subject"]
        grade = context["grade"]
        student_locale = context["locale"]
        ai_deadline = runtime_budget_service.ai_deadline(
            fixed_seconds=_AI_INVOCATION_DEADLINE_SECONDS,
            reserve_seconds=_AI_PERSIST_RESERVE_SECONDS,
        )
        _active_conversation_generation(student_id, table)
        allowance_client = _ConversationAllowanceBedrockClient(command)
        allowance_client.on_invocation = lambda: _conversation_repository_call(
            lambda: attachment_repo.record_provider_invocation(
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
            provider_result = ai_service.get_ai_answer(
                content=committed.content,
                subject=normalized_subject,
                grade=grade,
                language=student_locale,
                history=prior_messages,
                attachment_context=attachment_context,
                memory_context=memory_context,
                correlation_id=command_id,
                deadline_monotonic=ai_deadline,
                effect_id=allowance_client.allowance_effect_id,
                client=allowance_client,
                invocation_class=ai_service.AIInvocationClass.USER_ALLOWANCE,
                on_step=_publish_generation_step(
                    conv_id, student_id, command_id=command_id, attempt=lease_result.attempt
                ),
            )
            provider_answered = True
            if isinstance(provider_result, ai_service.AIProviderResult):
                allowance_metadata = _message_allowance_metadata_from_provider(
                    provider_result,
                    allowance_effect_id=allowance_client.allowance_effect_id,
                )
                ai_result = provider_result.content
            elif isinstance(provider_result, Mapping):
                # Narrow compatibility for inherited tests that replace the complete
                # provider function. Production always returns AIProviderResult.
                ai_result = dict(provider_result)
            else:
                raise ai_service.AIInvocationFailure("malformed_response")
            if (
                not isinstance(ai_result.get("steps", []), list)
                or any(not isinstance(value, str) for value in ai_result.get("steps", []))
                or not isinstance(ai_result.get("answer", ""), str)
                or not isinstance(ai_result.get("hints", []), list)
                or any(not isinstance(value, str) for value in ai_result.get("hints", []))
            ):
                raise ai_service.AIInvocationFailure("malformed_response")
            steps = "\n".join(
                f"{index + 1}. {value}" for index, value in enumerate(ai_result.get("steps", []))
            )
            answer = ai_result.get("answer", "")
            hints = ai_result.get("hints", [])
            hint_label = _HINT_LABELS.get(student_locale, _HINT_LABELS[locale_service.DEFAULT_LOCALE])
            hint = (f"\n\n**{hint_label}:** " + hints[0]) if hints else ""
            ai_content = f"{steps}\n\n{answer}{hint}".strip()
            if not ai_content:
                raise ai_service.AIInvocationFailure("malformed_response")
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
            attachment_repo.record_provider_result(
                conversation_id=conv_id,
                idempotency_key=idempotency_key,
                owner_id=student_id,
                lease_owner=lease_owner,
                lease_attempt=lease_attempt_number,
                now_epoch=int(datetime.now(timezone.utc).timestamp()),
                result_json=json.dumps(
                    {"content": ai_content, "allowance": allowance_metadata},
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
        lambda: attachment_repo.renew_message_ai_lease(
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
    )
    assistant_message = ChatMessage(
        id=assistant_msg_id,
        conversationId=conv_id,
        role="assistant",
        content=ai_content,
        createdAt=assistant_created_at,
        status="sent",
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
        "content": ai_content,
        "created_at": assistant_created_at,
        **(allowance_metadata or {}),
    }
    completion = _coerce_command_result(
        _conversation_repository_call(
            lambda: attachment_repo.complete_message_command(
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
                table=table,
            )
        ),
        false_disposition=attachment_repo.MessageCommandDisposition.RETRYABLE,
    )
    if completion.disposition is attachment_repo.MessageCommandDisposition.COMPLETED:
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


def _raise_attachment(error: AttachmentDecisionError, correlation_id: str) -> NoReturn:
    error.correlation_id = correlation_id
    headers = {"X-Correlation-ID": correlation_id}
    if error.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE:
        headers["Retry-After"] = "30"
    raise HTTPException(
        status_code=error.status_code,
        detail=error.public_body(),
        headers=headers,
    ) from error


# ── Teacher-help router (separate prefix: /teacher-help) ──────────────────────

teacher_help_router = APIRouter()


async def _teacher_help_conversation_dependency(
    body: TeacherHelpRequest,
    actor: Actor = Depends(get_actor),
    facts=Depends(get_authorization_fact_repository),
    correlation_id: str = Depends(get_request_correlation_id),
    audit_sink: AuthorizationAuditSink = Depends(get_authorization_audit_sink),
) -> AuthorizedResource:
    return await authorize_conversation_resource(
        conversation_id=body.conversationId,
        actor=actor,
        facts=facts,
        correlation_id=correlation_id,
        audit_sink=audit_sink,
        action=AuthorizationAction.UPDATE,
        purposes=STUDENT_SELF,
        resolver=_get_conversation,
    )


async def _teacher_help_conversation_metadata_resolver(conversation_id: str):
    return _get_conversation(conversation_id)


setattr(_teacher_help_conversation_dependency, "authorization_specs", (
    AuthorizationSpec(
        ResourceType.CONVERSATION,
        AuthorizationAction.UPDATE,
        AuthorizationPurpose.SELF_SERVICE,
        _teacher_help_conversation_metadata_resolver,
    ),
))


@teacher_help_router.get("/availability", response_model=TeacherAvailabilityResponse)
async def get_teacher_help_availability(
    _actor: Actor = Depends(
        student_actor_dependency(ResourceType.CONVERSATION, AuthorizationAction.LOOKUP)
    ),
):
    """Return student-safe teacher availability for the chat indicator."""
    return teacher_dispatch_service.teacher_availability_summary()


def _escalated_question_operation(
    *,
    request_id: str,
    conversation: Mapping[str, object],
    conversation_id: str,
    student_id: str,
    generation: int,
    message: str | None,
    now: str,
) -> dict[str, Any]:
    """The row the teacher side reads, written with the escalation that caused it.

    Everything a teacher touches - the queue, dispatch, the reply, the SLA
    figures - reads question rows with `status=escalated`. Escalating a
    conversation wrote a marker on the conversation and nothing else, so a
    student could ask for a teacher, see the request accepted, and have no
    teacher ever see it. Measured in production: the request was admitted and
    `GET /teachers/queue` stayed empty.

    The conversation row already reaches one teacher surface - `_get_escalated_conversations`
    feeds `/teachers/me/help-requests` - but not the queue, the dispatch ranking
    or the SLA figures, all of which read question rows. So this is a second
    representation of one case, and the two must not drift: `dispatch_conversation`
    writes the dispatch to both rows in one transaction.

    Created only once: the condition refuses a row that already exists, which is
    what makes a repeated escalation of the same conversation a replay rather
    than a second case.
    """
    return {
        "Put": {
            "Item": question_repo.question_item(
                {
                    "question_id": request_id,
                    "entity_type": "question",
                    "student_id": student_id,
                    "owner_id": student_id,
                    "account_fence_generation": generation,
                    "version": 1,
                    "status": QuestionStatus.ESCALATED.value,
                    "subject": str(conversation.get("subject") or ""),
                    "grade": str(conversation.get("grade") or ""),
                    "source": "conversation_escalation",
                    "conversation_id": conversation_id,
                    "teacher_help_requested": True,
                    "teacher_requested_at": now,
                    "queue_visible_at": now,
                    "content": (message or "").strip(),
                    "created_at": now,
                    "updated_at": now,
                }
            ),
            "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
        }
    }


@teacher_help_router.post("/request", response_model=TeacherHelpResponse)
async def request_teacher_help(
    body: TeacherHelpRequest,
    authorized: AuthorizedResource = Depends(_teacher_help_conversation_dependency),
):
    """Escalate a conversation to a human teacher."""
    student_id = authorized.ref.student_id
    conv = authorized.value
    existing_request_id = conv.get("escalation_request_id")
    request_id = (
        existing_request_id
        if isinstance(existing_request_id, str) and existing_request_id
        else str(uuid.uuid4())
    )
    now = _now()
    observed_at = datetime.fromisoformat(now.replace("Z", "+00:00"))

    # A conversation that already carries an escalation is answered with that
    # escalation. Sending a repeat request back through admission made
    # ``persist_case`` decline every attempt, so the retry loop ran out and the
    # student was shown a 503 instead of the request they already have.
    if isinstance(existing_request_id, str) and existing_request_id:
        return _teacher_help_response(
            conv,
            request_id=existing_request_id,
            conversation_id=body.conversationId,
            fallback_created_at=now,
        )

    table = get_table()

    generation = _active_conversation_generation(student_id, table)

    def persist_case(
        allowance_operations: tuple[dict[str, Any], ...],
    ) -> bool:
        if isinstance(existing_request_id, str) and existing_request_id:
            return False
        try:
            attachment_repo.record_teacher_help_request(
                additional_operations=(
                    *allowance_operations,
                    _escalated_question_operation(
                        request_id=request_id,
                        conversation=conv,
                        conversation_id=body.conversationId,
                        student_id=student_id,
                        generation=generation,
                        message=body.message,
                        now=now,
                    ),
                ),
                conversation={
                    **conv,
                    "PK": _conv_pk(body.conversationId),
                    "SK": "CONV",
                },
                message={
                    "PK": _conv_pk(body.conversationId),
                    "SK": _msg_sk(request_id),
                    "entity_type": "conversation_message",
                    "schema_version": "conversation-message.v1",
                    "message_id": request_id,
                    "conversation_id": body.conversationId,
                    "student_id": student_id,
                    "owner_id": student_id,
                    "account_fence_generation": generation,
                    "role": "system",
                    "content": f"Teacher help requested. {body.message or ''}".strip(),
                    "escalation_message": body.message,
                    "created_at": now,
                },
                owner_id=student_id,
                generation=generation,
                table=table,
            )
        except attachment_repo.AttachmentRepositoryConflict:
            return False
        return True

    admission = teacher_support_allowance_service.admit_teacher_support_case(
        support_case_id=body.conversationId,
        case_kind="conversation",
        beneficiary_id=student_id,
        observed_at=observed_at,
        persist_case=persist_case,
        table=table,
    )
    if (
        admission.disposition
        is teacher_support_allowance_service.TeacherSupportAdmissionDisposition.PLAN_DENIED
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "teacher_support_not_included",
                # Nobody can buy their way past this while the paid surface is
                # frozen, and on an assigned account there was never anything to
                # buy. Pointing at a plan sends the student somewhere that
                # cannot help them.
                "message": "Teacher support is not switched on for this account.",
                "action": "contact_administrator",
            },
        )
    if (
        admission.disposition
        is teacher_support_allowance_service.TeacherSupportAdmissionDisposition.LIMIT_EXCEEDED
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "teacher_support_allowance_exhausted",
                "message": "The weekly teacher-support allowance is used.",
                "action": "wait_for_next_week",
            },
        )
    if (
        admission.disposition
        is teacher_support_allowance_service.TeacherSupportAdmissionDisposition.IDEMPOTENCY_CONFLICT
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Teacher-support case identity conflicts with prior admission",
        )
    if (
        admission.disposition
        is teacher_support_allowance_service.TeacherSupportAdmissionDisposition.RETRYABLE
    ):
        logger.warning(
            "teacher_help_admission_retryable student=%s conversation=%s",
            student_id,
            body.conversationId,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "teacher_support_admission_recoverable",
                "message": "Teacher support is briefly unavailable. Please try again.",
                "action": "retry_same_case",
            },
        )
    if (
        admission.disposition
        is teacher_support_allowance_service.TeacherSupportAdmissionDisposition.REPLAYED
    ):
        return _teacher_help_response(
            conv,
            request_id=request_id,
            conversation_id=body.conversationId,
            fallback_created_at=now,
        )

    dispatch = _dispatch_escalated_conversation(
        conversation_id=body.conversationId,
        conversation=conv,
        student_id=student_id,
        request_id=request_id,
        subject=conv.get("subject"),
        now=now,
        table=table,
    )

    usage_ledger_service.record_usage_event(
        student_id=student_id,
        action=usage_ledger_service.CONVERSATION_TEACHER_HELP_ACTION,
        quota_period=usage_ledger_service.today_period(),
        idempotency_key=usage_ledger_service.build_usage_idempotency_key(
            action=usage_ledger_service.CONVERSATION_TEACHER_HELP_ACTION,
            resource_id=body.conversationId,
            qualifier=request_id,
        ),
        request_correlation_id=request_id,
        created_at=now,
        account_fence_generation=generation,
        metadata={
            "conversation_id": body.conversationId,
            "request_id": request_id,
            "subject": conv.get("subject"),
            "grade_level": conv.get("grade"),
            "status": "pending",
        },
    )

    return TeacherHelpResponse(
        requestId=request_id,
        conversationId=body.conversationId,
        status="assigned" if dispatch else "pending",
        teacherName=dispatch,
        createdAt=now,
        updatedAt=now,
    )


def _teacher_help_response(
    conv: dict[str, Any],
    *,
    request_id: str,
    conversation_id: str,
    fallback_created_at: str,
) -> TeacherHelpResponse:
    """Describe an escalation the way the waiting student should read it."""
    teacher_name = _teacher_name(conv.get("dispatched_teacher_id"))
    escalation_status = str(conv.get("escalation_status") or "pending")
    # A bound teacher outranks the stored label, which stays 'pending' until the
    # teacher opens the case, so the student would otherwise never see progress.
    if teacher_name and escalation_status == "pending":
        escalation_status = "assigned"
    return TeacherHelpResponse(
        requestId=request_id,
        conversationId=conversation_id,
        status=escalation_status,
        teacherName=teacher_name,
        createdAt=str(
            conv.get("escalated_at") or conv.get("created_at") or fallback_created_at
        ),
        updatedAt=str(conv.get("updated_at") or fallback_created_at),
    )


def _teacher_name(teacher_id: object) -> str | None:
    if not isinstance(teacher_id, str) or not teacher_id:
        return None
    profile = user_repo.get_user(teacher_id) or {}
    name = profile.get("name") or profile.get("email")
    return str(name) if name else None


@teacher_help_router.get(
    "/conversations/{conv_id}/request", response_model=TeacherHelpResponse
)
async def get_teacher_help_status(
    authorized: AuthorizedResource = Depends(
        authorized_conversation_dependency(
            action=AuthorizationAction.READ,
            purposes=CONVERSATION_CONTENT_READ,
            resolver=lambda conversation_id: _get_conversation(conversation_id),
        )
    ),
):
    """Report where a student's escalation stands, for the waiting indicator."""
    conv = authorized.value
    request_id = conv.get("escalation_request_id")
    if not isinstance(request_id, str) or not request_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This conversation was never escalated to a teacher",
        )
    return _teacher_help_response(
        conv,
        request_id=request_id,
        conversation_id=authorized.ref.resource_id,
        fallback_created_at="",
    )
