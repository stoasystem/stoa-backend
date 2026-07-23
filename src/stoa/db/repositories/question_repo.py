"""DynamoDB access patterns for the Question entity."""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, runtime_checkable

from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key
from stoa.db.repositories import account_deletion_repo
from stoa.db.dynamodb import get_table


type QuestionItem = dict[str, object]

_TAKEOVER_CLAIM_DOMAIN = b"stoa.teacher.takeover.claim.v1"
_TAKEOVER_SESSION_DOMAIN = b"stoa.teacher.takeover.session.v1"


class TeacherTakeoverDisposition(StrEnum):
    """Closed, identity-safe outcomes from the teacher takeover boundary."""

    CLAIMED = "claimed"
    REPLAYED = "replayed"
    ALREADY_CLAIMED = "already_claimed"
    RETRYABLE = "retryable"


@dataclass(frozen=True, slots=True)
class TeacherTakeoverResult:
    disposition: TeacherTakeoverDisposition
    question_id: str
    session_id: str | None = None
    question: QuestionItem | None = None
    session: QuestionItem | None = None


class QuestionMutationDisposition(StrEnum):
    """Identity-safe outcomes from the question state/version CAS boundary."""

    APPLIED = "applied"
    STALE = "stale"
    INVALID_TRANSITION = "invalid_transition"
    RETRYABLE = "retryable"


@dataclass(frozen=True, slots=True)
class QuestionMutationResult:
    disposition: QuestionMutationDisposition
    question_id: str
    question: QuestionItem | None = None


@runtime_checkable
class _GetTable(Protocol):
    def get_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _PutTable(Protocol):
    def put_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _QueryTable(Protocol):
    def query(self, **kwargs: object) -> object: ...


@runtime_checkable
class _UpdateTable(Protocol):
    def update_item(self, **kwargs: object) -> object: ...


def _table(candidate: object | None = None) -> object:
    return candidate or get_table()


def _get_item(table: object, **kwargs: object) -> QuestionItem:
    if not isinstance(table, _GetTable):
        raise account_deletion_repo.AccountDeletionConflict("question dependency unavailable")
    return _response(table.get_item(**kwargs))


def _put_item(table: object, **kwargs: object) -> object:
    if not isinstance(table, _PutTable):
        raise account_deletion_repo.AccountDeletionConflict("question dependency unavailable")
    return table.put_item(**kwargs)


def _query(table: object, **kwargs: object) -> QuestionItem:
    if not isinstance(table, _QueryTable):
        raise account_deletion_repo.AccountDeletionConflict("question dependency unavailable")
    return _response(table.query(**kwargs))


def _update_item(table: object, **kwargs: object) -> QuestionItem:
    if not isinstance(table, _UpdateTable):
        raise account_deletion_repo.AccountDeletionConflict("question dependency unavailable")
    result = table.update_item(**kwargs)
    return {} if result is None else _response(result)


def _response(value: object) -> QuestionItem:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise account_deletion_repo.AccountDeletionConflict("question dependency unavailable")
    return {key: item for key, item in value.items() if isinstance(key, str)}


