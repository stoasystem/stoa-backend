"""Practice module routes — subjects, topics, lessons, challenges, progress.

API contract matches stoa-frontend/src/services/practice/practiceApi.ts.
All content is pre-seeded in DynamoDB (PK=PRACTICE, SK=SUBJECT#…/TOPIC#…/LESSON#…/CHALLENGE#…).
Student progress is stored under PK=PROGRESS#{user_id}.
"""
import logging
from collections.abc import Mapping
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field

from stoa.config import settings
from stoa.db.repositories import practice_repo
from stoa.deps import get_actor
from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationPurpose,
    AuthorizedResource,
    ResourceRef,
    ResourceType,
)
from stoa.security.declared_authorization import (
    ATTEMPT,
    CHALLENGE,
    LESSON,
    SELF,
    AuthorizationContext,
    authorize_loaded,
    authorized,
    get_authorization_context,
    loaded_declaration,
    path,
    query,
)
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.security.identity import Actor, CanonicalRole
from stoa.models.practice import (
    PracticeAnswerSubmission,
    PracticeAttemptResult,
    QuizAnswerSubmission,
    PracticeMistakesResponse,
    ReviewDueResponse,
    ReviewSummaryResponse,
    PracticeHintResponse,
    PrivilegedPracticeAnswer,
)
from stoa.security.route_authorization import (
    STUDENT_CONTENT_READ,
    STUDENT_SELF,
    safe_public_dependency,
)
from stoa.services import (
    answer_recording,
    knowledge_map_service,
    curriculum_analytics_service,
    learning_profile_service,
    curriculum_service,
    entitlement_service,
    locale_service,
    quiz,
    student_evidence,
    usage_ledger_service,
)
from stoa.services import practice_projection_service, review_service
from stoa.services.curriculum_translations import translated_title
from stoa.services.practice_errors import PracticeErrorCode as _P, PracticeViolation

router = APIRouter()
logger = logging.getLogger(__name__)

_catalog_access = safe_public_dependency(ResourceType.PRACTICE)
_practice_read = authorized(ResourceType.PRACTICE, AuthorizationAction.READ, SELF, STUDENT_SELF)
_practice_update = authorized(
    ResourceType.PRACTICE, AuthorizationAction.UPDATE, SELF, STUDENT_SELF
)
_practice_progress = authorized(
    ResourceType.STUDENT,
    AuthorizationAction.READ,
    query("studentId", student_defaults_to_self=True),
    STUDENT_CONTENT_READ,
)
# Every role reads under the one narrow purpose; the policy grants it to
# assigned teachers and admins only.
_curriculum_answer_read = authorized(
    ResourceType.CURRICULUM_ANSWER,
    AuthorizationAction.READ,
    path("challenge_id"),
    {role: AuthorizationPurpose.CURRICULUM_ANSWER_READ for role in CanonicalRole},
)
_authorized_lesson_read = authorized(
    ResourceType.PRACTICE, AuthorizationAction.READ, path("lesson_id"), STUDENT_SELF, kind=LESSON
)
_authorized_lesson_update = authorized(
    ResourceType.PRACTICE,
    AuthorizationAction.UPDATE,
    path("lesson_id"),
    STUDENT_SELF,
    kind=LESSON,
)
_authorized_challenge_update = authorized(
    ResourceType.PRACTICE,
    AuthorizationAction.UPDATE,
    path("challenge_id"),
    STUDENT_SELF,
    kind=CHALLENGE,
)
_authorized_attempt_read = authorized(
    ResourceType.PRACTICE,
    AuthorizationAction.READ,
    path("attempt_id"),
    STUDENT_SELF,
    kind=ATTEMPT,
)

#: Wrong answers `/mistakes` sends, newest first.
MISTAKES_PAGE = 20


class PracticeHintRequest(BaseModel):
    """One hint request with an explicit logical-operation identity."""

    # Preserve the legacy route's tolerance for unrelated body keys while making
    # the rate-operation identity itself explicit and required.
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    challenge_id: str = Field(alias="challengeId", min_length=1, max_length=200)
    idempotency_key: str = Field(
        alias="idempotencyKey",
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9._~-]+$",
    )


class LessonQuizStartRequest(BaseModel):
    """Which of the two quizzes the student is taking (#92)."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    kind: Literal["skip", "testOut"] = "skip"


class LessonCompletionRequest(BaseModel):
    """The credential a passed quiz issued, when that is how the lesson is finished."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    quiz_credential: str | None = Field(
        default=None, alias="quizCredential", max_length=200
    )


