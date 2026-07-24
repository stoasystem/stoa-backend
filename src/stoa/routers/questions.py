"""Question routes — submit, retrieve, teacher escalation, feedback."""
import logging
import hashlib
import json
import secrets
import uuid
from collections.abc import Callable, Coroutine, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any, NoReturn, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from stoa.config import Settings, get_settings
from stoa.db.dynamodb import get_table
from stoa.db.repositories import (
    allowance_repo,
    attachment_repo,
    question_repo,
    question_submission_repo,
    user_repo,
)
from stoa.deps import get_actor
from stoa.jobs import reconcile_question_submissions as question_reconciliation_job
from stoa.security.authorization import AuthorizationAction, AuthorizedResource, ResourceType
from stoa.security.authorization import AuthorizationPurpose, AuthorizationSpec
from stoa.security.errors import normalize_correlation_id
from stoa.security.identity import Actor
from stoa.security.attachment_errors import AttachmentDecisionError
from stoa.security.request_correlation import get_request_correlation_id
from stoa.security.private_telemetry import emit_private_event
from stoa.security.route_authorization import (
    QUESTION_CONTENT_READ,
    STUDENT_SELF,
    authorized_question_dependency,
    student_create_actor_dependency,
)
from stoa.models.question import (
    FeedbackRequest,
    QuestionResponse,
    QuestionStatus,
    QuestionSubmissionErrorCode,
    SubmitQuestionRequest,
)
from stoa.models.moderation import ModerationCaseResponse, ModerationReportRequest
from stoa.services import (
    ai_service,
    allowance_service,
    bedrock_token_count_service,
    learning_profile_service,
    moderation_service,
    entitlement_service,
    notification_service,
    notify_service,
    ocr_service,
    teacher_dispatch_service,
    teacher_support_allowance_service,
    usage_ledger_service,
    attachment_service,
)

router = APIRouter()

_OCR_SOURCE_STATES = frozenset({QuestionStatus.PENDING.value})
_AI_SOURCE_STATES = frozenset({QuestionStatus.PENDING.value})
_ESCALATION_SOURCE_STATES = frozenset(
    {QuestionStatus.PENDING.value, QuestionStatus.AI_ANSWERED.value}
)
_FEEDBACK_SOURCE_STATES = frozenset(
    {QuestionStatus.AI_ANSWERED.value, QuestionStatus.RESOLVED.value}
)
_QUESTION_EFFECT_LEASE_SECONDS = 30


class _QuestionAllowanceFailure(Exception):
    """Stable user-facing admission/finalization failure."""

    def __init__(self, code: str, message: str, action: str, http_status: int):
        self.code = code
        self.message = message
        self.action = action
        self.http_status = http_status
        super().__init__(code)


def _raise_question_allowance_failure(
    error: _QuestionAllowanceFailure,
    *,
    correlation_id: str,
) -> NoReturn:
    raise HTTPException(
        status_code=error.http_status,
        detail={
            "code": error.code,
            "message": error.message,
            "action": error.action,
        },
        headers={"X-Correlation-ID": correlation_id},
    ) from error


