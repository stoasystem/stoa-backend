"""Weekly report aggregation and generation helpers."""

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
import json
import logging
import re
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr, Key

from stoa.config import settings
from stoa.db.dynamodb import get_table
from stoa.db.repositories import practice_repo, question_repo, user_repo

logger = logging.getLogger(__name__)

_MAX_REPORT_WEAK_TOPICS = 5
_MAX_REPORT_ACTIVITIES = 6
_MAX_ACTIVITY_SUMMARY_CHARS = 160

_REPORT_SYSTEM_PROMPT = """You write weekly parent reports for STOA.

Use only the structured report input provided by the user. Do not invent activity.
Write warm, concise parent-facing English.

Return ONLY strict JSON with this exact shape:
{
  "summary": "2-3 sentences",
  "strengths": ["short bullet"],
  "weakTopics": [{"topic": "topic name", "note": "short note"}],
  "recommendations": ["short action"],
  "teacherNote": "optional short note or null"
}

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

    questions = _list_all_questions(student_id)
    progress = practice_repo.get_progress(student_id)
    mistakes = practice_repo.get_mistakes(student_id)
    conversations = _list_conversations_for_student(student_id)

    weekly_questions = [
        item for item in questions if _is_in_window(item.get("created_at") or item.get("createdAt"), start, end)
    ]
    weekly_progress = [
        item
        for item in progress
        if item.get("status") == "completed"
        and _is_in_window(item.get("completed_at") or item.get("updated_at"), start, end)
    ]
    weekly_mistakes = [
        item for item in mistakes if _is_in_window(item.get("created_at") or item.get("createdAt"), start, end)
    ]
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

    weak_topics = _rank_weak_topics(weekly_questions, weekly_mistakes)
    activities = _sort_activities(
        [
            *[_question_activity(item) for item in weekly_questions],
            *[_practice_activity(item) for item in weekly_progress],
            *[_mistake_activity(item) for item in weekly_mistakes],
            *[_conversation_activity(item) for item in weekly_conversations],
        ]
    )

    return {
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
        "weakTopics": weak_topics,
        "activities": activities,
        "sourceCounts": {
            "questions": len(weekly_questions),
            "practiceProgress": len(weekly_progress),
            "mistakes": len(weekly_mistakes),
            "conversations": len(weekly_conversations),
        },
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

    return {
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
        "activities": activities,
    }


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


def generate_weekly_report_content(
    payload: dict[str, Any],
    bedrock_client: Any | None = None,
) -> dict[str, Any]:
    """Generate parent-facing weekly report content with deterministic fallback."""
    report_input = build_bedrock_report_input(payload)
    client = bedrock_client or boto3.client("bedrock-runtime", region_name=settings.aws_region)
    body = json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": min(settings.bedrock_max_tokens, 1200),
            "temperature": 0.2,
            "system": _REPORT_SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": json.dumps(report_input, separators=(",", ":"), ensure_ascii=False),
                }
            ],
        }
    )

    try:
        response = client.invoke_model(modelId=settings.bedrock_model_id, body=body)
        result = json.loads(response["body"].read())
        raw_text = result["content"][0]["text"]
        return parse_generated_report_json(raw_text)
    except Exception as exc:
        logger.warning("Weekly report generation fallback used after %s", type(exc).__name__)
        return build_deterministic_report_fallback(payload)


def build_deterministic_report_fallback(payload: dict[str, Any]) -> dict[str, Any]:
    """Create truthful parent-facing report content without model output."""
    student = payload.get("student", {})
    week = payload.get("week", {})
    metrics = payload.get("metrics", {})
    name = student.get("name") or "your child"
    week_range = _week_range_label(week)
    total_activity = sum(
        int(metrics.get(key, 0) or 0)
        for key in (
            "questionsAsked",
            "practiceLessonsCompleted",
            "mistakesLogged",
            "teacherHelpRequests",
        )
    )

    if total_activity == 0:
        summary = f"No weekly learning activity was recorded for {name} during {week_range}."
        strengths = ["No specific strengths were recorded from this week's activity."]
        recommendations = ["Encourage one short practice session before the next weekly report."]
    else:
        summary = (
            f"During {week_range}, {name} asked {int(metrics.get('questionsAsked', 0) or 0)} "
            f"question(s), completed {int(metrics.get('practiceLessonsCompleted', 0) or 0)} "
            f"practice lesson(s), and logged {int(metrics.get('mistakesLogged', 0) or 0)} mistake(s)."
        )
        strengths = _fallback_strengths(metrics)
        recommendations = _fallback_recommendations(payload)

    weak_topics = [
        {
            "topic": str(topic.get("topic", "")),
            "note": f"Seen in {int(topic.get('count', 0) or 0)} weekly signal(s).",
        }
        for topic in payload.get("weakTopics", [])[:_MAX_REPORT_WEAK_TOPICS]
        if topic.get("topic")
    ]
    teacher_note = None
    if int(metrics.get("teacherHelpRequests", 0) or 0) > 0:
        teacher_note = "Teacher help was requested this week; review any follow-up from the teacher team."

    return {
        "summary": summary,
        "strengths": strengths,
        "weakTopics": weak_topics,
        "recommendations": recommendations,
        "teacherNote": teacher_note,
    }


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


def _scan_children_for_parent(parent_id: str) -> list[dict[str, Any]]:
    table = get_table()
    scan_kwargs: dict[str, Any] = {
        "FilterExpression": "#pid = :pid AND #role = :role",
        "ExpressionAttributeNames": {"#pid": "parent_id", "#role": "role"},
        "ExpressionAttributeValues": {":pid": parent_id, ":role": "student"},
    }
    children: list[dict[str, Any]] = []
    while True:
        result = table.scan(**scan_kwargs)
        children.extend(result.get("Items", []))
        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            return children
        scan_kwargs["ExclusiveStartKey"] = last_key


def _get_linked_student_profile(parent_id: str, student_id: str) -> dict[str, Any]:
    for child in _scan_children_for_parent(parent_id):
        if child.get("user_id") == student_id or child.get("id") == student_id:
            return child
    raise ValueError("student is not linked to parent")


def _list_all_questions(student_id: str) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    last_key = None
    while True:
        result = question_repo.list_by_student(student_id, limit=500, last_key=last_key)
        questions.extend(result.get("Items", []))
        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            return questions


def _list_conversations_for_student(student_id: str) -> list[dict[str, Any]]:
    table = get_table()
    result = table.query(
        IndexName="GSI-StudentId",
        KeyConditionExpression=Key("student_id").eq(student_id),
        FilterExpression=Attr("entity_type").eq("conversation"),
        Limit=100,
        ScanIndexForward=False,
    )
    return result.get("Items", [])


def _question_requested_teacher_help(question: dict[str, Any]) -> bool:
    return bool(question.get("teacher_help_requested")) or question.get("status") in {
        "escalated",
        "teacher_requested",
        "teacher_help",
    }


def _rank_weak_topics(
    questions: list[dict[str, Any]],
    mistakes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for question in questions:
        counter.update(topic for topic in question.get("knowledge_points", []) if topic)
        if question.get("subject"):
            counter[question["subject"]] += 1
    for mistake in mistakes:
        for key in ("topic_id", "subject_id"):
            if mistake.get(key):
                counter[mistake[key]] += 1
    return [
        {"topic": topic, "count": count}
        for topic, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


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


def _practice_activity(progress: dict[str, Any]) -> dict[str, Any]:
    created_at = progress.get("completed_at") or progress.get("updated_at")
    return {
        "id": progress.get("lesson_id") or f"practice-{created_at}",
        "type": "practice",
        "title": "Practice lesson completed",
        "summary": progress.get("lesson_title") or progress.get("topic_id") or progress.get("subject_id") or "",
        "subject": progress.get("subject_id"),
        "createdAt": created_at,
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
        "summary": conversation.get("last_message_preview") or conversation.get("title") or "",
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


def _week_range_label(week: dict[str, Any]) -> str:
    start = week.get("start") or "the selected week"
    end = week.get("end")
    return f"{start} to {end}" if end else str(start)


def _fallback_strengths(metrics: dict[str, Any]) -> list[str]:
    strengths: list[str] = []
    if int(metrics.get("aiResolved", 0) or 0) > 0:
        strengths.append("Independent question practice was recorded this week.")
    if int(metrics.get("practiceLessonsCompleted", 0) or 0) > 0:
        strengths.append("Practice lessons were completed this week.")
    if int(metrics.get("teacherHelpRequests", 0) or 0) > 0:
        strengths.append("Support was requested when additional help was needed.")
    return strengths or ["Learning activity was recorded this week."]


def _fallback_recommendations(payload: dict[str, Any]) -> list[str]:
    metrics = payload.get("metrics", {})
    topics = [topic.get("topic") for topic in payload.get("weakTopics", [])[:2] if topic.get("topic")]
    recommendations: list[str] = []
    if topics:
        recommendations.append(f"Review {', '.join(str(topic) for topic in topics)} in the next practice session.")
    if int(metrics.get("teacherHelpRequests", 0) or 0) > 0:
        recommendations.append("Check whether any teacher follow-up needs attention.")
    if int(metrics.get("practiceLessonsCompleted", 0) or 0) == 0:
        recommendations.append("Schedule one short practice lesson to keep momentum.")
    return recommendations or ["Continue with the next planned practice activity."]