@loaded_declaration(ResourceType.PRACTICE, AuthorizationAction.UPDATE, STUDENT_SELF)
async def _authorized_hint_challenge_update(
    body: PracticeHintRequest,
    actor: Actor = Depends(get_actor),
    context: AuthorizationContext = Depends(get_authorization_context),
) -> AuthorizedResource:
    """The challenge a hint is asked for: its id is in the body, so load, then decide."""
    return await authorize_loaded(
        actor,
        ResourceRef(ResourceType.PRACTICE, body.challenge_id, actor.user_id),
        practice_repo.get_challenge(body.challenge_id),
        AuthorizationAction.UPDATE,
        STUDENT_SELF,
        context,
    )




def _optional_string_field(
    item: Mapping[str, object], field: str
) -> str | None:
    value = item.get(field)
    return value if isinstance(value, str) else None


def _hint_limit_for_student(student_id: str) -> int:
    entitlement = entitlement_service.resolve_student_entitlement(student_id, settings=settings)
    limits = entitlement.get("limits") or {}
    return int(limits.get("dailyHintLimit") or settings.daily_hint_limit)


# ── Response helpers ────────────────────────────────────────────────────────

def _lesson_status(lesson_id: str, completed_ids: set[str],
                   current_id: str | None) -> str:
    if lesson_id in completed_ids:
        return "completed"
    if lesson_id == current_id:
        return "current"
    return "available"


def _actor_locale(actor: Actor) -> str:
    """Resolve which language to show curriculum titles in.

    The language the client is rendering right now arrives on the request, so
    it answers this without a profile read at all — that also means a language
    switch in the UI is reflected by the very next response, instead of only
    after the preference write has landed.

    Falls back to German (the stored content language, so nothing looks
    broken) if the profile read fails, the same way recorded_study_days()
    treats a non-critical lookup as best-effort rather than fatal.

    The policy itself lives in `locale_service.reader_locale`, so this and
    `ask_question._answering._student_locale` cannot drift from each other (#124).
    """
    return locale_service.reader_locale(actor.user_id)


def _actor_projection(actor: Actor) -> dict[str, object]:
    return {
        "sub": actor.user_id,
        "user_id": actor.user_id,
        "role": actor.role.value,
        "capabilities": {
            grant.capability: "granted" for grant in actor.current_grants
        },
    }


def _enforce_curriculum_preview_access(user: Actor, include_preview: bool, rollout_state: str | None) -> None:
    preview_requested = include_preview or (rollout_state is not None and rollout_state.lower() != "active")
    if preview_requested and not curriculum_service.can_preview(_actor_projection(user)):
        raise SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED)


def _resolve_curriculum_student_id(user: dict, requested_student_id: str | None) -> str:
    role = str(user.get("role", "")).lower()
    if role == "student":
        if requested_student_id and requested_student_id != user.get("sub"):
            raise SecurityDecisionError(SecurityErrorCode.ACTION_NOT_ALLOWED)
        return user["sub"]
    if role in {"admin", "teacher"} and requested_student_id:
        return requested_student_id
    raise PracticeViolation(_P.CURRICULUM_STUDENT_REQUIRED)


# ── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/curriculum/catalog")
async def get_curriculum_catalog(
    subject_id: str | None = Query(default=None, alias="subjectId"),
    grade_level: str | None = Query(default=None, alias="gradeLevel"),
    rollout_state: str | None = Query(default=None, alias="rolloutState"),
    include_preview: bool = Query(default=False, alias="includePreview"),
    user: Actor = Depends(_catalog_access),
):
    _enforce_curriculum_preview_access(user, include_preview, rollout_state)
    return curriculum_service.list_catalog(
        subject_id=subject_id,
        grade_level=grade_level,
        rollout_state=rollout_state,
        include_preview=include_preview,
        locale=_actor_locale(user),
    )


@router.get("/curriculum/lessons/{lesson_id}")
async def get_curriculum_lesson(
    lesson_id: str,
    include_preview: bool = Query(default=False, alias="includePreview"),
    user: Actor = Depends(_catalog_access),
):
    _enforce_curriculum_preview_access(user, include_preview, None)
    lesson = curriculum_service.get_lesson_detail(
        lesson_id,
        include_preview=include_preview,
        locale=_actor_locale(user),
    )
    if not lesson:
        raise PracticeViolation(_P.CURRICULUM_LESSON_NOT_FOUND)
    return lesson


