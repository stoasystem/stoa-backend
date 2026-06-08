"""Teacher routes — work queue, takeover, reply, resolve."""
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from stoa.db.repositories import question_repo
from stoa.db.dynamodb import get_table
from stoa.deps import require_role
from stoa.models.question import QuestionStatus
from stoa.services import notification_service, teacher_reply_service

router = APIRouter()


class TakeoverResponse(BaseModel):
    question_id: str
    session_id: str
    status: str


class ReplyRequest(BaseModel):
    content: str | None = Field(default=None, max_length=4000)
    rich_content: dict[str, Any] | None = None


class ReplyResponse(BaseModel):
    question_id: str
    teacher_response: str
    teacher_response_text: str
    teacher_response_rich: dict[str, Any]
    teacher_response_format: str
    teacher_first_replied_at: str | None = None
    teacher_first_reply_sla_bucket: str | None = None
    status: str


def _list_escalated_questions(limit: int = 50) -> list[dict]:
    """Scan for ESCALATED questions (small scale; replace with GSI for production)."""
    table = get_table()
    result = table.scan(
        FilterExpression="#s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": QuestionStatus.ESCALATED.value},
        Limit=limit,
    )
    return result.get("Items", [])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/queue")
async def get_queue(
    user: dict = Depends(require_role("teacher", "admin")),
):
    """Return the list of questions awaiting teacher intervention."""
    questions = _list_escalated_questions()
    return {"items": questions, "count": len(questions)}


@router.post("/questions/{question_id}/takeover", response_model=TakeoverResponse)
async def takeover(
    question_id: str,
    user: dict = Depends(require_role("teacher")),
):
    """Lock a question to this teacher and start a session."""
    item = question_repo.get_question(question_id)
    if not item:
        raise HTTPException(status_code=404, detail="Question not found")
    if item.get("status") == QuestionStatus.TEACHER_ACTIVE.value:
        raise HTTPException(status_code=409, detail="Question is already taken by a teacher")
    if item.get("status") != QuestionStatus.ESCALATED.value:
        raise HTTPException(status_code=409, detail="Question is not awaiting teacher takeover")

    teacher_id = user["sub"]
    session_id = str(uuid.uuid4())
    now = _now()
    sla_fields = teacher_reply_service.compute_takeover_sla_fields(item, now)

    question_repo.update_status(
        question_id,
        QuestionStatus.TEACHER_ACTIVE.value,
        teacher_id=teacher_id,
        session_id=session_id,
        teacher_started_at=now,
        teacher_taken_over_at=now,
        **sla_fields,
    )

    # Persist a TeacherSession record in DynamoDB
    table = get_table()
    table.put_item(Item={
        "PK": f"SESSION#{session_id}",
        "SK": "META",
        "session_id": session_id,
        "question_id": question_id,
        "teacher_id": teacher_id,
        "student_id": item["student_id"],
        "started_at": now,
        "resolved_at": None,
    })
    notification_service.emit_teacher_takeover(question=item, teacher_id=teacher_id)

    return TakeoverResponse(
        question_id=question_id,
        session_id=session_id,
        status=QuestionStatus.TEACHER_ACTIVE.value,
    )


@router.post("/questions/{question_id}/reply", response_model=ReplyResponse)
async def reply(
    question_id: str,
    body: ReplyRequest,
    user: dict = Depends(require_role("teacher")),
):
    """Post the teacher's reply to a question they have taken over."""
    item = question_repo.get_question(question_id)
    if not item:
        raise HTTPException(status_code=404, detail="Question not found")
    if item.get("teacher_id") != user["sub"]:
        raise HTTPException(status_code=403, detail="You have not taken over this question")
    if item.get("status") == QuestionStatus.RESOLVED.value:
        raise HTTPException(status_code=409, detail="Question is already resolved")
    if item.get("status") != QuestionStatus.TEACHER_ACTIVE.value:
        raise HTTPException(status_code=409, detail="Question is not active with a teacher")

    try:
        reply_fields = teacher_reply_service.normalize_teacher_reply(
            body.content,
            body.rich_content,
        )
    except teacher_reply_service.TeacherReplyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    now = _now()
    if not item.get("teacher_first_replied_at"):
        reply_fields["teacher_first_replied_at"] = now
        reply_fields.update(teacher_reply_service.compute_sla_fields(item, now))

    question_repo.update_status(
        question_id,
        QuestionStatus.TEACHER_ACTIVE.value,
        **reply_fields,
    )
    notification_service.emit_teacher_reply(question=item, teacher_id=user["sub"])
    return ReplyResponse(
        question_id=question_id,
        teacher_response=reply_fields["teacher_response"],
        teacher_response_text=reply_fields["teacher_response_text"],
        teacher_response_rich=reply_fields["teacher_response_rich"],
        teacher_response_format=reply_fields["teacher_response_format"],
        teacher_first_replied_at=reply_fields.get("teacher_first_replied_at")
        or item.get("teacher_first_replied_at"),
        teacher_first_reply_sla_bucket=reply_fields.get("teacher_first_reply_sla_bucket")
        or item.get("teacher_first_reply_sla_bucket"),
        status=QuestionStatus.TEACHER_ACTIVE.value,
    )


@router.put("/questions/{question_id}/resolve", status_code=status.HTTP_200_OK)
async def resolve(
    question_id: str,
    user: dict = Depends(require_role("teacher")),
):
    """Mark a question as resolved and close the teacher session."""
    item = question_repo.get_question(question_id)
    if not item:
        raise HTTPException(status_code=404, detail="Question not found")
    if item.get("teacher_id") != user["sub"]:
        raise HTTPException(status_code=403, detail="You have not taken over this question")
    if item.get("status") == QuestionStatus.RESOLVED.value:
        raise HTTPException(status_code=409, detail="Question is already resolved")

    now = _now()
    question_repo.update_status(
        question_id,
        QuestionStatus.RESOLVED.value,
        resolved_at=now,
        **teacher_reply_service.compute_resolved_sla_fields(item, now),
    )

    # Update session record
    session_id = item.get("session_id")
    if session_id:
        table = get_table()
        table.update_item(
            Key={"PK": f"SESSION#{session_id}", "SK": "META"},
            UpdateExpression="SET resolved_at = :r",
            ExpressionAttributeValues={":r": now},
        )

    return {"question_id": question_id, "status": QuestionStatus.RESOLVED.value, "resolved_at": now}
