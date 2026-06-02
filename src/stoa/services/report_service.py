"""Weekly report aggregation helpers."""

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from boto3.dynamodb.conditions import Attr, Key

from stoa.db.dynamodb import get_table
from stoa.db.repositories import practice_repo, question_repo, user_repo


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