def put_question(item: QuestionItem) -> None:
    table = _table()
    student_id = str(item.get("student_id") or "")
    fence = account_deletion_repo.require_active_account_fence(student_id, table=table)
    persisted = {**item, "account_fence_generation": int(fence["generation"])}
    account_deletion_repo.transact(
        [
            account_deletion_repo.active_fence_condition(
                student_id, int(fence["generation"])
            ),
            {
                "Put": {
                    "Item": question_item(persisted),
                    "ConditionExpression": (
                        "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                    ),
                }
            },
        ],
        table=table,
    )


def question_item(item: QuestionItem) -> QuestionItem:
    """Build the canonical question transaction item without persisting it."""
    return {"PK": f"QUESTION#{item['question_id']}", "SK": "META", **item}


def get_question(
    question_id: str, *, table: object | None = None
) -> QuestionItem | None:
    table = _table(table)
    resp = _get_item(table,
        Key={"PK": f"QUESTION#{question_id}", "SK": "META"},
        ConsistentRead=True,
    )
    item = resp.get("Item")
    return _response(item) if isinstance(item, dict) else None


def get_teacher_session(
    session_id: str, *, table: object | None = None
) -> QuestionItem | None:
    """Read a current teacher-session snapshot without changing its lifecycle."""
    if not session_id:
        return None
    response = _get_item(_table(table),
        Key={"PK": f"SESSION#{session_id}", "SK": "META"},
        ConsistentRead=True,
    )
    item = response.get("Item")
    return _response(item) if isinstance(item, dict) else None


def _frame(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack(">I", len(encoded)) + encoded


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} is required")
    return value


def teacher_takeover_claim_id(question_id: str, teacher_id: str) -> str:
    """Derive one opaque durable claim identity for a teacher and question."""
    payload = (
        _TAKEOVER_CLAIM_DOMAIN
        + _frame(_required_text(question_id, "question_id"))
        + _frame(_required_text(teacher_id, "teacher_id"))
    )
    return hashlib.sha256(payload).hexdigest()


def teacher_session_id_for_claim(claim_id: str) -> str:
    """Derive the single session identity owned by a takeover claim."""
    payload = _TAKEOVER_SESSION_DOMAIN + _frame(
        _required_text(claim_id, "claim_id")
    )
    return hashlib.sha256(payload).hexdigest()


def _question_version(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, Decimal) and value == value.to_integral_value():
        parsed = int(value)
        return parsed if parsed > 0 else None
    return None


def _teacher_profile_observation_condition(
    teacher_id: str,
    profile_key: Mapping[str, object],
    profile_version: object,
) -> QuestionItem | None:
    """Bind the exact active canonical-teacher profile authorized by the route."""
    expected_key = {"PK": f"USER#{teacher_id}", "SK": "PROFILE"}
    if (
        profile_key.get("PK") != expected_key["PK"]
        or profile_key.get("SK") != expected_key["SK"]
    ):
        return None
    version = _question_version(profile_version)
    if version is None:
        return None
    return {
        "ConditionCheck": {
            "Key": expected_key,
            "ConditionExpression": (
                "attribute_exists(PK) AND attribute_exists(SK) AND "
                "#user_id=:teacher_id AND #role=:teacher_role AND "
                "#account_status=:active AND #version=:teacher_profile_version"
            ),
            "ExpressionAttributeNames": {
                "#user_id": "user_id",
                "#role": "role",
                "#account_status": "account_status",
                "#version": "version",
            },
            "ExpressionAttributeValues": {
                ":teacher_id": teacher_id,
                ":teacher_role": "teacher",
                ":active": "active",
                ":teacher_profile_version": version,
            },
        }
    }


def _dispatch_allows_takeover(
    question: Mapping[str, object], teacher_id: str, claimed_at: str
) -> bool:
    dispatch_status = str(question.get("dispatch_status") or "unassigned")
    if dispatch_status == "dispatched":
        deadline = question.get("dispatch_deadline_at")
        return (
            question.get("dispatched_teacher_id") == teacher_id
            and isinstance(deadline, str)
            and deadline > claimed_at
        )
    return dispatch_status in {"", "unassigned", "pending"}


def _takeover_session_item(
    *,
    session_id: str,
    claim_id: str,
    question_id: str,
    teacher_id: str,
    student_id: str,
    started_at: str,
    question_version: int,
    account_fence_generation: int,
) -> QuestionItem:
    return {
        "PK": f"SESSION#{session_id}",
        "SK": "META",
        "entity_type": "teacher_session",
        "session_id": session_id,
        "teacher_takeover_claim_id": claim_id,
        "question_id": question_id,
        "teacher_id": teacher_id,
        "student_id": student_id,
        "started_at": started_at,
        "resolved_at": None,
        "question_version": question_version,
        "account_fence_generation": account_fence_generation,
    }


def _matching_takeover_replay(
    question: Mapping[str, object],
    *,
    teacher_id: str,
    claim_id: str,
    session_id: str,
    table: object,
) -> TeacherTakeoverResult | None:
    question_id = str(question.get("question_id") or "")
    if question.get("status") != "teacher_active":
        return None
    if (
        question.get("teacher_id") != teacher_id
        or question.get("teacher_takeover_claim_id") != claim_id
        or question.get("session_id") != session_id
    ):
        return TeacherTakeoverResult(
            TeacherTakeoverDisposition.ALREADY_CLAIMED,
            question_id,
        )
    try:
        session = get_teacher_session(session_id, table=table)
    except Exception:
        return TeacherTakeoverResult(
            TeacherTakeoverDisposition.RETRYABLE,
            question_id,
        )
    if not session:
        return TeacherTakeoverResult(
            TeacherTakeoverDisposition.RETRYABLE,
            question_id,
        )
    if (
        session.get("entity_type") != "teacher_session"
        or session.get("session_id") != session_id
        or session.get("teacher_takeover_claim_id") != claim_id
        or session.get("question_id") != question_id
        or session.get("teacher_id") != teacher_id
        or session.get("student_id") != question.get("student_id")
    ):
        return TeacherTakeoverResult(
            TeacherTakeoverDisposition.RETRYABLE,
            question_id,
        )
    return TeacherTakeoverResult(
        TeacherTakeoverDisposition.REPLAYED,
        question_id,
        session_id=session_id,
        question=dict(question),
        session=dict(session),
    )


def claim_teacher_takeover(
    question_id: str,
    teacher_id: str,
    *,
    claimed_at: str,
    question: Mapping[str, object] | None = None,
    teacher_profile_key: Mapping[str, object],
    teacher_profile_version: object,
    sla_fields: Mapping[str, object] | None = None,
    table: object | None = None,
) -> TeacherTakeoverResult:
    """Atomically assign one teacher and create that claim's sole session."""
    question_id = _required_text(question_id, "question_id")
    teacher_id = _required_text(teacher_id, "teacher_id")
    claimed_at = _required_text(claimed_at, "claimed_at")
    target = _table(table)
    claim_id = teacher_takeover_claim_id(question_id, teacher_id)
    session_id = teacher_session_id_for_claim(claim_id)
    teacher_profile_condition = _teacher_profile_observation_condition(
        teacher_id,
        teacher_profile_key,
        teacher_profile_version,
    )
    if teacher_profile_condition is None:
        return TeacherTakeoverResult(
            TeacherTakeoverDisposition.RETRYABLE,
            question_id,
        )
    try:
        current = dict(question) if question is not None else get_question(
            question_id, table=target
        )
    except Exception:
        return TeacherTakeoverResult(
            TeacherTakeoverDisposition.RETRYABLE,
            question_id,
        )
    if not current:
        return TeacherTakeoverResult(
            TeacherTakeoverDisposition.ALREADY_CLAIMED,
            question_id,
        )
    replay = _matching_takeover_replay(
        current,
        teacher_id=teacher_id,
        claim_id=claim_id,
        session_id=session_id,
        table=target,
    )
    if replay is not None:
        return replay
    if current.get("status") != "escalated" or not _dispatch_allows_takeover(
        current, teacher_id, claimed_at
    ):
        return TeacherTakeoverResult(
            TeacherTakeoverDisposition.ALREADY_CLAIMED,
            question_id,
        )
    if current.get("question_id") != question_id:
        return TeacherTakeoverResult(
            TeacherTakeoverDisposition.RETRYABLE,
            question_id,
        )
    student_id = str(current.get("student_id") or "")
    if not student_id:
        return TeacherTakeoverResult(
            TeacherTakeoverDisposition.RETRYABLE,
            question_id,
        )
    expected_version = _question_version(current.get("version"))
    next_version = (expected_version or 0) + 1
    condition = (
        "attribute_exists(PK) AND attribute_exists(SK) AND student_id=:student "
        "AND #status=:escalated AND "
    )
    if expected_version is None:
        condition += "attribute_not_exists(#version) AND "
    else:
        condition += "#version=:expected_version AND "
    condition += (
        "(attribute_not_exists(dispatch_status) OR dispatch_status=:unassigned "
        "OR dispatch_status=:pending OR "
        "(dispatch_status=:dispatched AND dispatched_teacher_id=:teacher "
        "AND dispatch_deadline_at>:claimed_at))"
    )
    values: QuestionItem = {
        ":student": student_id,
        ":escalated": "escalated",
        ":active": "teacher_active",
        ":unassigned": "unassigned",
        ":pending": "pending",
        ":dispatched": "dispatched",
        ":accepted": "accepted",
        ":teacher": teacher_id,
        ":claim": claim_id,
        ":session": session_id,
        ":claimed_at": claimed_at,
        ":next_version": next_version,
    }
    if expected_version is not None:
        values[":expected_version"] = expected_version
    updates = [
        "#status=:active",
        "#version=:next_version",
        "teacher_id=:teacher",
        "teacher_takeover_claim_id=:claim",
        "session_id=:session",
        "teacher_started_at=:claimed_at",
        "teacher_taken_over_at=:claimed_at",
    ]
    if current.get("dispatch_status") == "dispatched":
        updates.extend(
            [
                "dispatch_status=:accepted",
                "dispatch_accepted_at=:claimed_at",
            ]
        )
    takeover_sla = (sla_fields or {}).get("sla_request_to_takeover_seconds")
    if isinstance(takeover_sla, int) and not isinstance(takeover_sla, bool):
        updates.append("sla_request_to_takeover_seconds=:takeover_sla")
        values[":takeover_sla"] = takeover_sla
    try:
        fence = account_deletion_repo.require_active_account_fence(
            student_id, table=target
        )
        generation = int(fence["generation"])
        teacher_fence = account_deletion_repo.require_active_account_fence(
            teacher_id, table=target
        )
        teacher_fence_generation = int(teacher_fence["generation"])
        persisted_question: QuestionItem = {
            **current,
            "status": "teacher_active",
            "version": next_version,
            "teacher_id": teacher_id,
            "teacher_takeover_claim_id": claim_id,
            "session_id": session_id,
            "teacher_started_at": claimed_at,
            "teacher_taken_over_at": claimed_at,
            "account_fence_generation": generation,
        }
        if current.get("dispatch_status") == "dispatched":
            persisted_question.update(
                dispatch_status="accepted", dispatch_accepted_at=claimed_at
            )
        if ":takeover_sla" in values:
            persisted_question["sla_request_to_takeover_seconds"] = values[
                ":takeover_sla"
            ]
        session = _takeover_session_item(
            session_id=session_id,
            claim_id=claim_id,
            question_id=question_id,
            teacher_id=teacher_id,
            student_id=student_id,
            started_at=claimed_at,
            question_version=next_version,
            account_fence_generation=generation,
        )
        account_deletion_repo.transact(
            [
                account_deletion_repo.active_fence_condition(
                    student_id, generation
                ),
                account_deletion_repo.active_fence_condition(
                    teacher_id, teacher_fence_generation
                ),
                teacher_profile_condition,
                {
                    "Update": {
                        "Key": {
                            "PK": f"QUESTION#{question_id}",
                            "SK": "META",
                        },
                        "UpdateExpression": "SET " + ", ".join(updates),
                        "ConditionExpression": condition,
                        "ExpressionAttributeNames": {
                            "#status": "status",
                            "#version": "version",
                        },
                        "ExpressionAttributeValues": values,
                    }
                },
                {
                    "Put": {
                        "Item": session,
                        "ConditionExpression": (
                            "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                        ),
                    }
                },
            ],
            table=target,
        )
    except Exception:
        try:
            refreshed = get_question(question_id, table=target)
        except Exception:
            refreshed = None
        if refreshed:
            replay = _matching_takeover_replay(
                refreshed,
                teacher_id=teacher_id,
                claim_id=claim_id,
                session_id=session_id,
                table=target,
            )
            if replay is not None:
                return replay
            if refreshed.get("status") != "escalated" or not _dispatch_allows_takeover(
                refreshed, teacher_id, claimed_at
            ):
                return TeacherTakeoverResult(
                    TeacherTakeoverDisposition.ALREADY_CLAIMED,
                    question_id,
                )
        return TeacherTakeoverResult(
            TeacherTakeoverDisposition.RETRYABLE,
            question_id,
        )
    return TeacherTakeoverResult(
        TeacherTakeoverDisposition.CLAIMED,
        question_id,
        session_id=session_id,
        question=persisted_question,
        session=session,
    )


def get_teacher_assignment(teacher_id: str, student_id: str) -> QuestionItem | None:
    """Read the existing scoped assignment row; Phase 475 owns its writes."""
    if not teacher_id or not student_id:
        return None
    response = _get_item(_table(),
        Key={
            "PK": f"TEACHER_ASSIGNMENT#{teacher_id}",
            "SK": f"STUDENT#{student_id}",
        },
        ConsistentRead=True,
    )
    item = response.get("Item")
    return _response(item) if isinstance(item, dict) else None


def get_teacher_curriculum_assignment(teacher_id: str) -> QuestionItem | None:
    """Read the current teacher curriculum-scope projection consistently.

    Phase 475 owns assignment write consistency. This read deliberately uses one
    current projection and fails closed when it is absent or unavailable.
    """
    if not teacher_id:
        return None
    response = _get_item(_table(),
        Key={
            "PK": f"TEACHER_ASSIGNMENT#{teacher_id}",
            "SK": "CURRICULUM#CURRENT",
        },
        ConsistentRead=True,
    )
    item = response.get("Item")
    if not isinstance(item, dict):
        return None
    version = item.get("version")
    if (
        item.get("PK") != f"TEACHER_ASSIGNMENT#{teacher_id}"
        or item.get("SK") != "CURRICULUM#CURRENT"
        or item.get("entity_type") != "teacher_curriculum_assignment"
        or item.get("teacher_id") != teacher_id
        or not isinstance(version, int)
        or isinstance(version, bool)
        or version <= 0
    ):
        return None
    return _response(item)


def list_by_student(
    student_id: str, limit: int = 20, last_key: QuestionItem | None = None
) -> QuestionItem:
    table = _table()
    kwargs: dict[str, object] = {
        "IndexName": "GSI-StudentId",
        "KeyConditionExpression": Key("student_id").eq(student_id),
        "Limit": limit,
        "ScanIndexForward": False,
    }
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return _query(table, **kwargs)


def record_daily_question_usage(student_id: str, day: str, limit: int, expires_at: int) -> int | None:
    """Atomically record one question submission, returning None when quota is exhausted."""
    table = _table()
    try:
        resp = _update_item(table,
            Key={"PK": f"USAGE#{student_id}", "SK": f"QUESTION#{day}"},
            UpdateExpression=(
                "ADD #c :one SET #ttl = if_not_exists(#ttl, :exp), "
                "usage_type = if_not_exists(usage_type, :usage_type)"
            ),
            ConditionExpression="attribute_not_exists(#c) OR #c < :limit",
            ExpressionAttributeNames={"#c": "count", "#ttl": "expires_at"},
            ExpressionAttributeValues={
                ":one": 1,
                ":limit": limit,
                ":exp": expires_at,
                ":usage_type": "daily_question_submission",
            },
            ReturnValues="UPDATED_NEW",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return None
        raise
    attributes = resp.get("Attributes")
    count = _response(attributes).get("count", 1) if isinstance(attributes, dict) else 1
    if isinstance(count, bool) or not isinstance(count, int):
        raise account_deletion_repo.AccountDeletionConflict("question dependency unavailable")
    return count


def build_question_update_transaction(
    question: QuestionItem,
    *,
    status: str,
    expected_generation: int,
    condition_expression: str | None = None,
    condition_names: dict[str, str] | None = None,
    condition_values: QuestionItem | None = None,
    extra_attrs: Mapping[str, object] | None = None,
) -> list[QuestionItem]:
    """Build the legacy-compatible shape through the state/version CAS contract."""
    question_id = str(question.get("question_id") or "")
    student_id = str(question.get("student_id") or "")
    source_status = str(question.get("status") or status)
    expected_version = _question_version(question.get("version")) or 1
    update_expr = "SET #s = :s, #version=:next_version"
    attr_names = {"#s": "status", "#version": "version"}
    attr_names.update(condition_names or {})
    attr_values = {
        ":s": status,
        ":source_status": source_status,
        ":expected_version": expected_version,
        ":next_version": expected_version + 1,
        **(condition_values or {}),
    }
    for k, v in (extra_attrs or {}).items():
        update_expr += f", {k} = :{k}"
        attr_values[f":{k}"] = v
    row_condition = (
        "attribute_exists(PK) AND attribute_exists(SK) AND student_id=:owner "
        "AND #s=:source_status AND #version=:expected_version"
    )
    attr_values[":owner"] = student_id
    if condition_expression:
        row_condition += f" AND ({condition_expression})"
    return [
        account_deletion_repo.active_fence_condition(student_id, expected_generation),
        {
            "Update": {
                "Key": {"PK": f"QUESTION#{question_id}", "SK": "META"},
                "UpdateExpression": update_expr,
                "ConditionExpression": row_condition,
                "ExpressionAttributeNames": attr_names,
                "ExpressionAttributeValues": attr_values,
            }
        },
    ]


_PROTECTED_QUESTION_FIELDS = frozenset(
    {"PK", "SK", "question_id", "student_id", "status", "version"}
)


def _mutation_identity(
    question: Mapping[str, object], allowed_source_statuses: frozenset[str]
) -> tuple[str, str, str]:
    question_id = _required_text(question.get("question_id"), "question_id")
    student_id = _required_text(question.get("student_id"), "student_id")
    source_status = _required_text(question.get("status"), "status")
    if not allowed_source_statuses or any(
        not isinstance(value, str) or not value for value in allowed_source_statuses
    ):
        raise ValueError("allowed_source_statuses must be a closed non-empty set")
    if question.get("PK", f"QUESTION#{question_id}") != f"QUESTION#{question_id}":
        raise ValueError("question identity does not match its partition key")
    if question.get("SK", "META") != "META":
        raise ValueError("question identity does not match its sort key")
    return question_id, student_id, source_status


def _mutation_fields(extra_attrs: Mapping[str, object] | None) -> QuestionItem:
    fields = dict(extra_attrs or {})
    protected = _PROTECTED_QUESTION_FIELDS.intersection(fields)
    if protected:
        raise ValueError("question mutation cannot replace identity, owner, state, or version")
    if any(not isinstance(key, str) or not key.isidentifier() for key in fields):
        raise ValueError("question mutation field names must be identifiers")
    return fields


def _question_mutation_operation(
    *,
    question_id: str,
    student_id: str,
    source_status: str,
    expected_version: int | None,
    status: str,
    extra_attrs: Mapping[str, object],
) -> QuestionItem:
    names: dict[str, str] = {"#status": "status", "#version": "version"}
    values: QuestionItem = {
        ":owner": student_id,
        ":expected_status": source_status,
        ":next_status": _required_text(status, "status"),
        ":next_version": 1 if expected_version is None else expected_version + 1,
    }
    updates = ["#status=:next_status", "#version=:next_version"]
    condition = (
        "attribute_exists(PK) AND attribute_exists(SK) AND student_id=:owner "
        "AND #status=:expected_status AND "
    )
    if expected_version is None:
        condition += "attribute_not_exists(#version)"
    else:
        condition += "#version=:expected_version"
        values[":expected_version"] = expected_version
    for index, (field, value) in enumerate(extra_attrs.items()):
        name_token = f"#field_{index}"
        value_token = f":field_{field}"
        names[name_token] = field
        values[value_token] = value
        updates.append(f"{name_token}={value_token}")
    return {
        "Update": {
            "Key": {"PK": f"QUESTION#{question_id}", "SK": "META"},
            "UpdateExpression": "SET " + ", ".join(updates),
            "ConditionExpression": condition,
            "ExpressionAttributeNames": names,
            "ExpressionAttributeValues": values,
        }
    }


def _matching_applied_mutation(
    question: Mapping[str, object],
    *,
    question_id: str,
    student_id: str,
    expected_version: int | None,
    status: str,
    extra_attrs: Mapping[str, object],
) -> bool:
    next_version = 1 if expected_version is None else expected_version + 1
    return (
        question.get("question_id") == question_id
        and question.get("student_id") == student_id
        and _question_version(question.get("version")) == next_version
        and question.get("status") == status
        and all(question.get(key) == value for key, value in extra_attrs.items())
    )


def _classify_question_mutation_loss(
    *,
    question_id: str,
    student_id: str,
    source_status: str,
    expected_version: int | None,
    status: str,
    extra_attrs: Mapping[str, object],
    table: object,
) -> QuestionMutationResult:
    try:
        refreshed = get_question(question_id, table=table)
    except Exception:
        refreshed = None
    if not refreshed or (
        refreshed.get("question_id") != question_id
        or refreshed.get("student_id") != student_id
    ):
        return QuestionMutationResult(QuestionMutationDisposition.RETRYABLE, question_id)
    if _matching_applied_mutation(
        refreshed,
        question_id=question_id,
        student_id=student_id,
        expected_version=expected_version,
        status=status,
        extra_attrs=extra_attrs,
    ):
        return QuestionMutationResult(
            QuestionMutationDisposition.APPLIED, question_id, dict(refreshed)
        )
    refreshed_version = _question_version(refreshed.get("version"))
    if refreshed_version != expected_version:
        return QuestionMutationResult(QuestionMutationDisposition.STALE, question_id)
    if refreshed.get("status") != source_status:
        return QuestionMutationResult(
            QuestionMutationDisposition.INVALID_TRANSITION, question_id
        )
    return QuestionMutationResult(QuestionMutationDisposition.RETRYABLE, question_id)


def mutate_question(
    question: Mapping[str, object],
    *,
    status: str,
    allowed_source_statuses: frozenset[str],
    additional_conditions: tuple[Mapping[str, object], ...] = (),
    extra_attrs: Mapping[str, object] | None = None,
    table: object | None = None,
) -> QuestionMutationResult:
    """Apply one owner/state/version CAS from a caller-observed snapshot."""
    question_id, student_id, source_status = _mutation_identity(
        question, allowed_source_statuses
    )
    if source_status not in allowed_source_statuses:
        return QuestionMutationResult(
            QuestionMutationDisposition.INVALID_TRANSITION, question_id
        )
    expected_version = _question_version(question.get("version"))
    if expected_version is None:
        raise ValueError("legacy questions require explicit version initialization")
    fields = _mutation_fields(extra_attrs)
    target = _table(table)
    try:
        fence = account_deletion_repo.require_active_account_fence(
            student_id, table=target
        )
        account_deletion_repo.transact(
            [
                account_deletion_repo.active_fence_condition(
                    student_id, int(fence["generation"])
                ),
                *additional_conditions,
                _question_mutation_operation(
                    question_id=question_id,
                    student_id=student_id,
                    source_status=source_status,
                    expected_version=expected_version,
                    status=status,
                    extra_attrs=fields,
                ),
            ],
            table=target,
        )
    except Exception:
        return _classify_question_mutation_loss(
            question_id=question_id,
            student_id=student_id,
            source_status=source_status,
            expected_version=expected_version,
            status=status,
            extra_attrs=fields,
            table=target,
        )
    applied: QuestionItem = {
        **question,
        "status": status,
        "version": expected_version + 1,
        **fields,
    }
    return QuestionMutationResult(
        QuestionMutationDisposition.APPLIED, question_id, applied
    )


def initialize_legacy_question_version(
    question: Mapping[str, object],
    *,
    allowed_source_statuses: frozenset[str],
    table: object | None = None,
) -> QuestionMutationResult:
    """Initialize an unversioned legacy row without performing its next mutation."""
    question_id, student_id, source_status = _mutation_identity(
        question, allowed_source_statuses
    )
    if source_status not in allowed_source_statuses:
        return QuestionMutationResult(
            QuestionMutationDisposition.INVALID_TRANSITION, question_id
        )
    if _question_version(question.get("version")) is not None:
        raise ValueError("question already has a positive version")
    target = _table(table)
    try:
        fence = account_deletion_repo.require_active_account_fence(
            student_id, table=target
        )
        account_deletion_repo.transact(
            [
                account_deletion_repo.active_fence_condition(
                    student_id, int(fence["generation"])
                ),
                _question_mutation_operation(
                    question_id=question_id,
                    student_id=student_id,
                    source_status=source_status,
                    expected_version=None,
                    status=source_status,
                    extra_attrs={},
                ),
            ],
            table=target,
        )
    except Exception:
        return _classify_question_mutation_loss(
            question_id=question_id,
            student_id=student_id,
            source_status=source_status,
            expected_version=None,
            status=source_status,
            extra_attrs={},
            table=target,
        )
    initialized = {**question, "version": 1}
    return QuestionMutationResult(
        QuestionMutationDisposition.APPLIED, question_id, initialized
    )


def update_status(question_id: str, status: str, **extra_attrs: object) -> None:
    """Compatibility adapter for non-production callers; use ``mutate_question``."""
    question = get_question(question_id)
    if not question:
        raise account_deletion_repo.AccountDeletionConflict("question does not exist")
    result = mutate_question(
        question,
        status=status,
        allowed_source_statuses=frozenset({str(question.get("status") or "")}),
        extra_attrs=extra_attrs,
    )
    if result.disposition is not QuestionMutationDisposition.APPLIED:
        raise account_deletion_repo.AccountDeletionConflict("question mutation lost")


def update_status_conditionally(
    question_id: str,
    status: str,
    *,
    condition_expression: str,
    condition_names: dict[str, str] | None = None,
    condition_values: QuestionItem | None = None,
    **extra_attrs: object,
) -> bool:
    """Compatibility adapter retained for historical test and API imports."""
    question = get_question(question_id)
    if not question:
        return False
    del condition_expression, condition_names, condition_values
    result = mutate_question(
        question,
        status=status,
        allowed_source_statuses=frozenset({str(question.get("status") or "")}),
        extra_attrs=extra_attrs,
    )
    return result.disposition is QuestionMutationDisposition.APPLIED


def create_teacher_session(item: QuestionItem, *, table: object | None = None) -> None:
    table = _table(table)
    if not hasattr(table, "get_item") or not hasattr(getattr(table, "meta", None), "client"):
        _put_item(table,
            Item={
                "PK": f"SESSION#{item['session_id']}",
                "SK": "META",
                "entity_type": "teacher_session",
                **item,
            }
        )
        return
    student_id = str(item.get("student_id") or "")
    fence = account_deletion_repo.require_active_account_fence(student_id, table=table)
    account_deletion_repo.transact(
        [
            account_deletion_repo.active_fence_condition(
                student_id, int(fence["generation"])
            ),
            {
                "Put": {
                    "Item": {
                        "PK": f"SESSION#{item['session_id']}",
                        "SK": "META",
                        "entity_type": "teacher_session",
                        **item,
                    },
                    "ConditionExpression": (
                        "attribute_not_exists(PK) AND attribute_not_exists(SK)"
                    ),
                }
            },
        ],
        table=table,
    )


def update_teacher_session(
    session_id: str, *, resolved_at: str, table: object | None = None
) -> bool:
    table = _table(table)
    if not hasattr(table, "get_item") or not hasattr(getattr(table, "meta", None), "client"):
        _update_item(table,
            Key={"PK": f"SESSION#{session_id}", "SK": "META"},
            UpdateExpression="SET resolved_at=:resolved",
            ExpressionAttributeValues={":resolved": resolved_at},
        )
        return True
    session = get_teacher_session(session_id)
    if not session:
        return False
    student_id = str(session.get("student_id") or "")
    try:
        fence = account_deletion_repo.require_active_account_fence(
            student_id, table=table
        )
        account_deletion_repo.transact(
            [
                account_deletion_repo.active_fence_condition(
                    student_id, int(fence["generation"])
                ),
                {
                    "Update": {
                        "Key": {"PK": f"SESSION#{session_id}", "SK": "META"},
                        "UpdateExpression": "SET resolved_at=:resolved",
                        "ConditionExpression": (
                            "attribute_exists(PK) AND attribute_exists(SK) "
                            "AND student_id=:owner"
                        ),
                        "ExpressionAttributeValues": {
                            ":resolved": resolved_at,
                            ":owner": student_id,
                        },
                    }
                },
            ],
            table=table,
        )
    except account_deletion_repo.AccountDeletionConflict:
        return False
    return True
