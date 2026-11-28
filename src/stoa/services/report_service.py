"""Weekly report aggregation and generation helpers."""

from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import logging
import re
import uuid
from collections.abc import Callable, Mapping
from time import monotonic
from typing import Any, Protocol, runtime_checkable


from stoa import config
from stoa.db import table as db_table
from stoa.db.repositories import (
    account_deletion_repo,
    allowance_repo,
    asked_knowledge_repo,
    question_repo,
    report_repo,
    user_repo,
)
from stoa.services import (
    allowance_service,
    current_relationship,
    email_layout,
    entitlement_service,
    knowledge_mastery_service,
    learning_session,
    locale_service,
    message_catalog,
    model_call,
    notifications,
    report_artifact_service,
    student_evidence,
    weak_topics,
)

logger = logging.getLogger(__name__)

# A report's `email_status` when the parent switched the weekly email off (#363).
EMAIL_SKIPPED_PREFERENCE = "skipped_preference"


def weekly_report_subject(student_name: str | None, locale: str | None) -> str:
    """The subject of one weekly report email, in the parent's language."""
    lang = locale or locale_service.DEFAULT_LOCALE
    student = str(student_name or "").strip() or message_catalog.text(
        "email.weekly_report.student_fallback", lang
    )
    return message_catalog.text("email.weekly_report.subject", lang, student=student)


def tell_report_ready(
    report: Mapping[str, Any],
    *,
    parent_email: str,
    generation: int,
    html: str,
    locale: str,
    resend: int = 0,
) -> notifications.EmailResult:
    """Tell the notifications that this report is ready for its parent (#687).

    The package decides the rest: whether the parent still wants it by email,
    the unsubscribe line, and that the same report - or the same resend - is
    sent once however often this is said.
    """
    return notifications.happened(
        notifications.WeeklyReportReady(
            report_id=str(report["report_id"]),
            parent_id=str(report["parent_id"]),
            parent_email=parent_email,
            student_id=str(report["student_id"]),
            generation=generation,
            subject=weekly_report_subject(report.get("student_name"), locale),
            html=html,
            resend=resend,
        )
    )


@runtime_checkable
class _QueryTable(Protocol):
    def query(self, **kwargs: object) -> object: ...


def _repository_response(value: object, *, label: str) -> dict[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise RuntimeError(f"{label} repository response is malformed")
    return dict(value)


def _repository_items(response: Mapping[str, object], *, label: str) -> list[dict[str, object]]:
    raw_items = response.get("Items")
    if not isinstance(raw_items, list) or any(not isinstance(item, Mapping) for item in raw_items):
        raise RuntimeError(f"{label} repository response is malformed")
    return [dict(item) for item in raw_items]

_MAX_REPORT_WEAK_TOPICS = 5
_MAX_REPORT_ACTIVITIES = 6
_MAX_ACTIVITY_SUMMARY_CHARS = 160

# The report is the input of one tool, forced by the request (#438): `strict`
# holds the input to the schema, so the JSON is the API's to write. The schema
# says what `parse_generated_report_json` accepts, in what strict tool schemas
# can say; the parser still checks the rest (no blank strings, at least one
# strength and one recommendation, no internal terms). The prompt names the
# tool; the two must stay the same.
REPORT_TOOL_NAME = "give_weekly_report"

# How freely the model writes a report, and how long it may write.
REPORT_TEMPERATURE = 0.2
REPORT_MAX_OUTPUT_TOKENS = 1200

# The report job has no deadline of its own; one model call gets at most this
# long (#435 item 9).
REPORT_DEADLINE_SECONDS = 60

_REPORT_TEXTS: dict[str, object] = {"type": "array", "items": {"type": "string"}}

REPORT_TOOL = model_call.Tool(
    name=REPORT_TOOL_NAME,
    description="Give the parent the whole weekly report.",
    strict=True,
    input_schema={
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "2-3 sentences."},
            "strengths": {**_REPORT_TEXTS, "description": "Short bullets; at least one."},
            "weakTopics": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string"},
                        "note": {"type": "string"},
                    },
                    "required": ["topic", "note"],
                    "additionalProperties": False,
                },
            },
            "recommendations": {**_REPORT_TEXTS, "description": "Short actions; at least one."},
            "teacherNote": {
                "type": ["string", "null"],
                "description": "An optional short note, or null.",
            },
        },
        "required": ["summary", "strengths", "weakTopics", "recommendations", "teacherNote"],
        "additionalProperties": False,
    },
)

_REPORT_SYSTEM_PROMPT = f"""You write weekly parent reports for STOA.

Use only the structured report input provided by the user. Do not invent activity.
Write warm, concise parent-facing text in the language `language` names: de German, en English, fr French, it Italian.

Give the whole report as one call of `{REPORT_TOOL_NAME}` and nothing else:
- summary: 2-3 sentences
- strengths: short bullets, at least one
- weakTopics: each a topic name and a short note; empty when there are none
- recommendations: short actions, at least one
- teacherNote: an optional short note, or null

What the student did on their own and with help from the AI:
- answeredRight counts the exercises answered right for the first time this week: onOwn without asking the AI about them, afterAskingAi only after asking it.
- starsLit is the stars lit this week: onOwn counts those lit mostly on the student's own; mostlyAfterAskingAi names those lit mostly with help from the AI.
- Say in the summary how many exercises the student solved on their own and how many with help from the AI, and how many stars lit. Name every star in mostlyAfterAskingAi and recommend practising it again without asking the AI.
- When afterAskingAi is 0 and mostlyAfterAskingAi is empty, do not mention the AI or help from it anywhere.
- When nothing was solved and no star lit, say nothing about either.

Do not mention providers, model names, prompts, systems, or implementation details."""

_FORBIDDEN_PARENT_COPY_TERMS = [
    "anthropic",
    "aws",
    "amazon web services",
    "claude",
    "bedrock",
    "openai",
    "gpt",
    "llm",
    "foundation model",
    "large language model",
    "language model",
    "ai model",
    "model name",
    "model names",
    "model id",
    "system prompt",
    "prompt engineering",
    "inference",
    "provider",
    "implementation detail",
    "implementation details",
]
_FORBIDDEN_PARENT_COPY_RE = re.compile(
    "|".join(rf"(?<!\w){re.escape(term)}(?!\w)" for term in _FORBIDDEN_PARENT_COPY_TERMS),
    re.IGNORECASE,
)


