"""DynamoDB access patterns for practice content and student progress."""
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping
import uuid

from boto3.dynamodb.conditions import Key
from stoa.db.dynamodb import get_table
from stoa.db.repositories import account_deletion_repo


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

PRACTICE_PRIVATE_ROW_REGISTRY = frozenset(
    {"progress", "attempt", "legacy_mistake", "usage"}
)
PRACTICE_WRITER_REGISTRY = frozenset(
    {"mark_lesson_completed", "put_attempt", "record_attempt", "usage_counter"}
)
PRACTICE_PRIVATE_FIELDS = frozenset(
    {
        "student_id",
        "user_id",
        "lesson_id",
        "subject_id",
        "topic_id",
        "unit_id",
        "challenge_id",
        "student_answer",
        "submitted_answer",
        "correct",
        "result",
        "standard_answer",
        "explanation",
        "feedback",
        "correct_feedback",
        "incorrect_feedback",
        "next_challenge_id",
        "prompt",
        "options",
        "challenge_type",
        "metadata",
        "request_correlation_id",
        "question_id",
        "entitlement_snapshot",
        "parent_id",
        "actor_id",
    }
)
PRACTICE_TOMBSTONE_ALLOWLIST = frozenset(
    {
        "PK",
        "SK",
        "entity_type",
        "schema_version",
        "status",
        "action",
        "quantity",
        "count",
        "quota_period",
        "expires_at",
        "retention_basis",
        "owner_deletion_generation",
        "created_at",
        "deleted_at",
    }
)


@dataclass(frozen=True, slots=True)
class PracticePrivatePage:
    items: tuple[dict[str, Any], ...]
    cursor: dict[str, str] | None = None


def _atomic_table(table: Any) -> bool:
    return callable(getattr(table, "transact_account_deletion", None)) or bool(
        getattr(getattr(table, "meta", None), "client", None)
        and getattr(table, "name", None)
    )


def _write_generation(
    owner_id: str, generation: int | None, table: Any
) -> int:
    if generation is not None:
        if type(generation) is not int or generation <= 0:
            raise account_deletion_repo.AccountDeletionConflict(
                "invalid account fence generation"
            )
        return generation
    if _atomic_table(table):
        fence = account_deletion_repo.require_active_account_fence(owner_id, table=table)
        return int(fence["generation"])
    # Unit fakes without a transaction surface cannot model the permanent fence.
    return 1


