#!/usr/bin/env python
"""Compare what account deletion does today with what the data type catalog says, row by row (#640).

Read-only. For every live account in the table it works out, for each row the
deletion reads, what happens to that row:

- **old**: what the 17 deletion branches do today. They are run for real - the
  known-key fast path first, then every branch in order, step after step, the
  way the scheduled run takes them - against an in-memory copy of the table
  (`SandboxTable`, the suite's `FakeTable`), with the account's fence set to
  `deletion_pending`. What they leave is compared with what was there: a row
  gone was deleted, a row replaced by a record of a few fields was tombstoned
  (with those fields), a row changed otherwise was scrubbed, a row unchanged was
  left alone. A branch that fails or leaves debt is reported too.
- **new**: what `stoa.db.data_catalog` says: the row's role for the account
  (`mentions`) and that role's action in `DELETIONS` - delete, a tombstone
  that keeps only its listed fields, scrub, keep - and nothing for a row that
  does not name the account.

The rows compared are those in the partitions a deletion of the account reads
(`account_deletion_repo.owner_partitions`: its derived partitions and those
registered under it), plus any other row the old run changed. Rows the catalog
says name the account but lie outside those partitions are listed on their own:
neither path reaches them.

Effects outside the row (an S3 object deleted, the sign-in provider's user
revoked, attachments released, a curriculum signal reconciled, an Ask
question cancelled, an email claim released, an external delivery counted) are
recorded as the old run makes them and compared per type with the effects the
catalog lists.

Nothing is written anywhere:

- The table is read once, by a consistent `Scan`; everything after that runs
  on the in-memory copy.
- S3 is only read (`ListObjectVersions`, `HeadObject`, ...): a deletion the old
  code asks for is recorded and remembered in memory, never sent. The sign-in
  provider and every other AWS client are doubles that record or refuse.
- Underneath all of that, every botocore call in the process is checked against
  `READ_OPERATIONS` before it is sent; anything else raises `RefusedCall`.

Output: counts, then every difference with its row's PK/SK, type, old action
and new action. Account ids in keys are replaced by aliases (`A1`, `A2`, ...)
and anything holding `@` by `<email>`, so the result can be posted on the
ticket; `--show-ids` prints them as stored. The whole result is written as JSON
to `--out`.

Usage (an operator shell; the SSO profile defaults to `stoa`):
    python scripts/compare_deletion_plan.py
    python scripts/compare_deletion_plan.py --out result.json --account <user id>
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import traceback
from bisect import bisect_right
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
for folder in (ROOT / "tests", ROOT, ROOT / "src"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import botocore.client  # noqa: E402
from boto3.dynamodb.conditions import ConditionExpressionBuilder  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402

from fakes.dynamodb import (  # noqa: E402
    DEFAULT_INDEXES,
    ConditionEvaluator,
    FakeTable,
    _object_condition_holds,
    from_wire,
)
from stoa import aws, config  # noqa: E402
from stoa.aws import Kind  # noqa: E402
from stoa.config import Settings  # noqa: E402
from stoa.db import data_catalog  # noqa: E402
from stoa.db import table as db_table  # noqa: E402
from stoa.db.repositories import account_deletion_repo, curriculum_analytics_repo  # noqa: E402
from stoa.services import account_deletion_service as service  # noqa: E402
from stoa.services import ask_question, attachment_service  # noqa: E402

DEFAULT_AWS_ACCOUNT_ID = "562923011260"
DEFAULT_TABLE = "stoa-main"
DEFAULT_REGION = "eu-central-2"

# How many rounds over the unfinished branches, and pages per branch step: the
# scheduled run's own step (`STEP_PAGES`), and enough rounds for a branch that
# needs a later round to settle.
ROUNDS = 6
STEP_PAGES = service.STEP_PAGES
GENERATION_FALLBACK = 1


# -- nothing leaves the process but a read --------------------------------------------------

READ_OPERATIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("dynamodb", "Scan"),
        ("dynamodb", "Query"),
        ("dynamodb", "GetItem"),
        ("dynamodb", "BatchGetItem"),
        ("dynamodb", "DescribeTable"),
        ("s3", "ListObjectVersions"),
        ("s3", "ListObjectsV2"),
        ("s3", "HeadObject"),
        ("s3", "GetObject"),
        ("s3", "ListMultipartUploads"),
        ("s3", "ListParts"),
        ("sts", "GetCallerIdentity"),
        # Signing in through the SSO profile: the role's credentials and the
        # refresh of the SSO token. Neither changes anything in the account.
        ("sso", "GetRoleCredentials"),
        ("sso-oidc", "CreateToken"),
    }
)


class RefusedCall(RuntimeError):
    """An AWS call this script will not send: only reads leave the process."""


@contextmanager
def read_only_aws() -> Iterator[None]:
    """Within it, every botocore call that is not in `READ_OPERATIONS` raises `RefusedCall`."""
    original = botocore.client.BaseClient._make_api_call

    def guarded(client: Any, operation_name: str, api_params: Any) -> Any:
        service_name = client.meta.service_model.service_name
        if (service_name, operation_name) not in READ_OPERATIONS:
            raise RefusedCall(f"{service_name}:{operation_name} is not a read")
        return original(client, operation_name, api_params)

    botocore.client.BaseClient._make_api_call = guarded  # type: ignore[method-assign]
    try:
        yield
    finally:
        botocore.client.BaseClient._make_api_call = original  # type: ignore[method-assign]


# -- the table, read once -------------------------------------------------------------------


Key = tuple[str, str]


def _key(row: Mapping[str, Any]) -> Key:
    return (str(row["PK"]), str(row["SK"]))


class Snapshot:
    """Every row of the table, by partition and by each index's partition key."""

    def __init__(self, rows: Sequence[Mapping[str, Any]]) -> None:
        self.partitions: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.indexes: dict[str, dict[Any, set[str]]] = {
            name: defaultdict(set) for name in DEFAULT_INDEXES
        }
        for row in rows:
            pk = str(row["PK"])
            self.partitions[pk].append(dict(row))
            for name, schema in DEFAULT_INDEXES.items():
                if schema.partition_key in row:
                    self.indexes[name][row[schema.partition_key]].add(pk)
        self.size = len(rows)

    def rows(self) -> Iterator[dict[str, Any]]:
        for rows in self.partitions.values():
            yield from rows