def report_week_window(week_start: str | date) -> tuple[date, date]:
    """Return the inclusive start and exclusive end date for a report week."""
    if isinstance(week_start, str):
        try:
            start = date.fromisoformat(week_start)
        except ValueError as exc:
            raise ValueError("week_start must be an ISO date") from exc
    else:
        start = week_start
    return start, start + timedelta(days=7)


def build_weekly_learning_payload(
    parent_id: str,
    student_id: str,
    week_start: str | date,
) -> dict[str, Any]:
    """Build a compact weekly learning payload from real student activity."""
    start, end = report_week_window(week_start)
    parent = user_repo.get_user(parent_id) or {"user_id": parent_id}
    student = _get_linked_student_profile(parent_id, student_id)

    # Written for the parent, so in the language the parent stored (#450), as
    # the email frame around it is (#278); star titles too.
    locale = locale_service.stored_locale(parent_id)
    questions = _list_all_questions(student_id)
    evidence = student_evidence.for_student(student_id, locale=locale)
    conversations = _list_conversations_for_student(student_id)
    # What Ask questions named (#143), read from the week's first day on; the
    # weak topics keep only that week's.
    asked = asked_knowledge_repo.list_for_student(student_id, since=start.isoformat())

    weekly_questions = [
        item for item in questions if _is_in_window(item.get("created_at") or item.get("createdAt"), start, end)
    ]
    window = (
        datetime.combine(start, time.min, tzinfo=timezone.utc),
        datetime.combine(end, time.min, tzinfo=timezone.utc),
    )
    weekly_progress = evidence.completions_between(*window)
    weekly_mistakes = list(evidence.mistakes_between(*window))
    answered_right = evidence.right_answers_between(*window)
    weekly_conversations = [
        item
        for item in conversations
        if _is_in_window(item.get("updated_at") or item.get("created_at"), start, end)
    ]

    ai_resolved = sum(1 for item in weekly_questions if item.get("status") == "ai_answered")
    teacher_help = sum(1 for item in weekly_questions if _question_requested_teacher_help(item))
    teacher_help += sum(
        1
        for item in conversations
        if item.get("escalated") and _is_in_window(item.get("escalated_at") or item.get("updated_at"), start, end)
    )

    # The week's weak topics, by the one rule every reader uses (#674).
    weak = weak_topics.for_student(
        evidence, [*questions, *asked], locale=locale, since=window[0], until=window[1]
    )
    activities = _sort_activities(
        [
            *[_question_activity(item) for item in weekly_questions],
            *[_practice_activity(item) for item in weekly_progress],
            *[_mistake_activity(item) for item in weekly_mistakes],
            *[_conversation_activity(item) for item in weekly_conversations],
        ]
    )

    return {
        "locale": locale,
        "parent": {
            "id": parent.get("user_id", parent_id),
            "email": parent.get("email", ""),
            "name": _display_name(parent),
        },
        "student": {
            "id": student.get("user_id", student_id),
            "email": student.get("email", ""),
            "name": _display_name(student),
            "grade": student.get("grade"),
        },
        "week": {
            "start": start.isoformat(),
            "end": (end - timedelta(days=1)).isoformat(),
        },
        "metrics": {
            "questionsAsked": len(weekly_questions),
            "aiResolved": ai_resolved,
            "teacherHelpRequests": teacher_help,
            "practiceLessonsCompleted": len(weekly_progress),
            "mistakesLogged": len(weekly_mistakes),
        },
        # This week's newly solved exercises and lit stars, on the student's own
        # and with help from Ask (#450).
        "answeredRight": {
            "onOwn": answered_right.independent,
            "afterAskingAi": answered_right.asked_ai,
        },
        "starsLit": _stars_lit(evidence, *window),
        "weakTopics": [{"topic": topic.name, "count": topic.count} for topic in weak],
        "activities": activities,
        "sourceCounts": {
            "questions": len(weekly_questions),
            "practiceProgress": len(weekly_progress),
            "mistakes": len(weekly_mistakes),
            "conversations": len(weekly_conversations),
        },
    }


def _stars_lit(
    evidence: student_evidence.StudentEvidence, start: datetime, end: datetime
) -> dict[str, Any]:
    """The stars lit in `[start, end)`: how many mostly on the student's own, and the rest by name (#450).

    "Mostly after asking AI" is `knowledge_mastery_service.mostly_with_ai`, on
    every right answer the star has, as the teacher sees it (#451). A report
    without its stars still goes out, so a failed read leaves them out.
    """
    try:
        lit = knowledge_mastery_service.lit_between(evidence, start, end)
        counts = evidence.right_answers_by_unit
        titles = {str(unit.get("id") or ""): unit.get("title") for unit in evidence.content.units}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Weekly report stars lit unavailable error_class=%s", type(exc).__name__)
        return {"onOwn": 0, "mostlyAfterAskingAi": []}
    with_ai = [
        unit_id
        for unit_id in lit
        if knowledge_mastery_service.mostly_with_ai(counts.get(unit_id, student_evidence.RightAnswers()))
    ]
    return {
        "onOwn": len(lit) - len(with_ai),
        "mostlyAfterAskingAi": [str(titles.get(unit_id) or unit_id) for unit_id in with_ai],
    }


