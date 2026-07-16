"""Question routes — submit, retrieve, teacher escalation, feedback."""
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from stoa.config import Settings, get_settings
from stoa.db.repositories import question_repo, user_repo
from stoa.deps import get_actor
from stoa.security.authorization import AuthorizationAction, AuthorizedResource, ResourceType
from stoa.security.authorization import AuthorizationPurpose, AuthorizationSpec
from stoa.security.identity import Actor
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.security.request_correlation import get_request_correlation_id
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


def _check_daily_limit(
    student_id: str,
    subscription_tier: str,
    settings: Settings,
    *,
    entitlement: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Raise 429 if the student has exceeded their daily question quota."""
    limits = {
        "free": settings.free_tier_daily_question_limit,
        "standard": settings.standard_tier_daily_question_limit,
        "premium": settings.premium_tier_daily_question_limit,
    }
    effective_plan = (entitlement or {}).get("effectivePlan") or subscription_tier
    limit = int(
        ((entitlement or {}).get("limits") or {}).get("dailyAiQuestionLimit")
        or limits.get(effective_plan, settings.free_tier_daily_question_limit)
    )
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    expires_at = int(datetime.now(timezone.utc).timestamp()) + 172800
    count = question_repo.record_daily_question_usage(student_id, today, limit, expires_at)
    if count is None:
        blocking_reason = (entitlement or {}).get("blockingReason")
        suffix = f" ({blocking_reason})" if blocking_reason else ""
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily question limit ({limit}) reached for your plan{suffix}",
        )
    return {
        "quotaPeriod": today,
        "counterKey": f"USAGE#{student_id}/QUESTION#{today}",
        "counterValue": count,
        "limit": limit,
        "expiresAt": expires_at,
    }


def _question_response(item: dict[str, Any]) -> QuestionResponse:
    public_item = dict(item)
    public_item.pop("image_s3_key", None)
    attachment_id = item.get("attachment_id")
    public_item["has_image"] = bool(
        attachment_id or item.get("image_s3_key") or item.get("has_image")
    )
    if attachment_id and not public_item.get("attachment"):
        summary = attachment_service.list_attachment_summaries([str(attachment_id)]).get(
            str(attachment_id)
        )
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
    extracted = ocr_service.extract_text_from_s3(
        settings.s3_images_bucket, attachment["object_key"]
    )
    ocr_text = extracted.strip()
    metadata["text_length"] = len(ocr_text)
    metadata["status"] = "succeeded" if ocr_text else "no_text"
    if ocr_text and corrected is None:
        content = f"{body.content}\n\n[Image text: {ocr_text}]" if body.content else ocr_text
    return content, metadata, ocr_text


def _question_retry_matches(existing_question: dict[str, Any], body: SubmitQuestionRequest, subject: str) -> bool:
    """Return whether an idempotent retry matches the original question intent."""
    return (
        existing_question.get("subject") == subject
        and (existing_question.get("original_content") or existing_question.get("content")) == body.content
        and (existing_question.get("corrected_text") or None) == (body.corrected_text or None)
        and (existing_question.get("attachment_source_identity") or None)
        == (_attachment_identity(body) or None)
    )


def _attachment_identity(body: SubmitQuestionRequest) -> str | None:
    if body.attachment is None:
        return None
    kind, value = body.attachment.identity
    return f"{kind}:{value}"


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


@router.post("", response_model=QuestionResponse, status_code=status.HTTP_201_CREATED)
async def submit_question(
    body: SubmitQuestionRequest,
    actor: Actor = Depends(_question_create_dependency),
    settings: Settings = Depends(get_settings),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Submit a question; run OCR if an image is provided, then call AI."""
    student_id = actor.user_id
    student_profile = user_repo.get_user(student_id) or {}
    subscription_tier = student_profile.get("subscription_tier", "free")
    entitlement = entitlement_service.resolve_student_entitlement(
        student_id,
        settings=settings,
        student_profile=student_profile,
    )
    language = student_profile.get("language", "de")
    grade = student_profile.get("grade", "Sek1")
    subject = learning_profile_service.normalize_subject(body.subject)
    question_id = str(uuid.uuid4())
    idempotency_key = usage_ledger_service.build_question_idempotency_key(
        question_id,
        body.idempotency_key,
    )
    quota_period = usage_ledger_service.today_period()

    if body.idempotency_key:
        existing_usage = usage_ledger_service.get_question_usage_event(
            student_id=student_id,
            quota_period=quota_period,
            idempotency_key=idempotency_key,
        )
        if existing_usage and existing_usage.get("question_id"):
            existing_question = question_repo.get_question(str(existing_usage["question_id"]))
            if existing_question:
                if not _question_retry_matches(existing_question, body, subject):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Idempotency key was already used for a different question submission",
                    )
                return _question_response(existing_question)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Question submission is already recorded; retry later",
            )

    prepared_attachment: dict[str, Any] | None = None
    if body.attachment is not None:
        try:
            prepared_attachment = attachment_service.reserve_question_attachment(
                body.attachment,
                actor,
                effective_plan=str(entitlement.get("effectivePlan") or subscription_tier),
            )
        except AttachmentDecisionError as error:
            _raise_attachment(error, correlation_id)

    try:
        usage_counter = _check_daily_limit(
            student_id, subscription_tier, settings, entitlement=entitlement
        )
    except Exception:
        if prepared_attachment is not None:
            attachment_service.release_question_attachment_reservation(
                prepared_attachment, actor
            )
        raise

    try:
        content, ocr_metadata, ocr_text = _build_question_content(
            body, settings, prepared_attachment
        )
    except Exception:
        if prepared_attachment is not None:
            attachment_service.release_question_attachment_reservation(
                prepared_attachment, actor
            )
        _raise_attachment(
            AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE),
            correlation_id,
        )

    now = datetime.now(timezone.utc).isoformat()
    usage_ledger_service.record_question_usage_event(
        student_id=student_id,
        question_id=question_id,
        quota_period=usage_counter["quotaPeriod"],
        idempotency_key=idempotency_key,
        counter_key=usage_counter["counterKey"],
        counter_value=usage_counter["counterValue"],
        quantity=1,
        entitlement=entitlement,
        created_at=now,
    )

    item = {
        "question_id": question_id,
        "student_id": student_id,
        "subject": subject,
        "content": content,
        "original_content": body.content,
        "corrected_text": body.corrected_text,
        "attachment_id": (
            prepared_attachment["attachment"]["attachment_id"]
            if prepared_attachment is not None
            else None
        ),
        "attachment_source_identity": _attachment_identity(body),
        "has_image": prepared_attachment is not None,
        "ocr_text": ocr_text,
        "ocr_metadata": ocr_metadata,
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
    if prepared_attachment is None:
        question_repo.put_question(item)
    else:
        try:
            summary = attachment_service.commit_question_with_attachment(
                question=question_repo.question_item(item),
                prepared=prepared_attachment,
                actor=actor,
                effective_plan=str(entitlement.get("effectivePlan") or subscription_tier),
            )
            item["attachment"] = summary
        except AttachmentDecisionError as error:
            attachment_service.release_question_attachment_reservation(
                prepared_attachment, actor
            )
            _raise_attachment(error, correlation_id)

    # Call AI synchronously (Lambda function has up to 30s; Haiku is fast)
    try:
        ai_resp = ai_service.get_ai_answer(
            content=content,
            subject=subject,
            grade=grade,
            language=language,
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
    except Exception:
        # AI call failed — leave as PENDING; client can poll
        pass

    return _question_response(item)


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
    notify_service.enqueue_teacher_request(
        question_id=question_id,
        student_id=student_id,
        subject=item["subject"],
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
