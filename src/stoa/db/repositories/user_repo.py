"""DynamoDB access patterns for the User entity."""

import base64
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
import json
import re
from typing import Any, Protocol, runtime_checkable

from boto3.dynamodb.conditions import Attr, Key
from stoa.db.repositories import account_deletion_repo
from stoa.db.dynamodb import get_table


type UserItem = dict[str, object]
type TransactionOperation = dict[str, Any]


@runtime_checkable
class _GetTable(Protocol):
    def get_item(self, **kwargs: object) -> object: ...


@runtime_checkable
class _QueryTable(Protocol):
    def query(self, **kwargs: object) -> object: ...


@runtime_checkable
class _ScanTable(Protocol):
    def scan(self, **kwargs: object) -> object: ...


def _dependency_mapping(value: object) -> UserItem:
    item = _optional_item(value)
    if item is None:
        raise ValueError("malformed user repository response")
    return item


def _get_item(table: object, **kwargs: object) -> UserItem:
    if not isinstance(table, _GetTable):
        raise ValueError("user repository dependency unavailable")
    return _dependency_mapping(table.get_item(**kwargs))


def _query(table: object, **kwargs: object) -> UserItem:
    if not isinstance(table, _QueryTable):
        raise ValueError("user repository dependency unavailable")
    return _dependency_mapping(table.query(**kwargs))


def _scan(table: object, **kwargs: object) -> UserItem:
    if not isinstance(table, _ScanTable):
        raise ValueError("user repository dependency unavailable")
    return _dependency_mapping(table.scan(**kwargs))


PROFILE_WRITE_MAX_ATTEMPTS = 3
PROFILE_SCRUB_OWNED_FIELDS = frozenset(
    {
        "child_user_id",
        "student_id",
        "child_id",
        "children",
        "child_summaries",
        "student_summaries",
    }
)

# Closed source inventory for every production mutation of USER#*/PROFILE.  The
# source-backed test in Plan 475-08 requires additions to be reviewed here; row
# creation and deletion scrub remain special lifecycle primitives, while every
# ordinary update is built by profile_update_operation().
PROFILE_WRITER_REGISTRY = frozenset(
    {
        "src/stoa/db/repositories/account_deletion_repo.py:materialize_profile_with_fence",
        "src/stoa/db/repositories/account_deletion_repo.py:_parent_profile_scrub_operation",
        "src/stoa/db/repositories/account_deletion_repo.py:replace_with_deletion_tombstone",
        "src/stoa/db/repositories/user_repo.py:profile_update_operation",
    }
)


class ProfileWriteDisposition(StrEnum):
    """Closed outcomes for one bounded shared-profile CAS operation."""

    UPDATED = "updated"
    RETRYABLE = "retryable"


@dataclass(frozen=True, slots=True)
class ProfileWriteResult:
    disposition: ProfileWriteDisposition
    profile: UserItem | None = None
    attempts: int = 0


def _profile_created_at(item: Mapping[str, object]) -> str:
    created_at = item.get("created_at")
    if created_at is None or created_at == "":
        return datetime.now(UTC).isoformat()
    if isinstance(created_at, str):
        return created_at
    raise ValueError("malformed user profile timestamp")


class _CapturedLifecycleTransaction:
    """Table stand-in that records the operations a lifecycle write would commit.

    It exists so this module never rebuilds the profile and fence rows itself: the
    repository that owns their shape builds them, and they are handed on unchanged to
    a wider commit. A second copy of that shape here is the one way the fence and the
    profile could ever drift apart.
    """

    def __init__(self) -> None:
        self.operations: list[TransactionOperation] = []

    def transact_account_deletion(self, operations: list[TransactionOperation]) -> None:
        self.operations = list(operations)


def put_user(item: Mapping[str, object]) -> None:
    account_deletion_repo.materialize_profile_with_fence(
        dict(item), now_iso=_profile_created_at(item), table=get_table()
    )


def put_user_with_email_claim(
    item: Mapping[str, object], *, claim_operation: TransactionOperation
) -> None:
    """Create one profile row and the address claim that makes it unique, atomically.

    Uniqueness cannot come from a read of GSI-Email - the index is eventually
    consistent - so it comes from the conditional claim, and the claim only means
    anything if it is decided in the same commit as the row it protects. Either the
    pair is taken and the profile exists, or neither happened.
    """
    capture = _CapturedLifecycleTransaction()
    account_deletion_repo.materialize_profile_with_fence(
        dict(item), now_iso=_profile_created_at(item), table=capture
    )
    if not capture.operations:
        raise ValueError("profile materialization produced no operations")
    account_deletion_repo.transact(
        [*capture.operations, claim_operation], table=get_table()
    )