def read_table(table: Any) -> list[dict[str, Any]]:
    """The whole table, by one consistent scan."""
    rows: list[dict[str, Any]] = []
    request: dict[str, Any] = {"ConsistentRead": True}
    while True:
        response = table.scan(**request)
        rows.extend(response.get("Items", []))
        last = response.get("LastEvaluatedKey")
        if not last:
            return rows
        request["ExclusiveStartKey"] = last


# -- the in-memory table the old branches run against ------------------------------------------


class SandboxUnsupported(RuntimeError):
    """The old code asked the sandbox for something it cannot answer faithfully."""


def _key_condition_value(kwargs: Mapping[str, Any], attribute: str) -> Any:
    """The value a query's key condition fixes `attribute` to, or None."""
    condition = kwargs.get("KeyConditionExpression")
    if condition is None:
        return None
    if isinstance(condition, str):
        expression = condition
        names = dict(kwargs.get("ExpressionAttributeNames") or {})
        values = dict(kwargs.get("ExpressionAttributeValues") or {})
    else:
        built = ConditionExpressionBuilder().build_expression(condition, is_key_condition=True)
        expression = built.condition_expression
        names = dict(built.attribute_name_placeholders)
        values = dict(built.attribute_value_placeholders)
    for name, token in re.findall(r"(#?[A-Za-z_][\w]*)\s*=\s*(:[\w]+)", expression):
        if names.get(name, name) == attribute and token in values:
            return values[token]
    return None


class SandboxTable(FakeTable):
    """The table as the snapshot holds it, a partition at a time, taking writes in memory.

    A partition is copied in from the snapshot the first time anything reads or
    writes it, so the old code sees the stored rows and its conditions are judged
    against them. Writes change only this copy. Every write is noted with the
    branch (and effect) that made it.
    """

    def __init__(self, snapshot: Snapshot) -> None:
        super().__init__()
        self.snapshot = snapshot
        self.loaded: set[str] = set()
        self.touched: set[Key] = set()
        self.before: dict[Key, dict[str, Any]] = {}
        self.writers: dict[Key, set[str]] = defaultdict(set)
        self.writes = 0
        self.actor = ""
        self.effect: str | None = None
        self.scans = 0

    # -- loading ----------------------------------------------------------------

    def load(self, pk: str) -> None:
        if pk in self.loaded:
            return
        self.loaded.add(pk)
        for row in self.snapshot.partitions.get(pk, ()):
            key = _key(row)
            self.before.setdefault(key, deepcopy(row))
            if key not in self.touched:
                self.rows[key] = deepcopy(row)

    def load_all(self) -> None:
        for pk in list(self.snapshot.partitions):
            self.load(pk)

    def _noted(self, keys: Sequence[Key]) -> None:
        self.writes += 1
        for key in keys:
            self.touched.add(key)
            self.writers[key].add(self.effect or self.actor)

    # -- reads ------------------------------------------------------------------

    def get_item(self, **kwargs: Any) -> dict[str, Any]:
        self.load(str(kwargs["Key"]["PK"]))
        return super().get_item(**kwargs)

    def query(self, **kwargs: Any) -> dict[str, Any]:
        index_name = kwargs.get("IndexName")
        if index_name is None:
            pk = _key_condition_value(kwargs, "PK")
            if pk is None:
                raise SandboxUnsupported("a base-table query with no fixed PK")
            self.load(str(pk))
        else:
            schema = self.indexes[str(index_name)]
            value = _key_condition_value(kwargs, schema.partition_key)
            if value is None:
                raise SandboxUnsupported(f"an index query on {index_name} with no fixed key")
            for pk in self.snapshot.indexes[str(index_name)].get(value, ()):
                self.load(pk)
        return super().query(**kwargs)

    def _base_candidates(
        self, kwargs: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
        pk = str(_key_condition_value(kwargs, "PK"))
        condition = kwargs["KeyConditionExpression"]
        rows = [row for key, row in sorted(self.rows.items()) if key[0] == pk]
        if isinstance(condition, str):
            evaluator = ConditionEvaluator(
                kwargs.get("ExpressionAttributeNames"), kwargs.get("ExpressionAttributeValues")
            )
            return [deepcopy(row) for row in rows if evaluator.holds(condition, row)], ()
        return [deepcopy(row) for row in rows if _object_condition_holds(condition, row)], ()

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        """A whole-table read: every partition is copied in first, then read in key order."""
        self.scans += 1
        self.load_all()
        self.calls["scan"] += 1
        keys = sorted(self.rows)
        start = 0
        resume = kwargs.get("ExclusiveStartKey")
        if resume:
            start = bisect_right(keys, (str(resume["PK"]), str(resume["SK"])))
        limit = int(kwargs.get("Limit") or 1000)
        window_keys = keys[start : start + limit]
        window = [deepcopy(self.rows[key]) for key in window_keys]
        response = self._page(window, {**kwargs, "ExclusiveStartKey": None}, index_key=())
        if "LastEvaluatedKey" not in response and window_keys and start + limit < len(keys):
            response["LastEvaluatedKey"] = {"PK": window_keys[-1][0], "SK": window_keys[-1][1]}
        return response

    # -- writes, in memory ----------------------------------------------------------

    def put_item(self, **kwargs: Any) -> dict[str, Any]:
        key = _key(kwargs["Item"])
        self.load(key[0])
        response = super().put_item(**kwargs)
        self._noted([key])
        return response

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        key = _key(kwargs["Key"])
        self.load(key[0])
        response = super().update_item(**kwargs)
        self._noted([key])
        return response

    def delete_item(self, **kwargs: Any) -> dict[str, Any]:
        key = _key(kwargs["Key"])
        self.load(key[0])
        response = super().delete_item(**kwargs)
        self._noted([key])
        return response

    def transact_write_items(self, *, TransactItems: list[dict[str, Any]]) -> None:  # noqa: N803
        written: list[Key] = []
        for operation in from_wire(TransactItems):
            ((kind, body),) = operation.items()
            key = _key(body["Key"] if "Key" in body else body["Item"])
            self.load(key[0])
            if kind != "ConditionCheck":
                written.append(key)
        super().transact_write_items(TransactItems=TransactItems)
        self._noted(written)


# -- the outside world, recorded ---------------------------------------------------------------


def _not_found(operation: str) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": "404", "Message": "Not Found"},
            "ResponseMetadata": {"HTTPStatusCode": 404},
        },
        operation,
    )


