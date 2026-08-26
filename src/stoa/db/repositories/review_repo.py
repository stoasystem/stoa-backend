"""Where each student's review schedule is kept.

One row per student per question, holding what the scheduler needs to decide
when that question comes back. Mistakes were until now recomputed by reading
every attempt a student had ever made; a card is written once per answer and
read by due date instead.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from boto3.dynamodb.conditions import Key

from stoa.db.dynamodb import get_table
from stoa.db.repositories import account_deletion_repo
from stoa.db.repositories.practice_repo import (
    _atomic_table,
    _get_item,
    _put_item,
    _query,
    _response_items,
    _write_generation,
    build_practice_write_transaction,
)
from stoa.services.review_scheduler import CardState, new_card

CARD_PREFIX = "CARD#"


def card_partition(student_id: str) -> str:
    return f"REVIEW#{student_id}"


def _decimal(value: float) -> Decimal:
    # DynamoDB refuses Python floats, and Decimal(float) would carry the
    # binary rounding error into storage.
    return Decimal(str(round(value, 6)))


def _float(value: Any, fallback: float) -> float:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return fallback


def as_int(value: Any, fallback: int = 0) -> int:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, Decimal):
        return int(value)
    if isinstance(value, int):
        return value
    return fallback


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def state_from_item(item: Mapping[str, Any], *, now: datetime) -> CardState:
    fallback = new_card(now=now)
    return CardState(
        stability=_float(item.get("stability"), fallback.stability),
        difficulty=_float(item.get("difficulty"), fallback.difficulty),
        due_at=_timestamp(item.get("due_at")) or now,
        last_reviewed_at=_timestamp(item.get("last_reviewed_at")),
        reps=as_int(item.get("reps")),
        lapses=as_int(item.get("lapses")),
    )


def item_from_state(
    student_id: str,
    challenge_id: str,
    state: CardState,
    *,
    lesson_id: str = "",
    subject_id: str = "",
    topic_id: str = "",
) -> dict[str, Any]:
    return {
        "PK": card_partition(student_id),
        "SK": f"{CARD_PREFIX}{challenge_id}",
        "entity_type": "review_card",
        "student_id": student_id,
        "user_id": student_id,
        "challenge_id": challenge_id,
        "lesson_id": lesson_id,
        "subject_id": subject_id,
        "topic_id": topic_id,
        "stability": _decimal(state.stability),
        "difficulty": _decimal(state.difficulty),
        "due_at": state.due_at.astimezone(timezone.utc).isoformat(),
        "last_reviewed_at": (
            state.last_reviewed_at.astimezone(timezone.utc).isoformat()
            if state.last_reviewed_at
            else ""
        ),
        "reps": state.reps,
        "lapses": state.lapses,
    }


def get_card(student_id: str, challenge_id: str, *, table: Any | None = None) -> dict[str, Any] | None:
    target = table or get_table()
    response = _get_item(
        target,
        Key={"PK": card_partition(student_id), "SK": f"{CARD_PREFIX}{challenge_id}"},
    )
    item = response.get("Item")
    return dict(item) if isinstance(item, Mapping) else None


def list_cards(student_id: str, *, table: Any | None = None) -> list[dict[str, Any]]:
    target = table or get_table()
    response = _query(
        target,
        KeyConditionExpression=(
            Key("PK").eq(card_partition(student_id)) & Key("SK").begins_with(CARD_PREFIX)
        ),
    )
    return _response_items(response.get("Items", []))


def list_due_cards(
    student_id: str, *, now: datetime, limit: int = 20, table: Any | None = None
) -> list[dict[str, Any]]:
    """Cards whose time has come, soonest first."""
    moment = now.astimezone(timezone.utc).isoformat()
    due = [card for card in list_cards(student_id, table=table) if str(card.get("due_at", "")) <= moment]
    due.sort(key=lambda card: str(card.get("due_at", "")))
    return due[:limit]


def save_card(
    student_id: str,
    challenge_id: str,
    state: CardState,
    *,
    lesson_id: str = "",
    subject_id: str = "",
    topic_id: str = "",
    account_fence_generation: int | None = None,
    table: Any | None = None,
) -> dict[str, Any]:
    """Write the schedule for one question behind the account fence."""
    target = table or get_table()
    generation = _write_generation(student_id, account_fence_generation, target)
    item = item_from_state(
        student_id,
        challenge_id,
        state,
        lesson_id=lesson_id,
        subject_id=subject_id,
        topic_id=topic_id,
    )
    existing = None
    if _atomic_table(target):
        existing = _get_item(
            target, Key={"PK": item["PK"], "SK": item["SK"]}, ConsistentRead=True
        ).get("Item")
    operations = build_practice_write_transaction(
        item=item,
        owner_id=student_id,
        generation=generation,
        mode="update" if existing else "put",
        updates={key: value for key, value in item.items() if key not in {"PK", "SK"}}
        if existing
        else None,
    )
    if _atomic_table(target):
        account_deletion_repo.transact(operations, table=target)
    else:
        _put_item(target, Item=operations[1]["Put"]["Item"])
    item.update(owner_id=student_id, account_fence_generation=generation)
    return item
