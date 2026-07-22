"""Question routes — submit, retrieve, teacher escalation, feedback."""
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
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


class _QuestionSubmissionRoute(APIRoute):
    """Redact request-validation details at the untrusted submission boundary."""

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
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
        command = result.command or {}
        question_id = command.get("question_id")
        question = question_repo.get_question(str(question_id)) if question_id else None
        if question is not None:
            return dict(question)
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
    try:
        existing_command = question_submission_repo.get_question_submission_command(
            student_id, idempotency_digest
        )
    except Exception:
        _raise_question_submission_error(
            QuestionSubmissionErrorCode.ADMISSION_UNAVAILABLE,
            correlation_id=correlation_id,
        )
    if existing_command is not None:
        classified = question_submission_repo.classify_question_submission_command(
            existing_command,
            student_id=student_id,
            idempotency_digest=idempotency_digest,
            fingerprint=fingerprint,
        )
        assert classified is not None
        replay = _project_question_admission(
            classified,
            correlation_id=correlation_id,
            limit=limit,
        )
        return _question_response(replay or {})

    prepared_attachment: dict[str, Any] | None = None
    if body.attachment is not None:
        try:
            prepared_attachment = attachment_service.reserve_question_attachment(
                body.attachment,
                actor,
                effective_plan=str(entitlement.get("effectivePlan") or subscription_tier),
            )
        except AttachmentDecisionError as error:
            try:
                command = question_submission_repo.get_question_submission_command(
                    student_id, idempotency_digest
                )
            except Exception:
                command = None
            if command is not None:
                classified = (
                    question_submission_repo.classify_question_submission_command(
                        command,
                        student_id=student_id,
                        idempotency_digest=idempotency_digest,
                        fingerprint=fingerprint,
                    )
                )
                assert classified is not None
                replay = _project_question_admission(
                    classified,
                    correlation_id=correlation_id,
                    limit=limit,
                )
                return _question_response(replay or {})
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

    try:
        ai_content, ocr_metadata, ocr_text = _build_question_content(
            body, settings, prepared_attachment
        )
        item["ocr_text"] = ocr_text
        item["ocr_metadata"] = ocr_metadata
        if prepared_attachment is not None:
            question_repo.update_status(
                question_id,
                QuestionStatus.PENDING.value,
                ocr_text=ocr_text,
                ocr_metadata=ocr_metadata,
            )
    except Exception as error:
        emit_private_event(
            "question_ocr_failed",
            exception=error,
            attachment_count=1,
            correlation_id=correlation_id,
            level=logging.WARNING,
        )
        return _question_response(item)

    # Call AI synchronously (Lambda function has up to 30s; Haiku is fast)
    try:
        ai_resp = ai_service.get_ai_answer(
            content=ai_content,
            subject=subject,
            grade=grade,
            language=language,
            correlation_id=correlation_id,
        )
        topic_seeds = learning_profile_service.topic_seeds_from_ai_response(
            subject=subject,
            response=ai_resp,
            question_id=question_id,
            timestamp=now,
        )
        question_repo.update_status(
            question_id,
            QuestionStatus.AI_ANSWERED.value,
            ai_response=ai_resp,
            knowledge_points=ai_resp.get("knowledge_points", []),
            topic_seeds=topic_seeds,
        )
        item["status"] = QuestionStatus.AI_ANSWERED.value
        item["ai_response"] = ai_resp
        item["knowledge_points"] = ai_resp.get("knowledge_points", [])
        item["topic_seeds"] = topic_seeds
    except Exception as exc:
        emit_private_event(
            "question_ai_failed",
            exception=exc,
            input_size=len(ai_content),
            attachment_count=1 if prepared_attachment is not None else 0,
            correlation_id=correlation_id,
            level=logging.ERROR,
        )
        # AI call failed — leave as PENDING; client can poll
        pass

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
    item = authorized.value
    if item.get("status") == QuestionStatus.TEACHER_ACTIVE.value:
        raise HTTPException(status_code=409, detail="Teacher already active on this question")

    now = datetime.now(timezone.utc).isoformat()
    question_repo.update_status(
        question_id,
        QuestionStatus.ESCALATED.value,
        teacher_requested_at=item.get("teacher_requested_at") or now,
        queue_visible_at=item.get("queue_visible_at") or now,
    )
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
    dispatch_question = {
        **item,
        "status": QuestionStatus.ESCALATED.value,
        "teacher_requested_at": item.get("teacher_requested_at") or now,
        "queue_visible_at": item.get("queue_visible_at") or now,
    }
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
    item = authorized.value
    question_repo.update_status(question_id, item["status"], student_feedback=body.rating)
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
