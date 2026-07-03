"""Question routes — submit, retrieve, teacher escalation, feedback."""
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from stoa.config import Settings, get_settings
from stoa.db.repositories import question_repo, user_repo
from stoa.deps import get_current_user, require_role
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
    public_item["image_s3_key"] = None
    public_item["has_image"] = bool(item.get("image_s3_key") or item.get("has_image"))
    public_item["ocr_metadata"] = item.get("ocr_metadata") or {
        "status": "not_requested",
        "source": None,
        "text_length": 0,
        "correction_applied": False,
        "failure_class": None,
    }
    return QuestionResponse(**public_item)


def _build_question_content(body: SubmitQuestionRequest, settings: Settings) -> tuple[str, dict[str, Any], str | None]:
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

    if not body.image_s3_key:
        return content, metadata, ocr_text

    metadata["source"] = "rekognition_s3"
    try:
        extracted = ocr_service.extract_text_from_s3(settings.s3_images_bucket, body.image_s3_key)
        ocr_text = extracted.strip()
        metadata["text_length"] = len(ocr_text)
        metadata["status"] = "succeeded" if ocr_text else "no_text"
        if ocr_text and corrected is None:
            content = f"{body.content}\n\n[Image text: {ocr_text}]" if body.content else ocr_text
    except Exception as exc:
        metadata["status"] = "failed"
        metadata["failure_class"] = type(exc).__name__
    return content, metadata, ocr_text


@router.post("", response_model=QuestionResponse, status_code=status.HTTP_201_CREATED)
async def submit_question(
    body: SubmitQuestionRequest,
    user: dict = Depends(require_role("student")),
    settings: Settings = Depends(get_settings),
):
    """Submit a question; run OCR if an image is provided, then call AI."""
    student_id = user["sub"]
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
                return _question_response(existing_question)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Question submission is already recorded; retry later",
            )

    usage_counter = _check_daily_limit(student_id, subscription_tier, settings, entitlement=entitlement)

    content, ocr_metadata, ocr_text = _build_question_content(body, settings)

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
        "image_s3_key": body.image_s3_key,
        "has_image": bool(body.image_s3_key),
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
    question_repo.put_question(item)

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
    question_id: str,
    user: dict = Depends(get_current_user),
):
    """Retrieve a question and its AI/teacher response."""
    item = question_repo.get_question(question_id)
    if not item:
        raise HTTPException(status_code=404, detail="Question not found")

    # Students may only view their own questions
    if user.get("role") == "student" and item.get("student_id") != user["sub"]:
        raise HTTPException(status_code=403, detail="Not your question")

    return _question_response(item)


@router.post("/{question_id}/request-teacher", status_code=status.HTTP_202_ACCEPTED)
async def request_teacher(
    question_id: str,
    user: dict = Depends(require_role("student")),
    settings: Settings = Depends(get_settings),
):
    """Escalate a question to a human teacher via SQS FIFO queue."""
    item = question_repo.get_question(question_id)
    if not item:
        raise HTTPException(status_code=404, detail="Question not found")
    if item.get("student_id") != user["sub"]:
        raise HTTPException(status_code=403, detail="Not your question")
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
        student_id=user["sub"],
        subject=item["subject"],
    )
    notification_service.emit_teacher_requested(
        question_id=question_id,
        student_id=user["sub"],
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
    return {"question_id": question_id, "status": QuestionStatus.ESCALATED.value, "dispatch": dispatch}


@router.post("/{question_id}/feedback", status_code=status.HTTP_200_OK)
async def submit_feedback(
    question_id: str,
    body: FeedbackRequest,
    user: dict = Depends(require_role("student")),
):
    """Rate a resolved question (1–5 stars)."""
    item = question_repo.get_question(question_id)
    if not item:
        raise HTTPException(status_code=404, detail="Question not found")
    if item.get("student_id") != user["sub"]:
        raise HTTPException(status_code=403, detail="Not your question")

    question_repo.update_status(question_id, item["status"], student_feedback=body.rating)
    return {"question_id": question_id, "rating": body.rating}


@router.post(
    "/{question_id}/reports",
    response_model=ModerationCaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def report_question_content(
    question_id: str,
    body: ModerationReportRequest,
    user: dict = Depends(get_current_user),
):
    """Create a moderation case for reportable question content."""
    return moderation_service.create_case(question_id, body, user)
