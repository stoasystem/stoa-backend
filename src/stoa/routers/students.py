"""Student routes — profile, learning summary, and question history."""
import base64
import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
import logging
from typing import NoReturn, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from stoa.db.repositories import practice_repo, question_repo, user_repo
from stoa.security.authorization import AuthorizationAction, AuthorizedResource
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.security.request_correlation import get_request_correlation_id
from stoa.security.route_authorization import (
    STUDENT_CONTENT_READ,
    STUDENT_SELF,
    authorized_student_dependency,
)
from stoa.services import learning_profile_service

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Profile models
# ---------------------------------------------------------------------------

class StudentProfileResponse(BaseModel):
    id: str
    userId: str
    name: str
    email: str
    grade: str
    primarySubjects: list[str]
    schoolSystem: str | None = None
    preferredAnswerLanguage: str | None = None
    guardianStatus: str
    createdAt: str
    updatedAt: str


class UpdateStudentProfileRequest(BaseModel):
    grade: str | None = None
    primarySubjects: list[str] | None = None
    schoolSystem: str | None = None
    name: str | None = None


def _invalid_stored_student_response(correlation_id: str, field: str) -> NoReturn:
    logger.warning("student_response_rejected category=invalid_%s", field)
    error = SecurityDecisionError(
        SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE,
        correlation_id=correlation_id,
        internal_detail=f"student_profile:{field}",
    )
    raise HTTPException(status_code=error.status_code, detail=error.public_body()) from error


def _required_profile_text(
    profile: Mapping[str, object], field: str, correlation_id: str
) -> str:
    value = profile.get(field)
    if not isinstance(value, str):
        _invalid_stored_student_response(correlation_id, field)
    return value


def _profile_subjects(profile: Mapping[str, object], correlation_id: str) -> list[str]:
    value = profile.get("primary_subjects", profile.get("subjects"))
    if not isinstance(value, list) or not all(isinstance(subject, str) for subject in value):
        _invalid_stored_student_response(correlation_id, "primary_subjects")
    return value


def _optional_profile_text(
    profile: Mapping[str, object], field: str, correlation_id: str
) -> str | None:
    value = profile.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        _invalid_stored_student_response(correlation_id, field)
    return value


def _guardian_status(profile: Mapping[str, object]) -> str:
    """Report whether a guardian account is linked, not the guardian's details."""
    if profile.get("parent_binding_status") == "active" and profile.get("parent_id"):
        return "linked"
    return "not_linked"


def _student_profile_response(
    profile: Mapping[str, object], *, fallback_user_id: str, correlation_id: str, updated_at: str | None = None
) -> StudentProfileResponse:
    user_id = profile.get("user_id", fallback_user_id)
    if not isinstance(user_id, str):
        _invalid_stored_student_response(correlation_id, "user_id")
    return StudentProfileResponse(
        id=user_id,
        userId=user_id,
        name=_required_profile_text(profile, "name", correlation_id),
        email=_optional_profile_text(profile, "email", correlation_id) or "",
        grade=_required_profile_text(profile, "grade", correlation_id),
        primarySubjects=_profile_subjects(profile, correlation_id),
        schoolSystem=_optional_profile_text(profile, "school_system", correlation_id),
        preferredAnswerLanguage=_optional_profile_text(
            profile, "preferred_locale", correlation_id
        ),
        guardianStatus=_guardian_status(profile),
        createdAt=_required_profile_text(profile, "created_at", correlation_id),
        updatedAt=updated_at or _required_profile_text(profile, "updated_at", correlation_id),
    )


def _question_rows(value: object, correlation_id: str) -> list[dict[str, object]]:
    if not isinstance(value, list):
        _invalid_stored_student_response(correlation_id, "question_items")
    rows: list[dict[str, object]] = []
    for value_row in value:
        if not isinstance(value_row, Mapping) or not all(isinstance(key, str) for key in value_row):
            _invalid_stored_student_response(correlation_id, "question_item")
        rows.append(dict(value_row))
    return rows


def _knowledge_points(row: Mapping[str, object], correlation_id: str) -> list[str]:
    value = row.get("knowledge_points", [])
    if not isinstance(value, list) or not all(isinstance(point, str) for point in value):
        _invalid_stored_student_response(correlation_id, "knowledge_points")
    return value


class LearningHistoryItem(BaseModel):
    id: str
    subject: str
    title: str
    summary: str
    createdAt: str
    sourceLabel: str


class LearningHistoryResponse(BaseModel):
    items: list[LearningHistoryItem] = Field(default_factory=list)


def _history_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _is_question_record(row: Mapping[str, object]) -> bool:
    """The student index carries every record with a student_id, not just questions."""
    return row.get("SK") == "META" and str(row.get("PK", "")).startswith("QUESTION#")