def build_bedrock_report_input(payload: dict[str, Any]) -> dict[str, Any]:
    """Build compact structured input for report generation."""
    student = payload.get("student", {})
    week = payload.get("week", {})
    metrics = payload.get("metrics", {})
    source_counts = payload.get("sourceCounts", {})

    weak_topics = [
        {
            "topic": str(topic.get("topic", "")),
            "count": int(topic.get("count", 0) or 0),
        }
        for topic in payload.get("weakTopics", [])[:_MAX_REPORT_WEAK_TOPICS]
        if topic.get("topic")
    ]
    activities = [
        {
            "type": str(activity.get("type", "")),
            "title": str(activity.get("title", "")),
            "summary": _truncate_activity_summary(activity.get("summary", "")),
            "subject": activity.get("subject"),
            "createdAt": activity.get("createdAt"),
        }
        for activity in payload.get("activities", [])[:_MAX_REPORT_ACTIVITIES]
    ]

    answered = payload.get("answeredRight") or {}
    stars = payload.get("starsLit") or {}
    return {
        "language": _report_locale(payload),
        "student": {
            "name": student.get("name") or "Student",
            "grade": student.get("grade"),
        },
        "week": {
            "start": week.get("start"),
            "end": week.get("end"),
        },
        "metrics": {
            "questionsAsked": int(metrics.get("questionsAsked", 0) or 0),
            "aiResolved": int(metrics.get("aiResolved", 0) or 0),
            "teacherHelpRequests": int(metrics.get("teacherHelpRequests", 0) or 0),
            "practiceLessonsCompleted": int(metrics.get("practiceLessonsCompleted", 0) or 0),
            "mistakesLogged": int(metrics.get("mistakesLogged", 0) or 0),
        },
        "weakTopics": weak_topics,
        "sourceCounts": {
            "questions": int(source_counts.get("questions", 0) or 0),
            "practiceProgress": int(source_counts.get("practiceProgress", 0) or 0),
            "mistakes": int(source_counts.get("mistakes", 0) or 0),
            "conversations": int(source_counts.get("conversations", 0) or 0),
        },
        "answeredRight": {
            "onOwn": _count(answered, "onOwn"),
            "afterAskingAi": _count(answered, "afterAskingAi"),
        },
        "starsLit": {
            "onOwn": _count(stars, "onOwn"),
            "mostlyAfterAskingAi": _star_titles(stars),
        },
        "activities": activities,
    }


def _report_locale(payload: Mapping[str, Any]) -> str:
    """The language a report is written in: the parent's, as the payload says (#450)."""
    locale = payload.get("locale")
    return locale if locale in locale_service.SUPPORTED_LOCALES else locale_service.DEFAULT_LOCALE


def _count(values: Mapping[str, Any], key: str) -> int:
    return int(values.get(key, 0) or 0)


def _star_titles(stars: Mapping[str, Any]) -> list[str]:
    """The stars lit mostly after asking AI, by name; all of them, they are few."""
    return [str(title) for title in stars.get("mostlyAfterAskingAi") or [] if title]


def parse_generated_report_json(raw_text: str) -> dict[str, Any]:
    """Parse and validate strict report JSON generated for parents."""
    try:
        parsed = json.loads(raw_text.strip())
    except json.JSONDecodeError as exc:
        raise ValueError("generated report must be strict JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("generated report JSON must be an object")

    content = {
        "summary": _required_string(parsed, "summary"),
        "strengths": _required_string_list(parsed, "strengths"),
        "weakTopics": _required_weak_topic_list(parsed, "weakTopics"),
        "recommendations": _required_string_list(parsed, "recommendations"),
        "teacherNote": _optional_string(parsed.get("teacherNote")),
    }
    _validate_parent_safe_content(content)
    return content


def weekly_report_request(payload: dict[str, Any]) -> dict[str, Any]:
    """What the model is asked for a report: `model_call.call`'s arguments but the deadline."""
    report_input = build_bedrock_report_input(payload)
    return {
        "system": _REPORT_SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": json.dumps(report_input, separators=(",", ":"), ensure_ascii=False),
            }
        ],
        "tool": REPORT_TOOL,
        "max_tokens": min(config.settings().bedrock_max_tokens, REPORT_MAX_OUTPUT_TOKENS),
        "temperature": REPORT_TEMPERATURE,
    }


class AllowanceExhausted(Exception):
    """The student's week cannot hold the report's model call: no report this week (#557)."""


class AllowanceUnavailable(RuntimeError):
    """The student's allowance could not be read or reserved: the report failed, and may be retried."""


def generate_weekly_report_content(
    payload: dict[str, Any],
    *,
    admission: model_call.AdmissionHook | None = None,
    clock: Callable[[], float] = monotonic,
) -> dict[str, Any]:
    """Generate parent-facing weekly report content with deterministic fallback.

    One model call (#438). A production report is asked with the admission hook
    of the student's allowance (`generate_and_send_weekly_report`, #557); the
    probe asks without one. Raises `AllowanceExhausted` when the hook finds the
    week cannot hold the call, `AllowanceUnavailable` when it cannot tell.
    Whatever else keeps it from giving a report the parser accepts (not sent,
    paid but unusable, a tool input the parser refuses, anything raised) ends
    in the deterministic report instead.
    """
    return _generate(payload, admission=admission, clock=clock)[0]


def _generate(
    payload: dict[str, Any],
    *,
    admission: model_call.AdmissionHook | None,
    clock: Callable[[], float],
) -> tuple[dict[str, Any], model_call.Usage | None]:
    """The report's content, and what its model call was paid, if it was."""
    try:
        result = model_call.call(
            **weekly_report_request(payload),
            deadline=clock() + REPORT_DEADLINE_SECONDS,
            admission=admission,
            clock=clock,
        )
    except model_call.NotInstalled:
        raise
    except Exception as exc:
        return _report_fallback(payload, type(exc).__name__), None
    if isinstance(result, model_call.NotSent):
        if result.category == ALLOWANCE_EXHAUSTED:
            raise AllowanceExhausted()
        if result.category == ALLOWANCE_UNAVAILABLE:
            raise AllowanceUnavailable(result.detail or ALLOWANCE_UNAVAILABLE)
        return _report_fallback(payload, result.category), None
    _log_report_usage(result.usage)
    if isinstance(result, model_call.PaidUnusable):
        return _report_fallback(payload, result.category), result.usage
    try:
        return parse_generated_report_json(result.tool_input), result.usage
    except ValueError as exc:
        return _report_fallback(payload, type(exc).__name__), result.usage


def _report_fallback(payload: dict[str, Any], failure: str) -> dict[str, Any]:
    logger.warning("Weekly report generation fallback used after %s", failure)
    return build_deterministic_report_fallback(payload)


# ── The student's allowance a report is charged to (#557) ─────────────────────

# What the report's admission hook refuses under: the week cannot hold the
# call, or the allowance could not say.
ALLOWANCE_EXHAUSTED = "allowance_exhausted"
ALLOWANCE_UNAVAILABLE = "allowance_unavailable"

# A report's `status` when the student's week could not hold its model call
# (#557): no report, no email, and nothing for recovery to retry.
STATUS_SKIPPED_ALLOWANCE = "skipped_allowance"