@router.get("/curriculum/exercises")
async def list_curriculum_exercises(
    lesson_id: str | None = Query(default=None, alias="lessonId"),
    subject_id: str | None = Query(default=None, alias="subjectId"),
    topic_id: str | None = Query(default=None, alias="topicId"),
    difficulty: str | None = Query(default=None),
    rollout_state: str | None = Query(default=None, alias="rolloutState"),
    include_preview: bool = Query(default=False, alias="includePreview"),
    user: Actor = Depends(_catalog_access),
):
    _enforce_curriculum_preview_access(user, include_preview, rollout_state)
    return curriculum_service.list_exercises(
        lesson_id=lesson_id,
        subject_id=subject_id,
        topic_id=topic_id,
        difficulty=difficulty,
        rollout_state=rollout_state,
        include_preview=include_preview,
        locale=_actor_locale(user),
    )


@router.get(
    "/curriculum/challenges/{challenge_id}/answer",
    response_model=PrivilegedPracticeAnswer,
)
async def get_privileged_curriculum_answer(
    challenge_id: str,
    authorized_challenge: AuthorizedResource = Depends(_curriculum_answer_read),
):
    """Return the already-resolved challenge through the narrow answer policy."""
    return practice_projection_service.build_privileged_answer(
        authorized_challenge.value
    )


@router.get("/curriculum/progress")
async def get_curriculum_progress(
    student_id: str | None = Query(default=None, alias="studentId"),
    subject_id: str | None = Query(default=None, alias="subjectId"),
    authorized_student: AuthorizedResource = Depends(_practice_progress),
):
    """One student's progress: lessons finished, streak, mistakes by topic.

    `subjectId` narrows the lessons and the mistakes; the streak is the
    student's, whatever the subject.
    """
    resolved_student_id = authorized_student.ref.student_id
    evidence = student_evidence.for_student(resolved_student_id)
    completed = evidence.completed_lesson_ids_in(subject_id)
    mistakes = [
        item
        for item in evidence.mistakes
        if not subject_id or curriculum_service.same_subject(item.get("subject_id", ""), subject_id)
    ]
    return {
        "studentId": resolved_student_id,
        "subjectId": curriculum_service.subject_key(subject_id) if subject_id else subject_id,
        "completedLessons": len(completed),
        "completedLessonIds": [
            item.lesson_id for item in evidence.completions if item.lesson_id in completed
        ],
        "mistakeCount": len(mistakes),
        "studyStreak": evidence.study_streak,
        "practisedToday": evidence.practised_today,
        "weakTopics": [
            {"topicId": topic_id, "count": count}
            for topic_id, count in evidence.mistakes_by_topic(subject_id).most_common(5)
        ],
        "source": "practice_progress",
    }


@router.get("/knowledge-map")
async def get_knowledge_map(
    subject_id: str | None = Query(default=None, alias="subjectId"),
    view: Literal["full", "skeleton"] = Query(default="full"),
    authorized_student: AuthorizedResource = Depends(_practice_progress),
    actor: Actor = Depends(get_actor),
):
    """The star map: every subject, topic and knowledge point with its state.

    The language comes from the request the way every other curriculum read
    here takes it, not from a query parameter with German wired in as the
    default: the names on this map are galaxy, nebula and knowledge-point
    titles, and a French student reading a sky labelled in German is the same
    defect as any other untranslated screen.

    The student is `authorized_student.ref.student_id` and nothing else. The
    `studentId` query parameter belongs to the authorization dependency, which
    declares and checks it; reading one here would be a way around the check.

    A `subjectId` naming no subject the curriculum has is a 422 rather than a
    sky labelled with it (#124). One the student has not started is not: the
    map is there to be browsed ahead of enrolment.

    `view=skeleton` sends every star with its state and position but none of
    its small stars; `/knowledge-map/stars` then sends the few around one in full.

    A star's `state` is `lit`, `in_progress` or `ready`; nothing is locked
    (#125). `unlitPrerequisiteIds` lists the star's stated prerequisites that
    are not lit yet, in the order stated - empty for a lit star - so the map
    can mark it and say which to learn first. `litAtSource` is `quiz` for a
    star lit by passing its star quiz, and `starQuizRetryAt` says when a star
    whose quiz was lost can be taken again - None when it can now (#165).
    A recommended star's `recommendation` is `{source, reason, relatedUnitId}`:
    `reason` is `in_progress`, `after_lit` (then `relatedUnitId` is the star
    whose lighting it follows), `grade` (nothing begun yet: the first star of
    the year group on the student's profile, #310) or `start`; only subjects
    the student takes carry one (#164) - those with progress, and those ticked
    on the profile (#321).
    """
    profile = authorized_student.value or {}
    if not isinstance(profile, Mapping):
        profile = {}
    try:
        return knowledge_map_service.knowledge_map(
            student_evidence.for_student(
                authorized_student.ref.student_id, locale=_actor_locale(actor)
            ),
            subject_id=subject_id,
            view=view,
            student_grade=profile.get("grade"),
            chosen_subject_ids=learning_profile_service.chosen_subjects(profile),
        )
    except knowledge_map_service.UnknownSubject:
        raise PracticeViolation(_P.SUBJECT_UNKNOWN) from None