def _question_history_items(student_id: str) -> list[LearningHistoryItem]:
    """Build history from the student's conversations.

    The student index is shared by every record carrying a student_id, so rows
    are selected by entity type rather than taken wholesale.
    """
    result = question_repo.list_by_student(student_id, limit=200)
    items = []
    for row in result.get("Items", []):
        if not isinstance(row, Mapping):
            continue
        created_at = _history_text(row.get("created_at"))
        if not created_at:
            continue
        if row.get("entity_type") == "conversation":
            escalated = bool(row.get("escalated"))
            items.append(
                LearningHistoryItem(
                    id=_history_text(row.get("conversation_id")) or f"conversation-{created_at}",
                    subject=_history_text(row.get("subject")) or "General",
                    title="Teacher help requested" if escalated else "Question asked",
                    summary=(
                        _history_text(row.get("escalation_message"))
                        or _history_text(row.get("title"))
                    ),
                    createdAt=created_at,
                    sourceLabel="Questions",
                )
            )
        elif _is_question_record(row):
            status = _history_text(row.get("status"))
            items.append(
                LearningHistoryItem(
                    id=_history_text(row.get("question_id")) or f"question-{created_at}",
                    subject=_history_text(row.get("subject")) or "General",
                    title=(
                        "Question answered" if status == "ai_answered" else "Question asked"
                    ),
                    summary=(
                        _history_text(row.get("summary")) or _history_text(row.get("prompt"))
                    ),
                    createdAt=created_at,
                    sourceLabel="Questions",
                )
            )
    return items


def _practice_history_items(student_id: str) -> list[LearningHistoryItem]:
    items = []
    for row in practice_repo.get_progress(student_id):
        if not isinstance(row, Mapping):
            continue
        created_at = (
            _history_text(row.get("completed_at"))
            or _history_text(row.get("updated_at"))
            or _history_text(row.get("created_at"))
        )
        if not created_at:
            continue
        items.append(
            LearningHistoryItem(
                id=_history_text(row.get("lesson_id")) or f"practice-{created_at}",
                subject=_history_text(row.get("subject_id")) or "Practice",
                title="Practice Path lesson",
                summary=(
                    _history_text(row.get("lesson_title")) or _history_text(row.get("topic_id"))
                ),
                createdAt=created_at,
                sourceLabel="Practice Path",
            )
        )
    return items


# ---------------------------------------------------------------------------
# Profile endpoints
# ---------------------------------------------------------------------------

@router.get("/me/learning-history", response_model=LearningHistoryResponse)
async def get_my_learning_history(
    authorized: AuthorizedResource = Depends(
        authorized_student_dependency(
            action=AuthorizationAction.READ, purposes=STUDENT_SELF, self_route=True
        )
    ),
):
    """Return the student's own questions and practice lessons, newest first."""
    student_id = authorized.ref.student_id
    items = _question_history_items(student_id) + _practice_history_items(student_id)
    items.sort(key=lambda item: item.createdAt, reverse=True)
    return LearningHistoryResponse(items=items)


@router.get("/me/profile", response_model=StudentProfileResponse)
async def get_my_profile(
    authorized: AuthorizedResource = Depends(
        authorized_student_dependency(
            action=AuthorizationAction.READ, purposes=STUDENT_SELF, self_route=True
        )
    ),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Return the current student's learning profile."""
    user_id = authorized.ref.student_id
    profile = authorized.value
    return _student_profile_response(
        profile,
        fallback_user_id=user_id,
        correlation_id=correlation_id,
    )


@router.patch("/me/profile", response_model=StudentProfileResponse)
async def update_my_profile(
    body: UpdateStudentProfileRequest,
    authorized: AuthorizedResource = Depends(
        authorized_student_dependency(
            action=AuthorizationAction.UPDATE, purposes=STUDENT_SELF, self_route=True
        )
    ),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Update the current student's learning profile."""
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

    updated = user_repo.update_profile_fields(
        user_id,
        update_expression="SET " + ", ".join(update_expr_parts),
        expression_attribute_values=expr_values,
        expression_attribute_names={"#n": "name"} if body.name is not None else None,
    )

    return _student_profile_response(
        updated,
        fallback_user_id=user_id,
        correlation_id=correlation_id,
        updated_at=now,
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
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Return aggregated learning stats for a student (student, parent, admin)."""
    student_id = authorized.ref.student_id

    result = question_repo.list_by_student(student_id, limit=500)
    questions = [
        row
        for row in _question_rows(result.get("Items", []), correlation_id)
        if _is_question_record(row)
    ]

    ai_resolved = sum(1 for q in questions if q.get("status") == "ai_answered")
    teacher_resolved = sum(1 for q in questions if q.get("status") == "resolved")

    kp_counter: Counter = Counter()
    for q in questions:
        for kp in _knowledge_points(q, correlation_id):
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
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Return subject-level activity and topic seeds for a student."""
    student_id = authorized.ref.student_id

    questions = _question_rows(
        question_repo.list_by_student(student_id, limit=500).get("Items", []),
        correlation_id,
    )
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
    correlation_id: str = Depends(get_request_correlation_id),
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
    items = _question_rows(result.get("Items", []), correlation_id)

    new_token = None
    if "LastEvaluatedKey" in result:
        new_token = base64.b64encode(json.dumps(result["LastEvaluatedKey"]).encode()).decode()

    return QuestionListResponse(items=items, next_token=new_token)