def build_practice_write_transaction(
    *,
    item: Mapping[str, Any],
    owner_id: str,
    generation: int,
    mode: str = "put",
    updates: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build one same-table practice mutation behind the canonical fence."""
    stored = {
        **dict(item),
        "owner_id": owner_id,
        "account_fence_generation": generation,
    }
    operations = [account_deletion_repo.active_fence_condition(owner_id, generation)]
    if mode == "put":
        operations.append(
            {
                "Put": {
                    "Item": stored,
                    "ConditionExpression": (
                        "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                    ),
                }
            }
        )
        return operations
    if mode != "update" or not updates:
        raise ValueError("practice write mode is invalid")
    names = {f"#{key}": key for key in updates}
    values = {f":{key}": value for key, value in updates.items()}
    values[":owner"] = owner_id
    operations.append(
        {
            "Update": {
                "Key": {"PK": stored["PK"], "SK": stored["SK"]},
                "UpdateExpression": "SET "
                + ", ".join(f"#{key}=:{key}" for key in updates),
                "ConditionExpression": (
                    "attribute_exists(PK) AND attribute_exists(SK) AND owner_id=:owner"
                ),
                "ExpressionAttributeNames": names,
                "ExpressionAttributeValues": values,
            }
        }
    )
    return operations


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


def mark_lesson_completed(
    user_id: str,
    lesson: dict,
    *,
    account_fence_generation: int | None = None,
) -> dict[str, Any]:
    from datetime import datetime, timezone
    table = get_table()
    generation = _write_generation(user_id, account_fence_generation, table)
    item = {
        "PK": f"PROGRESS#{user_id}",
        "SK": f"LESSON#{lesson['lesson_id']}",
        "entity_type": "practice_progress",
        "student_id": user_id,
        "lesson_id": lesson["lesson_id"],
        "subject_id": lesson.get("subject_id", ""),
        "topic_id": lesson.get("topic_id", ""),
        "unit_id": lesson.get("unit_id", ""),
        "status": "completed",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    existing = None
    if _atomic_table(table):
        existing = table.get_item(
            Key={"PK": item["PK"], "SK": item["SK"]}, ConsistentRead=True
        ).get("Item")
    operations = build_practice_write_transaction(
        item=item,
        owner_id=user_id,
        generation=generation,
        mode="update" if existing else "put",
        updates={key: value for key, value in item.items() if key not in {"PK", "SK"}}
        if existing
        else None,
    )
    if _atomic_table(table):
        account_deletion_repo.transact(operations, table=table)
    else:
        table.put_item(Item=operations[1]["Put"]["Item"])
    item.update(
        owner_id=user_id,
        account_fence_generation=generation,
    )
    return item


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
    account_fence_generation: int | None = None,
) -> dict:
    """Immutably record every answer and return its durable owner receipt."""
    from stoa.services.practice_projection_service import (
        PRACTICE_SUBMITTED_ANSWER_SCHEMA_VERSION,
        normalize_submitted_answer,
    )

    normalized_answer = normalize_submitted_answer(submitted_answer)
    table = get_table()
    generation = _write_generation(student_id, account_fence_generation, table)
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
        "student_answer": normalized_answer,
        "submitted_answer": normalized_answer,
        "submitted_answer_schema_version": PRACTICE_SUBMITTED_ANSWER_SCHEMA_VERSION,
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
    operations = build_practice_write_transaction(
        item=item, owner_id=student_id, generation=generation
    )
    if _atomic_table(table):
        account_deletion_repo.transact(operations, table=table)
    else:
        table.put_item(
            Item=operations[1]["Put"]["Item"],
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
    item.update(owner_id=student_id, account_fence_generation=generation)
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


def scan_practice_private_rows(
    owner_id: str,
    *,
    cursor: Mapping[str, Any] | None = None,
    maximum_pages: int = 1,
    table: Any | None = None,
) -> PracticePrivatePage:
    """Strongly scan current and legacy practice/usage rows owned by one student."""
    target = table or get_table()
    if maximum_pages <= 0:
        raise account_deletion_repo.AccountDeletionConflict("invalid page bound")
    marker = _practice_cursor(cursor) if cursor is not None else None
    found: list[dict[str, Any]] = []
    for _ in range(maximum_pages):
        kwargs: dict[str, Any] = {"ConsistentRead": True}
        if marker is not None:
            kwargs["ExclusiveStartKey"] = marker
        response = target.scan(**kwargs)
        items = response.get("Items", [])
        if not isinstance(items, list):
            raise account_deletion_repo.AccountDeletionConflict(
                "malformed practice deletion page"
            )
        found.extend(
            dict(item)
            for item in items
            if isinstance(item, Mapping) and _practice_owned(item, owner_id)
        )
        raw_next = response.get("LastEvaluatedKey")
        if raw_next is None:
            return PracticePrivatePage(tuple(found))
        next_marker = _practice_cursor(raw_next)
        if next_marker == marker:
            raise account_deletion_repo.AccountDeletionConflict(
                "practice deletion cursor did not advance"
            )
        marker = next_marker
    return PracticePrivatePage(tuple(found), marker)


def scrub_practice_private_row(
    item: Mapping[str, Any],
    *,
    owner_id: str,
    generation: int,
    now_iso: str,
    table: Any | None = None,
) -> dict[str, Any]:
    """Replace practice content with a strict noncontent/TTL tombstone."""
    if not _practice_owned(item, owner_id):
        raise account_deletion_repo.AccountDeletionConflict("practice row owner changed")
    is_usage = str(item.get("PK") or "").startswith(("USAGE#", "USAGE_LEDGER#"))
    retained: dict[str, Any] = {
        "PK": item["PK"],
        "SK": item["SK"],
        "entity_type": "practice_accounting_tombstone" if is_usage else "practice_deletion_tombstone",
        "schema_version": "practice-deletion-tombstone.v1",
        "status": "deleted",
        "owner_deletion_generation": generation,
        "deleted_at": now_iso,
    }
    if is_usage and item.get("expires_at") and item.get("action"):
        retained.update(
            action=item.get("action"),
            quantity=int(item.get("quantity") or 0),
            count=int(item.get("count") or 0),
            quota_period=item.get("quota_period"),
            expires_at=int(item["expires_at"]),
            retention_basis=str(item.get("retention_basis") or "usage_accounting"),
        )
    if item.get("created_at"):
        retained["created_at"] = item["created_at"]
    tombstone = {
        key: value
        for key, value in retained.items()
        if key in PRACTICE_TOMBSTONE_ALLOWLIST and value is not None
    }
    target = table or get_table()
    hook = getattr(target, "replace_learning_tombstone", None)
    if callable(hook):
        hook(dict(item), tombstone, owner_id, generation)
    else:
        account_deletion_repo.transact(
            [
                account_deletion_repo.deletion_fence_condition(owner_id, generation),
                {
                    "Put": {
                        "Item": tombstone,
                        "ConditionExpression": (
                            "attribute_exists(PK) AND attribute_exists(SK)"
                        ),
                    }
                },
            ],
            table=target,
        )
    return tombstone


def _practice_cursor(value: Mapping[str, Any] | None) -> dict[str, str]:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"PK", "SK"}
        or any(not isinstance(value.get(key), str) or not value.get(key) for key in ("PK", "SK"))
    ):
        raise account_deletion_repo.AccountDeletionConflict(
            "invalid practice deletion cursor"
        )
    return {"PK": str(value["PK"]), "SK": str(value["SK"])}


def _practice_owned(item: Mapping[str, Any], owner_id: str) -> bool:
    pk = str(item.get("PK") or "")
    return owner_id in {item.get("student_id"), item.get("user_id"), item.get("owner_id")} or pk in {
        f"PROGRESS#{owner_id}",
        f"ATTEMPTS#{owner_id}",
        f"MISTAKES#{owner_id}",
        f"USAGE#{owner_id}",
        f"USAGE_LEDGER#{owner_id}",
    }