class ReportAllowance:
    """One report's model call, charged to its student's weekly allowance (#557).

    As an Ask answer is: the admission hook reserves the counted input tokens
    and the output limit in the week the report is generated in (the new week:
    the report goes out on Monday for the week before); the reply's usage
    evidence is observed as soon as it is back, and finalized once the report
    is stored. The deterministic report a paid but unusable reply ends in is
    still a stored report, so that reply is charged as well. A reply not stored
    is given back, its provider cost kept; a call reserved but never paid is
    released at the reservation's ceiling. Each call is its own effect, so a
    retried report is charged again, and every parent's report is charged.

    Settling the charge after the report is decided never fails the report: a
    failure is logged, and the reservation is left for the week to end.
    """

    def __init__(self, student_id: str, report_id: str, *, observed_at: datetime) -> None:
        self.student_id = student_id
        # One effect per model call: a retry, or another parent's report, is a call of its own.
        self.effect_id = hashlib.sha256(
            b"stoa.weekly-report.allowance-effect.v1\x00"
            + f"{report_id}\x00{uuid.uuid4().hex}".encode()
        ).hexdigest()
        self._observed_at = observed_at
        self._paid: model_call.Usage | None = None

    def admission(self, input_tokens: int, max_output_tokens: int) -> model_call.Admit | model_call.Refuse:
        """The admission hook: reserve the call in the student's week, under the plan they are on now."""
        try:
            entitlement = entitlement_service.resolve_student_entitlement(
                self.student_id, settings=config.settings()
            )
            plan_id = str(entitlement.get("effectivePlan") or "free_trial")
            version = allowance_service.week_allowance_version(
                beneficiary_id=self.student_id,
                plan_id=plan_id,
                observed_at=self._observed_at,
            )
            fence = account_deletion_repo.require_active_account_fence(self.student_id)
            reservation = allowance_service.reserve_token_allowance(
                beneficiary_id=self.student_id,
                effect_id=self.effect_id,
                plan_id=plan_id,
                allowance_version=version,
                input_tokens=input_tokens,
                max_output_tokens=max_output_tokens,
                observed_at=self._observed_at,
                account_fence_generation=int(fence["generation"]),
            )
        except Exception as exc:  # noqa: BLE001 - an allowance that cannot be read cannot admit
            return model_call.Refuse(ALLOWANCE_UNAVAILABLE, detail=type(exc).__name__)
        if reservation.disposition is allowance_repo.ReservationDisposition.LIMIT_EXCEEDED:
            return model_call.Refuse(ALLOWANCE_EXHAUSTED)
        if reservation.disposition not in {
            allowance_repo.ReservationDisposition.ADMITTED,
            allowance_repo.ReservationDisposition.REPLAYED,
        }:
            return model_call.Refuse(
                ALLOWANCE_UNAVAILABLE, detail=f"reserve:{reservation.disposition.value}"
            )
        return model_call.Admit()

    def observe(self, usage: model_call.Usage | None) -> None:
        """Record what the reply cost; a call not paid for is released at once."""
        if usage is None:
            self.release()
            return
        evidence = usage.evidence(effect_id=self.effect_id)
        try:
            observed = allowance_service.record_provider_usage(
                beneficiary_id=self.student_id,
                effect_id=self.effect_id,
                provider_request_id=evidence.provider_request_id_digest,
                model_id=evidence.model_id_digest,
                input_tokens=evidence.input_tokens,
                output_tokens=evidence.output_tokens,
                cache_write_input_tokens=evidence.cache_write_input_tokens,
                cache_read_input_tokens=evidence.cache_read_input_tokens,
            )
            disposition = observed.disposition
        except Exception as exc:  # noqa: BLE001 - the report is not lost over its charge
            disposition = type(exc).__name__
        if disposition in {
            allowance_repo.ProviderUsageDisposition.RECORDED,
            allowance_repo.ProviderUsageDisposition.REPLAYED,
        }:
            self._paid = usage
            return
        self._log_unsettled("observe", disposition)
        # The cost could not be recorded: give the reservation back at its ceiling.
        self.release()

    def finalize(self) -> None:
        """Charge what was observed, once the report is stored."""
        if self._paid is None:
            return
        try:
            finalized = allowance_service.finalize_token_allowance(
                beneficiary_id=self.student_id,
                effect_id=self.effect_id,
                technical_validation_passed=True,
                safety_check_passed=True,
                durable_result_stored=True,
                stable_replay_readable=True,
            )
            disposition = finalized.disposition
        except Exception as exc:  # noqa: BLE001
            disposition = type(exc).__name__
        if disposition not in {
            allowance_repo.FinalizationDisposition.FINALIZED,
            allowance_repo.FinalizationDisposition.REPLAYED,
        }:
            self._log_unsettled("finalize", disposition)

    def release(self) -> None:
        """Give back what this call reserved, when no report was stored on it.

        A reply already observed keeps its provider cost; a call never paid has
        its cost recorded at the reservation's ceiling. Nothing reserved is
        nothing to give back.
        """
        try:
            released = allowance_service.release_unknown_cost_allowance(
                beneficiary_id=self.student_id, effect_id=self.effect_id
            )
            disposition = released.disposition
        except Exception as exc:  # noqa: BLE001
            disposition = type(exc).__name__
        if disposition not in {
            allowance_repo.ReleaseDisposition.RELEASED,
            allowance_repo.ReleaseDisposition.NOTHING_RESERVED,
            allowance_repo.ReleaseDisposition.ALREADY_SETTLED,
        }:
            self._log_unsettled("release", disposition)

    def _log_unsettled(self, stage: str, disposition: object) -> None:
        logger.warning(
            "Weekly report allowance not settled stage=%s disposition=%s student_id=%s",
            stage,
            getattr(disposition, "value", disposition),
            self.student_id,
        )