@router.get("/knowledge-map/stars")
async def get_knowledge_map_neighbourhood(
    subject_id: str | None = Query(default=None, alias="subjectId"),
    around: str | None = Query(default=None, max_length=200),
    authorized_student: AuthorizedResource = Depends(_practice_progress),
    actor: Actor = Depends(get_actor),
):
    """A few stars in full - small stars, practice sets, missing prerequisites -
    around `around`, or around where the student last practised.

    With the star come the ones it needs, the ones that need it and its
    neighbours in its nebula, so the client loads the part of the sky the
    student is about to look at. The student is decided by the authorization
    dependency, exactly as for `/knowledge-map`.
    """
    try:
        return knowledge_map_service.neighbourhood(
            student_evidence.for_student(
                authorized_student.ref.student_id, locale=_actor_locale(actor)
            ),
            subject_id=subject_id,
            around=around,
        )
    except knowledge_map_service.UnknownSubject:
        raise PracticeViolation(_P.SUBJECT_UNKNOWN) from None


class LitAcknowledgement(BaseModel):
    """The knowledge points whose lighting has now been shown to the student."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    # Ten units exist today and a sky is not going to hold hundreds. The cap
    # was 200, and every id in a request costs a conditional write whether or
    # not it names anything — a refused write is billed like any other.
    unit_ids: list[str] = Field(default_factory=list, alias="unitIds", max_length=50)


@router.post("/knowledge-map/acknowledged-lit")
async def acknowledge_lit_knowledge_points(
    body: LitAcknowledgement,
    actor: Actor = Depends(_practice_update),
):
    """Confirm that these lightings have been celebrated, so they stop coming back.

    The student is `actor.user_id`, and the request carries no student
    identifier at all - there is no field here that could name somebody else's
    sky, and the row the write addresses is built from the actor's own
    partition. A unit id belonging to another student's lighting therefore
    addresses a row that does not exist and confirms nothing.
    """
    return knowledge_map_service.acknowledge_lit(actor.user_id, body.unit_ids)


# ── The two quizzes, one module (`stoa.services.quiz`, #213) ────────────────

#: What each refusal of the quiz module is called, per kind.
_LESSON_QUIZ_REFUSALS: dict[quiz.Reason, _P] = {
    quiz.Reason.UNKNOWN: _P.LESSON_QUIZ_NOT_FOUND,
    quiz.Reason.FINISHED: _P.LESSON_QUIZ_FINISHED,
    quiz.Reason.EXPIRED: _P.LESSON_QUIZ_EXPIRED,
    quiz.Reason.GONE: _P.LESSON_QUIZ_UNAVAILABLE,
    quiz.Reason.OUT_OF_ORDER: _P.LESSON_QUIZ_OUT_OF_ORDER,
    quiz.Reason.ANSWER_INVALID: _P.PRACTICE_ANSWER_INVALID,
    quiz.Reason.NOTHING_TO_ASK: _P.LESSON_QUIZ_UNAVAILABLE,
    quiz.Reason.CREDENTIAL_INVALID: _P.LESSON_QUIZ_CREDENTIAL_INVALID,
    quiz.Reason.CREDENTIAL_EXPIRED: _P.LESSON_QUIZ_CREDENTIAL_EXPIRED,
}
_STAR_QUIZ_REFUSALS: dict[quiz.Reason, _P] = {
    quiz.Reason.UNKNOWN: _P.STAR_QUIZ_NOT_FOUND,
    quiz.Reason.FINISHED: _P.STAR_QUIZ_FINISHED,
    quiz.Reason.EXPIRED: _P.STAR_QUIZ_EXPIRED,
    quiz.Reason.GONE: _P.STAR_QUIZ_UNAVAILABLE,
    quiz.Reason.OUT_OF_ORDER: _P.STAR_QUIZ_OUT_OF_ORDER,
    quiz.Reason.ANSWER_INVALID: _P.PRACTICE_ANSWER_INVALID,
    quiz.Reason.NOTHING_TO_ASK: _P.STAR_QUIZ_UNAVAILABLE,
    quiz.Reason.NO_SUCH_STAR: _P.STAR_QUIZ_UNKNOWN_STAR,
    quiz.Reason.ALREADY_LIT: _P.STAR_QUIZ_ALREADY_LIT,
    quiz.Reason.COOLING_DOWN: _P.STAR_QUIZ_COOLING_DOWN,
}


def _quiz_refusal(codes: Mapping[quiz.Reason, _P], refused: quiz.Refused) -> PracticeViolation:
    if refused.retry_at:
        return PracticeViolation(codes[refused.reason], retryAt=refused.retry_at)
    return PracticeViolation(codes[refused.reason])


# ── Star quiz: one paper that lights a whole knowledge point (#165) ─────────


class StarQuizAnswer(BaseModel):
    """One answer to the exercise the paper is asking now.

    `exerciseId` names that exercise, so the same answer sent twice - a retry
    after a lost response - is recognised and answered with the first result
    rather than judged against the next exercise (#113).
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    exercise_id: str = Field(alias="exerciseId", min_length=1, max_length=200)
    answer: object


@router.post(
    "/knowledge-map/stars/{unit_id}/quiz",
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "`star_quiz_unknown_star`: no knowledge point with lessons has this id."
        },
        status.HTTP_409_CONFLICT: {
            "description": (
                "`star_quiz_already_lit`: the star is lit already; "
                "`star_quiz_cooling_down`: a quiz of this star was lost less than "
                "24 hours ago, `retryAt` says when it can be taken again; "
                "`star_quiz_unavailable`: the star has no exercise to ask."
            )
        },
    },
)
async def start_star_quiz(
    unit_id: str,
    actor: Actor = Depends(_practice_update),
):
    """Open the star quiz of one knowledge point, or the one already open (#165).

    Every star not lit can be taken, in progress or not, whatever its
    prerequisites. The paper asks at least one exercise from each core lesson,
    6 to 10 in all, each once; a second wrong answer loses it. A paper still
    open for this star is handed back rather than replaced, so leaving and
    coming back does not draw a fresh set of exercises.
    """
    try:
        return quiz.start_star_quiz(actor.user_id, unit_id, locale=_actor_locale(actor))
    except quiz.Refused as refused:
        raise _quiz_refusal(_STAR_QUIZ_REFUSALS, refused) from None