def _allowance_recoverable_failure() -> _QuestionAllowanceFailure:
    return _QuestionAllowanceFailure(
        "allowance_finalization_recoverable",
        "This answer is safely stored while token accounting finishes. Retry this question.",
        "retry_same_submission",
        status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def _question_allowance_coordinates(
    command: Mapping[str, object],
    question: Mapping[str, object],
    *,
    observed_at: datetime,
) -> tuple[str, str, int, int]:
    entitlement = question.get("entitlement")
    if not isinstance(entitlement, Mapping):
        entitlement = {}
    plan_id = str(
        entitlement.get("effectivePlan")
        or entitlement.get("effective_plan")
        or "free_trial"
    )
    raw_version = (
        entitlement.get("allowanceVersion")
        or entitlement.get("allowance_version")
        or entitlement.get("planVersion")
        or 1
    )
    if type(raw_version) is not int or raw_version < 1:
        raise _allowance_recoverable_failure()
    grant_id = str(
        entitlement.get("grantId")
        or entitlement.get("grant_id")
        or entitlement.get("source")
        or "student-local"
    )
    base_effect_id = question_submission_repo.question_effect_identity(
        command,
        question_submission_repo.QuestionEffectKind.AI,
    )
    week = allowance_service.zurich_week(observed_at)
    identity_payload = json.dumps(
        {
            "command_effect_id": base_effect_id,
            "command_id": str(command.get("command_id") or ""),
            "plan_id": plan_id,
            "grant_id": grant_id,
            "allowance_version": raw_version,
            "week": f"{week.iso_year:04d}-W{week.iso_week:02d}",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    allowance_effect_id = hashlib.sha256(
        b"stoa.question.allowance-effect.v1\x00" + identity_payload
    ).hexdigest()
    generation = command.get("account_fence_generation")
    if type(generation) is not int or generation < 1:
        raise _allowance_recoverable_failure()
    return allowance_effect_id, plan_id, raw_version, generation


class _QuestionAllowanceBedrockClient:
    """Count, reserve, and persist the Phase 475 intent before InvokeModel."""

    def __init__(
        self,
        command: Mapping[str, object],
        question: Mapping[str, object],
        *,
        observed_at: datetime,
    ) -> None:
        (
            self.allowance_effect_id,
            self.plan_id,
            self.allowance_version,
            self.account_fence_generation,
        ) = _question_allowance_coordinates(
            command,
            question,
            observed_at=observed_at,
        )
        self._command = dict(command)
        self._question = dict(question)
        self._observed_at = observed_at
        self.effect: dict[str, object] | None = None
        self._runtime_client: object | None = None

    def invoke_model(self, **kwargs: object) -> object:
        model_id = kwargs.get("modelId")
        request_body = kwargs.get("body")
        if not isinstance(model_id, str) or not isinstance(request_body, str):
            raise bedrock_token_count_service.ProviderTokenCountUnavailable()
        runtime_client = self._runtime_client or ai_service.boto3.client(
            "bedrock-runtime",
            region_name=ai_service.settings.aws_region,
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
            if (
                type(max_output_tokens) is not int
                or max_output_tokens < 1
            ):
                raise bedrock_token_count_service.ProviderTokenCountUnavailable()
        except (
            bedrock_token_count_service.ProviderTokenCountUnavailable,
            json.JSONDecodeError,
        ):
            raise _QuestionAllowanceFailure(
                "provider_token_count_unavailable",
                "Token admission is temporarily unavailable. Retry this question.",
                "retry_same_submission",
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
            raise _QuestionAllowanceFailure(
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

        if self.effect is None:
            intent = _begin_owned_question_effect(
                self._command,
                self._question,
                question_submission_repo.QuestionEffectKind.AI,
            )
            if (
                intent.disposition
                is not question_submission_repo.QuestionEffectDisposition.INVOKE_PROVIDER
                or intent.effect is None
            ):
                raise _allowance_recoverable_failure()
            self.effect = dict(intent.effect)
        invoke_model = getattr(runtime_client, "invoke_model", None)
        if not callable(invoke_model):
            raise RuntimeError("Bedrock invocation dependency unavailable")
        return invoke_model(**kwargs)


class _QuestionSubmissionRoute(APIRoute):
    """Redact request-validation details at the untrusted submission boundary."""

    def get_route_handler(
        self,
    ) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        route_handler = super().get_route_handler()

        async def redacted_route_handler(request: Request) -> Response:
            try:
                return await route_handler(request)
            except RequestValidationError:
                correlation_id = normalize_correlation_id(
                    getattr(request.state, "stoa_correlation_id", None)
                )
                request.state.stoa_correlation_id = correlation_id
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    content={
                        "detail": {
                            "code": QuestionSubmissionErrorCode.IDENTITY_INVALID.value,
                            "message": "Provide a valid question submission key and try again.",
                            "correlationId": correlation_id,
                        }
                    },
                    headers={"X-Correlation-ID": correlation_id},
                )

        return redacted_route_handler


def _question_limit(
    subscription_tier: str,
    settings: Settings,
    *,
    entitlement: dict[str, Any] | None = None,
) -> int:
    limits = {
        "free_trial": settings.free_tier_daily_question_limit,
        "student": settings.standard_tier_daily_question_limit,
        "teacher_supported": settings.premium_tier_daily_question_limit,
        "family": settings.premium_tier_daily_question_limit,
    }
    effective_plan = (entitlement or {}).get("effectivePlan") or subscription_tier
    return int(
        ((entitlement or {}).get("limits") or {}).get("dailyAiQuestionLimit")
        or limits.get(effective_plan, settings.free_tier_daily_question_limit)
    )


def _raise_question_submission_error(
    code: QuestionSubmissionErrorCode,
    *,
    correlation_id: str,
    limit: int | None = None,
) -> NoReturn:
    if code is QuestionSubmissionErrorCode.PAYLOAD_MISMATCH:
        http_status = status.HTTP_409_CONFLICT
        message = "This submission key belongs to different content. Submit the edit as a new question."
        action = "create_new_submission"
    elif code is QuestionSubmissionErrorCode.QUOTA_EXCEEDED:
        http_status = status.HTTP_429_TOO_MANY_REQUESTS
        message = f"Daily question limit ({limit}) reached for your plan"
        action = "wait_for_quota_reset"
    else:
        http_status = status.HTTP_503_SERVICE_UNAVAILABLE
        message = "Question submission is temporarily unavailable. Try again with the same submission key."
        action = "retry_same_submission"
    raise HTTPException(
        status_code=http_status,
        detail={"code": code.value, "message": message, "action": action},
        headers={"X-Correlation-ID": correlation_id},
    )


def _question_response(item: dict[str, Any]) -> QuestionResponse:
    public_item = dict(item)
    public_item.pop("image_s3_key", None)
    attachment_id = item.get("attachment_id")
    public_item["has_image"] = bool(
        attachment_id or item.get("image_s3_key") or item.get("has_image")
    )
    if attachment_id and not public_item.get("attachment"):
        try:
            summary = attachment_service.list_attachment_summaries(
                [str(attachment_id)]
            ).get(str(attachment_id))
        except Exception:
            summary = None
        public_item["attachment"] = summary
    public_item["ocr_metadata"] = item.get("ocr_metadata") or {
        "status": "not_requested",
        "source": None,
        "text_length": 0,
        "correction_applied": False,
        "failure_class": None,
    }
    return QuestionResponse(**public_item)


def _require_applied_question_mutation(
    result: question_repo.QuestionMutationResult,
) -> dict[str, Any]:
    if (
        result.disposition is question_repo.QuestionMutationDisposition.APPLIED
        and result.question is not None
    ):
        return dict(result.question)
    if result.disposition is question_repo.QuestionMutationDisposition.RETRYABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Question changed temporarily; retry with a fresh question state",
        )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Question state changed; refresh before retrying",
    )


def _initialize_legacy_question_for_mutation(
    question: Mapping[str, object],
    *,
    allowed_source_statuses: frozenset[str],
) -> dict[str, Any]:
    version = question.get("version")
    if isinstance(version, int) and not isinstance(version, bool) and version > 0:
        return dict(question)
    return _require_applied_question_mutation(
        question_repo.initialize_legacy_question_version(
            question,
            allowed_source_statuses=allowed_source_statuses,
        )
    )


def _build_question_content(
    body: SubmitQuestionRequest,
    settings: Settings,
    prepared_attachment: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any], str | None]:
    corrected = body.corrected_text.strip() if body.corrected_text else None
    content = corrected or body.content
    ocr_text: str | None = None
    metadata: dict[str, Any] = {
        "status": "not_requested",
        "source": None,
        "text_length": 0,
        "correction_applied": corrected is not None,
        "failure_class": None,
    }

    if prepared_attachment is None:
        return content, metadata, ocr_text

    metadata["source"] = "question_image"
    attachment = prepared_attachment["attachment"]
    extracted = ocr_service.extract_text_from_attachment(
        attachment, settings_obj=settings
    )
    ocr_text = extracted.strip()
    metadata["text_length"] = len(ocr_text)
    metadata["status"] = "succeeded" if ocr_text else "no_text"
    if ocr_text and corrected is None:
        content = f"{body.content}\n\n[Image text: {ocr_text}]" if body.content else ocr_text
    return content, metadata, ocr_text


def _attachment_identity(body: SubmitQuestionRequest) -> str | None:
    if body.attachment is None:
        return None
    kind, value = body.attachment.identity
    return f"{kind}:{value}"


def _project_question_admission(
    result: question_submission_repo.QuestionAdmissionResult,
    *,
    correlation_id: str,
    limit: int,
) -> dict[str, Any] | None:
    disposition = result.disposition
    if disposition is question_submission_repo.QuestionAdmissionDisposition.ADMITTED:
        return dict(result.question or {})
    if disposition is question_submission_repo.QuestionAdmissionDisposition.RESUME:
        if result.command is not None and result.question is not None:
            if result.command.get("status") == "terminal_failed":
                _reconcile_terminal_question_failure(
                    result.command,
                    correlation_id=correlation_id,
                )
            return dict(result.question)
        _raise_question_submission_error(
            QuestionSubmissionErrorCode.ADMISSION_UNAVAILABLE,
            correlation_id=correlation_id,
        )
    if disposition is question_submission_repo.QuestionAdmissionDisposition.PAYLOAD_MISMATCH:
        _raise_question_submission_error(
            QuestionSubmissionErrorCode.PAYLOAD_MISMATCH,
            correlation_id=correlation_id,
        )
    if disposition is question_submission_repo.QuestionAdmissionDisposition.QUOTA_EXCEEDED:
        _raise_question_submission_error(
            QuestionSubmissionErrorCode.QUOTA_EXCEEDED,
            correlation_id=correlation_id,
            limit=limit,
        )
    _raise_question_submission_error(
        QuestionSubmissionErrorCode.ADMISSION_UNAVAILABLE,
        correlation_id=correlation_id,
    )


_EFFECT_COMPLETION_SUCCEEDED = frozenset(
    {
        question_submission_repo.QuestionEffectDisposition.COMPLETED,
        question_submission_repo.QuestionEffectDisposition.COMPLETION_COMMITTED_RESPONSE_LOST,
    }
)
_EFFECT_RECEIPT_READY = frozenset(
    {
        question_submission_repo.QuestionEffectDisposition.RESULT_READY,
        question_submission_repo.QuestionEffectDisposition.RESULT_RECEIPT_AMBIGUOUS,
    }
)
_TERMINAL_FAILURE_PROVEN = frozenset(
    {
        question_submission_repo.QuestionTerminalFailureDisposition.PROVEN,
        question_submission_repo.QuestionTerminalFailureDisposition.ALREADY_PROVEN,
    }
)


def _raise_terminal_question_failure(*, correlation_id: str) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "question_submission_terminal_failed",
            "message": (
                "This question could not be completed. "
                "Create a new submission to try again."
            ),
            "action": "create_new_submission",
        },
        headers={"X-Correlation-ID": correlation_id},
    )