def generate_and_send_weekly_report(
    payload: dict[str, Any],
    *,
    now: datetime | None = None,
    clock: Callable[[], float] = monotonic,
) -> dict[str, Any]:
    """Generate one report on the student's allowance, then store and send it (#557).

    Raises `AllowanceExhausted` when the student's week cannot hold the model
    call: no model call, no deterministic report, nothing stored. Raises
    `AllowanceUnavailable`, or whatever storing raised, when the report failed.
    """
    student_id = str((payload.get("student") or {}).get("id") or "")
    report_id = _report_id(
        str((payload.get("parent") or {}).get("id") or ""),
        student_id,
        str((payload.get("week") or {}).get("start") or ""),
    )
    allowance = ReportAllowance(
        student_id, report_id, observed_at=now or datetime.now(timezone.utc)
    )
    content, usage = _generate(payload, admission=allowance.admission, clock=clock)
    allowance.observe(usage)
    try:
        stored = store_and_send_weekly_report(payload, content, now=now)
    except Exception:
        allowance.release()
        raise
    allowance.finalize()
    return stored


def _log_report_usage(usage: model_call.Usage) -> None:
    """What one report's model call was paid, and who pays it (`cost_class`)."""
    logger.info(
        "Weekly report model call paid input_tokens=%s output_tokens=%s "
        "cache_write_input_tokens=%s cache_read_input_tokens=%s cost_class=%s",
        usage.input_tokens,
        usage.output_tokens,
        usage.cache_write_input_tokens,
        usage.cache_read_input_tokens,
        usage.cost_class,
    )


def build_deterministic_report_fallback(payload: dict[str, Any]) -> dict[str, Any]:
    """Create truthful parent-facing report content without model output.

    In the parent's language, as the model is asked to write (#450). Help from
    the AI is mentioned only for a week that had some.
    """
    locale = _report_locale(payload)

    def copy(key: str, **values: Any) -> str:
        return message_catalog.text(f"weekly_report.{key}", locale, **values)

    student = payload.get("student", {})
    metrics = payload.get("metrics", {})
    name = student.get("name") or message_catalog.text("email.weekly_report.student_fallback", locale)
    week_range = _week_range_text(payload.get("week", {}), locale)
    answered = payload.get("answeredRight") or {}
    on_own, with_ai = _count(answered, "onOwn"), _count(answered, "afterAskingAi")
    stars = payload.get("starsLit") or {}
    stars_with_ai = _star_titles(stars)
    stars_lit = _count(stars, "onOwn") + len(stars_with_ai)
    total_activity = on_own + with_ai + stars_lit + sum(
        _count(metrics, key)
        for key in (
            "questionsAsked",
            "practiceLessonsCompleted",
            "mistakesLogged",
            "teacherHelpRequests",
        )
    )

    if total_activity == 0:
        summary = copy("summary.no_activity", student=name, week=week_range)
        strengths = [copy("strength.none")]
        recommendations = [copy("recommendation.start_practising", student=name)]
    else:
        sentences = [
            copy(
                "summary.activity",
                week=week_range,
                student=name,
                questions=_count(metrics, "questionsAsked"),
                lessons=_count(metrics, "practiceLessonsCompleted"),
                mistakes=_count(metrics, "mistakesLogged"),
            )
        ]
        if with_ai:
            sentences.append(
                copy(
                    "summary.solved_split",
                    student=name,
                    total=on_own + with_ai,
                    on_own=on_own,
                    with_ai=with_ai,
                )
            )
        elif on_own:
            sentences.append(copy("summary.solved_on_own", student=name, on_own=on_own))
        if stars_lit:
            sentences.append(copy("summary.stars_lit", count=stars_lit))
        if stars_with_ai:
            sentences.append(copy("summary.stars_mostly_with_ai", stars=", ".join(stars_with_ai)))
        summary = " ".join(sentences)
        strengths = _fallback_strengths(metrics, copy)
        recommendations = _fallback_recommendations(
            payload, copy, name=name, stars_with_ai=stars_with_ai
        )

    weak_topics = [
        {
            "topic": str(topic.get("topic", "")),
            "note": copy("weak_topic.note", count=_count(topic, "count")),
        }
        for topic in payload.get("weakTopics", [])[:_MAX_REPORT_WEAK_TOPICS]
        if topic.get("topic")
    ]
    teacher_note = None
    if _count(metrics, "teacherHelpRequests") > 0:
        teacher_note = copy("teacher_note")

    return {
        "summary": summary,
        "strengths": strengths,
        "weakTopics": weak_topics,
        "recommendations": recommendations,
        "teacherNote": teacher_note,
    }


