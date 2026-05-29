"""Student routes — profile, learning summary, and question history."""
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from stoa.db.repositories import question_repo, user_repo
from stoa.db.dynamodb import get_table
from stoa.deps import get_current_user, require_role

router = APIRouter()


# ---------------------------------------------------------------------------
# Profile models
# ---------------------------------------------------------------------------

class StudentProfileResponse(BaseModel):
    id: str
    userId: str
    name: str
    grade: str
    primarySubjects: list[str]
    schoolSystem: str | None = None
    createdAt: str
    updatedAt: str


class UpdateStudentProfileRequest(BaseModel):
    grade: str | None = None
    primarySubjects: list[str] | None = None
    schoolSystem: str | None = None
    name: str | None = None


# ---------------------------------------------------------------------------
# Profile endpoints
# ---------------------------------------------------------------------------

@router.get("/me/profile", response_model=StudentProfileResponse)
async def get_my_profile(user: dict = Depends(require_role("student"))):
    """Return the current student's learning profile."""
    user_id = user["sub"]
    profile = user_repo.get_user(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    now = datetime.now(timezone.utc).isoformat()
    return StudentProfileResponse(
        id=profile.get("user_id", user_id),
        userId=profile.get("user_id", user_id),
        name=profile.get("name", ""),
        grade=profile.get("grade", ""),
        primarySubjects=profile.get("primary_subjects", profile.get("subjects", [])),
        schoolSystem=profile.get("school_system"),
        createdAt=profile.get("created_at", now),
        updatedAt=profile.get("updated_at", now),
    )


@router.patch("/me/profile", response_model=StudentProfileResponse)
async def update_my_profile(
    body: UpdateStudentProfileRequest,
    user: dict = Depends(require_role("student")),
):
    """Update the current student's learning profile."""
    user_id = user["sub"]
    profile = user_repo.get_user(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    now = datetime.now(timezone.utc).isoformat()
    update_expr_parts = ["updated_at = :u"]
    expr_values: dict = {":u": now}

    if body.grade is not None:
        update_expr_parts.append("grade = :g")
        expr_values[":g"] = body.grade

    if body.primarySubjects is not None:
        update_expr_parts.append("primary_subjects = :s")
        expr_values[":s"] = body.primarySubjects

    if body.schoolSystem is not None:
        update_expr_parts.append("school_system = :ss")
        expr_values[":ss"] = body.schoolSystem

    if body.name is not None:
        update_expr_parts.append("#n = :n")
        expr_values[":n"] = body.name

    table = get_table()
    kwargs: dict = {
        "Key": {"PK": f"USER#{user_id}", "SK": "PROFILE"},
        "UpdateExpression": "SET " + ", ".join(update_expr_parts),
        "ExpressionAttributeValues": expr_values,
        "ReturnValues": "ALL_NEW",
    }
    if body.name is not None:
        kwargs["ExpressionAttributeNames"] = {"#n": "name"}

    result = table.update_item(**kwargs)
    updated = result.get("Attributes", {})

    return StudentProfileResponse(
        id=updated.get("user_id", user_id),
        userId=updated.get("user_id", user_id),
        name=updated.get("name", profile.get("name", "")),
        grade=updated.get("grade", ""),
        primarySubjects=updated.get("primary_subjects", []),
        schoolSystem=updated.get("school_system"),
        createdAt=updated.get("created_at", now),
        updatedAt=now,
    )


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