def get_user(user_id: str, *, table: object | None = None) -> UserItem | None:
    """One profile, optionally from a table the caller supplies.

    The injection is what lets a caller be tested without reaching the real
    one. Without it, a service that reads a profile takes the ambient table
    however it is called, which is how the suite ended up sending reads to the
    live table for weeks without anyone noticing.
    """
    resp = _get_item(
        table or get_table(),
        Key={"PK": f"USER#{user_id}", "SK": "PROFILE"},
        ConsistentRead=True,
    )
    return _optional_item(resp.get("Item"))


def _profiles_by_email(email: str) -> list[UserItem]:
    """Every canonical profile row carrying this address.

    GSI-Email holds whatever repeats the address, invitations included, so the profile
    rows have to be asked for explicitly. No Limit is sent: DynamoDB applies Limit
    before the filter, so a Limit here would drop a profile that happened to sort
    behind an invitation and report a taken address as free.
    """
    table = get_table()
    query_kwargs: dict[str, object] = {
        "IndexName": "GSI-Email",
        "KeyConditionExpression": Key("email").eq(email),
        "FilterExpression": Attr("SK").eq("PROFILE"),
    }
    profiles: list[UserItem] = []
    while True:
        resp = _query(table, **query_kwargs)
        profiles.extend(_items(resp.get("Items", [])))
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            return profiles
        query_kwargs["ExclusiveStartKey"] = last_key


# One census page is one scan call; the answer short-circuits on the first other
# active administrator, so the usual table never reaches the second page.
ADMIN_CENSUS_PAGE_SIZE = 200
ADMIN_CENSUS_MAX_PAGES = 25


def find_other_active_admin(user_id: str) -> str | None:
    """The id of some administrator other than `user_id` that is still active.

    A read, so it is only a candidate: whoever acts on the answer has to restate it
    as `active_admin_condition` in the same commit. A census that ran out of pages
    is not evidence that anyone else is active, so it answers None.
    """
    table = get_table()
    scan_kwargs: dict[str, object] = {
        "FilterExpression": "#entity = :profile AND #role = :role",
        "ExpressionAttributeNames": {"#entity": "SK", "#role": "role"},
        "ExpressionAttributeValues": {":profile": "PROFILE", ":role": "admin"},
        "Limit": ADMIN_CENSUS_PAGE_SIZE,
    }
    for _page in range(ADMIN_CENSUS_MAX_PAGES):
        result = _scan(table, **scan_kwargs)
        for row in _items(result.get("Items", [])):
            other = str(row.get("user_id") or "")
            if other and other != user_id and row.get("account_status") == "active":
                return other
        cursor = result.get("LastEvaluatedKey")
        if not cursor:
            return None
        scan_kwargs["ExclusiveStartKey"] = cursor
    return None


class InvalidAccountCursor(ValueError):
    """A list cursor that is not one `list_accounts` handed out."""


@dataclass(frozen=True, slots=True)
class AccountPage:
    """One page of profile rows, without their table keys, and where the next starts."""

    profiles: list[UserItem]
    next_cursor: str | None


# One scan page is rows read, not accounts found: `Limit` is applied before the
# filter, so on a table whose lessons and attempts outnumber its profiles a page
# can hold no account at all. The walk follows the continuation key until the
# requested page is full, and stops at a budget so it cannot become a table walk.
ACCOUNT_LIST_SCAN_PAGE_SIZE = 200
ACCOUNT_LIST_SCAN_MAX_PAGES = 25


def _encode_account_cursor(key: Mapping[str, object]) -> str:
    return base64.urlsafe_b64encode(json.dumps(dict(key), default=str).encode("utf-8")).decode(
        "ascii"
    )


def _decode_account_cursor(cursor: str) -> UserItem:
    try:
        decoded = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidAccountCursor("account list cursor is not readable") from exc
    if not isinstance(decoded, dict):
        raise InvalidAccountCursor("account list cursor is not a key")
    return _dependency_mapping(decoded)