class SandboxS3:
    """S3 read as it is; a deletion the old code asks for is remembered, never sent."""

    _READS = frozenset({"list_objects_v2", "get_object", "list_multipart_uploads", "list_parts"})
    _NOTED_WRITES = frozenset({"abort_multipart_upload"})

    def __init__(self, live: Any, table: SandboxTable) -> None:
        self.live = live
        self.table = table
        self.deleted: set[tuple[str, str, str | None]] = set()
        self.calls: list[dict[str, Any]] = []
        self.exceptions = getattr(live, "exceptions", None)

    def _gone(self, bucket: str, key: str, version: object) -> bool:
        return (bucket, key, None) in self.deleted or (bucket, key, str(version)) in self.deleted

    def delete_object(self, **kwargs: Any) -> dict[str, Any]:
        bucket, key = str(kwargs["Bucket"]), str(kwargs["Key"])
        version = kwargs.get("VersionId")
        self.deleted.add((bucket, key, None if version is None else str(version)))
        self.calls.append({"call": "delete_object", "key": key, "by": self.table.actor})
        return {"VersionId": version} if version is not None else {}

    def list_object_versions(self, **kwargs: Any) -> dict[str, Any]:
        response = dict(self.live.list_object_versions(**kwargs))
        bucket = str(kwargs["Bucket"])
        for name in ("Versions", "DeleteMarkers"):
            if name in response:
                response[name] = [
                    entry
                    for entry in response[name]
                    if not self._gone(bucket, str(entry.get("Key")), entry.get("VersionId"))
                ]
        return response

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        if self._gone(str(kwargs["Bucket"]), str(kwargs["Key"]), kwargs.get("VersionId")):
            raise _not_found("HeadObject")
        return self.live.head_object(**kwargs)

    def __getattr__(self, name: str) -> Any:
        if name in self._READS:
            return getattr(self.live, name)
        if name in self._NOTED_WRITES:

            def noted(**kwargs: Any) -> dict[str, Any]:
                self.calls.append({"call": name, "key": str(kwargs.get("Key")), "by": self.table.actor})
                return {}

            return noted
        raise RefusedCall(f"s3:{name} is not something this comparison sends")


class _ProviderUserNotFound(Exception):
    pass