@router.post(
    "/knowledge-map/stars/{unit_id}/quiz/{quiz_id}/answer",
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "`star_quiz_not_found`: this student has no such quiz of this star."
        },
        status.HTTP_409_CONFLICT: {
            "description": (
                "`star_quiz_finished`: the quiz was already passed or lost; "
                "`star_quiz_expired`: it is past its expiry; "
                "`star_quiz_out_of_order`: `exerciseId` is not the exercise the quiz "
                "is asking now; `star_quiz_unavailable`: the exercise it asked is gone."
            )
        },
    },
)
async def answer_star_quiz(
    unit_id: str,
    quiz_id: str,
    body: StarQuizAnswer,
    actor: Actor = Depends(_practice_update),
):
    """Judge one answer of a star quiz (#165).

    The answer names its exercise; an exercise already answered is answered
    again with its first result and nothing changes. Passing lights the star
    with the source `quiz` and schedules every answer of the paper for review,
    right or wrong, as ordinary practice would. Losing records nothing but
    when the star can be taken again (`retryAt`, 24 hours on): no evidence,
    no review card. The lessons are not touched either way.
    """
    try:
        return quiz.answer(
            quiz.STAR,
            actor.user_id,
            quiz_id,
            scope_id=unit_id,
            exercise_id=body.exercise_id,
            raw_answer=body.answer,
            locale=_actor_locale(actor),
        )
    except quiz.Refused as refused:
        raise _quiz_refusal(_STAR_QUIZ_REFUSALS, refused) from None