def _keyword_matches(profile: Mapping[str, object], keyword: str) -> bool:
    needle = keyword.strip().casefold()
    if not needle:
        return True
    return any(
        needle in str(profile.get(field) or "").casefold()
        for field in ("name", "email", "account_number", "user_id")
    )


def _within_created_range(
    profile: Mapping[str, object], created_from: str | None, created_to: str | None
) -> bool:
    created_at = str(profile.get("created_at") or "")
    if created_from and created_at < created_from:
        return False
    if created_to and created_at > created_to:
        return False
    return True


def list_accounts(
    *,
    limit: int,
    role: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    cursor: str | None = None,
    table: object | None = None,
) -> AccountPage:
    """Up to `limit` profiles that pass every filter given, in table order.

    `next_cursor` resumes right after the last profile returned, so a page neither
    repeats a profile nor skips the rest of the scan page it came from. It is also
    set when the scan budget runs out before the page is full, at the point the walk
    stopped: a short page with a cursor means "keep going", not "that was all".
    Raises `InvalidAccountCursor` for a cursor this function did not produce.
    """
    target = table or get_table()
    filter_expr = "#entity = :profile"
    attr_names = {"#entity": "SK"}
    attr_values: dict[str, object] = {":profile": "PROFILE"}
    if role:
        filter_expr += " AND #role = :role"
        attr_names["#role"] = "role"
        attr_values[":role"] = role
    scan_kwargs: dict[str, object] = {
        "FilterExpression": filter_expr,
        "ExpressionAttributeNames": attr_names,
        "ExpressionAttributeValues": attr_values,
        "Limit": ACCOUNT_LIST_SCAN_PAGE_SIZE,
    }
    if cursor:
        scan_kwargs["ExclusiveStartKey"] = _decode_account_cursor(cursor)

    profiles: list[UserItem] = []
    for _page in range(ACCOUNT_LIST_SCAN_MAX_PAGES):
        result = _scan(target, **scan_kwargs)
        for row in _items(result.get("Items", [])):
            row_key = {"PK": row.pop("PK", None), "SK": row.pop("SK", None)}
            if status and str(row.get("account_status") or "") != status:
                continue
            if keyword and not _keyword_matches(row, keyword):
                continue
            if not _within_created_range(row, created_from, created_to):
                continue
            profiles.append(row)
            if len(profiles) >= limit:
                return AccountPage(profiles, _encode_account_cursor(row_key))
        page_key = _optional_item(result.get("LastEvaluatedKey"))
        if not page_key:
            return AccountPage(profiles, None)
        scan_kwargs["ExclusiveStartKey"] = page_key
    return AccountPage(profiles, _encode_account_cursor(page_key))


def profile_role_census(
    *, page_budget: int, table: object | None = None
) -> tuple[list[UserItem], bool]:
    """Every profile's role, and whether the walk read the whole table.

    A single scan answers from at most one megabyte of rows read, so on any table
    past that size one call is a sample and not a census. Counting from a sample
    produces a number that looks like an answer, which is worse than no number.
    """
    return _scan_every_page(
        table or get_table(),
        page_budget=page_budget,
        FilterExpression="SK = :profile",
        ExpressionAttributeValues={":profile": "PROFILE"},
        ProjectionExpression="#role",
        ExpressionAttributeNames={"#role": "role"},
    )


def _scan_every_page(
    table: object, *, page_budget: int, **kwargs: object
) -> tuple[list[UserItem], bool]:
    rows: list[UserItem] = []
    request = dict(kwargs)
    for _page in range(page_budget):
        result = _scan(table, **request)
        rows.extend(_items(result.get("Items", [])))
        cursor = _optional_item(result.get("LastEvaluatedKey"))
        if not cursor:
            return rows, True
        request["ExclusiveStartKey"] = cursor
    return rows, False


def active_admin_condition(user_id: str) -> TransactionOperation:
    """Holds while `user_id` is still an active administrator, at commit time."""
    return {
        "ConditionCheck": {
            "Key": {"PK": f"USER#{user_id}", "SK": "PROFILE"},
            "ConditionExpression": "#role = :admin AND #account_status = :active",
            "ExpressionAttributeNames": {"#role": "role", "#account_status": "account_status"},
            "ExpressionAttributeValues": {":admin": "admin", ":active": "active"},
        }
    }