def _reconcile_terminal_question_failure(
    command: Mapping[str, object],
    *,
    correlation_id: str,
) -> NoReturn:
    try:
        result = question_reconciliation_job.reconcile_proven_terminal_question(
            student_id=str(command["student_id"]),
            command_digest=str(command["command_id"]),
        )
    except Exception:
        _raise_question_submission_error(
            QuestionSubmissionErrorCode.ADMISSION_UNAVAILABLE,
            correlation_id=correlation_id,
        )
    if (
        result.inspected != 1
        or len(result.results) != 1
        or result.results[0].get("disposition") != "committed"
        or result.results[0].get("proposedAction") != "none"
    ):
        _raise_question_submission_error(
            QuestionSubmissionErrorCode.ADMISSION_UNAVAILABLE,
            correlation_id=correlation_id,
        )
    _raise_terminal_question_failure(correlation_id=correlation_id)


def _promote_terminal_effect(
    receipt: question_submission_repo.QuestionEffectResult,
    *,
    correlation_id: str,
) -> None:
    if (
        receipt.disposition
        is not question_submission_repo.QuestionEffectDisposition.TERMINAL_PROVIDER_REJECTION
        or receipt.effect is None
    ):
        return
    proof = question_submission_repo.prove_terminal_question_failure(
        receipt.effect,
        proven_at=datetime.now(timezone.utc).isoformat(),
    )
    if proof.disposition in _TERMINAL_FAILURE_PROVEN and proof.command is not None:
        _reconcile_terminal_question_failure(
            proof.command,
            correlation_id=correlation_id,
        )


