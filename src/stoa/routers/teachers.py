"""Teacher routes — work queue, takeover, reply, resolve."""
import uuid
from datetime import datetime
from typing import Optional

import boto3
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from stoa.config import Settings, get_settings
from stoa.db.repositories import question_repo
from stoa.db.dynamodb import get_table
from stoa.deps import require_role
from stoa.models.question import QuestionStatus

router = APIRouter()


class TakeoverResponse(BaseModel):
    question_id: str
    session_id: str
    status: str


class ReplyRequest(BaseModel):
    content: str


class ReplyResponse(BaseModel):
    question_id: str
    teacher_response: str
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

    teacher_id = user["sub"]
    session_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    question_repo.update_status(
        question_id,
        QuestionStatus.TEACHER_ACTIVE.value,
        teacher_id=teacher_id,
        session_id=session_id,
        teacher_started_at=now,
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

    question_repo.update_status(
        question_id,
        QuestionStatus.TEACHER_ACTIVE.value,
        teacher_response=body.content,
    )
    return ReplyResponse(
        question_id=question_id,
        teacher_response=body.content,
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

    now = datetime.utcnow().isoformat()
    question_repo.update_status(
        question_id,
        QuestionStatus.RESOLVED.value,
        resolved_at=now,
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
