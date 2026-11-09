"""DynamoDB access patterns for internal curriculum authoring workflows."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from itertools import islice
from typing import NamedTuple, Protocol, SupportsInt, runtime_checkable

from boto3.dynamodb.conditions import Attr, Key

from stoa.db import table as db_table
from stoa.db.dynamodb import omit_none_attributes
from stoa.db.repositories import practice_repo


VERSION_ENTITY = "curriculum_version"
POINTER_ENTITY = "curriculum_pointer"
MANIFEST_ENTITY = "curriculum_publish_manifest"
AUDIT_ENTITY = "curriculum_audit_event"
MIGRATION_ENTITY = "curriculum_migration_evidence"


type CurriculumItem = dict[str, object]


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


@runtime_checkable
class _DeleteTable(Protocol):
    def delete_item(self, **kwargs: object) -> object: ...


class StalePointerError(RuntimeError):
    """Raised when a conditional publish/rollback pointer update loses a race."""


class ExerciseIdConflictError(RuntimeError):
    """Raised when an exercise id already resolves to another lesson's exercise."""


def _mapping(value: object) -> CurriculumItem:
    if not isinstance(value, Mapping):
        raise RuntimeError("curriculum dependency unavailable")
    item: CurriculumItem = {}
    for key, member in value.items():
        if not isinstance(key, str):
            raise RuntimeError("curriculum dependency unavailable")
        item[key] = member
    return item


def _get_item(table: object, **kwargs: object) -> CurriculumItem:
    if not isinstance(table, _GetTable):
        raise RuntimeError("curriculum dependency unavailable")
    return _mapping(table.get_item(**kwargs))


def _put_item(table: object, **kwargs: object) -> object:
    if not isinstance(table, _PutTable):
        raise RuntimeError("curriculum dependency unavailable")
    item = kwargs.get("Item")
    if isinstance(item, Mapping):
        # A fresh draft has no review state yet, and `review_state` keys
        # GSI-ReviewState; the table refuses it as NULL.
        kwargs["Item"] = omit_none_attributes(item)
    return table.put_item(**kwargs)


def _query(table: object, **kwargs: object) -> CurriculumItem:
    if not isinstance(table, _QueryTable):
        raise RuntimeError("curriculum dependency unavailable")
    return _mapping(table.query(**kwargs))


def _update_item(table: object, **kwargs: object) -> CurriculumItem:
    if not isinstance(table, _UpdateTable):
        raise RuntimeError("curriculum dependency unavailable")
    return _mapping(table.update_item(**kwargs))


def _practice_rows(table: object, **request: object) -> list[CurriculumItem]:
    """Every row one practice query admits, across at most `PRACTICE_PAGE_BUDGET` pages."""
    if not isinstance(table, _QueryTable):
        raise RuntimeError("curriculum dependency unavailable")
    items: list[CurriculumItem] = []
    started_at: dict[str, object] | None = None
    for page in islice(db_table.pages("query", table=table, **request), PRACTICE_PAGE_BUDGET):
        items.extend(_items(page.items))
        if page.last_key is None:
            return items
        if page.last_key == started_at:
            raise RuntimeError("practice pagination did not move forward")
        started_at = page.last_key
    raise RuntimeError("practice pagination exceeded the bounded page limit")


def _delete_item(table: object, **kwargs: object) -> object:
    if not isinstance(table, _DeleteTable):
        raise RuntimeError("curriculum dependency unavailable")
    return table.delete_item(**kwargs)


def _items(value: object) -> list[CurriculumItem]:
    if not isinstance(value, list):
        raise RuntimeError("curriculum dependency unavailable")
    return [_mapping(item) for item in value]


def _integer(value: object) -> int:
    if isinstance(value, (str, bytes, bytearray, SupportsInt)):
        return int(value)
    raise RuntimeError("curriculum dependency unavailable")