@router.get("/{subject_id}/{topic_id}/roadmap")
async def get_roadmap(
    subject_id: str,
    topic_id: str,
    actor: Actor = Depends(_practice_read),
):
    """Return the lesson roadmap for a topic.

    What the student catalog shows, nothing more (#354): a topic, unit or
    lesson that is archived or still in preview is left out, as
    `curriculum_service.list_catalog` leaves it out. The subject is answered
    as its canonical id, however it was spelled in the path.
    """
    locale = _actor_locale(actor)
    topic = practice_repo.get_topic(topic_id)
    if (
        not topic
        or not curriculum_service.same_subject(topic.get("subject_id", ""), subject_id)
        or not curriculum_service.visible_to_students(topic)
    ):
        raise PracticeViolation(_P.TOPIC_NOT_FOUND)
    subject = curriculum_service.subject_key(subject_id)

    completed_ids = student_evidence.for_student(actor.user_id).completed_lesson_ids_in(subject)

    units_raw = sorted(
        (unit for unit in practice_repo.get_units(topic_id) if curriculum_service.visible_to_students(unit)),
        key=lambda x: x.get("order", 0),
    )
    unit_ids = {unit["unit_id"] for unit in units_raw}
    # Find the current lesson (first non-completed)
    all_lessons = sorted(
        (
            lesson
            for lesson in practice_repo.get_lessons(topic_id=topic_id)
            if lesson.get("unit_id") in unit_ids and curriculum_service.visible_to_students(lesson)
        ),
        key=lambda x: (x.get("unit_id", ""), x.get("order", 0)),
    )
    current_lesson_id = next(
        (lesson["lesson_id"] for lesson in all_lessons if lesson["lesson_id"] not in completed_ids),
        all_lessons[-1]["lesson_id"] if all_lessons else None,
    )
    progress_pct = int(len(completed_ids) / len(all_lessons) * 100) if all_lessons else 0

    roadmap_units = []
    for unit_raw in units_raw:
        unit_lessons_raw = [lesson for lesson in all_lessons if lesson.get("unit_id") == unit_raw["unit_id"]]
        roadmap_lessons = []
        for lesson in unit_lessons_raw:
            st = _lesson_status(lesson["lesson_id"], completed_ids, current_lesson_id)
            roadmap_lessons.append({
                "id": lesson["lesson_id"],
                "title": translated_title(lesson["lesson_id"], lesson["title"], locale),
                "description": lesson.get("description", ""),
                "order": lesson.get("order", 1),
                "status": st,
                "estimatedMinutes": lesson.get("estimated_minutes", 10),
                "subjectId": subject,
                "gradeLevel": lesson.get("grade_level", ""),
                "topicId": topic_id,
                "unitId": lesson.get("unit_id", ""),
                "challengeCount": lesson.get("challenge_count", 3),
            })
        roadmap_units.append({
            "id": unit_raw["unit_id"],
            "title": translated_title(unit_raw["unit_id"], unit_raw["title"], locale),
            "description": unit_raw.get("description", ""),
            "order": unit_raw.get("order", 1),
            "lessons": roadmap_lessons,
        })

    return {
        "subjectId": subject,
        "topicId": topic_id,
        "gradeLevel": topic.get("grade_level", ""),
        "topic": {
            "id": topic["topic_id"],
            "subjectId": subject,
            "gradeLevel": topic.get("grade_level", ""),
            "title": translated_title(topic["topic_id"], topic["title"], locale),
            "description": topic.get("description", ""),
            "progress": progress_pct,
            "currentLessonId": current_lesson_id,
        },
        "progress": progress_pct,
        "currentLessonId": current_lesson_id,
        "units": roadmap_units,
    }


@router.get("/lessons/{lesson_id}")
async def get_lesson(
    lesson_id: str,
    actor: Actor = Depends(_practice_read),
    authorized_lesson: AuthorizedResource = Depends(_authorized_lesson_read),
):
    lesson = dict(authorized_lesson.value)

    completed_ids = student_evidence.for_student(actor.user_id).completed_lesson_ids
    lesson_topic_id = _optional_string_field(lesson, "topic_id")
    all_lessons = sorted(
        practice_repo.get_lessons(topic_id=lesson_topic_id),
        key=lambda x: x.get("order", 0),
    )
    current_id = next(
        (lesson["lesson_id"] for lesson in all_lessons if lesson["lesson_id"] not in completed_ids),
        None,
    )
    st = _lesson_status(lesson_id, completed_ids, current_id)
    locale = _actor_locale(actor)
    challenges: list[Mapping[str, Any]] = [
        practice_projection_service.build_challenge_preview(c, locale)
        for c in practice_repo.get_challenges(lesson_id)
    ]
    return practice_projection_service.build_lesson_preview(lesson, challenges, st, locale=locale)


@router.post(
    "/lessons/{lesson_id}/quiz",
    responses={
        status.HTTP_409_CONFLICT: {
            "description": (
                "`lesson_quiz_unavailable`: the lesson has no exercise "
                "to draw a quiz from."
            )
        }
    },
)
async def start_lesson_quiz(
    lesson_id: str,
    body: LessonQuizStartRequest | None = None,
    actor: Actor = Depends(_practice_update),
    authorized_lesson: AuthorizedResource = Depends(_authorized_lesson_update),
):
    """Draw the short quiz that can complete this lesson (#92).

    The exercises are drawn here and kept in a row of this student's own, so
    what the quiz asks and how many mistakes are left are facts the client
    cannot restate. Nothing in the answer-free projection carries the answer.
    """
    try:
        return quiz.start_lesson_quiz(
            actor.user_id,
            lesson_id,
            kind=body.kind if body else quiz.rules.SKIP_QUIZ,
            locale=_actor_locale(actor),
        )
    except quiz.Refused as refused:
        raise _quiz_refusal(_LESSON_QUIZ_REFUSALS, refused) from None


