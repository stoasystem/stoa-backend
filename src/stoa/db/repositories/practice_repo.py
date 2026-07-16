"""DynamoDB access patterns for practice content and student progress."""
from datetime import datetime, timezone
from typing import Any
import uuid

from boto3.dynamodb.conditions import Key, Attr
from stoa.db.dynamodb import get_table


# ── Content read ──────────────────────────────────────────────────────────

def get_subjects() -> list[dict]:
    table = get_table()
    resp = table.query(
        KeyConditionExpression=(
            Key("PK").eq("PRACTICE") & Key("SK").begins_with("SUBJECT#")
        )
    )
    return resp.get("Items", [])


def get_topics(subject_id: str | None = None) -> list[dict]:
    table = get_table()
    resp = table.query(
        KeyConditionExpression=(
            Key("PK").eq("PRACTICE") & Key("SK").begins_with("TOPIC#")
        )
    )
    items = resp.get("Items", [])
    if subject_id:
        items = [i for i in items if i.get("subject_id") == subject_id]
    return items


def get_topic(topic_id: str) -> dict | None:
    table = get_table()
    resp = table.get_item(Key={"PK": "PRACTICE", "SK": f"TOPIC#{topic_id}"})
    return resp.get("Item")


def get_lessons(topic_id: str | None = None, unit_id: str | None = None) -> list[dict]:
    table = get_table()
    resp = table.query(
        KeyConditionExpression=(
            Key("PK").eq("PRACTICE") & Key("SK").begins_with("LESSON#")
        )
    )
    items = resp.get("Items", [])
    if topic_id:
        items = [i for i in items if i.get("topic_id") == topic_id]
    if unit_id:
        items = [i for i in items if i.get("unit_id") == unit_id]
    return items


def get_lesson(lesson_id: str) -> dict | None:
    table = get_table()
    resp = table.get_item(Key={"PK": "PRACTICE", "SK": f"LESSON#{lesson_id}"})
    return resp.get("Item")


def get_challenges(lesson_id: str) -> list[dict]:
    table = get_table()
    resp = table.query(
        KeyConditionExpression=(
            Key("PK").eq("PRACTICE") & Key("SK").begins_with(f"CHALLENGE#{lesson_id}#")
        )
    )
    items = resp.get("Items", [])
    return sorted(items, key=lambda x: x.get("order", 0))


def get_all_challenges(
    lesson_id: str | None = None,
    subject_id: str | None = None,
    topic_id: str | None = None,
) -> list[dict]:
    table = get_table()
    prefix = f"CHALLENGE#{lesson_id}#" if lesson_id else "CHALLENGE#"
    resp = table.query(
        KeyConditionExpression=(
            Key("PK").eq("PRACTICE") & Key("SK").begins_with(prefix)
        )
    )
    items = resp.get("Items", [])
    if subject_id:
        items = [i for i in items if i.get("subject_id") == subject_id]
    if topic_id:
        items = [i for i in items if i.get("topic_id") == topic_id]
    return sorted(items, key=lambda x: (x.get("lesson_id", ""), x.get("order", 0)))


def get_challenge(challenge_id: str) -> dict | None:
    """Look up a challenge by its full SK (CHALLENGE#{lesson_id}#{challenge_id})
    or by scanning for challenge_id attribute."""
    table = get_table()
    # Try direct lookup with known SK pattern first
    for prefix in ["CHALLENGE#"]:
        resp = table.query(
            KeyConditionExpression=(
                Key("PK").eq("PRACTICE") & Key("SK").begins_with(prefix)
            ),
            FilterExpression=Attr("challenge_id").eq(challenge_id),
        )
        items = resp.get("Items", [])
        if items:
            return items[0]
    return None


def get_units(topic_id: str) -> list[dict]:
    table = get_table()
    resp = table.query(
        KeyConditionExpression=(
            Key("PK").eq("PRACTICE") & Key("SK").begins_with("UNIT#")
        )
    )
    items = resp.get("Items", [])
    return [i for i in items if i.get("topic_id") == topic_id]


