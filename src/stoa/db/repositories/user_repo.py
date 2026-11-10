"""DynamoDB access patterns for the User entity."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from itertools import islice
import re
from typing import Any, Protocol, runtime_checkable

from boto3.dynamodb.conditions import Attr, Key
from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo


type UserItem = dict[str, object]
type TransactionOperation = dict[str, Any]


@runtime_checkable
class _GetTable(Protocol):
    def get_item(self, **kwargs: object) -> object: ...


def _dependency_mapping(value: object) -> UserItem:
    item = _optional_item(value)
    if item is None:
        raise ValueError("malformed user repository response")
    return item


def _get_item(table: object, **kwargs: object) -> UserItem:
    if not isinstance(table, _GetTable):
        raise ValueError("user repository dependency unavailable")
    return _dependency_mapping(table.get_item(**kwargs))


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


def put_user(item: Mapping[str, object]) -> None:
    db_table.transact(
        account_deletion_repo.materialize_profile_with_fence(
            dict(item), now_iso=_profile_created_at(item)
        ),
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
    db_table.transact(
        [
            *account_deletion_repo.materialize_profile_with_fence(
                dict(item), now_iso=_profile_created_at(item)
            ),
            claim_operation,
        ],
    )


def get_user(user_id: str, *, table: object | None = None) -> UserItem | None:
    """One profile, optionally from a table the caller supplies.

    The injection is what lets a caller be tested without reaching the real
    one. Without it, a service that reads a profile takes the ambient table
    however it is called, which is how the suite ended up sending reads to the
    live table for weeks without anyone noticing.
    """
    resp = _get_item(
        table or db_table.table(),
        Key={"PK": f"USER#{user_id}", "SK": "PROFILE"},
        ConsistentRead=True,
    )
    return _optional_item(resp.get("Item"))


# GSI-Email is keyed on the address alone; a page of it ends on the base key and that.
EMAIL_INDEX_KEY = ("PK", "SK", "email")


def _profiles_by_email(email: str) -> list[UserItem]:
    """Every canonical profile row carrying this address.

    GSI-Email holds whatever repeats the address, invitations included, so the profile
    rows have to be asked for explicitly. No Limit is sent: DynamoDB applies Limit
    before the filter, so a Limit here would drop a profile that happened to sort
    behind an invitation and report a taken address as free.
    """
    profiles: list[UserItem] = []
    try:
        for page in db_table.pages(
            "query",
            key=EMAIL_INDEX_KEY,
            IndexName="GSI-Email",
            KeyConditionExpression=Key("email").eq(email),
            FilterExpression=Attr("SK").eq("PROFILE"),
        ):
            profiles.extend(_items(page.items))
    except db_table.TableUnavailable as exc:
        raise ValueError("user repository dependency unavailable") from exc
    return profiles


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
    census = db_table.pages(
        "scan",
        FilterExpression="#entity = :profile AND #role = :role",
        ExpressionAttributeNames={"#entity": "SK", "#role": "role"},
        ExpressionAttributeValues={":profile": "PROFILE", ":role": "admin"},
        Limit=ADMIN_CENSUS_PAGE_SIZE,
    )
    try:
        for page in islice(census, ADMIN_CENSUS_MAX_PAGES):
            for row in _items(page.items):
                other = str(row.get("user_id") or "")
                if other and other != user_id and row.get("account_status") == "active":
                    return other
    except db_table.TableUnavailable as exc:
        raise ValueError("user repository dependency unavailable") from exc
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


ACCOUNT_LIST_SCOPE = "admin_accounts"


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
    target = table or db_table.table()
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
    try:
        walk = db_table.pages(
            "scan", token=cursor or None, scope=ACCOUNT_LIST_SCOPE, table=target, **scan_kwargs
        )
    except db_table.PageTokenInvalid as exc:
        raise InvalidAccountCursor("account list cursor is not readable") from exc

    profiles: list[UserItem] = []
    page_key: UserItem | None = None
    for page in islice(walk, ACCOUNT_LIST_SCAN_MAX_PAGES):
        for row in page.items:
            row_key = {"PK": row.pop("PK", None), "SK": row.pop("SK", None)}
            if status and str(row.get("account_status") or "") != status:
                continue
            if keyword and not _keyword_matches(row, keyword):
                continue
            if not _within_created_range(row, created_from, created_to):
                continue
            profiles.append(row)
            if len(profiles) >= limit:
                return AccountPage(profiles, db_table.page_token(ACCOUNT_LIST_SCOPE, row_key))
        if page.last_key is None:
            return AccountPage(profiles, None)
        page_key = page.last_key
    return AccountPage(
        profiles, db_table.page_token(ACCOUNT_LIST_SCOPE, page_key) if page_key else None
    )


def profile_role_census(
    *, page_budget: int, table: object | None = None
) -> tuple[list[UserItem], bool]:
    """Every profile's role, and whether the walk read the whole table.

    A single scan answers from at most one megabyte of rows read, so on any table
    past that size one call is a sample and not a census. Counting from a sample
    produces a number that looks like an answer, which is worse than no number.
    """
    rows: list[UserItem] = []
    for page in islice(
        db_table.pages(
            "scan",
            table=table or db_table.table(),
            FilterExpression="SK = :profile",
            ExpressionAttributeValues={":profile": "PROFILE"},
            ProjectionExpression="#role",
            ExpressionAttributeNames={"#role": "role"},
        ),
        page_budget,
    ):
        rows.extend(page.items)
        if page.last_key is None:
            return rows, True
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


def get_users_by_email(email: str) -> list[UserItem]:
    """Every account on this address; one person may hold one per role."""
    return _profiles_by_email(email)


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
    begun deletion from being written to; it asks only that the fence be
    active, so it is not read either.
    """
    db_table.fenced(
        user_id,
        [
            profile_update_operation(
                user_id,
                update_expression="SET last_login_at = :signed_in_at",
                expression_attribute_values={":signed_in_at": signed_in_at},
                expected_version=_optional_profile_version(profile.get("version")),
            ),
        ],
        any_generation=True,
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
    subjects is not done here: that goes through `curriculum_service.subject_key`.
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
    table = db_table.table()
    for attempt in range(1, attempt_limit + 1):
        profile = get_user(user_id)
        if profile is None:
            return ProfileWriteResult(ProfileWriteDisposition.RETRYABLE, attempts=attempt)
        expected_version = _optional_profile_version(profile.get("version"))
        try:
            values = dict(expression_attribute_values)
            if values_from_profile is not None:
                values.update(values_from_profile(profile))
            db_table.fenced(
                user_id,
                [
                    profile_update_operation(
                        user_id,
                        update_expression=update_expression,
                        expression_attribute_values=values,
                        expression_attribute_names=expression_attribute_names,
                        expected_version=expected_version,
                    )
                ],
                table=table,
            )
        except (
            account_deletion_repo.AccountDeletionConflict,
            db_table.WriteRefused,
            db_table.TableUnavailable,
        ):
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
