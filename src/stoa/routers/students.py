"""Student routes — profile, learning summary, and question history."""
from collections import Counter
from collections.abc import Mapping
from decimal import Decimal
from datetime import datetime, timezone
import logging
from typing import Literal, NoReturn, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from stoa.db import table as db_table
from stoa.db.repositories import (
    asked_knowledge_repo,
    parent_link_repo,
    practice_repo,
    question_repo,
    user_repo,
)
from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizedResource,
    ResourceType,
)
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.security.request_correlation import get_request_correlation_id
from stoa.security.declared_authorization import SELF, authorized, path
from stoa.security.declared_authorization import STUDENT_CONTENT_READ, STUDENT_SELF
from stoa import config
from stoa.services.account_errors import AccountErrorCode, AccountViolation
from stoa.services import (
    allowance_service,
    current_relationship,
    curriculum_service,
    entitlement_service,
    help_requests,
    learning_profile_service,
    locale_service,
    message_catalog,
    parent_link_service,
    student_evidence,
)
from stoa.routers import conversations as conversation_routes
from stoa.routers.parents import (
    admit_parent_link_request,
    parent_link_request_conflict,
)
from stoa.security.identity import Actor
from stoa.services.curriculum_translations import translated_title

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Profile models
# ---------------------------------------------------------------------------

class ProfileChoice(BaseModel):
    """One value a list-chosen profile field may take, named for the reader."""

    code: str
    label: str


class ProfileChoices(BaseModel):
    """What each list-chosen profile field may be set to, in the order offered.

    The client renders these instead of keeping its own copy
    (`learning_profile_service.PROFILE_CHOICES`); the write accepts a `code`
    from the field's list, or "" (the grade: not said; the answer style:
    `standard`).
    """

    grade: list[ProfileChoice]
    # Declared as `answer_style` (`PROFILE_CHOICES`), sent as `answerStyle`
    # like the profile field it is the list for.
    answerStyle: list[ProfileChoice] = Field(validation_alias="answer_style")


class StudentProfileResponse(BaseModel):
    id: str
    userId: str
    name: str
    email: str
    # The code the stored year group means, "" when none was said. A row
    # holding text no code can be read from is sent back as stored: it is in
    # no list, so a client treats it as not said and asks again.
    grade: str
    primarySubjects: list[str]
    schoolSystem: str | None = None
    preferredAnswerLanguage: str | None = None
    # How the assistant answers this student (#314): a code from
    # `choices.answerStyle`, `standard` when none was chosen. The student's own
    # profile only: no parent, teacher or admin view carries or sets it.
    answerStyle: str
    guardianStatus: str
    createdAt: str
    updatedAt: str
    choices: ProfileChoices


class UpdateStudentProfileRequest(BaseModel):
    grade: str | None = None
    primarySubjects: list[str] | None = None
    schoolSystem: str | None = None
    name: str | None = None
    # A code from `choices.answerStyle`, or "" for `standard`.
    answerStyle: str | None = None


def _invalid_stored_student_response(correlation_id: str, field: str) -> NoReturn:
    logger.warning("student_response_rejected category=invalid_%s", field)
    raise SecurityDecisionError(
        SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE,
        correlation_id=correlation_id,
        internal_detail=f"student_profile:{field}",
    )


def _required_profile_text(
    profile: Mapping[str, object], field: str, correlation_id: str
) -> str:
    value = profile.get(field)
    if not isinstance(value, str):
        _invalid_stored_student_response(correlation_id, field)
    return value


def _unset_or_text(profile: Mapping[str, object], field: str, correlation_id: str) -> str:
    """A field the student has not filled in yet, told apart from a damaged one.

    `grade` is asked for on the learning profile, not when the account is opened,
    so every account an administrator opens has none - and treating that as a
    damaged row answered the student's own profile with a 503. The distinction is
    the same one `minorKnown` draws: nobody said, which is not the same as
    somebody stored nonsense. A value of the wrong type is still refused, because
    that is the case this guard was put here for.
    """
    if field not in profile or profile[field] is None:
        return ""
    return _required_profile_text(profile, field, correlation_id)


