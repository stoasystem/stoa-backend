"""DynamoDB access patterns for practice content and student progress."""
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
import uuid

from boto3.dynamodb.conditions import Key
from stoa.db.dynamodb import get_table


CHALLENGE_POINTER_PK = "PRACTICE_CHALLENGE_LOOKUP"
CHALLENGE_POINTER_ENTITY = "practice_challenge_pointer"
_CHALLENGE_METADATA_FIELDS = {
    "PK",
    "SK",
    "challenge_content_hash",
    "challenge_version",
    "entity_type",
    "hint_non_derivability_decision",
}
_POINTER_FIELDS = {
    "PK",
    "SK",
    "entity_type",
    "challenge_id",
    "target_pk",
    "target_sk",
    "challenge_version",
    "challenge_content_hash",
}
_MAX_CHALLENGE_PAGES = 1000


def _canonical_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _canonical_json_value(child)
            for key, child in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_json_value(child) for child in value]
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return format(value.normalize(), "f")
    if isinstance(value, float):
        decimal = Decimal(str(value))
        if decimal == decimal.to_integral_value():
            return int(decimal)
        return format(decimal.normalize(), "f")
    return value


def canonical_challenge_content_hash(challenge: dict | Any) -> str:
    """Hash every challenge content field while excluding storage/approval metadata."""
    if not isinstance(challenge, dict):
        challenge = dict(challenge)
    content = {
        key: value
        for key, value in challenge.items()
        if key not in _CHALLENGE_METADATA_FIELDS
    }
    encoded = json.dumps(
        _canonical_json_value(content),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def version_challenge(challenge: dict[str, Any]) -> dict[str, Any]:
    """Return one canonical row with a content-derived immutable version."""
    canonical = dict(challenge)
    content_hash = canonical_challenge_content_hash(canonical)
    canonical["challenge_content_hash"] = content_hash
    canonical["challenge_version"] = f"sha256:{content_hash}"
    return canonical


def challenge_pointer(challenge: dict[str, Any]) -> dict[str, Any]:
    """Build an answer-free direct pointer to one exact canonical row."""
    return {
        "PK": CHALLENGE_POINTER_PK,
        "SK": f"CHALLENGE#{challenge['challenge_id']}",
        "entity_type": CHALLENGE_POINTER_ENTITY,
        "challenge_id": challenge["challenge_id"],
        "target_pk": challenge["PK"],
        "target_sk": challenge["SK"],
        "challenge_version": challenge["challenge_version"],
        "challenge_content_hash": challenge["challenge_content_hash"],
    }


def _valid_versioned_challenge(challenge: Any) -> bool:
    if not isinstance(challenge, dict):
        return False
    challenge_id = challenge.get("challenge_id")
    content_hash = challenge.get("challenge_content_hash")
    version = challenge.get("challenge_version")
    if not isinstance(challenge_id, str) or not challenge_id.strip():
        return False
    if not isinstance(content_hash, str) or len(content_hash) != 64:
        return False
    if version != f"sha256:{content_hash}":
        return False
    return canonical_challenge_content_hash(challenge) == content_hash


def _query_all_challenge_pages(table: Any, **query: Any) -> list[dict]:
    items: list[dict] = []
    previous_marker: dict[str, Any] | None = None
    for _page in range(_MAX_CHALLENGE_PAGES):
        response = table.query(**query)
        page_items = response.get("Items", [])
        if not isinstance(page_items, list):
            raise ValueError("malformed challenge pagination response")
        items.extend(page_items)
        marker = response.get("LastEvaluatedKey")
        if marker is None:
            break
        if not isinstance(marker, dict) or not marker or marker == previous_marker:
            raise ValueError("challenge pagination did not make progress")
        previous_marker = marker
        query["ExclusiveStartKey"] = marker
    else:
        raise ValueError("challenge pagination exceeded the bounded page limit")
    return items


def _validate_unique_challenges(items: list[dict]) -> list[dict]:
    identities: set[tuple[str, str]] = set()
    ids: set[str] = set()
    for item in items:
        if not _valid_versioned_challenge(item):
            raise ValueError("malformed versioned challenge row")
        challenge_id = item["challenge_id"]
        identity = (challenge_id, item["challenge_version"])
        if challenge_id in ids or identity in identities:
            raise ValueError("duplicate challenge identity")
        ids.add(challenge_id)
        identities.add(identity)
    return items


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
    items = _query_all_challenge_pages(
        table,
        KeyConditionExpression=(
            Key("PK").eq("PRACTICE") & Key("SK").begins_with(f"CHALLENGE#{lesson_id}#")
        )
    )
    return sorted(_validate_unique_challenges(items), key=lambda x: x.get("order", 0))


def get_all_challenges(
    lesson_id: str | None = None,
    subject_id: str | None = None,
    topic_id: str | None = None,
) -> list[dict]:
    table = get_table()
    prefix = f"CHALLENGE#{lesson_id}#" if lesson_id else "CHALLENGE#"
    items = _query_all_challenge_pages(
        table,
        KeyConditionExpression=(
            Key("PK").eq("PRACTICE") & Key("SK").begins_with(prefix)
        )
    )
    items = _validate_unique_challenges(items)
    if subject_id:
        items = [i for i in items if i.get("subject_id") == subject_id]
    if topic_id:
        items = [i for i in items if i.get("topic_id") == topic_id]
    return sorted(items, key=lambda x: (x.get("lesson_id", ""), x.get("order", 0)))


def get_challenge(challenge_id: str) -> dict | None:
    """Resolve one opaque ID through an answer-free pointer and exact row key."""
    if not isinstance(challenge_id, str) or not challenge_id.strip():
        return None
    table = get_table()
    pointer = table.get_item(
        Key={"PK": CHALLENGE_POINTER_PK, "SK": f"CHALLENGE#{challenge_id}"}
    ).get("Item")
    if not isinstance(pointer, dict) or set(pointer) != _POINTER_FIELDS:
        return None
    if (
        pointer.get("PK") != CHALLENGE_POINTER_PK
        or pointer.get("SK") != f"CHALLENGE#{challenge_id}"
        or pointer.get("entity_type") != CHALLENGE_POINTER_ENTITY
        or pointer.get("challenge_id") != challenge_id
        or pointer.get("target_pk") != "PRACTICE"
        or not isinstance(pointer.get("target_sk"), str)
        or not pointer["target_sk"].startswith("CHALLENGE#")
    ):
        return None
    challenge = table.get_item(
        Key={"PK": pointer["target_pk"], "SK": pointer["target_sk"]}
    ).get("Item")
    if not _valid_versioned_challenge(challenge):
        return None
    if (
        challenge.get("PK") != pointer["target_pk"]
        or challenge.get("SK") != pointer["target_sk"]
        or challenge.get("challenge_id") != challenge_id
        or challenge.get("challenge_version") != pointer.get("challenge_version")
        or challenge.get("challenge_content_hash")
        != pointer.get("challenge_content_hash")
    ):
        return None
    return challenge


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
    unit_id: str = "",
    challenge_version: str = "",
    challenge_content_hash: str = "",
    standard_answer: Any = None,
    explanation: str = "",
    correct_feedback: str = "",
    incorrect_feedback: str = "",
    feedback: str = "",
    next_challenge_id: str | None = None,
    prompt: str = "",
    options: list[Any] | None = None,
    challenge_type: str = "",
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
        "unit_id": unit_id,
        "student_answer": submitted_answer,
        "submitted_answer": submitted_answer,
        "correct": bool(correct),
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
    }
    snapshot_fields = {
        "challenge_version": challenge_version,
        "challenge_content_hash": challenge_content_hash,
        "standard_answer": standard_answer,
        "explanation": explanation,
        "correct_feedback": correct_feedback,
        "incorrect_feedback": incorrect_feedback,
        "feedback": feedback,
        "next_challenge_id": next_challenge_id,
        "prompt": prompt,
        "options": options,
        "challenge_type": challenge_type,
    }
    if any(value not in (None, "", []) for value in snapshot_fields.values()):
        item.update(snapshot_fields)
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
