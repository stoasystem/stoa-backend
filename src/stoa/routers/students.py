"""Student routes — profile, learning summary, and question history."""
import base64
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from stoa.db.repositories import practice_repo, question_repo
from stoa.db.dynamodb import get_table
from stoa.security.authorization import AuthorizationAction, AuthorizedResource
from stoa.security.route_authorization import (
    STUDENT_CONTENT_READ,
    STUDENT_SELF,
    authorized_student_dependency,
)
from stoa.services import learning_profile_service

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
async def get_my_profile(
    authorized: AuthorizedResource = Depends(
        authorized_student_dependency(
            action=AuthorizationAction.READ, purposes=STUDENT_SELF, self_route=True
        )
    ),
):
    """Return the current student's learning profile."""
    user_id = authorized.ref.student_id
    profile = authorized.value
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
    authorized: AuthorizedResource = Depends(
        authorized_student_dependency(
            action=AuthorizationAction.UPDATE, purposes=STUDENT_SELF, self_route=True
        )
    ),
):
    """Update the current student's learning profile."""
    profile = authorized.value
    user_id = authorized.ref.student_id

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


class LearningSubjectDefinition(BaseModel):
    id: str
    label: str
    rolloutState: str


class LearningSubjectActivity(BaseModel):
    subject: str
    label: str
    rolloutState: str
    questionCount: int
    aiResolvedCount: int
    teacherEscalationCount: int
    feedbackAverage: float | None = None


class LearningWeakTopic(BaseModel):
    subject: str
    topicId: str
    label: str
    count: int
    latestEvidenceAt: str | None = None
    evidenceQuestionIds: list[str] = Field(default_factory=list)


class LearningProfileResponse(BaseModel):
    studentId: str
    subjects: list[LearningSubjectDefinition]
    subjectActivity: list[LearningSubjectActivity]
    weakTopics: list[LearningWeakTopic]
    strengthTopics: list[dict] = Field(default_factory=list)
    updatedAt: str


@router.get("/{student_id}/summary", response_model=SummaryResponse)
async def get_summary(
    authorized: AuthorizedResource = Depends(
        authorized_student_dependency(
            action=AuthorizationAction.READ, purposes=STUDENT_CONTENT_READ
        )
    ),
):
    """Return aggregated learning stats for a student (student, parent, admin)."""
    student_id = authorized.ref.student_id

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


@router.get("/{student_id}/learning-profile", response_model=LearningProfileResponse)
async def get_learning_profile(
    authorized: AuthorizedResource = Depends(
        authorized_student_dependency(
            action=AuthorizationAction.READ, purposes=STUDENT_CONTENT_READ
        )
    ),
):
    """Return subject-level activity and topic seeds for a student."""
    student_id = authorized.ref.student_id

    questions = question_repo.list_by_student(student_id, limit=500).get("Items", [])
    mistakes = practice_repo.get_mistakes(student_id)
    return learning_profile_service.build_learning_profile(
        student_id=student_id,
        questions=questions,
        mistakes=mistakes,
    )


@router.get("/{student_id}/questions", response_model=QuestionListResponse)
async def list_questions(
    authorized: AuthorizedResource = Depends(
        authorized_student_dependency(
            action=AuthorizationAction.READ, purposes=STUDENT_CONTENT_READ
        )
    ),
    limit: int = Query(default=20, ge=1, le=100),
    next_token: Optional[str] = Query(default=None),
):
    """Paginated question history for a student."""
    student_id = authorized.ref.student_id

    last_key = None
    if next_token:
        try:
            last_key = json.loads(base64.b64decode(next_token).decode())
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid next_token")

    result = question_repo.list_by_student(student_id, limit=limit, last_key=last_key)
    items = result.get("Items", [])

    new_token = None
    if "LastEvaluatedKey" in result:
        new_token = base64.b64encode(json.dumps(result["LastEvaluatedKey"]).encode()).decode()

    return QuestionListResponse(items=items, next_token=new_token)