def store_and_send_weekly_report(
    payload: dict[str, Any],
    generated_content: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Store report artifacts and metadata before attempting parent email."""
    timestamp = _now_iso(now)
    report_item = build_weekly_report_record(payload, generated_content, generated_at=timestamp)
    fence = account_deletion_repo.require_active_account_fence(
        str(report_item["student_id"])
    )
    generation = int(fence["generation"])
    report_item["account_fence_generation"] = generation
    # Written for the parent by a job, so in the language the parent stored (#278).
    locale = locale_service.stored_locale(str(report_item["parent_id"]))
    html_report = render_weekly_report_html(payload, generated_content, locale=locale)
    json_report = build_weekly_report_json_artifact(payload, generated_content, report_item)

    report_artifact_service.write_fenced_report_artifacts(
        report_artifact_service.ReportArtifactKeys(
            json_key=report_item["json_s3_key"],
            html_key=report_item["html_s3_key"],
        ),
        json_report,
        html_report,
        owner_id=str(report_item["student_id"]),
        generation=generation,
        report_id=str(report_item["report_id"]),
    )
    report_repo.put_report(report_item)
    logger.info(
        "Weekly report stored report_id=%s parent_id=%s student_id=%s week_start=%s counts=%s",
        report_item["report_id"],
        report_item["parent_id"],
        report_item["student_id"],
        report_item["week_start"],
        report_item.get("source_counts", {}),
    )

    # The payload was judged before the AI call and the artifact writes; the
    # relationship can end, or the address change, in between. Judge again at
    # the last moment, and send to the address the parent has now.
    recipient = current_relationship.current_parent_recipient(
        str(report_item["parent_id"]),
        str(report_item["student_id"]),
    )
    if recipient.email is None:
        return _mark_report_email_failed(
            report_item,
            error_class=str(recipient.refusal),
            error_message=_WITHHELD_MESSAGES.get(str(recipient.refusal), "withheld"),
        )
    email = tell_report_ready(
        report_item,
        parent_email=recipient.email,
        generation=generation,
        html=html_report,
        locale=locale,
    )
    # A parent who unsubscribed still has the report in STOA; only the email
    # stops, and the report says so (#363).
    if email.outcome is notifications.EmailOutcome.UNSUBSCRIBED:
        return _mark_report_email_skipped(report_item)
    if email.outcome is not notifications.EmailOutcome.SENT:
        error = email.error or RuntimeError("email not sent")
        return _mark_report_email_failed(
            report_item,
            error_class=type(error).__name__,
            error_message=str(error)[:240],
        )

    sent_at = _now_iso()
    report_repo.update_report_status(
        report_item["report_id"],
        "email_sent",
        email_status="sent",
        email_sent_at=sent_at,
        updated_at=sent_at,
    )
    logger.info(
        "Weekly report email sent report_id=%s parent_id=%s student_id=%s week_start=%s",
        report_item["report_id"],
        report_item["parent_id"],
        report_item["student_id"],
        report_item["week_start"],
    )
    return {
        **report_item,
        "status": "email_sent",
        "email_status": "sent",
        "email_sent_at": sent_at,
        "updated_at": sent_at,
    }


_WITHHELD_MESSAGES = {
    current_relationship.RECIPIENT_RELATIONSHIP_REVOKED: (
        "Parent is no longer linked to the student"
    ),
    current_relationship.RECIPIENT_MISSING: "Parent has no email address",
}


def _mark_report_email_skipped(report_item: dict[str, Any]) -> dict[str, Any]:
    """Record that the parent switched the weekly report email off (#363)."""
    skipped_at = _now_iso()
    report_repo.update_report_status(
        report_item["report_id"],
        "generated",
        email_status=EMAIL_SKIPPED_PREFERENCE,
        email_skipped_at=skipped_at,
        updated_at=skipped_at,
    )
    logger.info(
        "Weekly report email skipped by preference report_id=%s parent_id=%s student_id=%s week_start=%s",
        report_item["report_id"],
        report_item["parent_id"],
        report_item["student_id"],
        report_item["week_start"],
    )
    return {
        **report_item,
        "status": "generated",
        "email_status": EMAIL_SKIPPED_PREFERENCE,
        "email_skipped_at": skipped_at,
        "updated_at": skipped_at,
    }


def _mark_report_email_failed(
    report_item: dict[str, Any],
    *,
    error_class: str,
    error_message: str,
) -> dict[str, Any]:
    failed_at = _now_iso()
    report_repo.update_report_status(
        report_item["report_id"],
        "email_failed",
        email_status="failed",
        email_failed_at=failed_at,
        email_error_class=error_class,
        email_error_message=error_message,
        updated_at=failed_at,
    )
    logger.warning(
        "Weekly report email failed report_id=%s parent_id=%s student_id=%s week_start=%s error_class=%s",
        report_item["report_id"],
        report_item["parent_id"],
        report_item["student_id"],
        report_item["week_start"],
        error_class,
    )
    return {
        **report_item,
        "status": "email_failed",
        "email_status": "failed",
        "email_failed_at": failed_at,
        "email_error_class": error_class,
        "email_error_message": error_message,
        "updated_at": failed_at,
    }


def build_weekly_report_record(
    payload: dict[str, Any],
    generated_content: dict[str, Any],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    parent = payload.get("parent", {})
    student = payload.get("student", {})
    week = payload.get("week", {})
    metrics = payload.get("metrics", {})
    source_counts = payload.get("sourceCounts", {})
    parent_id = parent.get("id", "")
    student_id = student.get("id", "")
    week_start = week.get("start", "")
    report_id = _report_id(parent_id, student_id, week_start)
    json_key, html_key = _report_artifact_keys(parent_id, student_id, week_start)
    recommendations = generated_content.get("recommendations", [])
    weak_topics = generated_content.get("weakTopics", [])
    timestamp = generated_at or _now_iso()

    return {
        "report_id": report_id,
        "parent_id": parent_id,
        "student_id": student_id,
        "parent_email": parent.get("email", ""),
        "student_name": student.get("name") or "Student",
        "week_start": week_start,
        "week_end": week.get("end", ""),
        "status": "generated",
        "email_status": "pending",
        "generated_at": timestamp,
        "created_at": timestamp,
        "updated_at": timestamp,
        "usage_count": int(metrics.get("questionsAsked", 0) or 0),
        "ai_resolved": int(metrics.get("aiResolved", 0) or 0),
        "teacher_resolved": int(metrics.get("teacherHelpRequests", 0) or 0),
        "practice_lessons_completed": int(metrics.get("practiceLessonsCompleted", 0) or 0),
        "mistakes_logged": int(metrics.get("mistakesLogged", 0) or 0),
        "stats": {
            "questionsAsked": int(metrics.get("questionsAsked", 0) or 0),
            "aiResolved": int(metrics.get("aiResolved", 0) or 0),
            "teacherHelpRequests": int(metrics.get("teacherHelpRequests", 0) or 0),
            "practiceLessonsCompleted": int(metrics.get("practiceLessonsCompleted", 0) or 0),
            "mistakesLogged": int(metrics.get("mistakesLogged", 0) or 0),
        },
        "summary": generated_content.get("summary", ""),
        "strengths": generated_content.get("strengths", []),
        "weak_topics": weak_topics,
        "weak_knowledge_points": [topic.get("topic", "") for topic in weak_topics if topic.get("topic")],
        "recommendations": "; ".join(recommendations) if isinstance(recommendations, list) else str(recommendations),
        "recommendation_items": recommendations if isinstance(recommendations, list) else [str(recommendations)],
        "teacher_note": generated_content.get("teacherNote"),
        "s3_key": html_key,
        "html_s3_key": html_key,
        "json_s3_key": json_key,
        "source_counts": {
            "questions": int(source_counts.get("questions", 0) or 0),
            "practiceProgress": int(source_counts.get("practiceProgress", 0) or 0),
            "mistakes": int(source_counts.get("mistakes", 0) or 0),
            "conversations": int(source_counts.get("conversations", 0) or 0),
        },
        "email_error_class": None,
        "email_error_message": None,
    }


def build_weekly_report_claim(
    parent_id: str,
    student_id: str,
    week_start: str,
    *,
    claimed_at: str | None = None,
) -> dict[str, Any]:
    json_key, html_key = _report_artifact_keys(parent_id, student_id, week_start)
    timestamp = claimed_at or _now_iso()
    return {
        "report_id": _report_id(parent_id, student_id, week_start),
        "parent_id": parent_id,
        "student_id": student_id,
        "week_start": week_start,
        "status": "generation_claimed",
        "email_status": "not_started",
        "created_at": timestamp,
        "updated_at": timestamp,
        "usage_count": 0,
        "ai_resolved": 0,
        "teacher_resolved": 0,
        "weak_knowledge_points": [],
        "recommendations": "",
        "s3_key": html_key,
        "html_s3_key": html_key,
        "json_s3_key": json_key,
    }


def build_weekly_report_json_artifact(
    payload: dict[str, Any],
    generated_content: dict[str, Any],
    report_item: dict[str, Any],
) -> dict[str, Any]:
    return {
        "report": {
            "reportId": report_item["report_id"],
            "parentId": report_item["parent_id"],
            "studentId": report_item["student_id"],
            "studentName": report_item["student_name"],
            "weekStart": report_item["week_start"],
            "weekEnd": report_item["week_end"],
            "generatedAt": report_item["generated_at"],
            "status": report_item["status"],
            "emailStatus": report_item["email_status"],
        },
        "stats": report_item["stats"],
        "content": generated_content,
        "sourceCounts": report_item["source_counts"],
        "activities": payload.get("activities", []),
    }


def render_weekly_report_html(
    payload: dict[str, Any],
    generated_content: dict[str, Any],
    *,
    locale: str | None = None,
) -> str:
    """The report a parent is emailed, in the STOA frame (#374), in `locale`.

    Only the frame is translated here; the summary, recommendations and topics are
    generated content and arrive in whatever language they were generated in. The
    unsubscribe line is added when the report is sent (#363), so the stored copy
    can be resent as it is.
    """
    lang = locale or locale_service.DEFAULT_LOCALE

    def copy(key: str, **values: Any) -> str:
        return message_catalog.text(f"email.weekly_report.{key}", lang, **values)

    student = payload.get("student", {})
    week = payload.get("week", {})
    student_name = student.get("name") or copy("student_fallback")
    recommendations = generated_content.get("recommendations", [])
    if not isinstance(recommendations, list):
        recommendations = [str(recommendations)]
    weak_topics = generated_content.get("weakTopics", [])
    teacher_note = generated_content.get("teacherNote")

    blocks: list[email_layout.Block] = [
        email_layout.Paragraph(copy("intro")),
        email_layout.LabeledParagraph(copy("week"), _week_range_text(week, lang)),
        email_layout.Paragraph(str(generated_content.get("summary", ""))),
    ]
    if recommendations:
        blocks += [
            email_layout.Subheading(copy("recommendations")),
            email_layout.Bullets(tuple(str(item) for item in recommendations)),
        ]
    if weak_topics:
        blocks += [
            email_layout.Subheading(copy("weak_topics")),
            email_layout.Items(
                tuple(
                    (str(topic.get("topic", "")), str(topic.get("note", "")))
                    for topic in weak_topics
                )
            ),
        ]
    if teacher_note:
        blocks.append(email_layout.LabeledParagraph(copy("teacher_note"), str(teacher_note)))
    blocks.append(
        email_layout.Action(
            copy("portal_link"),
            _parent_portal_link(student.get("id", ""), week.get("start", "")),
        )
    )
    return email_layout.render(
        subject=copy("subject", student=student_name),
        title=copy("title", student=student_name),
        greeting=email_layout.greeting((payload.get("parent") or {}).get("name"), lang),
        blocks=blocks,
        locale=lang,
        footer_reason=None,
    ).html


def _week_range_text(week: dict[str, Any], locale: str) -> str:
    start, end = week.get("start"), week.get("end")
    if start and end:
        return message_catalog.text(
            "email.weekly_report.week_range",
            locale,
            start=email_layout.format_date(start, locale),
            end=email_layout.format_date(end, locale),
        )
    return email_layout.format_date(start or end or "", locale)


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_in_window(value: Any, start: date, end: date) -> bool:
    parsed = _parse_iso_datetime(value)
    if parsed is None:
        return False
    start_dt = datetime.combine(start, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end, time.min, tzinfo=timezone.utc)
    return start_dt <= parsed < end_dt


def _get_linked_student_profile(parent_id: str, student_id: str) -> dict[str, Any]:
    """A report is private data, so the relationship is judged, not matched.

    The profile scan this replaced accepted any student carrying the parent's
    identifier, including one whose relationship had been revoked.
    """
    if not current_relationship.judge(parent_id, student_id).is_current:
        raise ValueError("student is not linked to parent")
    student = user_repo.get_user(student_id)
    if not student:
        raise ValueError("student is not linked to parent")
    return dict(student)


def _list_all_questions(student_id: str) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    last_key: dict[str, object] | None = None
    while True:
        result = question_repo.list_by_student(student_id, limit=500, last_key=last_key)
        questions.extend(
            row
            for row in _repository_items(result, label="student questions")
            if question_repo.is_question_record(row)
        )
        raw_last_key = result.get("LastEvaluatedKey")
        if raw_last_key is None:
            return questions
        if not isinstance(raw_last_key, Mapping):
            raise RuntimeError("student question pagination is malformed")
        last_key = dict(raw_last_key)


# One conversation list keeps at most this many conversations, and reads this
# many index rows a page.
_CONVERSATION_LIMIT = 100


def _list_conversations_for_student(student_id: str) -> list[dict[str, Any]]:
    """The student's conversations, newest first, with their help requests.

    The listing is `learning_session.list_for_student`. A list cut short is
    not shown in the report as such.
    """
    table = db_table.table()
    if not isinstance(table, _QueryTable):
        raise RuntimeError("report table query dependency is unavailable")

    listed = learning_session.list_for_student(
        student_id, limit=_CONVERSATION_LIMIT, page_size=_CONVERSATION_LIMIT
    )
    from stoa.services import help_requests

    # Whether a teacher was asked is the request's, not the conversation's (#189).
    return help_requests.with_requests(listed.items, student_id, table=table)


def _question_requested_teacher_help(question: dict[str, Any]) -> bool:
    return bool(question.get("teacher_help_requested")) or question.get("status") in {
        "escalated",
        "teacher_requested",
        "teacher_help",
    }


def _display_name(profile: dict[str, Any]) -> str:
    email = profile.get("email", "")
    return profile.get("name") or (email.split("@")[0] if email else "")


def _question_activity(question: dict[str, Any]) -> dict[str, Any]:
    created_at = question.get("created_at") or question.get("createdAt")
    return {
        "id": question.get("question_id") or question.get("id") or f"question-{created_at}",
        "type": "teacher_help" if _question_requested_teacher_help(question) else "question",
        "title": "Teacher help requested" if _question_requested_teacher_help(question) else "Question answered",
        "summary": question.get("summary") or question.get("prompt") or question.get("question") or "",
        "subject": question.get("subject"),
        "createdAt": created_at,
    }


def _practice_activity(lesson: student_evidence.Completion) -> dict[str, Any]:
    return {
        "id": lesson.lesson_id,
        "type": "practice",
        "title": "Practice lesson completed",
        "summary": lesson.title or lesson.topic_id or lesson.subject_id,
        "subject": lesson.subject_id or None,
        "createdAt": lesson.completed_at,
    }


def _mistake_activity(mistake: dict[str, Any]) -> dict[str, Any]:
    created_at = mistake.get("created_at") or mistake.get("createdAt")
    return {
        "id": mistake.get("attempt_id") or mistake.get("challenge_id") or f"mistake-{created_at}",
        "type": "practice_mistake",
        "title": "Practice mistake logged",
        "summary": mistake.get("topic_id") or mistake.get("subject_id") or "",
        "subject": mistake.get("subject_id"),
        "createdAt": created_at,
    }


def _conversation_activity(conversation: dict[str, Any]) -> dict[str, Any]:
    created_at = conversation.get("updated_at") or conversation.get("created_at")
    escalated = bool(conversation.get("escalated"))
    return {
        "id": conversation.get("conversation_id") or f"conversation-{created_at}",
        "type": "teacher_help" if escalated else "conversation",
        "title": "Teacher help requested" if escalated else "AI conversation",
        # A conversation's title and preview are the student's own words; the
        # report names what was asked about, never the question (#143).
        "summary": "",
        "subject": conversation.get("subject"),
        "createdAt": created_at,
    }


def _sort_activities(activities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        activities,
        key=lambda item: (
            _parse_iso_datetime(item.get("createdAt")) or datetime.min.replace(tzinfo=timezone.utc),
            item.get("id", ""),
        ),
        reverse=True,
    )


def _truncate_activity_summary(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) <= _MAX_ACTIVITY_SUMMARY_CHARS:
        return text
    return text[: _MAX_ACTIVITY_SUMMARY_CHARS - 3].rstrip() + "..."


def _now_iso(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _report_id(parent_id: str, student_id: str, week_start: str) -> str:
    return f"weekly-report-{parent_id}-{student_id}-{week_start}"


def _report_artifact_keys(parent_id: str, student_id: str, week_start: str) -> tuple[str, str]:
    keys = report_artifact_service.build_report_artifact_keys(
        parent_id,
        student_id,
        week_start,
    )
    return keys.json_key, keys.html_key


def _safe_s3_segment(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.=-]+", "-", str(value).strip())
    return safe.strip("-") or "unknown"


def _parent_portal_link(student_id: str, week_start: str) -> str:
    return (
        "https://app.stoaedu.ch/parent/children/"
        f"{_safe_s3_segment(student_id)}/reports/{_safe_s3_segment(week_start)}"
    )


def _required_string(parsed: dict[str, Any], key: str) -> str:
    value = parsed.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"generated report missing {key}")
    return value.strip()


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("generated report teacherNote must be a string or null")
    return value.strip() or None


def _required_string_list(parsed: dict[str, Any], key: str) -> list[str]:
    value = parsed.get(key)
    if not isinstance(value, list):
        raise ValueError(f"generated report {key} must be a list")
    if not value:
        raise ValueError(f"generated report {key} must not be empty")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"generated report {key} has invalid item")
        items.append(item.strip())
    return items


def _required_weak_topic_list(parsed: dict[str, Any], key: str) -> list[dict[str, str]]:
    value = parsed.get(key)
    if not isinstance(value, list):
        raise ValueError(f"generated report {key} must be a list")
    topics: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"generated report {key} has invalid item")
        topic = item.get("topic")
        note = item.get("note")
        if not isinstance(topic, str) or not topic.strip():
            raise ValueError(f"generated report {key} has invalid topic")
        if not isinstance(note, str):
            raise ValueError(f"generated report {key} has invalid note")
        topics.append({"topic": topic.strip(), "note": note.strip()})
    return topics


def _validate_parent_safe_content(content: dict[str, Any]) -> None:
    values: list[str] = []
    for value in content.values():
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    values.append(item)
                elif isinstance(item, dict):
                    values.extend(str(nested) for nested in item.values() if nested)
    if _FORBIDDEN_PARENT_COPY_RE.search(" ".join(values)):
        raise ValueError("generated report contains internal terms")


def _fallback_strengths(metrics: dict[str, Any], copy: Callable[..., str]) -> list[str]:
    strengths: list[str] = []
    if _count(metrics, "aiResolved") > 0:
        strengths.append(copy("strength.questions"))
    if _count(metrics, "practiceLessonsCompleted") > 0:
        strengths.append(copy("strength.practice"))
    if _count(metrics, "teacherHelpRequests") > 0:
        strengths.append(copy("strength.support"))
    return strengths or [copy("strength.activity")]


def _fallback_recommendations(
    payload: dict[str, Any],
    copy: Callable[..., str],
    *,
    name: str,
    stars_with_ai: list[str],
) -> list[str]:
    metrics = payload.get("metrics", {})
    topics = [topic.get("topic") for topic in payload.get("weakTopics", [])[:2] if topic.get("topic")]
    recommendations: list[str] = []
    if topics:
        recommendations.append(
            copy("recommendation.review_topics", topics=", ".join(str(topic) for topic in topics))
        )
    if stars_with_ai:
        recommendations.append(
            copy("recommendation.retry_without_ai", student=name, stars=", ".join(stars_with_ai))
        )
    if _count(metrics, "teacherHelpRequests") > 0:
        recommendations.append(copy("recommendation.teacher_follow_up"))
    if _count(metrics, "practiceLessonsCompleted") == 0:
        recommendations.append(copy("recommendation.schedule_practice"))
    return recommendations or [copy("recommendation.continue")]