def _persisted_question_or_snapshot(
    question: Mapping[str, object],
    command: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    if command is None:
        return dict(question)
    try:
        replay = question_submission_repo.classify_question_submission_replay(
            student_id=str(command["student_id"]),
            idempotency_digest=str(command["command_id"]),
            fingerprint=str(command["fingerprint"]),
        )
    except Exception:
        replay = None
    if (
        replay is not None
        and replay.disposition
        is question_submission_repo.QuestionAdmissionDisposition.RESUME
        and replay.question is not None
    ):
        return dict(replay.question)
    return dict(question)


def _recover_question_effect_receipts(
    command: Mapping[str, object],
    question: Mapping[str, object],
    *,
    correlation_id: str,
    body: SubmitQuestionRequest | None = None,
    settings: Settings | None = None,
    subject: str = "",
    grade: str = "",
    language: str = "",
) -> dict[str, Any]:
    """Drive durable receipts and safely recover unstarted or expired invocations."""
    current_command = dict(command)
    current_question = dict(question)
    for kind in (
        question_submission_repo.QuestionEffectKind.OCR,
        question_submission_repo.QuestionEffectKind.AI,
    ):
        try:
            observed = question_submission_repo.get_question_effect(
                current_command, kind
            )
        except Exception:
            return _persisted_question_or_snapshot(current_question, current_command)
        if observed is None or observed.disposition in {
            question_submission_repo.QuestionEffectDisposition.INTENT_READY,
            question_submission_repo.QuestionEffectDisposition.PROVIDER_INFLIGHT,
        }:
            recovered = _recover_missing_question_effect(
                current_command,
                current_question,
                kind=kind,
                body=body,
                settings=settings,
                subject=subject,
                grade=grade,
                language=language,
                correlation_id=correlation_id,
            )
            if recovered is None:
                continue
            if recovered.question is not None:
                current_question = dict(recovered.question)
            if recovered.command is not None:
                current_command = dict(recovered.command)
            if (
                recovered.disposition
                is question_submission_repo.QuestionEffectDisposition.TERMINAL_PROVIDER_REJECTION
            ):
                _promote_terminal_effect(
                    recovered,
                    correlation_id=correlation_id,
                )
            if recovered.disposition not in _EFFECT_COMPLETION_SUCCEEDED:
                return _persisted_question_or_snapshot(
                    current_question, current_command
                )
            continue
        if (
            observed.disposition
            is question_submission_repo.QuestionEffectDisposition.TERMINAL_PROVIDER_REJECTION
        ):
            _promote_terminal_effect(
                observed,
                correlation_id=correlation_id,
            )
            return _persisted_question_or_snapshot(
                current_question, current_command
            )
        if observed.disposition is question_submission_repo.QuestionEffectDisposition.COMPLETED:
            try:
                refreshed = (
                    question_submission_repo.classify_question_submission_replay(
                        student_id=str(current_command["student_id"]),
                        idempotency_digest=str(current_command["command_id"]),
                        fingerprint=str(current_command["fingerprint"]),
                    )
                )
            except Exception:
                return current_question
            if (
                refreshed is None
                or refreshed.disposition
                is not question_submission_repo.QuestionAdmissionDisposition.RESUME
                or refreshed.command is None
                or refreshed.question is None
            ):
                return current_question
            current_command = dict(refreshed.command)
            current_question = dict(refreshed.question)
            if (
                kind is question_submission_repo.QuestionEffectKind.AI
                and not _finalize_question_allowance(current_question)
            ):
                _raise_question_allowance_failure(
                    _allowance_recoverable_failure(),
                    correlation_id=correlation_id,
                )
            continue
        if (
            observed.disposition
            is not question_submission_repo.QuestionEffectDisposition.RESULT_READY
            or observed.effect is None
        ):
            return _persisted_question_or_snapshot(current_question, current_command)
        try:
            completion = (
                _complete_ready_ai_effect(observed)
                if kind is question_submission_repo.QuestionEffectKind.AI
                else _complete_ready_effect(observed)
            )
        except _QuestionAllowanceFailure as error:
            _raise_question_allowance_failure(
                error,
                correlation_id=correlation_id,
            )
        if completion.disposition not in _EFFECT_COMPLETION_SUCCEEDED:
            return _persisted_question_or_snapshot(current_question, current_command)
        if completion.question is not None:
            current_question = dict(completion.question)
        else:
            current_question = _persisted_question_or_snapshot(
                current_question, current_command
            )
        if completion.command is not None:
            current_command = dict(completion.command)
    return current_question


def _complete_ready_effect(
    receipt: question_submission_repo.QuestionEffectResult,
) -> question_submission_repo.QuestionEffectResult:
    if receipt.disposition not in _EFFECT_RECEIPT_READY or receipt.effect is None:
        return receipt
    return question_submission_repo.complete_question_effect(
        receipt.effect,
        completed_at=datetime.now(timezone.utc).isoformat(),
    )


_QUESTION_ALLOWANCE_METADATA_FIELDS = frozenset(
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


def _question_allowance_metadata(
    ai_response: object,
) -> dict[str, object] | None:
    if not isinstance(ai_response, Mapping):
        return None
    if not _QUESTION_ALLOWANCE_METADATA_FIELDS.issubset(ai_response):
        return None
    metadata = {
        field: ai_response[field] for field in _QUESTION_ALLOWANCE_METADATA_FIELDS
    }
    text_fields = (
        "allowance_effect_id",
        "provider_usage_evidence_id",
        "allowance_finalization_status",
        "provider_request_id_digest",
        "provider_model_id_digest",
    )
    if any(
        not isinstance(metadata[field], str) or not str(metadata[field])
        for field in text_fields
    ):
        return None
    if (
        type(metadata["provider_input_tokens"]) is not int
        or int(metadata["provider_input_tokens"]) < 0
        or type(metadata["provider_output_tokens"]) is not int
        or int(metadata["provider_output_tokens"]) < 0
    ):
        return None
    return metadata


def _with_question_allowance_metadata(
    provider_result: ai_service.AIProviderResult[dict[str, object]],
    *,
    allowance_effect_id: str,
) -> dict[str, object]:
    response = dict(provider_result.content)
    response.update(
        {
            "allowance_effect_id": allowance_effect_id,
            "provider_usage_evidence_id": provider_result.usage.evidence_id,
            "allowance_finalization_status": "durable_result_boundary",
            "provider_request_id_digest": (
                provider_result.usage.provider_request_id_digest
            ),
            "provider_model_id_digest": provider_result.usage.model_id_digest,
            "provider_input_tokens": provider_result.usage.input_tokens,
            "provider_output_tokens": provider_result.usage.output_tokens,
        }
    )
    return response


def _observe_question_provider_usage(
    *,
    beneficiary_id: str,
    ai_response: object,
) -> bool:
    metadata = _question_allowance_metadata(ai_response)
    if metadata is None:
        return True
    observed = allowance_service.record_provider_usage(
        beneficiary_id=beneficiary_id,
        effect_id=str(metadata["allowance_effect_id"]),
        provider_request_id=str(metadata["provider_request_id_digest"]),
        model_id=str(metadata["provider_model_id_digest"]),
        input_tokens=cast(int, metadata["provider_input_tokens"]),
        output_tokens=cast(int, metadata["provider_output_tokens"]),
    )
    return (
        observed.disposition
        in {
            allowance_repo.ProviderUsageDisposition.RECORDED,
            allowance_repo.ProviderUsageDisposition.REPLAYED,
        }
        and observed.evidence is not None
    )


def _finalize_question_allowance(
    question: Mapping[str, object],
) -> bool:
    metadata = _question_allowance_metadata(question.get("ai_response"))
    if metadata is None:
        return True
    finalized = allowance_service.finalize_token_allowance(
        beneficiary_id=str(question["student_id"]),
        effect_id=str(metadata["allowance_effect_id"]),
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


def _restore_question_allowance(
    *,
    beneficiary_id: str,
    ai_response: object,
) -> bool:
    metadata = _question_allowance_metadata(ai_response)
    if metadata is None:
        return True
    restored = allowance_service.restore_user_allowance(
        beneficiary_id=beneficiary_id,
        effect_id=str(metadata["allowance_effect_id"]),
        technical_validation_passed=True,
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


def _complete_ready_ai_effect(
    receipt: question_submission_repo.QuestionEffectResult,
) -> question_submission_repo.QuestionEffectResult:
    effect = receipt.effect
    effect_result = effect.get("result") if isinstance(effect, Mapping) else None
    ai_response = (
        effect_result.get("ai_response")
        if isinstance(effect_result, Mapping)
        else None
    )
    if _question_allowance_metadata(ai_response) is not None:
        if effect is None or not effect.get("student_id"):
            return receipt
        if not _observe_question_provider_usage(
            beneficiary_id=str(effect["student_id"]),
            ai_response=ai_response,
        ):
            return receipt
    completion = _complete_ready_effect(receipt)
    if completion.disposition in _EFFECT_COMPLETION_SUCCEEDED:
        question = completion.question
        if question is not None and not _finalize_question_allowance(question):
            raise _allowance_recoverable_failure()
    return completion


def _begin_owned_question_effect(
    command: Mapping[str, object],
    question: Mapping[str, object],
    kind: question_submission_repo.QuestionEffectKind,
) -> question_submission_repo.QuestionEffectResult:
    claimed_at = datetime.now(timezone.utc)
    return question_submission_repo.begin_question_effect(
        command,
        question,
        kind,
        started_at=claimed_at.isoformat(),
        invocation_owner=secrets.token_urlsafe(24),
        lease_expires_at=(
            claimed_at + timedelta(seconds=_QUESTION_EFFECT_LEASE_SECONDS)
        ).isoformat(),
    )


def _recover_missing_question_effect(
    command: Mapping[str, object],
    question: Mapping[str, object],
    *,
    kind: question_submission_repo.QuestionEffectKind,
    body: SubmitQuestionRequest | None,
    settings: Settings | None,
    subject: str,
    grade: str,
    language: str,
    correlation_id: str,
) -> question_submission_repo.QuestionEffectResult | None:
    """Recreate a missing intent or reclaim an expired invocation, then converge it."""
    if body is None or settings is None or question.get("status") != "pending":
        return None
    provider_result: dict[str, object]
    if kind is question_submission_repo.QuestionEffectKind.OCR:
        attachment_id = str(question.get("attachment_id") or "")
        if not attachment_id:
            return None
        attachment = attachment_repo.get_attachment(attachment_id)
        if not attachment:
            return None
        prepared = {"attachment": dict(attachment)}
    else:
        if question.get("has_image") and not question.get("ocr_text"):
            return None
        prepared = None

    intent: question_submission_repo.QuestionEffectResult | None = None
    allowance_client: _QuestionAllowanceBedrockClient | None = None
    if kind is question_submission_repo.QuestionEffectKind.OCR:
        intent = _begin_owned_question_effect(command, question, kind)
        if (
            intent.disposition
            is not question_submission_repo.QuestionEffectDisposition.INVOKE_PROVIDER
            or intent.effect is None
        ):
            return intent
    else:
        allowance_client = _QuestionAllowanceBedrockClient(
            command,
            question,
            observed_at=datetime.now(timezone.utc),
        )
        intent = _begin_owned_question_effect(command, question, kind)
        if (
            intent.disposition
            is not question_submission_repo.QuestionEffectDisposition.INVOKE_PROVIDER
            or intent.effect is None
        ):
            return intent
        allowance_client.effect = dict(intent.effect)
    try:
        if kind is question_submission_repo.QuestionEffectKind.OCR:
            assert intent is not None
            ai_content, ocr_metadata, ocr_text = _build_question_content(
                body, settings, prepared
            )
            provider_result = {
                "ai_content": ai_content,
                "ocr_text": ocr_text,
                "ocr_metadata": ocr_metadata,
            }
        else:
            assert allowance_client is not None
            ai_content = body.corrected_text.strip() if body.corrected_text else body.content
            ocr_text = str(question.get("ocr_text") or "")
            if ocr_text and body.corrected_text is None:
                ai_content = (
                    f"{body.content}\n\n[Image text: {ocr_text}]"
                    if body.content
                    else ocr_text
                )
            ai_provider_result = ai_service.get_ai_answer(
                content=ai_content,
                subject=subject,
                grade=grade,
                language=language,
                correlation_id=correlation_id,
                effect_id=allowance_client.allowance_effect_id,
                client=allowance_client,
            )
            if isinstance(ai_provider_result, ai_service.AIProviderResult):
                ai_response = _with_question_allowance_metadata(
                    ai_provider_result,
                    allowance_effect_id=allowance_client.allowance_effect_id,
                )
            elif isinstance(ai_provider_result, Mapping):
                ai_response = dict(ai_provider_result)
            else:
                raise ValueError("AI provider result is invalid")
            try:
                topic_seeds = learning_profile_service.topic_seeds_from_ai_response(
                    subject=subject,
                    response=ai_response,
                    question_id=str(question["question_id"]),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            except Exception:
                topic_seeds = []
            provider_result = {
                "ai_response": ai_response,
                "knowledge_points": ai_response.get("knowledge_points", []),
                "topic_seeds": topic_seeds,
            }
            if allowance_client.effect is None:
                intent = _begin_owned_question_effect(command, question, kind)
                if (
                    intent.disposition
                    is not question_submission_repo.QuestionEffectDisposition.INVOKE_PROVIDER
                    or intent.effect is None
                ):
                    return intent
            else:
                intent = question_submission_repo.QuestionEffectResult(
                    question_submission_repo.QuestionEffectDisposition.INVOKE_PROVIDER,
                    effect=allowance_client.effect,
                )
    except _QuestionAllowanceFailure as error:
        _raise_question_allowance_failure(
            error,
            correlation_id=correlation_id,
        )
    except Exception as error:
        if intent is None and allowance_client is not None:
            if allowance_client.effect is not None:
                intent = question_submission_repo.QuestionEffectResult(
                    question_submission_repo.QuestionEffectDisposition.INVOKE_PROVIDER,
                    effect=allowance_client.effect,
                )
            else:
                intent = _begin_owned_question_effect(command, question, kind)
        if intent.effect is None:
            return intent
        terminal = (
            kind is question_submission_repo.QuestionEffectKind.OCR
            and isinstance(error, ocr_service.OcrAttachmentFailure)
            and error.terminal
            and error.category in {"invalid_attachment", "invalid_object"}
        ) or (
            kind is question_submission_repo.QuestionEffectKind.AI
            and isinstance(error, ai_service.AIInvocationFailure)
            and error.category == "response_cleanup_failed"
        )
        if terminal:
            receipt = question_submission_repo.mark_question_effect_terminal(
                intent.effect,
                failure_code="provider_rejected",
                failed_at=datetime.now(timezone.utc).isoformat(),
            )
            _promote_terminal_effect(receipt, correlation_id=correlation_id)
            return receipt
        return question_submission_repo.mark_question_effect_outcome_unknown(
            intent.effect,
            observed_at=datetime.now(timezone.utc).isoformat(),
        )
    assert intent is not None and intent.effect is not None
    provider_usage_ready = (
        kind is not question_submission_repo.QuestionEffectKind.AI
        or _observe_question_provider_usage(
            beneficiary_id=str(intent.effect["student_id"]),
            ai_response=provider_result.get("ai_response"),
        )
    )
    try:
        receipt = question_submission_repo.record_question_effect_result(
            intent.effect,
            provider_result,
            recorded_at=datetime.now(timezone.utc).isoformat(),
        )
    except ValueError:
        if (
            kind is question_submission_repo.QuestionEffectKind.AI
            and (
                not provider_usage_ready
                or not _restore_question_allowance(
                    beneficiary_id=str(intent.effect["student_id"]),
                    ai_response=provider_result.get("ai_response"),
                )
            )
        ):
            _raise_question_allowance_failure(
                _allowance_recoverable_failure(),
                correlation_id=correlation_id,
            )
        receipt = question_submission_repo.mark_question_effect_terminal(
            intent.effect,
            failure_code="provider_rejected",
            failed_at=datetime.now(timezone.utc).isoformat(),
        )
        _promote_terminal_effect(receipt, correlation_id=correlation_id)
        return receipt
    if kind is question_submission_repo.QuestionEffectKind.AI:
        if not provider_usage_ready:
            return receipt
        return _complete_ready_ai_effect(receipt)
    return _complete_ready_effect(receipt)


def _question_attachment_operations(
    *,
    question: dict[str, Any],
    prepared: dict[str, Any] | None,
    actor: Actor,
    effective_plan: str,
    now: str,
) -> tuple[object, ...]:
    if prepared is None:
        return ()
    attachment = prepared["attachment"]
    attachment_id = str(attachment["attachment_id"])
    question_id = str(question["question_id"])
    association: dict[str, object] = {
        **attachment_repo.question_association_key(attachment_id, question_id),
        "attachment_id": attachment_id,
        "owner_id": actor.user_id,
        "student_id": actor.user_id,
        "entity_type": "attachment_association",
        "resource_type": "question",
        "resource_id": question_id,
        "created_at": now,
    }
    return tuple(
        attachment_repo.build_question_attachment_transaction(
            question=question_repo.question_item(question),
            prepared=prepared,
            attachment=attachment,
            association=association,
            owner_id=actor.user_id,
            limit_bytes=attachment_service.storage_limit_for_entitlement(effective_plan),
            now_iso=now,
        )
    )


def _prepared_attachment_summary(
    prepared: dict[str, Any] | None,
) -> dict[str, object] | None:
    if prepared is None:
        return None
    attachment = prepared["attachment"]
    return {
        "attachmentId": str(attachment["attachment_id"]),
        "filename": str(attachment["original_filename"]),
        "mediaType": str(attachment["detected_type"]),
        "sizeBytes": int(attachment["content_length"]),
        "status": "active",
        "createdAt": str(attachment["created_at"]),
    }


def _raise_attachment(error: AttachmentDecisionError, correlation_id: str) -> None:
    error.correlation_id = correlation_id
    raise HTTPException(
        status_code=error.status_code,
        detail=error.public_body(),
        headers={"X-Correlation-ID": correlation_id},
    ) from error


async def _question_attachment_inventory_resolver(resource_id: str):
    return {"student_id": resource_id}


_question_create_actor_dependency = student_create_actor_dependency(ResourceType.QUESTION)


async def _question_create_dependency(
    actor: Actor = Depends(_question_create_actor_dependency),
) -> Actor:
    return actor


_question_create_dependency.authorization_specs = (  # type: ignore[attr-defined]
    *getattr(_question_create_actor_dependency, "authorization_specs", ()),
    AuthorizationSpec(
        ResourceType.UPLOAD,
        AuthorizationAction.UPDATE,
        AuthorizationPurpose.SELF_SERVICE,
        _question_attachment_inventory_resolver,
    ),
    AuthorizationSpec(
        ResourceType.ATTACHMENT,
        AuthorizationAction.READ,
        AuthorizationPurpose.SELF_SERVICE,
        _question_attachment_inventory_resolver,
    ),
)


async def submit_question(
    body: SubmitQuestionRequest,
    actor: Actor = Depends(_question_create_dependency),
    settings: Settings = Depends(get_settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Submit a question; run OCR if an image is provided, then call AI."""
    student_id = actor.user_id
    idempotency_digest = (
        question_submission_repo.question_submission_command_digest(
            student_id, body.idempotency_key
        )
    )
    student_profile = user_repo.get_user(student_id) or {}
    subscription_tier = str(
        student_profile.get("subscription_tier") or "free_trial"
    )
    entitlement = entitlement_service.resolve_student_entitlement(
        student_id,
        settings=settings,
        student_profile=student_profile,
    )
    language = str(student_profile.get("language") or "de")
    grade = str(student_profile.get("grade") or "Sek1")
    subject = learning_profile_service.normalize_subject(body.subject)
    question_id = str(uuid.uuid4())
    quota_period = usage_ledger_service.today_period()
    attachment_identity = _attachment_identity(body)
    attachment_identities = (attachment_identity,) if attachment_identity else ()
    fingerprint = question_submission_repo.question_submission_fingerprint(
        subject=subject,
        original_content=body.content,
        corrected_content=body.corrected_text,
        attachment_identities=attachment_identities,
    )
    limit = _question_limit(
        subscription_tier, settings, entitlement=entitlement
    )

    # Avoid re-reserving an upload for a durable replay. A later strong read in
    # admit_question_submission remains the authority for concurrent first calls.
    existing_replay = question_submission_repo.classify_question_submission_replay(
        student_id=student_id,
        idempotency_digest=idempotency_digest,
        fingerprint=fingerprint,
    )
    if existing_replay is not None:
        replay = _project_question_admission(
            existing_replay,
            correlation_id=correlation_id,
            limit=limit,
        )
        recovered = _recover_question_effect_receipts(
            existing_replay.command or {},
            replay or {},
            correlation_id=correlation_id,
            body=body,
            settings=settings,
            subject=subject,
            grade=grade,
            language=language,
        )
        return _question_response(recovered)

    prepared_attachment: dict[str, Any] | None = None
    if body.attachment is not None:
        try:
            prepared_attachment = attachment_service.reserve_question_attachment(
                body.attachment,
                actor,
                effective_plan=str(entitlement.get("effectivePlan") or subscription_tier),
            )
        except AttachmentDecisionError as error:
            replay_result = (
                question_submission_repo.classify_question_submission_replay(
                    student_id=student_id,
                    idempotency_digest=idempotency_digest,
                    fingerprint=fingerprint,
                )
            )
            if replay_result is not None:
                replay = _project_question_admission(
                    replay_result,
                    correlation_id=correlation_id,
                    limit=limit,
                )
                recovered = _recover_question_effect_receipts(
                    replay_result.command or {},
                    replay or {},
                    correlation_id=correlation_id,
                    body=body,
                    settings=settings,
                    subject=subject,
                    grade=grade,
                    language=language,
                )
                return _question_response(recovered)
            _raise_attachment(error, correlation_id)

    now = datetime.now(timezone.utc).isoformat()
    public_content = body.corrected_text.strip() if body.corrected_text else body.content
    initial_ocr_metadata = {
        "status": "processing" if prepared_attachment is not None else "not_requested",
        "source": "question_image" if prepared_attachment is not None else None,
        "text_length": 0,
        "correction_applied": body.corrected_text is not None,
        "failure_class": None,
    }
    item: dict[str, Any] = {
        "entity_type": "question",
        "schema_version": "question.v1",
        "question_id": question_id,
        "student_id": student_id,
        "subject": subject,
        "content": public_content,
        "original_content": body.content,
        "corrected_text": body.corrected_text,
        "attachment_id": (
            prepared_attachment["attachment"]["attachment_id"]
            if prepared_attachment is not None
            else None
        ),
        "attachment_source_identity": attachment_identity,
        "has_image": prepared_attachment is not None,
        "ocr_text": None,
        "ocr_metadata": initial_ocr_metadata,
        "status": QuestionStatus.PENDING.value,
        "ai_response": None,
        "teacher_id": None,
        "teacher_response": None,
        "knowledge_points": [],
        "topic_seeds": [],
        "entitlement": entitlement,
        "student_feedback": None,
        "created_at": now,
        "resolved_at": None,
        "version": 1,
    }
    usage_event = usage_ledger_service.build_question_usage_event(
        student_id=student_id,
        question_id=question_id,
        quota_period=quota_period,
        idempotency_digest=idempotency_digest,
        counter_key=f"USAGE#{student_id}/QUESTION#{quota_period}",
        counter_value=1,
        quantity=1,
        entitlement=entitlement,
        created_at=now,
    )
    try:
        result = question_submission_repo.admit_question_submission(
            student_id=student_id,
            idempotency_digest=idempotency_digest,
            fingerprint=fingerprint,
            question=item,
            usage_event=usage_event,
            quota_period=quota_period,
            limit=limit,
            expires_at=usage_ledger_service.counter_ttl(),
            attachment_identities=attachment_identities,
            attachment_operations=_question_attachment_operations(
                question=item,
                prepared=prepared_attachment,
                actor=actor,
                effective_plan=str(
                    entitlement.get("effectivePlan") or subscription_tier
                ),
                now=now,
            ),
            created_at=now,
        )
    except Exception:
        if prepared_attachment is not None:
            attachment_service.release_question_attachment_reservation(
                prepared_attachment, actor
            )
        _raise_question_submission_error(
            QuestionSubmissionErrorCode.ADMISSION_UNAVAILABLE,
            correlation_id=correlation_id,
        )
    if result.disposition is not question_submission_repo.QuestionAdmissionDisposition.ADMITTED:
        if prepared_attachment is not None:
            attachment_service.release_question_attachment_reservation(
                prepared_attachment, actor
            )
        replay = _project_question_admission(
            result,
            correlation_id=correlation_id,
            limit=limit,
        )
        return _question_response(replay or {})

    item["attachment"] = _prepared_attachment_summary(prepared_attachment)

    command = dict(result.command or {})
    if not command:
        return _question_response(_persisted_question_or_snapshot(item))
    ai_content = body.corrected_text.strip() if body.corrected_text else body.content

    if prepared_attachment is not None:
        intent = _begin_owned_question_effect(
            command, item, question_submission_repo.QuestionEffectKind.OCR
        )
        if (
            intent.disposition
            is not question_submission_repo.QuestionEffectDisposition.INVOKE_PROVIDER
            or intent.effect is None
        ):
            return _question_response(_persisted_question_or_snapshot(item, command))
        try:
            ai_content, ocr_metadata, ocr_text = _build_question_content(
                body, settings, prepared_attachment
            )
            receipt = question_submission_repo.record_question_effect_result(
                intent.effect,
                {
                    "ai_content": ai_content,
                    "ocr_text": ocr_text,
                    "ocr_metadata": ocr_metadata,
                },
                recorded_at=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as error:
            terminal = (
                isinstance(error, ocr_service.OcrAttachmentFailure)
                and error.terminal
                and error.category in {"invalid_attachment", "invalid_object"}
            )
            if terminal:
                terminal_receipt = question_submission_repo.mark_question_effect_terminal(
                    intent.effect,
                    failure_code="provider_rejected",
                    failed_at=datetime.now(timezone.utc).isoformat(),
                )
            else:
                question_submission_repo.mark_question_effect_outcome_unknown(
                    intent.effect,
                    observed_at=datetime.now(timezone.utc).isoformat(),
                )
            emit_private_event(
                "question_ocr_failed",
                exception=error,
                attachment_count=1,
                correlation_id=correlation_id,
                level=logging.WARNING,
            )
            if terminal:
                _promote_terminal_effect(
                    terminal_receipt,
                    correlation_id=correlation_id,
                )
            return _question_response(_persisted_question_or_snapshot(item, command))
        completion = _complete_ready_effect(receipt)
        if completion.disposition not in _EFFECT_COMPLETION_SUCCEEDED:
            return _question_response(_persisted_question_or_snapshot(item, command))
        if completion.question is not None:
            item = dict(completion.question)
        if completion.command is not None:
            command = dict(completion.command)

    try:
        allowance_client = _QuestionAllowanceBedrockClient(
            command,
            item,
            observed_at=datetime.now(timezone.utc),
        )
        ai_intent = _begin_owned_question_effect(
            command,
            item,
            question_submission_repo.QuestionEffectKind.AI,
        )
        if (
            ai_intent.disposition
            is not question_submission_repo.QuestionEffectDisposition.INVOKE_PROVIDER
            or ai_intent.effect is None
        ):
            return _question_response(
                _persisted_question_or_snapshot(item, command)
            )
        allowance_client.effect = dict(ai_intent.effect)
    except _QuestionAllowanceFailure as error:
        _raise_question_allowance_failure(
            error,
            correlation_id=correlation_id,
        )
    try:
        ai_provider_result = ai_service.get_ai_answer(
            content=ai_content,
            subject=subject,
            grade=grade,
            language=language,
            correlation_id=correlation_id,
            effect_id=allowance_client.allowance_effect_id,
            client=allowance_client,
        )
        if isinstance(ai_provider_result, ai_service.AIProviderResult):
            ai_resp = _with_question_allowance_metadata(
                ai_provider_result,
                allowance_effect_id=allowance_client.allowance_effect_id,
            )
        elif isinstance(ai_provider_result, Mapping):
            ai_resp = dict(ai_provider_result)
        else:
            raise ValueError("AI provider result is invalid")
        try:
            topic_seeds = learning_profile_service.topic_seeds_from_ai_response(
                subject=subject,
                response=ai_resp,
                question_id=question_id,
                timestamp=now,
            )
        except Exception:
            topic_seeds = []
        if allowance_client.effect is None:
            legacy_intent = _begin_owned_question_effect(
                command,
                item,
                question_submission_repo.QuestionEffectKind.AI,
            )
            if (
                legacy_intent.disposition
                is not question_submission_repo.QuestionEffectDisposition.INVOKE_PROVIDER
                or legacy_intent.effect is None
            ):
                return _question_response(
                    _persisted_question_or_snapshot(item, command)
                )
            ai_effect = dict(legacy_intent.effect)
        else:
            ai_effect = dict(allowance_client.effect)
    except _QuestionAllowanceFailure as error:
        _raise_question_allowance_failure(
            error,
            correlation_id=correlation_id,
        )
    except Exception as exc:
        if allowance_client.effect is None:
            legacy_intent = _begin_owned_question_effect(
                command,
                item,
                question_submission_repo.QuestionEffectKind.AI,
            )
            ai_effect = (
                dict(legacy_intent.effect)
                if legacy_intent.effect is not None
                else None
            )
        else:
            ai_effect = dict(allowance_client.effect)
        if ai_effect is None:
            return _question_response(
                _persisted_question_or_snapshot(item, command)
            )
        terminal = (
            isinstance(exc, ai_service.AIInvocationFailure)
            and exc.category == "response_cleanup_failed"
        )
        if terminal:
            terminal_receipt = question_submission_repo.mark_question_effect_terminal(
                ai_effect,
                failure_code="provider_rejected",
                failed_at=datetime.now(timezone.utc).isoformat(),
            )
        else:
            question_submission_repo.mark_question_effect_outcome_unknown(
                ai_effect,
                observed_at=datetime.now(timezone.utc).isoformat(),
            )
        emit_private_event(
            "question_ai_failed",
            exception=exc,
            input_size=len(ai_content),
            attachment_count=1 if prepared_attachment is not None else 0,
            correlation_id=correlation_id,
            level=logging.ERROR,
        )
        if terminal:
            _promote_terminal_effect(
                terminal_receipt,
                correlation_id=correlation_id,
            )
        return _question_response(_persisted_question_or_snapshot(item, command))

    ai_result = {
        "ai_response": ai_resp,
        "knowledge_points": ai_resp.get("knowledge_points", []),
        "topic_seeds": topic_seeds,
    }
    provider_usage_ready = _observe_question_provider_usage(
        beneficiary_id=student_id,
        ai_response=ai_resp,
    )
    try:
        ai_receipt = question_submission_repo.record_question_effect_result(
            ai_effect,
            ai_result,
            recorded_at=datetime.now(timezone.utc).isoformat(),
        )
    except ValueError:
        if (
            not provider_usage_ready
            or not _restore_question_allowance(
                beneficiary_id=student_id,
                ai_response=ai_resp,
            )
        ):
            _raise_question_allowance_failure(
                _allowance_recoverable_failure(),
                correlation_id=correlation_id,
            )
        terminal_receipt = question_submission_repo.mark_question_effect_terminal(
            ai_effect,
            failure_code="provider_rejected",
            failed_at=datetime.now(timezone.utc).isoformat(),
        )
        _promote_terminal_effect(
            terminal_receipt,
            correlation_id=correlation_id,
        )
        return _question_response(_persisted_question_or_snapshot(item, command))
    if not provider_usage_ready:
        return _question_response(_persisted_question_or_snapshot(item, command))
    try:
        ai_completion = _complete_ready_ai_effect(ai_receipt)
    except _QuestionAllowanceFailure as error:
        _raise_question_allowance_failure(
            error,
            correlation_id=correlation_id,
        )
    if ai_completion.disposition in _EFFECT_COMPLETION_SUCCEEDED:
        if ai_completion.question is not None:
            item = dict(ai_completion.question)
    else:
        item = _persisted_question_or_snapshot(item, command)

    return _question_response(item)


router.add_api_route(
    "",
    submit_question,
    methods=["POST"],
    response_model=QuestionResponse,
    status_code=status.HTTP_201_CREATED,
    route_class_override=_QuestionSubmissionRoute,
)


@router.get("/{question_id}", response_model=QuestionResponse)
async def get_question(
    authorized: AuthorizedResource = Depends(
        authorized_question_dependency(
            action=AuthorizationAction.READ, purposes=QUESTION_CONTENT_READ
        )
    ),
):
    """Retrieve a question and its AI/teacher response."""
    return _question_response(dict(authorized.value))


@router.post("/{question_id}/request-teacher", status_code=status.HTTP_202_ACCEPTED)
async def request_teacher(
    authorized: AuthorizedResource = Depends(
        authorized_question_dependency(
            action=AuthorizationAction.UPDATE, purposes=STUDENT_SELF
        )
    ),
    settings: Settings = Depends(get_settings),
):
    """Escalate a question to a human teacher via SQS FIFO queue."""
    question_id = authorized.ref.resource_id
    student_id = authorized.ref.student_id
    observed_item = authorized.value
    if observed_item.get("status") == QuestionStatus.TEACHER_ACTIVE.value:
        raise HTTPException(status_code=409, detail="Teacher already active on this question")
    is_replay = observed_item.get("status") == QuestionStatus.ESCALATED.value
    if not is_replay and observed_item.get("status") not in _ESCALATION_SOURCE_STATES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Question cannot be escalated from its current state",
        )
    item = (
        dict(observed_item)
        if is_replay
        else _initialize_legacy_question_for_mutation(
            observed_item,
            allowed_source_statuses=_ESCALATION_SOURCE_STATES,
        )
    )
    observed_at = datetime.now(timezone.utc)
    now = observed_at.isoformat()
    table = get_table()
    mutations: list[question_repo.QuestionMutationResult] = []

    admission = teacher_support_allowance_service.admit_teacher_support_case(
        support_case_id=question_id,
        case_kind="question",
        beneficiary_id=student_id,
        observed_at=observed_at,
        persist_case=lambda allowance_operations: (
            False
            if is_replay
            else (
                mutations.append(
                    question_repo.mutate_question(
                        item,
                        status=QuestionStatus.ESCALATED.value,
                        allowed_source_statuses=_ESCALATION_SOURCE_STATES,
                        additional_operations=allowance_operations,
                        extra_attrs={
                            "teacher_requested_at": (
                                item.get("teacher_requested_at") or now
                            ),
                            "queue_visible_at": item.get("queue_visible_at") or now,
                        },
                        table=table,
                    )
                )
                or mutations[-1].disposition
                is question_repo.QuestionMutationDisposition.APPLIED
            )
        ),
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
                "message": "Teacher support is not included in the active plan.",
                "action": "choose_paid_plan",
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
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "teacher_support_admission_recoverable",
                "message": "Teacher support admission is safely recoverable.",
                "action": "retry_same_case",
            },
        )
    if (
        admission.disposition
        is teacher_support_allowance_service.TeacherSupportAdmissionDisposition.REPLAYED
    ):
        return {
            "question_id": question_id,
            "status": QuestionStatus.ESCALATED.value,
            "dispatch": {"questionId": question_id, "status": "replayed"},
        }
    if not mutations:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Teacher-support case admission did not return its durable case",
        )
    dispatch_question = _require_applied_question_mutation(mutations[-1])

    operation_id = str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"stoa:teacher-support:question:{question_id}")
    )
    notify_service.enqueue_teacher_request(
        question_id=question_id,
        operation_id=operation_id,
        generation=int(item.get("account_fence_generation") or 1),
        owner_id=student_id,
    )
    notification_service.emit_teacher_requested(
        question_id=question_id,
        student_id=student_id,
        subject=item["subject"],
    )
    try:
        dispatch = teacher_dispatch_service.dispatch_question(question_id, question=dispatch_question, now=now)
    except Exception as exc:  # noqa: BLE001
        dispatch = {
            "questionId": question_id,
            "status": "deferred",
            "reason": type(exc).__name__,
        }
    usage_ledger_service.record_usage_event(
        student_id=student_id,
        action=usage_ledger_service.QUESTION_TEACHER_HELP_ACTION,
        quota_period=usage_ledger_service.today_period(),
        idempotency_key=usage_ledger_service.build_usage_idempotency_key(
            action=usage_ledger_service.QUESTION_TEACHER_HELP_ACTION,
            resource_id=question_id,
        ),
        created_at=now,
        request_correlation_id=question_id,
        metadata={
            "question_id": question_id,
            "subject": item.get("subject"),
            "status": QuestionStatus.ESCALATED.value,
        },
    )
    return {"question_id": question_id, "status": QuestionStatus.ESCALATED.value, "dispatch": dispatch}


@router.post("/{question_id}/feedback", status_code=status.HTTP_200_OK)
async def submit_feedback(
    body: FeedbackRequest,
    authorized: AuthorizedResource = Depends(
        authorized_question_dependency(
            action=AuthorizationAction.UPDATE, purposes=STUDENT_SELF
        )
    ),
):
    """Rate a resolved question (1–5 stars)."""
    question_id = authorized.ref.resource_id
    observed_item = authorized.value
    if observed_item.get("status") not in _FEEDBACK_SOURCE_STATES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Feedback is not available for the current question state",
        )
    item = _initialize_legacy_question_for_mutation(
        observed_item,
        allowed_source_statuses=_FEEDBACK_SOURCE_STATES,
    )
    _require_applied_question_mutation(
        question_repo.mutate_question(
            item,
            status=str(item["status"]),
            allowed_source_statuses=_FEEDBACK_SOURCE_STATES,
            extra_attrs={"student_feedback": body.rating},
        )
    )
    return {"question_id": question_id, "rating": body.rating}


@router.post(
    "/{question_id}/reports",
    response_model=ModerationCaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def report_question_content(
    body: ModerationReportRequest,
    authorized: AuthorizedResource = Depends(
        authorized_question_dependency(
            action=AuthorizationAction.CREATE, purposes=QUESTION_CONTENT_READ
        )
    ),
    actor: Actor = Depends(get_actor),
):
    """Create a moderation case for reportable question content."""
    return moderation_service.create_case(
        authorized.ref.resource_id,
        body,
        {"sub": actor.user_id, "role": actor.role.value},
        question=dict(authorized.value),
    )