def get_user_by_email(email: str) -> UserItem | None:
    profiles = _profiles_by_email(email)
    return profiles[0] if profiles else None


def get_user_by_email_and_role(email: str, role: str) -> UserItem | None:
    """The account this address holds in this role, if any.

    The uniqueness key is the pair, not the address: one person holds a teacher
    account and a parent account on the same address, so the address alone can no
    longer answer "is this taken".
    """
    wanted = str(role or "").strip()
    for profile in _profiles_by_email(email):
        if str(profile.get("role") or "") == wanted:
            return profile
    return None


def update_locale_preference(user_id: str, locale: str, updated_at: str) -> UserItem:
    return update_profile_fields(
        user_id,
        update_expression=(
            "SET preferred_locale = :locale, preferredLocale = :locale, "
            "#language = :locale, locale_updated_at = :updated_at, updated_at = :updated_at"
        ),
        expression_attribute_names={"#language": "language"},
        expression_attribute_values={
            ":locale": locale,
            ":updated_at": updated_at,
        },
    )


def record_sign_in(
    user_id: str, profile: Mapping[str, object], *, signed_in_at: str
) -> None:
    """Stamp `last_login_at` with one transaction and no reads of its own (#107).

    The version checked is the one on the profile the sign-in itself just read,
    so a sign-in costs no extra round trip. An edit that lands in between makes
    this write lose rather than retry: missing one sign-in's time is cheaper
    than another read. Edits read the version in the request that writes it, so
    a sign-in can only move it under one inside that request, as any other
    profile write can. The fence condition is what keeps an account that has
    begun deletion from being written to.
    """
    account_deletion_repo.transact(
        [
            account_deletion_repo.active_fence_condition(user_id),
            profile_update_operation(
                user_id,
                update_expression="SET last_login_at = :signed_in_at",
                expression_attribute_values={":signed_in_at": signed_in_at},
                expected_version=_optional_profile_version(profile.get("version")),
            ),
        ],
        table=get_table(),
    )


TEACHER_AVAILABILITY_FIELDS = ("dispatch_availability", "availability_status", "teacher_status")


def stored_teacher_availability(profile: Mapping[str, object] | None) -> str | None:
    """The stored word for whether a teacher takes dispatch.

    Older profiles carry it in `availability_status` or `teacher_status`; the
    first non-empty field wins. This is the one reading of those fields, used
    by the dispatch planner and by the save that has to keep it.
    """
    for field in TEACHER_AVAILABILITY_FIELDS:
        value = (profile or {}).get(field)
        if value:
            return str(value)
    return None


TEACHER_SUBJECT_FIELDS = ("dispatch_subjects", "primary_subjects", "subjects", "subject_ids")


def stored_teacher_subjects(profile: Mapping[str, object] | None) -> list[str]:
    """The subjects a teacher is stored as taking, exactly as saved.

    Older profiles carry them in `subjects` or `subject_ids`; the first
    non-empty field wins. This is the one reading of those fields, used by the
    dispatch planner and by the teacher's own availability view. Comparing
    subjects is not done here: that goes through `practice_repo.normal_subject_id`.
    """
    for field in TEACHER_SUBJECT_FIELDS:
        value = (profile or {}).get(field)
        if not value:
            continue
        items = value if isinstance(value, (list, tuple, set)) else [value]
        subjects = [str(item).strip() for item in items if str(item).strip()]
        if subjects:
            return subjects
    return []


def update_teacher_availability(
    user_id: str,
    *,
    subjects: list[str] | None,
    weekly_availability: list[Mapping[str, object]] | None,
    updated_at: str,
    status: str | None = None,
) -> UserItem:
    """Save what a teacher changed of subjects, hours and dispatch status.

    A field passed as `None` is left as stored, so switching status never clears
    subjects or hours. An omitted `status` keeps the stored one, read from the
    same profile whose version the write is checked against; a teacher who has
    never had one becomes `available`, which is what saving has always meant.
    Both status fields are written with the same word, so the planner's
    fallback can no longer disagree with the first field.
    """
    parts = [
        "availability_status = :availability",
        "dispatch_availability = :availability",
        "updated_at = :updated_at",
    ]
    values: dict[str, object] = {":updated_at": updated_at}
    if subjects is not None:
        # Every field the reading falls back through is written, so an
        # explicit `[]` is not answered by an older `subject_ids`.
        parts[:0] = [
            "subjects = :subjects",
            "primary_subjects = :subjects",
            "dispatch_subjects = :subjects",
            "subject_ids = :subjects",
        ]
        values[":subjects"] = subjects
    if weekly_availability is not None:
        parts[:0] = [
            "weekly_availability = :weekly_availability",
            "weeklyAvailability = :weekly_availability",
        ]
        values[":weekly_availability"] = weekly_availability
    if status is not None:
        values[":availability"] = status

    def kept_status(profile: UserItem) -> Mapping[str, object]:
        if status is not None:
            return {}
        return {":availability": stored_teacher_availability(profile) or "available"}

    return update_profile_fields(
        user_id,
        update_expression="SET " + ", ".join(parts),
        expression_attribute_values=values,
        values_from_profile=kept_status,
    )