def _profile_subjects(profile: Mapping[str, object], correlation_id: str) -> list[str]:
    if "primary_subjects" not in profile and "subjects" not in profile:
        return []
    value = profile.get("primary_subjects", profile.get("subjects"))
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(subject, str) for subject in value):
        _invalid_stored_student_response(correlation_id, "primary_subjects")
    # Read through the subject entry point (#354): `mathematics` written before
    # writes were checked reads as `math`; a value it does not know, as stored.
    return list(dict.fromkeys(curriculum_service.readable_subject(subject) for subject in value))


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
    """Report whether a guardian is currently linked, not the guardian's details."""
    student_id = profile.get("user_id")
    if isinstance(student_id, str) and current_relationship.parents_of(student_id):
        return "linked"
    return "not_linked"


def _profile_grade(profile: Mapping[str, object], correlation_id: str) -> str:
    """The stored year group as the code it means; text nothing reads from, as stored."""
    stored = _unset_or_text(profile, "grade", correlation_id)
    code = learning_profile_service.resolve_grade_code(stored)
    return stored if code is None else code


def _student_profile_response(
    profile: Mapping[str, object], *, fallback_user_id: str, correlation_id: str, updated_at: str | None = None
) -> StudentProfileResponse:
    user_id = profile.get("user_id", fallback_user_id)
    if not isinstance(user_id, str):
        _invalid_stored_student_response(correlation_id, "user_id")
    locale = locale_service.resolve_locale(dict(profile))
    return StudentProfileResponse(
        id=user_id,
        userId=user_id,
        name=_required_profile_text(profile, "name", correlation_id),
        email=_optional_profile_text(profile, "email", correlation_id) or "",
        grade=_profile_grade(profile, correlation_id),
        primarySubjects=_profile_subjects(profile, correlation_id),
        schoolSystem=_optional_profile_text(profile, "school_system", correlation_id),
        preferredAnswerLanguage=_optional_profile_text(
            profile, "preferred_locale", correlation_id
        ),
        answerStyle=learning_profile_service.answer_style_code(profile.get("answer_style")),
        guardianStatus=_guardian_status(profile),
        createdAt=_required_profile_text(profile, "created_at", correlation_id),
        updatedAt=updated_at or _required_profile_text(profile, "updated_at", correlation_id),
        choices=ProfileChoices.model_validate(learning_profile_service.profile_choices(locale)),
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
    # The labels above are English fallbacks. The client renders these two in
    # the reader's language, so a translated screen never shows an English row.
    kind: str
    source: str


class LearningHistoryResponse(BaseModel):
    items: list[LearningHistoryItem] = Field(default_factory=list)


def _plan_includes_teacher_support(plan: str) -> bool:
    """Whether this plan carries any teacher-support cases at all."""
    try:
        budget = allowance_service.plan_allowance_budget(plan, allowance_version=1)
    except ValueError:
        return False
    return budget.teacher_support_cases > 0


class StudentUsagePeriod(BaseModel):
    """The student's effective usage period (#239).

    `endsAt` is the last day it may be used, a Zurich date (`YYYY-MM-DD`); the
    period ends at 23:59:59 that day. `daysLeft` counts the Zurich days after
    today: 0 on the end day and once expired, `null` without a period.
    `paidBy` says whether the student's own period or a parent's covers them,
    `null` without one; which parent is never said.
    """

    endsAt: str | None
    state: Literal["active", "expired", "none"]
    daysLeft: int | None
    paidBy: Literal["self", "parent"] | None


class StudentEntitlementResponse(BaseModel):
    effectivePlan: str
    newUsageAllowed: bool
    teacherSupportIncluded: bool = False
    dailyAiQuestionLimit: int | None = None
    dailyChatMessageLimit: int | None = None
    usagePeriod: StudentUsagePeriod
    renewalContactEmail: str


def _stored_limit(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    return None


def _history_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _question_history_items(student_id: str) -> list[LearningHistoryItem]:
    """Build history from the student's conversations.

    The student index is shared by every record carrying a student_id, so rows
    are selected by entity type rather than taken wholesale.
    """
    result = question_repo.list_by_student(student_id, limit=200)
    items = []
    # The same policy its sibling `_practice_history_items` already uses: the
    # language the client is rendering in right now. These entries are labels
    # this backend writes, not content, so they follow the reader (#124).
    locale = locale_service.resolve_locale(None)
    # Whether a teacher was asked is the request's, not the conversation's (#189).
    raw_rows = result.get("Items", [])
    rows = help_requests.with_requests(
        [row for row in (raw_rows if isinstance(raw_rows, list) else []) if isinstance(row, Mapping)],
        student_id,
        table=db_table.table(),
    )
    for row in rows:
        created_at = _history_text(row.get("created_at"))
        if not created_at:
            continue
        if row.get("entity_type") == "conversation":
            escalated = bool(row.get("escalated"))
            items.append(
                LearningHistoryItem(
                    id=_history_text(row.get("conversation_id")) or f"conversation-{created_at}",
                    subject=_history_text(row.get("subject"))
                    or message_catalog.text("activity.subject.unknown", locale),
                    title=message_catalog.text(
                        "activity.teacher_help_requested"
                        if escalated
                        else "activity.question_asked",
                        locale,
                    ),
                    summary=(
                        _history_text(row.get("escalation_message"))
                        or _history_text(row.get("title"))
                    ),
                    createdAt=created_at,
                    sourceLabel=message_catalog.text("activity.source.questions", locale),
                    kind="teacher_help" if escalated else "question_asked",
                    source="questions",
                )
            )
        elif question_repo.is_question_record(row):
            status = _history_text(row.get("status"))
            answered = status == "ai_answered"
            items.append(
                LearningHistoryItem(
                    id=_history_text(row.get("question_id")) or f"question-{created_at}",
                    subject=_history_text(row.get("subject"))
                    or message_catalog.text("activity.subject.unknown", locale),
                    title=message_catalog.text(
                        "activity.question_answered"
                        if answered
                        else "activity.question_asked",
                        locale,
                    ),
                    summary=(
                        _history_text(row.get("summary")) or _history_text(row.get("prompt"))
                    ),
                    createdAt=created_at,
                    sourceLabel=message_catalog.text("activity.source.questions", locale),
                    kind="question_answered" if answered else "question_asked",
                    source="questions",
                )
            )
    return items


def _lesson_titles() -> dict[str, str]:
    """Progress rows record which lesson, not what it was called."""
    try:
        lessons = practice_repo.get_lessons()
    except Exception:
        return {}
    return {
        _history_text(lesson.get("lesson_id")): _history_text(lesson.get("title"))
        for lesson in lessons
        if isinstance(lesson, Mapping)
    }


def _practice_history_items(student_id: str) -> list[LearningHistoryItem]:
    """The lessons this student finished, from their evidence (#214)."""
    items = []
    titles = _lesson_titles()
    locale = locale_service.resolve_locale(None)
    for lesson in student_evidence.for_student(student_id).completions:
        if not lesson.completed_at:
            continue
        stored_title = lesson.title or titles.get(lesson.lesson_id, "") or lesson.topic_id
        items.append(
            LearningHistoryItem(
                id=lesson.lesson_id,
                subject=(
                    translated_title(lesson.subject_id, lesson.subject_id, locale)
                    if lesson.subject_id
                    else "Practice"
                ),
                title=message_catalog.text("activity.practice_path_lesson", locale),
                # The lesson name is curriculum content, so it gets the same
                # title translation the roadmap and the lesson header use.
                summary=translated_title(lesson.lesson_id, stored_title, locale),
                createdAt=lesson.completed_at,
                sourceLabel=message_catalog.text("activity.source.practice_path", locale),
                kind="practice_lesson",
                source="practice_path",
            )
        )
    return items


# ---------------------------------------------------------------------------
# Authorization declarations (#348)
# ---------------------------------------------------------------------------

_own_account_read = authorized(
    ResourceType.STUDENT, AuthorizationAction.READ, SELF, STUDENT_SELF
)
_own_account_update = authorized(
    ResourceType.STUDENT, AuthorizationAction.UPDATE, SELF, STUDENT_SELF
)
_student_content_read = authorized(
    ResourceType.STUDENT, AuthorizationAction.READ, path("student_id"), STUDENT_CONTENT_READ
)
_own_parent_links_read = authorized(
    ResourceType.PARENT_BINDING, AuthorizationAction.READ, SELF, STUDENT_SELF
)
_own_parent_links_update = authorized(
    ResourceType.PARENT_BINDING, AuthorizationAction.UPDATE, SELF, STUDENT_SELF
)
_own_parent_links_create = authorized(
    ResourceType.PARENT_BINDING, AuthorizationAction.CREATE, SELF, STUDENT_SELF
)


# ---------------------------------------------------------------------------
# Profile endpoints
# ---------------------------------------------------------------------------

@router.get("/me/entitlement", response_model=StudentEntitlementResponse)
async def get_my_entitlement(
    actor: Actor = Depends(_own_account_read),
):
    """Tell a student which plan covers them and what it allows today.

    Their plan is decided by a parent's billing, which only a parent may read,
    so a student had no way to learn their own limits.
    """
    entitlement = entitlement_service.resolve_student_entitlement(
        actor.user_id,
        settings=config.settings(),
        student_profile=dict(user_repo.get_user(actor.user_id) or {}),
    )
    limits = entitlement.get("limits") or {}
    period = entitlement.get("usagePeriod") or {}
    plan = str(entitlement.get("effectivePlan") or "free_trial")
    return StudentEntitlementResponse(
        effectivePlan=plan,
        newUsageAllowed=bool(entitlement.get("newUsageAllowed")),
        teacherSupportIncluded=_plan_includes_teacher_support(plan),
        dailyAiQuestionLimit=_stored_limit(limits.get("dailyAiQuestionLimit")),
        dailyChatMessageLimit=_stored_limit(limits.get("dailyChatMessageLimit")),
        # `payerId` stays on the server: the student is told self or parent only.
        usagePeriod=StudentUsagePeriod(
            endsAt=period.get("endsAt"),
            state=period.get("state") or "none",
            daysLeft=period.get("daysLeft"),
            paidBy=period.get("paidBy"),
        ),
        renewalContactEmail=config.settings().renewal_contact_email,
    )


@router.get("/me/learning-history", response_model=LearningHistoryResponse)
async def get_my_learning_history(
    actor: Actor = Depends(_own_account_read),
):
    """Return the student's own questions and practice lessons, newest first."""
    student_id = actor.user_id
    items = _question_history_items(student_id) + _practice_history_items(student_id)
    items.sort(key=lambda item: item.createdAt, reverse=True)
    return LearningHistoryResponse(items=items)


def _grade_to_store(sent: str) -> str:
    """The year group a profile write stores: a code from `choices.grade`, or "".

    Anything else - a code the list does not offer, or typed text such as
    "6. Klasse" - is refused with `profile_choice_unknown` and nothing is
    written. Free text written before the dropdown (#323) stays in the table
    and is still read through `resolve_grade_code`; it just cannot be written
    any more.
    """
    try:
        return learning_profile_service.normalize_grade(sent)
    except ValueError:
        raise AccountViolation(
            AccountErrorCode.PROFILE_CHOICE_UNKNOWN, fields=["grade"]
        ) from None


def _answer_style_to_store(sent: str) -> str:
    """The answer style a profile write stores: a code from `choices.answerStyle`.

    "" (or whitespace) is the student going back to `standard`, and is stored
    as that code. Anything outside the list is refused, like the grade, and
    nothing in the request is written.
    """
    try:
        code = learning_profile_service.normalize_choice("answer_style", sent)
    except ValueError:
        raise AccountViolation(
            AccountErrorCode.PROFILE_CHOICE_UNKNOWN, fields=["answerStyle"]
        ) from None
    return code or learning_profile_service.DEFAULT_ANSWER_STYLE


@router.get("/me/profile", response_model=StudentProfileResponse)
async def get_my_profile(
    actor: Actor = Depends(_own_account_read),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Return the current student's learning profile."""
    user_id = actor.user_id
    # Read again after the authorization read: `SELF` hands over the Actor.
    profile = user_repo.get_user(user_id)
    if not profile:
        raise SecurityDecisionError(SecurityErrorCode.RESOURCE_NOT_FOUND, correlation_id)
    return _student_profile_response(
        profile,
        fallback_user_id=user_id,
        correlation_id=correlation_id,
    )


@router.patch("/me/profile", response_model=StudentProfileResponse)
async def update_my_profile(
    body: UpdateStudentProfileRequest,
    actor: Actor = Depends(_own_account_update),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Update the current student's learning profile."""
    user_id = actor.user_id

    now = datetime.now(timezone.utc).isoformat()
    update_expr_parts = ["updated_at = :u"]
    expr_values: dict = {":u": now}

    if body.grade is not None:
        update_expr_parts.append("grade = :g")
        expr_values[":g"] = _grade_to_store(body.grade)

    if body.answerStyle is not None:
        update_expr_parts.append("answer_style = :as")
        expr_values[":as"] = _answer_style_to_store(body.answerStyle)

    if body.primarySubjects is not None:
        update_expr_parts.append("primary_subjects = :s")
        expr_values[":s"] = curriculum_service.require_subjects(
            body.primarySubjects, field="primarySubjects"
        )

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


class QuestionListItem(BaseModel):
    """One question in a student's history: what they asked and where it stands.

    Built from named fields, never from the stored row, which carries dispatch
    teachers, timed-out teachers, dispatch ids, versions and table keys (#76).
    """

    question_id: str
    subject: str = ""
    content: str = ""
    status: str
    has_image: bool = False
    student_feedback: Optional[int] = None
    created_at: str
    resolved_at: Optional[str] = None


class QuestionListResponse(BaseModel):
    items: list[QuestionListItem]
    next_token: Optional[str] = None


def _question_list_items(rows: list[dict[str, object]]) -> list[QuestionListItem]:
    """Question rows only: `GSI-StudentId` also returns conversations and messages."""
    items: list[QuestionListItem] = []
    for row in rows:
        question_id = row.get("question_id")
        if (
            row.get("SK") != "META"
            or not isinstance(question_id, str)
            or row.get("PK") != f"QUESTION#{question_id}"
        ):
            continue
        feedback = row.get("student_feedback")
        resolved_at = row.get("resolved_at")
        items.append(
            QuestionListItem(
                question_id=question_id,
                subject=str(row.get("subject") or ""),
                content=str(row.get("content") or ""),
                status=str(row.get("status") or ""),
                has_image=bool(
                    row.get("attachment_id") or row.get("image_s3_key") or row.get("has_image")
                ),
                student_feedback=int(feedback) if isinstance(feedback, (int, Decimal)) else None,
                created_at=str(row.get("created_at") or ""),
                resolved_at=str(resolved_at) if resolved_at else None,
            )
        )
    return items


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
    authorized: AuthorizedResource = Depends(_student_content_read),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Return aggregated learning stats for a student (student, parent, admin)."""
    student_id = authorized.ref.student_id

    result = question_repo.list_questions_by_student(student_id, limit=500)
    questions = [
        row
        for row in _question_rows(result.get("Items", []), correlation_id)
        if question_repo.is_question_record(row)
    ]

    ai_resolved = sum(1 for q in questions if q.get("status") == "ai_answered")
    teacher_resolved = sum(1 for q in questions if q.get("status") == "resolved")
    # A chat help request is not a question (#77); a resolved one is counted
    # through its conversation (user decision, 2026-09-29).
    teacher_resolved += sum(
        1
        for conversation in help_requests.with_requests(
            conversation_routes._list_conversations(student_id).items,
            student_id,
            table=db_table.table(),
        )
        if conversation.get("escalated") and conversation.get("escalation_status") == "resolved"
    )

    kp_counter: Counter = Counter()
    for q in questions:
        for kp in _knowledge_points(q, correlation_id):
            kp_counter[kp] += 1
    # What Ask questions named counts the same (#143).
    for record in asked_knowledge_repo.list_for_student(student_id):
        for kp in _knowledge_points(record, correlation_id):
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
    authorized: AuthorizedResource = Depends(_student_content_read),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Return subject-level activity and topic seeds for a student."""
    student_id = authorized.ref.student_id

    questions = _question_rows(
        question_repo.list_questions_by_student(student_id, limit=500).get("Items", []),
        correlation_id,
    )
    evidence = student_evidence.for_student(student_id, locale=locale_service.resolve_locale(None))
    return learning_profile_service.build_learning_profile(
        student_id=student_id,
        questions=questions,
        mistakes=list(evidence.mistakes),
        asked=asked_knowledge_repo.list_for_student(student_id),
        catalog=evidence.content.catalog,
        locale=evidence.content.locale,
    )


@router.get("/{student_id}/questions", response_model=QuestionListResponse)
async def list_questions(
    authorized: AuthorizedResource = Depends(_student_content_read),
    limit: int = Query(default=20, ge=1, le=100),
    next_token: Optional[str] = Query(default=None),
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Paginated question history for a student."""
    student_id = authorized.ref.student_id
    # The history is a query on this student's partition of GSI-StudentId: a
    # token from another student's history continues nothing here.
    scope = f"student_questions:{student_id}"

    last_key = None
    if next_token:
        try:
            last_key = db_table.read_page_token(
                next_token,
                scope,
                key=QUESTION_HISTORY_KEY,
                within=lambda key: key["student_id"] == student_id,
            )
        except db_table.PageTokenInvalid:
            raise AccountViolation(AccountErrorCode.CURSOR_INVALID) from None

    result = question_repo.list_questions_by_student(student_id, limit=limit, last_key=last_key)
    items = _question_list_items(_question_rows(result.get("Items", []), correlation_id))

    resume = result.get("LastEvaluatedKey")
    new_token = db_table.page_token(scope, resume) if resume else None

    return QuestionListResponse(items=items, next_token=new_token)


QUESTION_HISTORY_KEY = ("PK", "SK", "student_id", "created_at")


# ---------------------------------------------------------------------------
# Parent links raised from the student side
# ---------------------------------------------------------------------------

class ParentRequestCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parentNumber: str = Field(min_length=3, max_length=40)
    relationship: str = Field(default="child", min_length=1, max_length=40)


class ParentRequestItem(BaseModel):
    parentId: str
    studentId: str
    status: str
    initiatorRole: str
    relationship: str


class ParentRequestListResponse(BaseModel):
    items: list[ParentRequestItem] = Field(default_factory=list)


def _parent_request_item(link: Mapping[str, object]) -> ParentRequestItem:
    return ParentRequestItem(
        parentId=str(link.get("parent_id") or ""),
        studentId=str(link.get("student_id") or ""),
        status=str(link.get("status") or ""),
        initiatorRole=str(link.get("initiator_role") or ""),
        relationship=str(link.get("relationship") or ""),
    )


@router.get("/me/parent-requests", response_model=ParentRequestListResponse)
async def list_my_parent_requests(
    actor: Actor = Depends(_own_parent_links_read),
) -> ParentRequestListResponse:
    """Link requests awaiting this student's answer; pending grants no visibility."""
    return ParentRequestListResponse(
        items=[
            _parent_request_item(link)
            for link in parent_link_service.pending_requests_for_student(actor.user_id)
        ]
    )


@router.post("/me/parent-requests/{parent_id}/confirm", response_model=ParentRequestItem)
async def confirm_my_parent_request(
    parent_id: str,
    actor: Actor = Depends(_own_parent_links_update),
) -> ParentRequestItem:
    """Only the side that did not ask can turn a request into visibility."""
    link = parent_link_service.confirm_link(
        parent_id=parent_id, student_id=actor.user_id, actor_id=actor.user_id
    )
    return _parent_request_item(link)


@router.post("/me/parent-requests/{parent_id}/reject", response_model=ParentRequestItem)
async def reject_my_parent_request(
    parent_id: str,
    actor: Actor = Depends(_own_parent_links_update),
) -> ParentRequestItem:
    link = parent_link_service.reject_link(
        parent_id=parent_id, student_id=actor.user_id, actor_id=actor.user_id
    )
    return _parent_request_item(link)


@router.post("/me/parent-requests", response_model=ParentRequestItem)
async def request_parent_link(
    body: ParentRequestCommand,
    actor: Actor = Depends(_own_parent_links_create),
) -> ParentRequestItem:
    """Propose a link by parent number. It stops at `pending` and grants nothing."""
    admit_parent_link_request(actor.user_id)
    try:
        link = parent_link_service.request_link(
            requester_id=actor.user_id,
            counterpart_number=body.parentNumber,
            relationship=body.relationship,
        )
    except parent_link_repo.ParentLinkConflict as exc:
        raise parent_link_request_conflict() from exc
    return _parent_request_item(link)