def put_version(item: CurriculumItem) -> None:
    table = db_table.table()
    _put_item(
        table,
        Item={
            "PK": f"CURRICULUM_VERSION#{item['public_id']}",
            "SK": f"VERSION#{item['version_id']}",
            "entity_type": VERSION_ENTITY,
            **item,
        },
    )


def get_version(public_id: str, version_id: str) -> CurriculumItem | None:
    table = db_table.table()
    resp = _get_item(
        table,
        Key={
            "PK": f"CURRICULUM_VERSION#{public_id}",
            "SK": f"VERSION#{version_id}",
        },
    )
    item = resp.get("Item")
    return _mapping(item) if item is not None else None


def get_pointer(public_id: str) -> CurriculumItem | None:
    table = db_table.table()
    resp = _get_item(table, Key={"PK": f"CURRICULUM_POINTER#{public_id}", "SK": "META"})
    item = resp.get("Item")
    return _mapping(item) if item is not None else None


def put_pointer(item: CurriculumItem) -> None:
    """Set the named fields on a lesson's pointer and keep every field it does not name.

    A new draft names only `draft_version_id`. Replacing the row erased the published
    version and manifest, so the next publish that named the live version as expected
    was refused as stale."""
    table = db_table.table()
    fields = {
        "entity_type": POINTER_ENTITY,
        **{key: value for key, value in item.items() if value is not None},
    }
    names = {f"#f{index}": key for index, key in enumerate(sorted(fields))}
    values: CurriculumItem = {f":f{index}": fields[key] for index, key in enumerate(sorted(fields))}
    _update_item(
        table,
        Key={"PK": f"CURRICULUM_POINTER#{item['public_id']}", "SK": "META"},
        UpdateExpression="SET " + ", ".join(f"{name} = :{name[1:]}" for name in names),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def set_published_pointer(
    *,
    public_id: str,
    version_id: str,
    manifest_id: str,
    expected_published_version_id: str | None,
    actor_id: str,
    updated_at: str,
) -> CurriculumItem:
    table = db_table.table()
    names = {
        "#published_version_id": "published_version_id",
        "#manifest_id": "manifest_id",
        "#updated_at": "updated_at",
        "#updated_by": "updated_by",
        "#entity_type": "entity_type",
        "#public_id": "public_id",
    }
    values: CurriculumItem = {
        ":version_id": version_id,
        ":manifest_id": manifest_id,
        ":updated_at": updated_at,
        ":updated_by": actor_id,
        ":entity_type": POINTER_ENTITY,
        ":public_id": public_id,
    }
    condition = "attribute_not_exists(#published_version_id)"
    if expected_published_version_id is not None:
        condition = "#published_version_id = :expected"
        values[":expected"] = expected_published_version_id
    if not isinstance(table, _UpdateTable):
        raise RuntimeError("curriculum dependency unavailable")
    try:
        attributes = db_table.update(
            table=table,
            Key={"PK": f"CURRICULUM_POINTER#{public_id}", "SK": "META"},
            UpdateExpression=(
                "SET #entity_type = :entity_type, #public_id = :public_id, "
                "#published_version_id = :version_id, #manifest_id = :manifest_id, "
                "#updated_at = :updated_at, #updated_by = :updated_by"
            ),
            ConditionExpression=condition,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ReturnValues="ALL_NEW",
        )
    except db_table.WriteRefused as exc:
        raise StalePointerError("Published pointer changed") from exc
    return _mapping(attributes)


def put_manifest(item: CurriculumItem) -> None:
    table = db_table.table()
    _put_item(
        table,
        Item={
            "PK": f"CURRICULUM_MANIFEST#{item['public_id']}",
            "SK": f"MANIFEST#{item['manifest_id']}",
            "entity_type": MANIFEST_ENTITY,
            **item,
        },
    )


def put_migration_evidence(item: CurriculumItem) -> None:
    table = db_table.table()
    _put_item(
        table,
        Item={
            "PK": f"CURRICULUM_MIGRATION#{item['migration_id']}",
            "SK": "EVIDENCE",
            "entity_type": MIGRATION_ENTITY,
            **item,
        },
    )


def get_migration_evidence(migration_id: str) -> CurriculumItem | None:
    table = db_table.table()
    resp = _get_item(
        table,
        Key={
            "PK": f"CURRICULUM_MIGRATION#{migration_id}",
            "SK": "EVIDENCE",
        },
    )
    item = resp.get("Item")
    return _mapping(item) if item is not None else None


# Authoring fields that never reach a runtime row. A student hint is a reviewed
# template bound to the content hash; the practice reads refuse to render one next
# to free text, and the seed refuses to write it.
_AUTHORING_ONLY_EXERCISE_FIELDS = frozenset({"hint", "hints"})
# What an exercise takes from its lesson: the practice reads select and project
# challenges by these, and `build_exercise_preview` requires subject and topic.
_LESSON_CONTEXT_FIELDS = ("subject_id", "topic_id", "unit_id", "grade_level")


def _version_exercises(version: CurriculumItem) -> list[CurriculumItem]:
    raw_exercises = version.get("exercises")
    if raw_exercises is None:
        return []
    if not isinstance(raw_exercises, list):
        raise RuntimeError("curriculum dependency unavailable")
    return [_mapping(exercise) for exercise in raw_exercises]


def _exercise_id(exercise: CurriculumItem) -> str:
    return str(exercise.get("exercise_id") or exercise.get("challenge_id"))


def _challenge_sort_key(public_id: object, exercise_id: str) -> str:
    return f"CHALLENGE#{public_id}#{exercise_id}"


def published_challenge_rows(
    version: CurriculumItem, manifest: CurriculumItem
) -> list[CurriculumItem]:
    """The runtime challenge rows a published version stands for, versioned as stored.

    The hash covers the row exactly as the table will hold it - no top-level None,
    no float - because the practice reads recompute it from what they read back."""
    public_id = version["public_id"]
    raw_lesson = version.get("lesson")
    lesson = {} if raw_lesson is None else _mapping(raw_lesson)
    rows: list[CurriculumItem] = []
    seen: set[str] = set()
    for index, exercise in enumerate(_version_exercises(version), start=1):
        exercise_id = _exercise_id(exercise)
        if exercise_id in seen:
            raise RuntimeError("duplicate exercise id in a published version")
        seen.add(exercise_id)
        item = {
            key: value
            for key, value in exercise.items()
            if key not in _AUTHORING_ONLY_EXERCISE_FIELDS
        }
        for field in _LESSON_CONTEXT_FIELDS:
            if lesson.get(field):
                item[field] = lesson[field]
        item["challenge_id"] = exercise_id
        item["exercise_id"] = exercise_id
        item["lesson_id"] = public_id
        item["status"] = "active"
        item["rollout_state"] = "active"
        item["version_id"] = version["version_id"]
        item["manifest_id"] = manifest["manifest_id"]
        item["order"] = _integer(item.get("order") or index)
        item["PK"] = PRACTICE_PK
        item["SK"] = _challenge_sort_key(public_id, exercise_id)
        stored = omit_none_attributes(_mapping(_storable(item)))
        rows.append(practice_repo.version_challenge(stored))
    return rows


def assert_exercise_ids_available(version: CurriculumItem) -> None:
    """Refuse a version whose exercise id already resolves to another lesson's row.

    Challenge ids are global: the lookup pointer is keyed by the id alone. Taking one
    over would repoint a seeded or published exercise at this lesson's row. Called
    before the published pointer moves, so a refusal leaves nothing half-published."""
    table = db_table.table()
    public_id = version["public_id"]
    for exercise in _version_exercises(version):
        exercise_id = _exercise_id(exercise)
        resp = _get_item(
            table,
            Key={"PK": practice_repo.CHALLENGE_POINTER_PK, "SK": f"CHALLENGE#{exercise_id}"},
        )
        pointer = resp.get("Item")
        if pointer is None:
            continue
        if _mapping(pointer).get("target_sk") != _challenge_sort_key(public_id, exercise_id):
            raise ExerciseIdConflictError(exercise_id)


def _lesson_challenge_rows(table: object, public_id: object) -> list[CurriculumItem]:
    """Every challenge row under one lesson, read raw: rows an earlier projection
    wrote unversioned must still be found to be retired."""
    return _practice_rows(
        table,
        KeyConditionExpression=Key("PK").eq(PRACTICE_PK)
        & Key("SK").begins_with(_challenge_sort_key(public_id, "")),
    )


def put_published_projection(version: CurriculumItem, manifest: CurriculumItem) -> None:
    """Make the practice partition hold exactly this version of the lesson.

    Each exercise becomes a versioned challenge row with its lookup pointer, the way
    the seed writes them, and the exercises an earlier projection wrote that this
    version no longer has are retired with their pointers."""
    table = db_table.table()
    public_id = version["public_id"]
    assert_exercise_ids_available(version)
    rows = published_challenge_rows(version, manifest)
    previous = _lesson_challenge_rows(table, public_id)

    for row in rows:
        _put_item(table, Item=row)
        _put_item(table, Item=practice_repo.challenge_pointer(row))

    raw_lesson = version.get("lesson")
    lesson = {} if raw_lesson is None else _mapping(raw_lesson)
    lesson["lesson_id"] = public_id
    lesson["status"] = "active"
    lesson["rollout_state"] = "active"
    lesson["version_id"] = version["version_id"]
    lesson["manifest_id"] = manifest["manifest_id"]
    lesson["challenge_count"] = len(rows)
    lesson["exercise_index"] = practice_repo.exercise_index(rows)
    _put_item(
        table,
        Item={"PK": PRACTICE_PK, "SK": f"LESSON#{public_id}", **lesson},
    )

    current = {row["SK"] for row in rows}
    for row in previous:
        sort_key = row.get("SK")
        if sort_key in current:
            continue
        _delete_item(table, Key={"PK": PRACTICE_PK, "SK": sort_key})
        challenge_id = row.get("challenge_id")
        if not isinstance(challenge_id, str):
            continue
        if not isinstance(table, _DeleteTable):
            raise RuntimeError("curriculum dependency unavailable")
        try:
            db_table.delete(
                table=table,
                Key={"PK": practice_repo.CHALLENGE_POINTER_PK, "SK": f"CHALLENGE#{challenge_id}"},
                ConditionExpression=Attr("target_sk").eq(sort_key),
            )
        except db_table.WriteRefused:
            # No pointer was ever written for it, or the id now points elsewhere.
            pass


def get_practice_unit(unit_id: str) -> CurriculumItem | None:
    table = db_table.table()
    resp = _get_item(table, Key={"PK": "PRACTICE", "SK": f"UNIT#{unit_id}"})
    item = resp.get("Item")
    return _mapping(item) if item is not None else None


def list_practice_units() -> list[CurriculumItem]:
    """Every unit row, across every page: the knowledge base brings two hundred."""
    table = db_table.table()
    return _practice_rows(
        table,
        KeyConditionExpression=Key("PK").eq(PRACTICE_PK) & Key("SK").begins_with("UNIT#"),
    )


def append_audit_event(public_id: str, event: CurriculumItem) -> None:
    table = db_table.table()
    _put_item(
        table,
        Item={
            "PK": f"CURRICULUM_AUDIT#{public_id}",
            "SK": f"EVENT#{event['event_id']}",
            "entity_type": AUDIT_ENTITY,
            **event,
        },
    )


def list_audit_events(public_id: str, limit: int = 50) -> list[CurriculumItem]:
    table = db_table.table()
    resp = _query(
        table,
        KeyConditionExpression=(
            Key("PK").eq(f"CURRICULUM_AUDIT#{public_id}") & Key("SK").begins_with("EVENT#")
        ),
        Limit=limit,
        ScanIndexForward=False,
    )
    return _items(resp.get("Items", []))


class WorklistRows(NamedTuple):
    """Every lesson version, newest first, and each lesson's live version.

    `published_version_ids` maps a lesson's public id to the version its pointer
    names, for every lesson that has one. It comes from the pointer rows, not from
    the versions, so it stays right after a rollback and for a lesson whose live
    version is too old to make the worklist's cut (#111)."""

    versions: list[CurriculumItem]
    published_version_ids: dict[str, str]


def list_worklist() -> WorklistRows:
    table = db_table.table()
    # One scan for both: the versions and the pointers that say which one is live.
    rows = db_table.rows(
        "scan",
        table=table,
        FilterExpression=Attr("entity_type").is_in([VERSION_ENTITY, POINTER_ENTITY]),
    )
    versions: list[CurriculumItem] = []
    published_version_ids: dict[str, str] = {}
    for item in _items(rows):
        if item.get("entity_type") == POINTER_ENTITY:
            public_id = item.get("public_id") or str(item.get("PK", "")).removeprefix("CURRICULUM_POINTER#")
            published = item.get("published_version_id")
            if isinstance(public_id, str) and public_id and isinstance(published, str):
                published_version_ids[public_id] = published
        else:
            versions.append(item)
    # Sorted here, cut by the caller: with the cut first the list was whichever
    # versions came off the front of the table, not the ones last touched.
    newest = sorted(versions, key=lambda item: str(item.get("updated_at", "")), reverse=True)
    return WorklistRows(newest, published_version_ids)


def list_active_assignment_refs(public_id: str, limit: int = 100) -> list[CurriculumItem]:
    table = db_table.table()
    # This one answers "is anything still using this lesson?". A miss here
    # does not shorten a list; it turns a no into a yes.
    rows = db_table.rows(
        "scan",
        table=table,
        want=limit,
        FilterExpression=(
            Attr("entity_type").eq("learning_assignment")
            & Attr("lesson_id").eq(public_id)
            & Attr("status").is_in(["recommended", "assigned", "started"])
        ),
    )
    return _items(rows)


# ── Starmap layout (stoasystem/stoa-backend#60) ───────────────────────────


PRACTICE_PK = "PRACTICE"
PRACTICE_PAGE_BUDGET = 50


def _storable(value: object) -> object:
    """One value in the form the table accepts; it refuses a float."""
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, Mapping):
        return {str(key): _storable(member) for key, member in value.items()}
    if isinstance(value, (list, tuple)):
        return [_storable(member) for member in value]
    return value


def list_practice_rows() -> list[CurriculumItem]:
    """Every row in the practice content partition, across every page.

    The starmap layout reads subjects, topics, units, lessons and skills in one
    pass. A first-page-only read would drop whichever of them the table hands
    back last, and a layout computed from part of a subject is wrong everywhere,
    not just where the rows went missing.
    """
    table = db_table.table()
    return _practice_rows(table, KeyConditionExpression=Key("PK").eq(PRACTICE_PK))


def set_practice_attributes(sort_key: str, attributes: Mapping[str, object]) -> None:
    """Write layout attributes onto one practice row that already exists."""
    if not attributes:
        return
    table = db_table.table()
    names: dict[str, str] = {}
    values: CurriculumItem = {}
    assignments: list[str] = []
    for index, name in enumerate(sorted(attributes)):
        names[f"#a{index}"] = name
        values[f":a{index}"] = _storable(attributes[name])
        assignments.append(f"#a{index} = :a{index}")
    _update_item(
        table,
        Key={"PK": PRACTICE_PK, "SK": sort_key},
        UpdateExpression="SET " + ", ".join(assignments),
        ConditionExpression="attribute_exists(SK)",
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )
