"""Question routes — submit, retrieve, teacher escalation, feedback."""
import logging
import secrets
import uuid
from collections.abc import Callable, Coroutine, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from stoa.config import Settings, get_settings
from stoa.db.repositories import (
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
    learning_profile_service,
    moderation_service,
    entitlement_service,
    notification_service,
    notify_service,
    ocr_service,
    teacher_dispatch_service,
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
        "free": settings.free_tier_daily_question_limit,
        "standard": settings.standard_tier_daily_question_limit,
        "premium": settings.premium_tier_daily_question_limit,
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
            continue
        if (
            observed.disposition
            is not question_submission_repo.QuestionEffectDisposition.RESULT_READY
            or observed.effect is None
        ):
            return _persisted_question_or_snapshot(current_question, current_command)
        completion = question_submission_repo.complete_question_effect(
            observed.effect,
            completed_at=datetime.now(timezone.utc).isoformat(),
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

    intent = _begin_owned_question_effect(command, question, kind)
    if (
        intent.disposition
        is not question_submission_repo.QuestionEffectDisposition.INVOKE_PROVIDER
        or intent.effect is None
    ):
        return intent
    try:
        if kind is question_submission_repo.QuestionEffectKind.OCR:
            ai_content, ocr_metadata, ocr_text = _build_question_content(
                body, settings, prepared
            )
            provider_result = {
                "ai_content": ai_content,
                "ocr_text": ocr_text,
                "ocr_metadata": ocr_metadata,
            }
        else:
            ai_content = body.corrected_text.strip() if body.corrected_text else body.content
            ocr_text = str(question.get("ocr_text") or "")
            if ocr_text and body.corrected_text is None:
                ai_content = (
                    f"{body.content}\n\n[Image text: {ocr_text}]"
                    if body.content
                    else ocr_text
                )
            ai_response = ai_service.get_ai_answer(
                content=ai_content,
                subject=subject,
                grade=grade,
                language=language,
                correlation_id=correlation_id,
            )
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
    except Exception as error:
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
    try:
        receipt = question_submission_repo.record_question_effect_result(
            intent.effect,
            provider_result,
            recorded_at=datetime.now(timezone.utc).isoformat(),
        )
    except ValueError:
        receipt = question_submission_repo.mark_question_effect_terminal(
            intent.effect,
            failure_code="invalid_provider_result",
            failed_at=datetime.now(timezone.utc).isoformat(),
        )
        _promote_terminal_effect(receipt, correlation_id=correlation_id)
        return receipt
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
    subscription_tier = str(student_profile.get("subscription_tier") or "free")
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

    ai_intent = _begin_owned_question_effect(
        command, item, question_submission_repo.QuestionEffectKind.AI
    )
    if (
        ai_intent.disposition
        is not question_submission_repo.QuestionEffectDisposition.INVOKE_PROVIDER
        or ai_intent.effect is None
    ):
        return _question_response(_persisted_question_or_snapshot(item, command))

    try:
        ai_resp = ai_service.get_ai_answer(
            content=ai_content,
            subject=subject,
            grade=grade,
            language=language,
            correlation_id=correlation_id,
        )
        try:
            topic_seeds = learning_profile_service.topic_seeds_from_ai_response(
                subject=subject,
                response=ai_resp,
                question_id=question_id,
                timestamp=now,
            )
        except Exception:
            topic_seeds = []
        ai_receipt = question_submission_repo.record_question_effect_result(
            ai_intent.effect,
            {
                "ai_response": ai_resp,
                "knowledge_points": ai_resp.get("knowledge_points", []),
                "topic_seeds": topic_seeds,
            },
            recorded_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        terminal = (
            isinstance(exc, ai_service.AIInvocationFailure)
            and exc.category == "response_cleanup_failed"
        )
        if terminal:
            terminal_receipt = question_submission_repo.mark_question_effect_terminal(
                ai_intent.effect,
                failure_code="provider_rejected",
                failed_at=datetime.now(timezone.utc).isoformat(),
            )
        else:
            question_submission_repo.mark_question_effect_outcome_unknown(
                ai_intent.effect,
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
    ai_completion = _complete_ready_effect(ai_receipt)
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
    if observed_item.get("status") not in _ESCALATION_SOURCE_STATES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Question cannot be escalated from its current state",
        )
    item = _initialize_legacy_question_for_mutation(
        observed_item,
        allowed_source_statuses=_ESCALATION_SOURCE_STATES,
    )

    now = datetime.now(timezone.utc).isoformat()
    mutation = question_repo.mutate_question(
        item,
        status=QuestionStatus.ESCALATED.value,
        allowed_source_statuses=_ESCALATION_SOURCE_STATES,
        extra_attrs={
            "teacher_requested_at": item.get("teacher_requested_at") or now,
            "queue_visible_at": item.get("queue_visible_at") or now,
        },
    )
    dispatch_question = _require_applied_question_mutation(mutation)
    operation_id = str(uuid.uuid4())
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
