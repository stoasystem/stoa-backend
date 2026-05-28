"""Student routes — learning summary and question history."""
from collections import Counter
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from stoa.db.repositories import question_repo, user_repo
from stoa.deps import get_current_user, require_role

router = APIRouter()


class SummaryResponse(BaseModel):
    student_id: str
    total_questions: int
    ai_resolved: int
    teacher_resolved: int
    weak_knowledge_points: list[str]


class QuestionListResponse(BaseModel):
    items: list[dict]
    next_token: Optional[str] = None


@router.get("/{student_id}/summary", response_model=SummaryResponse)
async def get_summary(
    student_id: str,
    user: dict = Depends(get_current_user),
):
    """Return aggregated learning stats for a student (student, parent, admin)."""
    role = user.get("role", "")
    uid = user["sub"]

    # Students can only see their own summary; parents and admins can see any
    if role == "student" and uid != student_id:
        raise HTTPException(status_code=403, detail="Cannot view another student's summary")
    if role not in ("student", "parent", "admin"):
        raise HTTPException(status_code=403, detail="Role not permitted")

    result = question_repo.list_by_student(student_id, limit=500)
    questions = result.get("Items", [])

    ai_resolved = sum(1 for q in questions if q.get("status") == "ai_answered")
    teacher_resolved = sum(1 for q in questions if q.get("status") == "resolved")

    kp_counter: Counter = Counter()
    for q in questions:
        for kp in q.get("knowledge_points", []):
            kp_counter[kp] += 1
    weak_kps = [kp for kp, _ in kp_counter.most_common(10)]

    return SummaryResponse(
        student_id=student_id,
        total_questions=len(questions),
        ai_resolved=ai_resolved,
        teacher_resolved=teacher_resolved,
        weak_knowledge_points=weak_kps,
    )


@router.get("/{student_id}/questions", response_model=QuestionListResponse)
async def list_questions(
    student_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    next_token: Optional[str] = Query(default=None),
    user: dict = Depends(get_current_user),
):
    """Paginated question history for a student."""
    role = user.get("role", "")
    uid = user["sub"]

    if role == "student" and uid != student_id:
        raise HTTPException(status_code=403, detail="Cannot view another student's questions")
    if role not in ("student", "parent", "teacher", "admin"):
        raise HTTPException(status_code=403, detail="Role not permitted")

    last_key = None
    if next_token:
        import json, base64
        try:
            last_key = json.loads(base64.b64decode(next_token).decode())
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid next_token")

    result = question_repo.list_by_student(student_id, limit=limit, last_key=last_key)
    items = result.get("Items", [])

    new_token = None
    if "LastEvaluatedKey" in result:
        import json, base64
        new_token = base64.b64encode(json.dumps(result["LastEvaluatedKey"]).encode()).decode()

    return QuestionListResponse(items=items, next_token=new_token)