@router.post(
    "/lessons/{lesson_id}/quiz/{quiz_id}/answer",
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "`lesson_quiz_not_found`: this student has no such open quiz."
        },
        status.HTTP_409_CONFLICT: {
            "description": (
                "`lesson_quiz_expired`: the quiz is past its expiry; "
                "`lesson_quiz_finished`: it was already passed or lost; "
                "`lesson_quiz_out_of_order`: `exerciseId` is not the exercise the quiz "
                "is asking now; `lesson_quiz_unavailable`: the exercise it asked is gone."
            )
        },
    },
)
async def answer_lesson_quiz(
    lesson_id: str,
    quiz_id: str,
    body: QuizAnswerSubmission,
    actor: Actor = Depends(_practice_update),
    authorized_lesson: AuthorizedResource = Depends(_authorized_lesson_update),
):
    """Judge one quiz answer. No hint, no Ask, no skip - and no second slip.

    A wrong answer costs a heart and sends the exercise to the back of the
    queue; the second one loses the quiz. `exerciseId` names the exercise
    answered: sent again for an exercise already answered, it gets the first
    result back (#113). Quiz answers are not recorded as attempts: passing
    completes the lesson and nothing more, so a knowledge point still lights
    only on exercises answered right in the ordinary way (#9).
    """
    try:
        return quiz.answer(
            quiz.LESSON,
            actor.user_id,
            quiz_id,
            scope_id=lesson_id,
            exercise_id=body.exercise_id,
            raw_answer=body.answer,
            locale=_actor_locale(actor),
        )
    except quiz.Refused as refused:
        raise _quiz_refusal(_LESSON_QUIZ_REFUSALS, refused) from None

@router.post(
    "/lessons/{lesson_id}/complete",
    responses={
        status.HTTP_409_CONFLICT: {
            "description": (
                "`lesson_exercises_unanswered`: an exercise of the lesson "
                "has never been answered right and no quiz credential was sent "
                "(the message says how many); `lesson_quiz_credential_invalid`: the "
                "credential is unknown, already spent, or belongs to another student or "
                "lesson; `lesson_quiz_credential_expired`: the credential is past its "
                "expiry."
            )
        }
    },
)
async def complete_lesson(
    lesson_id: str,
    body: LessonCompletionRequest | None = None,
    actor: Actor = Depends(_practice_update),
    authorized_lesson: AuthorizedResource = Depends(_authorized_lesson_update),
):
    lesson = dict(authorized_lesson.value)

    credential = (body.quiz_credential or "").strip() if body else ""
    if credential:
        # Either road to completion, never both: a client that presents a
        # credential is judged on that credential, so a forged one cannot be
        # waved through by exercises that happened to be answered anyway.
        try:
            quiz.spend_credential(actor.user_id, lesson_id, credential)
        except quiz.Refused as refused:
            raise _quiz_refusal(_LESSON_QUIZ_REFUSALS, refused) from None
    else:
        # A lesson is complete once every exercise in it has been answered right at
        # least once (#83). The frontend held to this alone; any client could
        # mark any lesson complete. A lesson without exercises has nothing to answer.
        unanswered = practice_repo.unanswered_challenge_ids(actor.user_id, lesson_id)
        if unanswered:
            raise PracticeViolation(
                _P.LESSON_EXERCISES_UNANSWERED, params={"count": len(unanswered)}
            )

    progress_row = practice_repo.mark_lesson_completed(actor.user_id, lesson)
    curriculum_analytics_service.record_lesson_completed(student_id=actor.user_id, lesson=lesson)
    _record_practice_usage(
        student_id=actor.user_id,
        action=usage_ledger_service.PRACTICE_LESSON_COMPLETION_ACTION,
        resource_id=lesson_id,
        metadata={"status": "completed"},
        account_fence_generation=(
            int(progress_row["account_fence_generation"])
            if isinstance(progress_row, dict)
            and type(progress_row.get("account_fence_generation")) is int
            else None
        ),
    )
    lesson_topic_id = _optional_string_field(lesson, "topic_id")
    all_lessons = sorted(
        practice_repo.get_lessons(topic_id=lesson_topic_id),
        key=lambda x: x.get("order", 0),
    )
    # Read after the completion is written; the lesson just finished counts
    # even if the read does not see that write yet.
    evidence = student_evidence.for_student(actor.user_id)
    completed_ids = evidence.completed_lesson_ids | {lesson_id}
    next_lesson = next(
        (lesson for lesson in all_lessons if lesson["lesson_id"] not in completed_ids), None
    )
    return {
        "lessonId": lesson_id,
        "completed": True,
        "nextLessonId": next_lesson["lesson_id"] if next_lesson else None,
        "progressPoints": len(completed_ids) * 10,
        "studyStreak": evidence.study_streak,
        "dailyGoalCompleted": False,
    }