# ── Progress read / write ─────────────────────────────────────────────────

def get_progress(user_id: str, subject_id: str | None = None) -> list[dict]:
    table = get_table()
    resp = table.query(
        KeyConditionExpression=(
            Key("PK").eq(f"PROGRESS#{user_id}") & Key("SK").begins_with("LESSON#")
        )
    )
    items = resp.get("Items", [])
    if subject_id:
        items = [i for i in items if i.get("subject_id") == subject_id]
    return items


def mark_lesson_completed(user_id: str, lesson: dict) -> None:
    from datetime import datetime, timezone
    table = get_table()
    table.put_item(Item={
        "PK": f"PROGRESS#{user_id}",
        "SK": f"LESSON#{lesson['lesson_id']}",
        "lesson_id": lesson["lesson_id"],
        "subject_id": lesson.get("subject_id", ""),
        "topic_id": lesson.get("topic_id", ""),
        "unit_id": lesson.get("unit_id", ""),
        "status": "completed",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    })


def put_attempt(
    student_id: str,
    challenge_id: str,
    submitted_answer: Any,
    correct: bool,
    *,
    subject_id: str = "",
    lesson_id: str = "",
    topic_id: str = "",
    attempt_id: str | None = None,
    created_at: str | None = None,
) -> dict:
    """Immutably record every answer and return its durable owner receipt."""
    table = get_table()
    attempt_key = attempt_id or str(uuid.uuid4())
    item = {
        "PK": f"ATTEMPTS#{student_id}",
        "SK": f"ATTEMPT#{attempt_key}",
        "attempt_id": attempt_key,
        "student_id": student_id,
        "user_id": student_id,
        "challenge_id": challenge_id,
        "subject_id": subject_id,
        "topic_id": topic_id,
        "lesson_id": lesson_id,
        "student_answer": submitted_answer,
        "submitted_answer": submitted_answer,
        "correct": bool(correct),
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
    }
    table.put_item(
        Item=item,
        ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
    )
    return item


def get_attempt(student_id: str, attempt_id: str) -> dict | None:
    """Load one attempt through its owner-scoped primary key."""
    table = get_table()
    response = table.get_item(
        Key={"PK": f"ATTEMPTS#{student_id}", "SK": f"ATTEMPT#{attempt_id}"}
    )
    return response.get("Item")


def list_student_attempts(student_id: str, *, correct: bool | None = None) -> list[dict]:
    table = get_table()
    response = table.query(
        KeyConditionExpression=(
            Key("PK").eq(f"ATTEMPTS#{student_id}") & Key("SK").begins_with("ATTEMPT#")
        )
    )
    items = response.get("Items", [])
    if correct is not None:
        items = [item for item in items if bool(item.get("correct")) is correct]
    return items


def record_attempt(
    user_id: str,
    challenge_id: str,
    correct: bool,
    subject_id: str = "",
    lesson_id: str = "",
    topic_id: str = "",
    attempt_id: str | None = None,
    student_answer: Any = "",
) -> dict:
    """Compatibility wrapper for callers migrating to the all-attempt contract."""
    return put_attempt(
        user_id,
        challenge_id,
        student_answer,
        correct,
        subject_id=subject_id,
        lesson_id=lesson_id,
        topic_id=topic_id,
        attempt_id=attempt_id,
    )


def get_mistakes(user_id: str) -> list[dict]:
    attempts = list_student_attempts(user_id, correct=False)
    table = get_table()
    legacy = table.query(
        KeyConditionExpression=(
            Key("PK").eq(f"MISTAKES#{user_id}") & Key("SK").begins_with("ATTEMPT#")
        )
    ).get("Items", [])
    known_attempt_ids = {item.get("attempt_id") for item in attempts}
    attempts.extend(
        item
        for item in legacy
        if (item.get("attempt_id") or str(item.get("SK", "")).removeprefix("ATTEMPT#"))
        not in known_attempt_ids
    )
    return attempts
