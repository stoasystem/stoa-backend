"""Question routes — submit, retrieve, teacher escalation, feedback."""
import uuid
from datetime import datetime

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
from stoa.services import ai_service, notify_service, ocr_service

router = APIRouter()


def _check_daily_limit(student_id: str, subscription_tier: str, settings: Settings) -> None:
    """Raise 429 if the student has exceeded their daily question quota."""
    limits = {
        "free": settings.free_tier_daily_question_limit,
        "standard": settings.standard_tier_daily_question_limit,
        "premium": settings.premium_tier_daily_question_limit,
    }
    today = datetime.utcnow().strftime("%Y-%m-%d")
    result = question_repo.list_by_student(student_id, limit=200)
    questions_today = [
        q for q in result.get("Items", [])
        if q.get("created_at", "").startswith(today)
    ]
    limit = limits.get(subscription_tier, settings.free_tier_daily_question_limit)
    if len(questions_today) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily question limit ({limit}) reached for your plan",
        )


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
    language = student_profile.get("language", "de")
    grade = student_profile.get("grade", "Sek1")

    _check_daily_limit(student_id, subscription_tier, settings)

    content = body.content

    # OCR: extract text from uploaded image if provided
    if body.image_s3_key:
        try:
            extracted = ocr_service.extract_text_from_s3(settings.s3_images_bucket, body.image_s3_key)
            if extracted.strip():
                content = f"{content}\n\n[Image text: {extracted}]" if content else extracted
        except Exception:
            pass  # OCR failure is non-fatal; proceed with text content

    question_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    item = {
        "question_id": question_id,
        "student_id": student_id,
        "subject": body.subject,
        "content": content,
        "image_s3_key": body.image_s3_key,
        "status": QuestionStatus.PENDING.value,
        "ai_response": None,
        "teacher_id": None,
        "teacher_response": None,
        "knowledge_points": [],
        "student_feedback": None,
        "created_at": now,
        "resolved_at": None,
    }
    question_repo.put_question(item)

    # Call AI synchronously (Lambda function has up to 30s; Haiku is fast)
    try:
        ai_resp = ai_service.get_ai_answer(
            content=content,
            subject=body.subject,
            grade=grade,
            language=language,
        )
        question_repo.update_status(
            question_id,
            QuestionStatus.AI_ANSWERED.value,
            ai_response=ai_resp,
            knowledge_points=ai_resp.get("knowledge_points", []),
        )
        item["status"] = QuestionStatus.AI_ANSWERED.value
        item["ai_response"] = ai_resp
    except Exception as exc:
        # AI call failed — leave as PENDING; client can poll
        pass

    return QuestionResponse(**item)


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

    return QuestionResponse(**item)


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

    question_repo.update_status(question_id, QuestionStatus.ESCALATED.value)
    notify_service.enqueue_teacher_request(
        question_id=question_id,
        student_id=user["sub"],
        subject=item["subject"],
    )
    return {"question_id": question_id, "status": QuestionStatus.ESCALATED.value}


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