@router.post(
    "/challenges/{challenge_id}/answer",
    response_model=PracticeAttemptResult,
)
async def submit_answer(
    challenge_id: str,
    body: PracticeAnswerSubmission,
    actor: Actor = Depends(_practice_update),
    authorized_challenge: AuthorizedResource = Depends(_authorized_challenge_update),
):
    """Judge a practice answer in the reader's language and record it (`answer_recording`)."""
    try:
        return answer_recording.answer_practice(
            actor.user_id,
            dict(authorized_challenge.value),
            body.answer,
            locale=_actor_locale(actor),
        )
    except answer_recording.AnswerInvalid as error:
        raise PracticeViolation(_P.PRACTICE_ANSWER_INVALID) from error
    except answer_recording.ReceiptUnavailable as error:
        raise PracticeViolation(_P.PRACTICE_ATTEMPT_UNAVAILABLE) from error


@router.get(
    "/attempts/{attempt_id}/result",
    response_model=PracticeAttemptResult,
)
async def get_attempt_result(
    attempt_id: str,
    authorized_attempt: AuthorizedResource = Depends(_authorized_attempt_read),
):
    attempt = dict(authorized_attempt.value)
    try:
        return practice_projection_service.build_attempt_result(attempt)
    except (KeyError, TypeError, ValueError):
        raise PracticeViolation(_P.PRACTICE_ATTEMPT_NOT_FOUND)


@router.get("/mistakes", response_model=PracticeMistakesResponse)
async def get_mistakes(actor: Actor = Depends(_practice_read)):
    mistakes = []
    for attempt in student_evidence.for_student(actor.user_id).mistakes[:MISTAKES_PAGE]:
        try:
            mistakes.append(
                practice_projection_service.build_mistake_projection(attempt)
            )
        except (KeyError, TypeError, ValueError):
            continue
    return PracticeMistakesResponse(items=mistakes)


@router.get("/review/due", response_model=ReviewDueResponse)
async def get_due_review(
    unit_id: str | None = Query(default=None, alias="unitId"),
    actor: Actor = Depends(_practice_read),
):
    """The questions this student is due to see again.

    With `unitId`, the session is one knowledge point's cards and `dueCount` is
    how many that knowledge point has due, which is the number the star map
    shows on it. Without it, the answer is unchanged.
    """
    return ReviewDueResponse.model_validate(
        review_service.due_review(
            student_id=actor.user_id, unit_id=unit_id, locale=_actor_locale(actor)
        )
    )


@router.get("/review/summary", response_model=ReviewSummaryResponse)
async def get_review_summary(actor: Actor = Depends(_practice_read)):
    """How much review is waiting, for badges and prompts."""
    return ReviewSummaryResponse.model_validate(
        review_service.review_summary(student_id=actor.user_id)
    )


@router.post("/hints", response_model=PracticeHintResponse)
async def get_hint(
    body: PracticeHintRequest,
    actor: Actor = Depends(_practice_update),
    authorized_challenge: AuthorizedResource = Depends(_authorized_hint_challenge_update),
):
    from stoa.services.rate_limit import check_and_record_hint
    challenge_id = body.challenge_id
    challenge = dict(authorized_challenge.value)

    usage_counter = check_and_record_hint(
        actor.user_id,
        challenge_id,
        body.idempotency_key,
        limit=_hint_limit_for_student(actor.user_id),
    )

    hint = practice_projection_service.approved_directional_hint(challenge)

    _record_practice_usage(
        student_id=actor.user_id,
        action=usage_ledger_service.HINT_REQUEST_ACTION,
        resource_id=challenge_id,
        usage_counter=usage_counter,
        metadata={"status": "returned" if hint else "unavailable"},
    )

    return PracticeHintResponse(
        challengeId=challenge_id,
        hintAvailable=hint is not None,
        hint=hint,
    )


#: A hint and a finished lesson leave the same kind of usage event an answer does.
_record_practice_usage = answer_recording.record_practice_usage