def update_email_verification_state(user_id: str, fields: Mapping[str, object]) -> UserItem:
    """Update bounded email verification metadata on a user profile."""
    if not fields:
        return get_user(user_id) or {}
    update_parts = []
    attr_names: dict[str, str] = {}
    attr_values: dict[str, object] = {}
    for idx, (field, value) in enumerate(fields.items()):
        name_key = f"#f{idx}"
        value_key = f":v{idx}"
        attr_names[name_key] = field
        attr_values[value_key] = value
        update_parts.append(f"{name_key} = {value_key}")
    return update_profile_fields(
        user_id,
        update_expression="SET " + ", ".join(update_parts),
        expression_attribute_names=attr_names,
        expression_attribute_values=attr_values,
    )


def build_profile_update_transaction(
    user_id: str,
    *,
    update_expression: str,
    expression_attribute_values: Mapping[str, object],
    expression_attribute_names: Mapping[str, str] | None = None,
    expected_generation: int,
    expected_version: int | None = None,
) -> list[TransactionOperation]:
    """Build one exact-generation, exact-version profile update."""
    return [
        account_deletion_repo.active_fence_condition(user_id, expected_generation),
        profile_update_operation(
            user_id,
            update_expression=update_expression,
            expression_attribute_values=expression_attribute_values,
            expression_attribute_names=expression_attribute_names,
            expected_version=expected_version,
        ),
    ]


def profile_update_operation(
    user_id: str,
    *,
    update_expression: str,
    expression_attribute_values: Mapping[str, object],
    expression_attribute_names: Mapping[str, str] | None = None,
    expected_version: int | None,
    additional_condition_expression: str | None = None,
) -> TransactionOperation:
    """Build the sole ordinary PROFILE update shape: narrow CAS plus one increment."""
    expression = update_expression.strip()
    if not expression:
        raise ValueError("profile update expression is required")
    names = dict(expression_attribute_names or {})
    values = dict(expression_attribute_values)
    if ":next_profile_version" in values:
        raise ValueError("profile version aliases are repository-owned")
    if expected_version is None:
        condition = "attribute_not_exists(version)"
        next_version = 1
    else:
        expected_version = _required_profile_version(expected_version)
        condition = "version=:expected_profile_version"
        values[":expected_profile_version"] = expected_version
        next_version = expected_version + 1
    values[":next_profile_version"] = next_version

    if expression.upper().startswith("SET "):
        expression = "SET version=:next_profile_version, " + expression[4:].lstrip()
    else:
        expression = "SET version=:next_profile_version " + expression
    condition_expression = "attribute_exists(PK) AND attribute_exists(SK) AND " + condition
    if additional_condition_expression:
        condition_expression += f" AND ({additional_condition_expression})"
    return {
        "Update": {
            "Key": {"PK": f"USER#{user_id}", "SK": "PROFILE"},
            "UpdateExpression": expression,
            "ConditionExpression": condition_expression,
            **({"ExpressionAttributeNames": names} if names else {}),
            "ExpressionAttributeValues": values,
        }
    }