class SandboxProvider:
    """The sign-in provider: a sign-out or deletion is recorded, never sent."""

    class exceptions:  # noqa: N801 - the boto3 client's attribute name
        UserNotFoundException = _ProviderUserNotFound

    def __init__(self) -> None:
        self.calls: list[str] = []

    def admin_user_global_sign_out(self, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append("admin_user_global_sign_out")
        return {}

    def admin_delete_user(self, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append("admin_delete_user")
        return {}

    def __getattr__(self, name: str) -> Any:
        raise RefusedCall(f"cognito-idp:{name} is not something this comparison sends")


class Refusing:
    """Any other AWS client: nothing is sent."""

    def __init__(self, kind: Kind) -> None:
        self.kind = kind

    def __getattr__(self, name: str) -> Any:
        raise RefusedCall(f"{self.kind.value}:{name} is not something this comparison sends")


# -- what happens to one row ------------------------------------------------------------------


TOMBSTONE_TYPES = frozenset({"identity_deletion_evidence"})


@dataclass(frozen=True, slots=True)
class Action:
    """What a deletion does to one row."""

    kind: str  # delete | tombstone | scrub | keep | none | created
    fields: frozenset[str] = frozenset()
    note: str = ""

    def label(self) -> str:
        if self.kind == "tombstone" and self.note:
            return f"tombstone ({self.note})"
        if self.kind in {"keep", "none"} and self.note:
            return f"{self.kind} ({self.note})"
        return self.kind


def is_tombstone(row: Mapping[str, Any]) -> bool:
    entity = str(row.get("entity_type") or "")
    return (
        entity.endswith(data_catalog.DELETION_TOMBSTONE_SUFFIX)
        or entity in TOMBSTONE_TYPES
        or row.get("privacy_deleted") is True
        or row.get("owner_deletion_generation") is not None
    )


def old_action(before: Mapping[str, Any] | None, after: Mapping[str, Any] | None) -> Action:
    """What the old run did to a row, read from the row before and after it."""
    if before is None:
        return Action("created") if after is not None else Action("none")
    if after is None:
        return Action("delete")
    if dict(after) == dict(before):
        return Action("none")
    if is_tombstone(after) and not is_tombstone(before):
        return Action("tombstone", frozenset(after))
    changed = frozenset(
        name for name in set(before) | set(after) if before.get(name) != after.get(name)
    )
    return Action("scrub", changed)


def new_action(row: Mapping[str, Any], account: str) -> tuple[Action, str | None]:
    """What the catalog says deleting `account` does to `row`, and the row's role."""
    entry = data_catalog.data_type_of(row)
    if entry is None:
        return Action("none", note="unknown to the catalog"), None
    role = data_catalog.mentions(row).get(account)
    if role is None:
        return Action("none"), None
    deletion = entry.deletion
    chosen = None
    if deletion is not None:
        chosen = deletion.owner if role == data_catalog.OWNER else deletion.reference
    if chosen is None:
        return Action("none", note=f"no {role} action in DELETIONS"), role
    if isinstance(chosen, data_catalog.Delete):
        return Action("delete"), role
    if isinstance(chosen, data_catalog.Tombstone):
        return Action("tombstone", chosen.keeps), role
    if isinstance(chosen, data_catalog.Keep):
        return Action("keep", note=chosen.because), role
    return Action("scrub"), role


def judge(
    old: Action, new: Action, after: Mapping[str, Any] | None, account: str
) -> str | None:
    """Why `old` is not what `new` says, or None when they agree."""
    if new.kind in {"keep", "none"}:
        return None if old.kind == "none" else f"old {old.kind}s a row the catalog leaves"
    if old.kind == "none":
        return f"old leaves a row the catalog says to {new.kind}"
    if new.kind == "delete":
        return None if old.kind == "delete" else f"old {old.kind}s, catalog deletes"
    if new.kind == "tombstone":
        if old.kind != "tombstone":
            return f"old {old.kind}s, catalog tombstones"
        extra = sorted(old.fields - new.fields)
        if extra:
            return "tombstone holds fields the catalog does not list: " + ", ".join(extra)
        return None
    # new scrub
    if old.kind != "scrub":
        return f"old {old.kind}s, catalog scrubs"
    if after is not None and data_catalog.names(after, account):
        return "the scrub leaves the account named"
    return None


def type_label(row: Mapping[str, Any]) -> str:
    entry = data_catalog.data_type_of(row)
    if entry is not None and entry.untyped_key is not None:
        return f"(untyped) {entry.name}"
    entity = row.get("entity_type")
    if isinstance(entity, str) and entity:
        return entity
    pk, sk = str(row.get("PK") or ""), str(row.get("SK") or "")
    return f"(untyped) {pk.split('#')[0] or '?'}/{sk.split('#')[0] or '?'}"


# -- effects ----------------------------------------------------------------------------------


@dataclass
class Effects:
    """The effects the old run made, as they can be tied to rows, and the calls that failed."""

    on_rows: dict[Key, set[str]] = field(default_factory=lambda: defaultdict(set))
    released: set[tuple[str, str]] = field(default_factory=set)
    failures: dict[Key, list[str]] = field(default_factory=lambda: defaultdict(list))
    errors: list[dict[str, str]] = field(default_factory=list)


# The calls a branch hands one row to, inside its own `try`: a failure there
# becomes the branch's debt and the exception is gone. Wrapped so the comparison
# can say why a row was left.
def _row_calls() -> tuple[tuple[Any, str], ...]:
    from stoa.db.repositories import (
        adaptive_learning_repo,
        ai_teacher_tools_repo,
        attachment_repo,
        moderation_repo,
        notification_repo,
        practice_repo,
        report_repo,
        websocket_repo,
    )
    from stoa.services import help_requests, moderation_service

    return (
        (account_deletion_repo, "replace_with_deletion_tombstone"),
        (account_deletion_repo, "delete_owned_row"),
        (account_deletion_repo, "terminalize_identity_row"),
        (account_deletion_repo, "scrub_parent_profile_child"),
        (account_deletion_repo, "scrub_teacher_question_reference"),
        (account_deletion_repo, "replace_teacher_session_with_tombstone"),
        (help_requests, "scrub_teacher"),
        (moderation_service, "delete_case_image"),
        (moderation_repo, "scrub_moderation_row"),
        (report_repo, "scrub_report_private_row"),
        (report_repo, "purge_report_object_intent"),
        (attachment_repo, "scrub_conversation_private_row"),
        (practice_repo, "scrub_practice_private_row"),
        (adaptive_learning_repo, "scrub_adaptive_private_row"),
        (ai_teacher_tools_repo, "scrub_ai_draft_private_row"),
        (notification_repo, "scrub_notification_private_row"),
        (websocket_repo, "revoke_account_connection"),
        (curriculum_analytics_repo, "reconcile_curriculum_signal"),
        (ask_question, "cancel_for_account_deletion"),
    )


@contextmanager
def patched(target: Any, name: str, replacement: Any) -> Iterator[None]:
    original = getattr(target, name)
    setattr(target, name, replacement)
    try:
        yield
    finally:
        setattr(target, name, original)


@contextmanager
def recording_effects(sandbox: SandboxTable, effects: Effects) -> Iterator[None]:
    """Wrap the calls that act outside a row, so their effect is noted against it."""
    cancel = ask_question.cancel_for_account_deletion
    release_conversation = attachment_service.release_conversation_attachments
    release_resource = attachment_service.release_resource_attachments
    reconcile = curriculum_analytics_repo.reconcile_curriculum_signal

    @contextmanager
    def acting(effect: str) -> Iterator[None]:
        previous, sandbox.effect = sandbox.effect, effect
        try:
            yield
        finally:
            sandbox.effect = previous

    def cancel_recorded(item: Mapping[str, Any], *args: Any, **kwargs: Any) -> Any:
        writes = sandbox.writes
        with acting("cancel_inflight_question"):
            result = cancel(item, *args, **kwargs)
        if sandbox.writes > writes:
            effects.on_rows[_key(item)].add("cancel_inflight_question")
        return result

    def release_conversation_recorded(*args: Any, **kwargs: Any) -> Any:
        effects.released.add(("conversation", str(kwargs.get("conversation_id"))))
        with acting("release_attachments"):
            return release_conversation(*args, **kwargs)

    def release_resource_recorded(*args: Any, **kwargs: Any) -> Any:
        named = dict(zip(("owner_id", "resource_type", "resource_id"), args, strict=False))
        named.update(kwargs)
        effects.released.add((str(named.get("resource_type")), str(named.get("resource_id"))))
        with acting("release_attachments"):
            return release_resource(*args, **kwargs)

    def reconcile_recorded(*args: Any, **kwargs: Any) -> Any:
        manifest = args[0] if args else kwargs["manifest"]
        with acting("reconcile_curriculum_signal"):
            result = reconcile(*args, **kwargs)
        effects.on_rows[_key(manifest)].add("reconcile_curriculum_signal")
        return result

    def noting(call: Callable[..., Any], name: str) -> Callable[..., Any]:
        def noted(*args: Any, **kwargs: Any) -> Any:
            try:
                return call(*args, **kwargs)
            except Exception as exc:
                item = args[0] if args and isinstance(args[0], Mapping) else None
                text = f"{name}: {type(exc).__name__} at {_where(exc)}: {str(exc)[:160]}"
                if item is not None and "PK" in item and "SK" in item:
                    effects.failures[_key(item)].append(text)
                effects.errors.append(
                    {
                        "branch": sandbox.actor,
                        "error": f"{name}: {type(exc).__name__}",
                        "message": str(exc)[:200],
                        "at": _where(exc),
                    }
                )
                raise

        return noted

    purge = attachment_service.purge_student_attachments

    def purge_noted(*args: Any, **kwargs: Any) -> Any:
        result = purge(*args, **kwargs)
        status = str(getattr(result, "status", ""))
        if not status.endswith("complete") and "COMPLETE" not in status.upper():
            effects.errors.append(
                {
                    "branch": sandbox.actor,
                    "error": "purge_student_attachments: not complete",
                    "message": status,
                    "at": "attachment_service.purge_student_attachments",
                }
            )
        return result

    with ExitStack() as stack:
        stack.enter_context(patched(ask_question, "cancel_for_account_deletion", cancel_recorded))
        stack.enter_context(
            patched(
                attachment_service,
                "release_conversation_attachments",
                release_conversation_recorded,
            )
        )
        stack.enter_context(
            patched(attachment_service, "release_resource_attachments", release_resource_recorded)
        )
        stack.enter_context(
            patched(curriculum_analytics_repo, "reconcile_curriculum_signal", reconcile_recorded)
        )
        stack.enter_context(patched(attachment_service, "purge_student_attachments", purge_noted))
        for module, name in _row_calls():
            stack.enter_context(patched(module, name, noting(getattr(module, name), name)))
        yield


def _strings(value: object, depth: int = 0) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif depth < 5 and isinstance(value, Mapping):
        for member in value.values():
            yield from _strings(member, depth + 1)
    elif depth < 5 and isinstance(value, (list, tuple, set, frozenset)):
        for member in value:
            yield from _strings(member, depth + 1)


def observed_effects(
    sandbox: SandboxTable,
    effects: Effects,
    s3: SandboxS3,
    provider: SandboxProvider,
    changed: Mapping[Key, Action],
) -> dict[Key, set[str]]:
    """Every effect the old run made, tied to the rows it was made for."""
    found: dict[Key, set[str]] = defaultdict(set)
    for key, names in effects.on_rows.items():
        found[key] |= names
    deleted_objects = {call["key"] for call in s3.calls if call["call"] == "delete_object"}
    revoked = "admin_delete_user" in provider.calls
    claim_released = any(
        changed.get(key) is not None
        and changed[key].kind == "delete"
        and str(row.get("entity_type") or "") == "account_email_claim"
        for key, row in sandbox.before.items()
    )
    for key, row in sandbox.before.items():
        if deleted_objects and any(text in deleted_objects for text in _strings(row)):
            found[key].add("delete_stored_object")
        entity = str(row.get("entity_type") or "")
        if key in changed:
            if revoked and entity in {
                "identity_binding",
                "user_identity_inventory",
                "public_identity_command",
            }:
                found[key].add("revoke_provider_identity")
            if claim_released and row.get("SK") == "PROFILE" and changed[key].kind == "tombstone":
                found[key].add("release_email_claim")
            if entity == "notification_delivery_intent" and row.get("status") in {
                "accepted",
                "provider_acceptance_unknown",
            }:
                found[key].add("count_external_delivery")
            if effects.released and (
                (entity == "attachment_association"
                 and (str(row.get("resource_type")), str(row.get("resource_id"))) in effects.released)
                or (row.get("attachment_ids")
                    and ("conversation", str(row.get("conversation_id"))) in effects.released)
            ):
                found[key].add("release_attachments")
    return found


# -- one account ------------------------------------------------------------------------------


@dataclass
class AccountRun:
    """What the old run left for one account, and what went wrong on the way."""

    account: str
    scope: tuple[str, ...]
    rows: dict[Key, tuple[dict[str, Any] | None, dict[str, Any] | None]]
    writers: dict[Key, set[str]]
    effects: dict[Key, set[str]]
    errors: list[dict[str, str]]
    debts: dict[Key, list[str]]
    failures: dict[Key, list[str]]
    unfinished: list[str]
    scans: int


def _where(exc: BaseException) -> str:
    frames = traceback.extract_tb(exc.__traceback__)
    inside = [frame for frame in frames if "stoa" in frame.filename.replace("\\", "/")]
    frame = (inside or frames or [None])[-1]
    if frame is None:
        return "?"
    return f"{Path(frame.filename).name}:{frame.lineno} {frame.name}"


_DEBT_KEY = re.compile(r"^(?:[a-z_]+:)?(?P<pk>[^|]+)\|(?P<sk>.+)$")


def run_account(
    account: str, snapshot: Snapshot, live_s3: Any, *, now: Callable[[], str]
) -> AccountRun:
    """Run the old deletion for `account` against a copy of the snapshot; nothing is sent."""
    sandbox = SandboxTable(snapshot)
    db_table.install(sandbox)
    s3 = SandboxS3(live_s3, sandbox)
    provider = SandboxProvider()
    aws.install(
        {
            **{kind: Refusing(kind) for kind in Kind},
            Kind.S3: s3,
            Kind.COGNITO: provider,
        }
    )
    sandbox.load(f"USER#{account}")
    fence_key = (f"USER#{account}", "ACCOUNT_FENCE")
    fence = sandbox.rows.get(fence_key)
    generation = int((fence or {}).get("generation") or GENERATION_FALLBACK)
    sandbox.rows[fence_key] = {
        **(fence or {"PK": fence_key[0], "SK": fence_key[1]}),
        "status": "deletion_pending",
        "generation": Decimal(generation),
    }
    sandbox.touched.add(fence_key)
    scope = account_deletion_repo.owner_partitions(account, table=sandbox)
    for pk in scope:
        sandbox.load(pk)

    errors: list[dict[str, str]] = []
    debts: dict[Key, list[str]] = defaultdict(list)
    effects = Effects()
    command: dict[str, Any] = {
        "user_id": account,
        "generation": generation,
        "command_id": "compare-deletion-plan",
        "branch_results": {},
    }

    def note_error(actor: str, exc: BaseException) -> None:
        errors.append(
            {"branch": actor, "error": type(exc).__name__, "message": str(exc)[:200], "at": _where(exc)}
        )

    with recording_effects(sandbox, effects):
        sandbox.actor = "known_key_fast_path"
        try:
            service.known_key_fast_path(
                user_id=account, generation=generation, now_iso=now(), provider=True
            )
        except Exception as exc:  # noqa: BLE001 - the service logs and goes on, so does this
            note_error("known_key_fast_path", exc)
        results: dict[str, dict[str, Any]] = command["branch_results"]
        for _round in range(ROUNDS):
            pending = [
                branch
                for branch in service.ACCOUNT_DELETION_BRANCH_IDS
                if not service._branch_complete(results.get(branch))
            ]
            if not pending:
                break
            progressed = False
            for branch in pending:
                sandbox.actor = branch
                handler = service.BRANCH_HANDLERS[branch]
                state: Mapping[str, Any] = results.get(branch) or {}
                for _page in range(STEP_PAGES):
                    try:
                        with account_deletion_repo.registry_scope(account, table=sandbox):
                            result = handler(command=command, previous=state)
                    except Exception as exc:  # noqa: BLE001 - as the service does
                        note_error(branch, exc)
                        result = service.BranchResult("retryable", debt_counts={"dependency": 1})
                    state = result.persisted(now(), generation=generation)
                    for name in (result.debt_counts or {}):
                        match = _DEBT_KEY.match(str(name))
                        if match:
                            debts[(match["pk"], match["sk"])].append(f"{branch}: debt")
                    blocked = service._blocked(result)
                    progressed = progressed or not blocked
                    if result.status == "complete" or blocked:
                        break
                results[branch] = dict(state)
            if not progressed:
                break
    unfinished = [
        branch
        for branch in service.ACCOUNT_DELETION_BRANCH_IDS
        if not service._branch_complete(command["branch_results"].get(branch))
    ]

    keys = (set(sandbox.before) | sandbox.touched) - {fence_key}
    rows = {key: (sandbox.before.get(key), sandbox.rows.get(key)) for key in keys}
    changed = {
        key: old_action(before, after)
        for key, (before, after) in rows.items()
        if before != after
    }
    found_effects = observed_effects(sandbox, effects, s3, provider, changed)
    return AccountRun(
        account=account,
        scope=scope,
        rows=rows,
        writers=dict(sandbox.writers),
        effects=dict(found_effects),
        errors=[dict(entry) for entry in {tuple(e.items()): e for e in [*errors, *effects.errors]}.values()],
        debts=dict(debts),
        failures=dict(effects.failures),
        unfinished=unfinished,
        scans=sandbox.scans,
    )


# -- the comparison ---------------------------------------------------------------------------


class Masker:
    """Account ids in keys as aliases; anything holding `@` as `<email>`."""

    def __init__(self, accounts: Sequence[str], *, show_ids: bool) -> None:
        self.show_ids = show_ids
        self.aliases = {account: f"A{index}" for index, account in enumerate(accounts, 1)}
        ordered = sorted(self.aliases, key=len, reverse=True)
        self.pattern = re.compile("|".join(re.escape(a) for a in ordered)) if ordered else None

    def __call__(self, text: str) -> str:
        if self.show_ids:
            return text
        parts = re.split(r"([#:/|])", text)
        parts = ["<email>" if "@" in part else part for part in parts]
        masked = "".join(parts)
        if self.pattern is not None:
            masked = self.pattern.sub(lambda match: self.aliases[match.group(0)], masked)
        return masked


def live_accounts(snapshot: Snapshot) -> list[str]:
    """Every account with a live profile, in id order."""
    found = set()
    for row in snapshot.partitions.values():
        for item in row:
            entry = data_catalog.data_type_of(item)
            if entry is not None and entry.name == "user_profile" and item.get("SK") == "PROFILE":
                user_id = item.get("user_id")
                if isinstance(user_id, str) and data_catalog.is_account_id(user_id):
                    found.add(user_id)
    return sorted(found)


def named_by_catalog(snapshot: Snapshot, accounts: set[str]) -> dict[str, set[Key]]:
    """For each account, every row in the table the catalog says names it."""
    found: dict[str, set[Key]] = defaultdict(set)
    for row in snapshot.rows():
        for account in data_catalog.mentions(row):
            if account in accounts:
                found[account].add(_key(row))
    return found


def compare_account(
    run: AccountRun,
    named: set[Key],
    snapshot_rows: Mapping[Key, Mapping[str, Any]],
    mask: Masker,
) -> dict[str, Any]:
    """Old against new for every row of one account."""
    account = run.account
    alias = mask(account)
    scope = set(run.scope)
    compared = agreed = 0
    differences: list[dict[str, Any]] = []
    side: list[dict[str, Any]] = []
    effects: dict[str, dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))
    for key in sorted(run.rows):
        before, after = run.rows[key]
        old = old_action(before, after)
        writers = sorted(run.writers.get(key, ()))
        if before is None:
            if after is not None:
                side.append({"type": type_label(after), "old": "created", "by": writers})
            continue
        new, role = new_action(before, account)
        in_scope = key[0] in scope
        if not in_scope and new.kind == "none":
            if old.kind != "none":
                side.append({"type": type_label(before), "old": old.label(), "by": writers})
            continue
        compared += 1
        label = type_label(before)
        if role is not None and old.kind != "none":
            entry = data_catalog.data_type_of(before)
            declared: tuple[str, ...] = ()
            if entry is not None and entry.deletion is not None:
                chosen = entry.deletion.owner if role == data_catalog.OWNER else entry.deletion.reference
                declared = tuple(getattr(chosen, "effects", ()))
            for effect in declared:
                effects[label]["declared"][effect] += 1
        for effect in run.effects.get(key, ()):
            effects[label]["observed"][effect] += 1
        reason = judge(old, new, after, account)
        if reason is None:
            agreed += 1
            continue
        old_text = old.label()
        if old.kind == "tombstone":
            old_text = "tombstone[" + ",".join(sorted(old.fields)) + "]"
        elif old.kind == "scrub":
            old_text = "scrub[" + ",".join(sorted(old.fields)) + "]"
        differences.append(
            {
                "account": alias,
                "PK": mask(key[0]),
                "SK": mask(key[1]),
                "type": label,
                "role": role,
                "old": old_text,
                "new": new.label() if new.kind != "tombstone" else "tombstone(catalog keeps)",
                "reason": reason,
                "old_by": writers,
                "old_errors": [mask(text) for text in run.failures.get(key, [])],
                "debt": run.debts.get(key, []),
            }
        )
    outside = sorted(key for key in named if key[0] not in scope)
    return {
        "account": alias,
        "rows_compared": compared,
        "rows_agreeing": agreed,
        "differences": differences,
        "side_rows": side,
        "outside_partitions": [
            {"PK": mask(key[0]), "SK": mask(key[1]), "type": type_label(snapshot_rows[key])}
            for key in outside
            if key in snapshot_rows
        ],
        "effects": {name: {k: dict(v) for k, v in kinds.items()} for name, kinds in effects.items()},
        "errors": [{**error, "message": mask(error["message"])} for error in run.errors],
        "unfinished": run.unfinished,
        "scans": run.scans,
    }


def run(
    live_table: Any,
    live_s3: Any,
    *,
    accounts: Sequence[str] | None = None,
    show_ids: bool = False,
    settings: Settings | None = None,
    progress: Callable[[str], None] = lambda _line: None,
) -> dict[str, Any]:
    """The whole comparison; `live_table` is only scanned and `live_s3` only read."""
    started = time.monotonic()
    snapshot = Snapshot(read_table(live_table))
    progress(f"read {snapshot.size} rows")
    snapshot_rows = {_key(row): row for row in snapshot.rows()}
    every_account = live_accounts(snapshot)
    chosen = [a for a in every_account if accounts is None or a in set(accounts)]
    mask = Masker(every_account, show_ids=show_ids)
    named = named_by_catalog(snapshot, set(chosen))
    config.install(settings or Settings())
    per_account: list[dict[str, Any]] = []
    try:
        for index, account in enumerate(chosen, 1):
            result = run_account(
                account, snapshot, live_s3, now=lambda: datetime.now(UTC).isoformat()
            )
            per_account.append(compare_account(result, named.get(account, set()), snapshot_rows, mask))
            progress(
                f"[{index}/{len(chosen)}] {mask(account)}: "
                f"{per_account[-1]['rows_compared']} rows, "
                f"{len(per_account[-1]['differences'])} differences"
            )
    finally:
        db_table.install(None)
        aws.install(None)
        config.install(None)
    return summarize(per_account, snapshot.size, len(every_account), time.monotonic() - started)


def summarize(
    per_account: Sequence[Mapping[str, Any]], rows_read: int, accounts_live: int, seconds: float
) -> dict[str, Any]:
    by_kind: Counter[tuple[str, str, str, str]] = Counter()
    side: Counter[tuple[str, str, str]] = Counter()
    outside: Counter[str] = Counter()
    errors: Counter[tuple[str, str, str, str]] = Counter()
    unfinished: Counter[str] = Counter()
    declared: dict[str, Counter[str]] = defaultdict(Counter)
    observed: dict[str, Counter[str]] = defaultdict(Counter)
    differences: list[Mapping[str, Any]] = []
    for result in per_account:
        for difference in result["differences"]:
            differences.append(difference)
            by_kind[(difference["type"], difference["old"], difference["new"], difference["reason"])] += 1
        for row in result["side_rows"]:
            side[(row["type"], row["old"], "+".join(row["by"]))] += 1
        for row in result["outside_partitions"]:
            outside[row["type"]] += 1
        for error in result["errors"]:
            errors[(error["branch"], error["error"], error["at"], error["message"])] += 1
        for branch in result["unfinished"]:
            unfinished[branch] += 1
        for name, kinds in result["effects"].items():
            declared[name].update(kinds.get("declared", {}))
            observed[name].update(kinds.get("observed", {}))
    effect_differences = []
    for name in sorted(set(declared) | set(observed)):
        for effect in sorted(set(observed[name]) - set(declared[name])):
            effect_differences.append(
                {"type": name, "effect": effect, "rows": observed[name][effect], "kind": "old makes it, catalog does not list it"}
            )
        for effect in sorted(set(declared[name]) - set(observed[name])):
            effect_differences.append(
                {"type": name, "effect": effect, "rows": declared[name][effect], "kind": "catalog lists it, old never made it"}
            )
    return {
        "rows_read": rows_read,
        "accounts_live": accounts_live,
        "accounts_compared": len(per_account),
        "rows_compared": sum(result["rows_compared"] for result in per_account),
        "rows_agreeing": sum(result["rows_agreeing"] for result in per_account),
        "differences": len(differences),
        "differences_by_kind": [
            {"type": t, "old": o, "new": n, "reason": r, "rows": count}
            for (t, o, n, r), count in sorted(by_kind.items())
        ],
        "difference_rows": differences,
        "effect_differences": effect_differences,
        "side_rows": [
            {"type": t, "old": o, "by": b, "rows": count} for (t, o, b), count in sorted(side.items())
        ],
        "outside_partitions": dict(sorted(outside.items())),
        "branch_errors": [
            {"branch": b, "error": e, "at": a, "message": m, "accounts": count}
            for (b, e, a, m), count in sorted(errors.items())
        ],
        "branches_unfinished": dict(sorted(unfinished.items())),
        "sandbox_scans": sum(result["scans"] for result in per_account),
        "seconds": round(seconds, 1),
    }


def print_report(report: Mapping[str, Any], *, limit: int, out: Path | None) -> None:
    def line(text: str = "") -> None:
        print(text)

    line("== account deletion: old branches against the data catalog (#640) ==")
    for name in (
        "rows_read", "accounts_live", "accounts_compared", "rows_compared", "rows_agreeing",
        "differences", "sandbox_scans", "seconds",
    ):
        line(f"{name}: {report[name]}")
    line()
    line("-- differences by kind (type | old | new | reason | rows)")
    for kind in report["differences_by_kind"]:
        line(f"{kind['type']} | {kind['old']} | {kind['new']} | {kind['reason']} | {kind['rows']}")
    line()
    line(f"-- difference rows (first {limit}; all in the JSON)")
    for row in report["difference_rows"][:limit]:
        by = ",".join(row["old_by"]) or "-"
        line(
            f"{row['account']} {row['PK']} / {row['SK']} | {row['type']} | "
            f"old {row['old']} by {by} | new {row['new']} | {row['reason']}"
        )
        for text in [*row["old_errors"], *row["debt"]]:
            line(f"    {text}")
    line()
    line("-- effects that differ (type | effect | rows | kind)")
    for effect in report["effect_differences"]:
        line(f"{effect['type']} | {effect['effect']} | {effect['rows']} | {effect['kind']}")
    line()
    line("-- rows the old run changed outside the compared rows (type | old | by | rows)")
    for row in report["side_rows"]:
        line(f"{row['type']} | {row['old']} | {row['by']} | {row['rows']}")
    line()
    line("-- rows the catalog gives an account outside its partitions (type: rows)")
    for name, count in report["outside_partitions"].items():
        line(f"{name}: {count}")
    line()
    line("-- branch errors (branch | error | where | message | accounts)")
    for error in report["branch_errors"]:
        line(f"{error['branch']} | {error['error']} | {error['at']} | {error['message']} | {error['accounts']}")
    line()
    line(f"-- branches not complete after the run (branch: accounts): {report['branches_unfinished']}")
    if out is not None:
        line()
        line(f"full result: {out}")


def _json_default(value: object) -> object:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    return str(value)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--table", default=os.environ.get("STOA_TABLE", DEFAULT_TABLE))
    parser.add_argument("--region", default=os.environ.get("AWS_DEFAULT_REGION", DEFAULT_REGION))
    parser.add_argument("--profile", default=os.environ.get("AWS_PROFILE", "stoa"))
    parser.add_argument("--account-id", default=os.environ.get("AWS_ACCOUNT_ID", DEFAULT_AWS_ACCOUNT_ID))
    parser.add_argument("--images-bucket", help="default: stoa-images-<account id>")
    parser.add_argument("--reports-bucket", help="default: stoa-reports-<account id>")
    parser.add_argument("--account", action="append", help="compare only this account (repeatable)")
    parser.add_argument("--out", type=Path, default=Path("compare-deletion-plan.json"))
    parser.add_argument("--limit", type=int, default=300, help="difference rows printed")
    parser.add_argument("--show-ids", action="store_true", help="print account ids as stored")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.ERROR)
    logging.getLogger().setLevel(logging.ERROR)
    from stoa.security.aws_operator_identity import require_sso_operator_session

    with read_only_aws():
        session = require_sso_operator_session(
            profile_name=args.profile,
            region_name=args.region,
            expected_account_id=args.account_id,
        )
        live_table = session.resource("dynamodb", region_name=args.region).Table(args.table)
        live_s3 = session.client("s3", region_name=args.region)
        settings = Settings(
            dynamodb_table_name=args.table,
            aws_region=args.region,
            s3_images_bucket=args.images_bucket or f"stoa-images-{args.account_id}",
            s3_reports_bucket=args.reports_bucket or f"stoa-reports-{args.account_id}",
            cognito_user_pool_id="compare-deletion-plan",
        )
        report = run(
            live_table,
            live_s3,
            accounts=args.account,
            show_ids=args.show_ids,
            settings=settings,
            progress=lambda text: print(text, file=sys.stderr, flush=True),
        )
    args.out.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print_report(report, limit=args.limit, out=args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