def update_profile_fields_versioned(
    user_id: str,
    *,
    update_expression: str,
    expression_attribute_values: Mapping[str, object],
    expression_attribute_names: Mapping[str, str] | None = None,
    owned_fields: frozenset[str] | None = None,
    max_attempts: int = PROFILE_WRITE_MAX_ATTEMPTS,
    values_from_profile: Callable[[UserItem], Mapping[str, object]] | None = None,
) -> ProfileWriteResult:
    """Strong-read and apply one bounded, narrow profile CAS operation.

    `values_from_profile` adds expression values computed from the profile read
    on each attempt, so a value that depends on stored state is written under
    the same version check as that read.
    """
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
        raise ValueError("max_attempts must be a positive integer")
    fields = owned_fields or _profile_update_fields(update_expression, expression_attribute_names)
    # A stale ordinary mutation of scrub-owned data is never replayed after a
    # scrub wins.  Unrelated writers retain bounded retry and convergence.
    attempt_limit = 1 if fields & PROFILE_SCRUB_OWNED_FIELDS else max_attempts
    table = get_table()
    for attempt in range(1, attempt_limit + 1):
        profile = get_user(user_id)
        if profile is None:
            return ProfileWriteResult(ProfileWriteDisposition.RETRYABLE, attempts=attempt)
        expected_version = _optional_profile_version(profile.get("version"))
        try:
            fence = account_deletion_repo.require_active_account_fence(user_id, table=table)
            values = dict(expression_attribute_values)
            if values_from_profile is not None:
                values.update(values_from_profile(profile))
            account_deletion_repo.transact(
                build_profile_update_transaction(
                    user_id,
                    update_expression=update_expression,
                    expression_attribute_values=values,
                    expression_attribute_names=expression_attribute_names,
                    expected_generation=_required_positive_integer(fence.get("generation")),
                    expected_version=expected_version,
                ),
                table=table,
            )
        except account_deletion_repo.AccountDeletionConflict:
            continue
        current = get_user(user_id)
        if current is None:
            return ProfileWriteResult(ProfileWriteDisposition.RETRYABLE, attempts=attempt)
        return ProfileWriteResult(
            ProfileWriteDisposition.UPDATED,
            profile=current,
            attempts=attempt,
        )
    return ProfileWriteResult(ProfileWriteDisposition.RETRYABLE, attempts=attempt_limit)


def update_profile_fields(
    user_id: str,
    *,
    update_expression: str,
    expression_attribute_values: Mapping[str, object],
    expression_attribute_names: Mapping[str, str] | None = None,
    owned_fields: frozenset[str] | None = None,
    values_from_profile: Callable[[UserItem], Mapping[str, object]] | None = None,
) -> UserItem:
    """Compatibility projection over the typed, bounded profile writer."""
    result = update_profile_fields_versioned(
        user_id,
        update_expression=update_expression,
        expression_attribute_values=expression_attribute_values,
        expression_attribute_names=expression_attribute_names,
        owned_fields=owned_fields,
        values_from_profile=values_from_profile,
    )
    if result.disposition is not ProfileWriteDisposition.UPDATED or result.profile is None:
        raise account_deletion_repo.AccountDeletionConflict("profile write remains retryable")
    return result.profile


def _optional_item(value: object) -> UserItem | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("malformed user repository response")
    item: UserItem = {}
    for key, member in value.items():
        if not isinstance(key, str):
            raise ValueError("malformed user repository response")
        item[key] = member
    return item


def _items(value: object) -> list[UserItem]:
    if not isinstance(value, list):
        raise ValueError("malformed user repository response")
    items: list[UserItem] = []
    for member in value:
        item = _optional_item(member)
        if item is None:
            raise ValueError("malformed user repository response")
        items.append(item)
    return items


def _required_positive_integer(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("malformed account fence generation")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, Decimal) and value == value.to_integral_value():
        parsed = int(value)
    else:
        raise ValueError("malformed account fence generation")
    if parsed < 1:
        raise ValueError("malformed account fence generation")
    return parsed


def _required_profile_version(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("malformed profile version")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, Decimal) and value == value.to_integral_value():
        parsed = int(value)
    else:
        raise ValueError("malformed profile version")
    if parsed < 1:
        raise ValueError("malformed profile version")
    return parsed


def _optional_profile_version(value: object) -> int | None:
    if value is None:
        return None
    return _required_profile_version(value)


def _profile_update_fields(
    update_expression: str, expression_attribute_names: Mapping[str, str] | None
) -> frozenset[str]:
    aliases = set((expression_attribute_names or {}).values())
    identifiers = set(re.findall(r"(?<![:#])[A-Za-z_][A-Za-z0-9_]*", update_expression))
    return frozenset(aliases | identifiers)
