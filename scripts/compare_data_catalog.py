#!/usr/bin/env python
"""Compare the old account rules with the data type catalog over the live table (#587).

Read-only. Scans the table once and, for every row, compares the accounts
the old rules take it for with the accounts `stoa.db.data_catalog.mentions`
says it points to:

- the old rules: `account_deletion_repo.mentioned_accounts` (the owner
  registry's roles, what registration reads until #589), and the deletion
  rules as they stood before #588 put deletion on the catalog, frozen
  below: every account the generic matcher (`_targets_user`) took the row
  for, and the deletion families' own tests that look at one row
  (notifications, reports, practice, adaptive learning, AI drafts,
  conversations, attachments, invitations, sign-ins, websockets, curriculum
  owner manifests);
- the catalog: `data_catalog.mentions`.

The accounts tried are the strings in the row itself (its values, map keys,
and the parts of its keys), so a rule that needs anything beyond the row - a
moderation event's question, a legacy curriculum signal's `studentHash` - is
not compared; legacy signals are counted on their own.

It prints counts only: rows scanned, rows by `entity_type` (or key family, for
rows written without one) the catalog does not know, and the differences
grouped by (entity_type, field, kind), each marked with the intended
difference it falls under (`INTENDED`, below; `tests/test_data_catalog.py`
holds every difference in its test rows to that list) or `UNEXPECTED`.
Never an id, a key or row content.

Usage (an operator shell with read access to the table):
    AWS_PROFILE=<sso profile> python scripts/compare_data_catalog.py
    python scripts/compare_data_catalog.py --table stoa-main --region eu-central-2 --max-pages 5
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from stoa.db import data_catalog, owner_registry  # noqa: E402
from stoa.db.repositories import (  # noqa: E402
    account_deletion_repo,
    adaptive_learning_repo,
    ai_teacher_tools_repo,
    notification_repo,
    report_repo,
    websocket_repo,
)

DEFAULT_TABLE = "stoa-main"
DEFAULT_REGION = "eu-central-2"
_SEPARATORS = ("#", ":", "/")
_ADAPTIVE_TYPES = frozenset(
    {adaptive_learning_repo.ASSIGNMENT_ENTITY, adaptive_learning_repo.MEMORY_ENTITY}
)

# -- the old rules --------------------------------------------------------------------------


def candidates(row: Mapping[str, Any]) -> set[str]:
    """Every string in the row that could be an account id: values, map keys, key parts."""
    found: set[str] = set()

    def visit(value: object, depth: int) -> None:
        if isinstance(value, str):
            parts = {value}
            for separator in _SEPARATORS:
                parts = {piece for part in parts for piece in part.split(separator)}
            found.update(part for part in parts | {value} if part.strip())
        elif depth < 5 and isinstance(value, Mapping):
            for name, member in value.items():
                visit(name, depth + 1)
                visit(member, depth + 1)
        elif depth < 5 and isinstance(value, (list, tuple, set, frozenset)):
            for member in value:
                visit(member, depth + 1)

    for name, value in row.items():
        if name != "entity_type":
            visit(value, 0)
    return found


# Deletion's rules as they stood before #588 (main 538719ce), when every
# deletion scan still had its own: frozen here, because deletion now reads the
# catalog and these are the old answer this comparison and the parity gate in
# `tests/test_data_catalog.py` measure it against. They decide nothing in
# production. Retire them with this script once registration and the sweep
# read the catalog too (#589, #590).

_OLD_NOTIFICATION_OWNER_METADATA = frozenset({"owner_id", "student_id"})
_OLD_NOTIFICATION_REFERENCE_METADATA = frozenset({"actor_id", "teacher_id", "parent_id"})

# What `account_deletion_repo.CROSS_ACCOUNT_IDENTITY_REFERENCE_REGISTRY` was.
OLD_CROSS_ACCOUNT_REFERENCES: Mapping[
    str, tuple[frozenset[str], frozenset[str], frozenset[str]]
] = {
    "parent_student_link": (frozenset({"parent_id"}), frozenset(), frozenset()),
    "question": (
        frozenset({"teacher_id", "dispatched_teacher_id"}),
        frozenset({"previous_dispatch_teacher_ids"}),
        frozenset(),
    ),
    "help_request": (
        frozenset({"teacher_id", "dispatched_teacher_id"}),
        frozenset({"previous_dispatch_teacher_ids", "declined_dispatch_teacher_ids"}),
        frozenset(),
    ),
    "teacher_session": (frozenset({"teacher_id"}), frozenset(), frozenset()),
    "account_invitation": (frozenset({"account_id"}), frozenset(), frozenset()),
    "notification_event": (
        frozenset({"actor_id"}),
        frozenset(),
        _OLD_NOTIFICATION_OWNER_METADATA | _OLD_NOTIFICATION_REFERENCE_METADATA,
    ),
    "allowance_counter": (frozenset({"beneficiary_id"}), frozenset(), frozenset()),
    "allowance_effect": (frozenset({"beneficiary_id"}), frozenset(), frozenset()),
    "provider_usage_evidence": (frozenset({"beneficiary_id"}), frozenset(), frozenset()),
    "teacher_support_admission": (frozenset({"beneficiary_id"}), frozenset(), frozenset()),
}
OLD_NOTIFICATION_OWNER_METADATA = _OLD_NOTIFICATION_OWNER_METADATA


def old_targets_user(item: Mapping[str, Any], user_id: str) -> bool:
    """What `account_deletion_repo._targets_user`, the generic deletion matcher, said."""
    user_id = user_id.strip()
    if not user_id:
        return False
    if user_id in {
        item.get("owner_id"),
        item.get("student_id"),
        item.get("user_id"),
        item.get("child_id"),
        item.get("child_user_id"),
        item.get("target_user_id"),
    }:
        return True
    sk = str(item.get("SK") or "")
    if sk in {f"CHILD#{user_id}", f"PARENT#{user_id}"}:
        return True
    scalar, collection, inside = OLD_CROSS_ACCOUNT_REFERENCES.get(
        str(item.get("entity_type") or ""), (frozenset(), frozenset(), frozenset())
    )
    if any(item.get(name) == user_id for name in scalar):
        return True
    if any(
        isinstance(item.get(name), (list, tuple, set, frozenset)) and user_id in item[name]
        for name in collection
    ):
        return True
    metadata = item.get("metadata")
    if isinstance(metadata, Mapping) and any(metadata.get(name) == user_id for name in inside):
        return True
    for name in ("children", "child_summaries", "student_summaries"):
        value = item.get(name)
        entries: Iterable[object]
        if isinstance(value, Mapping):
            if user_id in value:
                return True
            entries = value.values()
        elif isinstance(value, (list, tuple)):
            entries = value
        else:
            continue
        for entry in entries:
            if isinstance(entry, Mapping) and user_id in {
                entry.get("user_id"),
                entry.get("student_id"),
                entry.get("child_id"),
            }:
                return True
    scope = str(item.get("scope") or "")
    return scope in {f"student:{user_id}", f"student/{user_id}", user_id}


def _report_takes(row: Mapping[str, Any], account: str) -> bool:
    pk, sk = str(row.get("PK") or ""), str(row.get("SK") or "")
    registered = any(
        (pk == prefix or pk.startswith(prefix)) and sk.startswith(sk_prefix)
        for prefix, sk_prefix in report_repo.REPORT_PRIVATE_ROW_REGISTRY.values()
    )
    if not registered or row.get("privacy_deleted") is True:
        return False
    if account in {row.get("student_id"), row.get("owner_id")}:
        return True
    return report_repo._is_recovery_job_record(pk, sk) and account in (
        report_repo._recovery_job_record_accounts(row)
    )


def _is_tombstone(row: Mapping[str, Any]) -> bool:
    return str(row.get("entity_type") or "").endswith("_deletion_tombstone")


def _notification_takes(row: Mapping[str, Any], account: str) -> bool:
    if row.get("entity_type") not in notification_repo.NOTIFICATION_PRIVATE_ROW_REGISTRY:
        return False
    if account in {row.get("owner_id"), row.get("student_id"), row.get("user_id")}:
        return True
    metadata = row.get("metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}
    if any(metadata.get(name) == account for name in _OLD_NOTIFICATION_OWNER_METADATA):
        return True
    if row.get("entity_type") != notification_repo.NOTIFICATION_ENTITY:
        return False
    return row.get("actor_id") == account or any(
        metadata.get(name) == account for name in _OLD_NOTIFICATION_REFERENCE_METADATA
    )


_OLD_PRACTICE_PARTITIONS = (
    "PROGRESS#",
    "ATTEMPTS#",
    "REVIEW#",
    "ACTIVITY#",
    "USAGE#",
    "USAGE_LEDGER#",
    "QUIZ#",
)


def _practice_takes(row: Mapping[str, Any], account: str) -> bool:
    if _is_tombstone(row):
        return False
    pk = str(row.get("PK") or "")
    if pk in {f"{prefix}{account}" for prefix in _OLD_PRACTICE_PARTITIONS}:
        return True
    if account not in {row.get("student_id"), row.get("user_id"), row.get("owner_id")}:
        return False
    return pk.startswith(("PRACTICE#", "PRACTICE_ATTEMPT#", "PRACTICE_PROGRESS#"))


def _conversation_takes(row: Mapping[str, Any], account: str) -> bool:
    if _is_tombstone(row) or account not in {row.get("owner_id"), row.get("student_id")}:
        return False
    pk, sk = str(row.get("PK") or ""), str(row.get("SK") or "")
    return pk.startswith(
        ("CONV#", f"USAGE#{account}", f"USAGE_LEDGER#{account}")
    ) or sk.startswith("REF#CONVERSATION#")


def _attachment_debt_takes(row: Mapping[str, Any], account: str) -> bool:
    if row.get("PK") == f"STORAGE#{account}" and row.get("SK") == "USAGE":
        return True
    if account not in {row.get("student_id"), row.get("owner_id")}:
        return False
    return (
        row.get("entity_type")
        in {"attachment", "attachment_association", "upload_intent", "upload_code"}
        or row.get("staging_cleanup_status") == "pending"
    )


def _family_takes(row: Mapping[str, Any], account: str) -> bool:
    """Whether a deletion family's own one-row test took `row` for `account`."""
    entity = row.get("entity_type")
    if _notification_takes(row, account):
        return True
    if entity in _ADAPTIVE_TYPES and (
        account in {row.get("student_id"), row.get("owner_id")}
        or str(row.get("PK") or "").startswith(f"LEARNING_MEMORY#{account}")
    ):
        return True
    if entity == ai_teacher_tools_repo.DRAFT_ENTITY and account in {
        row.get("student_id"),
        row.get("owner_id"),
    }:
        return True
    if entity == websocket_repo.CONNECTION_ENTITY and account in {
        row.get("owner_id"),
        row.get("user_id"),
    }:
        return True
    return (
        _report_takes(row, account)
        or _practice_takes(row, account)
        or _conversation_takes(row, account)
        or _attachment_debt_takes(row, account)
        or (entity == "account_invitation" and row.get("account_id") == account)
        or (
            row.get("PK") == f"USER#{account}"
            and str(row.get("SK") or "").startswith("SIGNIN#")
        )
        or row.get("PK") == f"CURRICULUM_SIGNAL_OWNER#{account}"
    )


def old_rule(row: Mapping[str, Any]) -> dict[str, str | None]:
    """Every account the old rules take `row` for: its registry role, or None if unregistered."""
    found: dict[str, str | None] = dict(account_deletion_repo.mentioned_accounts(row))
    for account in candidates(row):
        if account not in found and (
            old_targets_user(row, account) or _family_takes(row, account)
        ):
            found[account] = None
    return found


# -- the comparison -----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Difference:
    """Where today's rules and the catalog disagree about one account in one row."""

    entity_type: str
    field: str
    kind: str  # `old_only`, `new_only`, or `role:{old}->{new}`
    account: str  # kept for the tests; never printed


def where(row: Mapping[str, Any], account: str) -> str:
    """The attributes `account` appears in, as `metadata.student_id`, `PK`, `children`..."""
    places: set[str] = set()

    def visit(value: object, path: str, depth: int) -> None:
        if isinstance(value, str):
            if value == account or value.strip() == account.strip():
                places.add(path)
            elif path in {"PK", "SK", "scope"} and any(
                value.endswith(f"{separator}{account}") for separator in _SEPARATORS
            ):
                places.add(path)
        elif depth < 5 and isinstance(value, Mapping):
            for name, member in value.items():
                if name == account:
                    places.add(path)
                visit(member, path if path in _SUMMARY_FIELDS else f"{path}.{name}", depth + 1)
        elif depth < 5 and isinstance(value, (list, tuple, set, frozenset)):
            for member in value:
                visit(member, path, depth + 1)

    for name, value in row.items():
        if name != "entity_type":
            visit(value, name, 0)
    return "+".join(sorted(places)) or "?"


_SUMMARY_FIELDS = frozenset({"children", "child_summaries", "student_summaries"})


def entity_label(row: Mapping[str, Any]) -> str:
    entry = data_catalog.data_type_of(row)
    if entry is not None and entry.untyped_key is not None:
        return f"(untyped) {entry.name}"
    entity = row.get("entity_type")
    if isinstance(entity, str) and entity:
        return entity
    pk, sk = str(row.get("PK") or ""), str(row.get("SK") or "")
    return f"(untyped) {pk.split('#')[0] or '?'}/{sk.split('#')[0] or '?'}"


def declared_in(row: Mapping[str, Any], account: str) -> str:
    """The catalog pointers of the row's kind that read `account`, as their attributes."""
    entry = data_catalog.data_type_of(row)
    if entry is None:
        return "?"
    return "+".join(
        sorted(
            {
                pointer.attribute
                for pointer in entry.accounts
                if any(value == account for value in pointer.values(row))
            }
        )
    ) or "?"


def compare(row: Mapping[str, Any]) -> list[Difference]:
    """Today's rules against the catalog for one row the catalog knows."""
    old = old_rule(row)
    new = data_catalog.mentions(row)
    label = entity_label(row)
    found: list[Difference] = []
    for account in sorted(old.keys() | new.keys()):
        if account not in new:
            kind, field = "old_only", where(row, account)
        elif account not in old:
            kind, field = "new_only", declared_in(row, account)
        elif old[account] is not None and old[account] != new[account]:
            kind, field = f"role:{old[account]}->{new[account]}", declared_in(row, account)
        else:
            continue
        found.append(Difference(label, field, kind, account))
    return found


# -- the intended differences ----------------------------------------------------------------

# Attributes the old matcher read on every row, whatever its type (`_targets_user`):
# the catalog reads each only on the types that write it (#586 decision 4).
GENERIC_FALLBACKS = frozenset(
    {"owner_id", "student_id", "user_id", "child_id", "child_user_id", "target_user_id"}
)


def intended(difference: Difference, row: Mapping[str, Any]) -> str | None:
    """The intended difference (#586) this one falls under, or None."""
    entry = data_catalog.data_type_of(row)
    declared = {pointer.attribute for pointer in entry.accounts} if entry else set()
    account, field, kind = difference.account, difference.field, difference.kind
    if kind.startswith("role:"):
        name = entry.name if entry else ""
        listed = {ROLE_CHANGES.get((name, attribute)) for attribute in field.split("+")}
        kinds = {f"role:{pair[0]}->{pair[1]}" if pair else None for pair in listed}
        return "role" if kinds == {kind} else None
    if kind == "new_only":
        if account != account.strip() and account.strip() in row_old_accounts(row):
            return "exact_ids"
        return None
    # old_only from here.
    fields = set(field.split("+"))
    if fields == {"scope"} and row.get("scope") == account:
        return "bare_scope"
    if account != account.strip() or any(s in account for s in _SEPARATORS):
        return "exact_ids"
    if fields <= {"target_user_id"}:
        return "target_user_id"
    undeclared = fields - declared
    if not undeclared:
        return None
    if undeclared <= GENERIC_FALLBACKS | {"target_user_id"}:
        return "generic_fallback"
    if undeclared <= _SUMMARY_FIELDS:
        return "generic_fallback"
    if fields == {"SK"} and str(row.get("SK") or "") in {f"CHILD#{account}", f"PARENT#{account}"}:
        return "generic_fallback"
    if fields == {"scope"}:
        return "generic_fallback"
    if entry is not None and undeclared <= FAMILY_FALLBACKS.get(entry.name, frozenset()):
        return "family_fallback"
    return None


def row_old_accounts(row: Mapping[str, Any]) -> set[str]:
    return set(old_rule(row))


# Why each intended difference is intended. The rule ids above name these.
INTENDED: Mapping[str, str] = {
    # #586 decision 4: `_targets_user` reads owner_id, student_id, user_id,
    # child_id, child_user_id, a link SK (`CHILD#`/`PARENT#`), the profile
    # summaries and a `student:` scope on every row; the catalog reads each
    # only on the types that write it. The writer gate checks that a type
    # writing one of them declares it.
    "generic_fallback": "a generic fallback field the row's type does not write",
    # #586 decision 4: nothing writes `target_user_id` any more
    # (`test_nothing_writes_target_user_id`).
    "target_user_id": "target_user_id has no writer",
    # #586 decision 4: a bare `scope` equal to an id; any scope string would
    # pass for an account. Registration never read it back.
    "bare_scope": "a bare scope is not an account",
    # #586 decision 5: ids are compared as stored (the registry stripped them),
    # and a value with `#`, `:` or `/` is never an account id.
    "exact_ids": "ids are exact and never hold a key separator",
    # A family's own test reads an attribute on every kind of its family; the
    # catalog reads it only on the kinds that write it (`FAMILY_FALLBACKS`).
    "family_fallback": "a family's field the row's type does not write",
    # #586 decision 7: roles now say what the deletion does (owner: the row is
    # removed or tombstoned; reference: the name is scrubbed). Nothing read the
    # registry's roles (`owner_partitions` and the sweep's census ignore them).
    "role": "roles follow what deletion does with the row (decision 7)",
}

_NOTIFICATION_METADATA_OWNERS = frozenset({"metadata.owner_id", "metadata.student_id"})
_RECOVERY_FILTERS = frozenset({"filters.student_id", "filters.parent_id"})
_RECOVERY_METADATA = frozenset(
    {
        f"metadata.{holder}{field}"
        for holder in ("", "filters.", "result_filters.")
        for field in ("student_id", "parent_id")
    }
)

# Attributes a family's own one-row test reads on every kind of its family,
# by the kinds whose writers do not write them (#586 decision 4, as for the
# generic fallbacks):
FAMILY_FALLBACKS: Mapping[str, frozenset[str]] = {
    # `notification_repo._targets_owner` reads `metadata.owner_id` /
    # `metadata.student_id` on every notification row; only a
    # `notification_event` has `metadata`.
    **{
        name: _NOTIFICATION_METADATA_OWNERS
        for name in notification_repo.NOTIFICATION_PRIVATE_ROW_REGISTRY
        if name != notification_repo.NOTIFICATION_ENTITY
    },
    # `report_repo._recovery_job_record_accounts` reads `filters` and
    # `metadata` on a recovery job's summary and audit events alike; the
    # summary writes `filters`, an event `metadata`. It also reads
    # `metadata.result_filters` as a map, but the job service writes it as a
    # list of result codes (`_normalized_resume_results`), so that never named
    # anyone.
    "REPORT_RECOVERY_JOB": _RECOVERY_METADATA,
    "REPORT_RECOVERY_JOB_AUDIT_EVENT": _RECOVERY_FILTERS
    | {"metadata.result_filters.student_id", "metadata.result_filters.parent_id"},
}

# Every role that differs from the owner registry's today, by (type, field):
# (today's, the catalog's). Today `mentioned_accounts` files the six generic
# fields as `owner` and everything else as `reference`; the catalog says what
# the deletion does (#586 decision 7).
ROLE_CHANGES: Mapping[tuple[str, str], tuple[str, str]] = {
    # The identity branch deletes the invitation that opened the account.
    ("account_invitation", "account_id"): ("reference", "owner"),
    # The student's allowance rows go with the student (account_profile branch, #534).
    ("allowance_counter", "beneficiary_id"): ("reference", "owner"),
    ("allowance_effect", "beneficiary_id"): ("reference", "owner"),
    ("provider_usage_evidence", "beneficiary_id"): ("reference", "owner"),
    ("teacher_support_admission", "beneficiary_id"): ("reference", "owner"),
    # A student's deletion terminalizes a grant scoped to them (capability_scope branch).
    ("capability_grant_current", "scope"): ("reference", "owner"),
    ("capability_grant_revision", "scope"): ("reference", "owner"),
    # Either side's deletion deletes both link rows (account_profile branch).
    ("parent_student_link", "SK"): ("reference", "owner"),
    ("parent_student_link", "parent_id"): ("reference", "owner"),
    # A notification about a student is tombstoned with them (#574).
    ("notification_event", "metadata.owner_id"): ("reference", "owner"),
    ("notification_event", "metadata.student_id"): ("reference", "owner"),
    # A teacher's deletion tombstones the session (`replace_teacher_session_with_tombstone`).
    ("teacher_session", "teacher_id"): ("reference", "owner"),
    # A child's deletion scrubs the child out of the parent's profile
    # (`scrub_parent_profile_child`); the profile stays.
    ("user_profile", "child_user_id"): ("owner", "reference"),
    ("user_profile", "student_id"): ("owner", "reference"),
    ("user_profile", "child_id"): ("owner", "reference"),
}


# -- the scan -------------------------------------------------------------------------------


def _rows(table: Any, max_pages: int | None) -> Iterator[Mapping[str, Any]]:
    request: dict[str, Any] = {}
    pages = 0
    while True:
        response = table.scan(**request)
        yield from response.get("Items", [])
        pages += 1
        last = response.get("LastEvaluatedKey")
        if not last or (max_pages is not None and pages >= max_pages):
            return
        request["ExclusiveStartKey"] = last


# Intended differences that rest on a type not writing a field: on a stored
# row that has the field, they are worth a look rather than a pass.
_WRITTEN_AFTER_ALL = frozenset({"generic_fallback", "family_fallback"})


def run(table: Any, *, max_pages: int | None = None) -> dict[str, Any]:
    scanned = 0
    unknown: Counter[str] = Counter()
    unknown_taken_today: Counter[str] = Counter()
    differences: Counter[tuple[str, str, str, str]] = Counter()
    legacy_signals = 0
    for row in _rows(table, max_pages):
        scanned += 1
        if owner_registry.is_registry_row(row):
            continue
        metadata = row.get("metadata")
        if row.get("entity_type") == "curriculum_analytics_signal" and isinstance(
            metadata, Mapping
        ) and metadata.get("studentHash"):
            legacy_signals += 1
        if data_catalog.data_type_of(row) is None:
            label = entity_label(row)
            unknown[label] += 1
            if old_rule(row):
                unknown_taken_today[label] += 1
            continue
        for difference in compare(row):
            reason = intended(difference, row) or "UNEXPECTED"
            if reason in _WRITTEN_AFTER_ALL:
                # The rule says the type never writes this field, and here is
                # a stored row of it that has it: an older writer, or a writer
                # the gate cannot see. Look before switching over.
                reason = f"REVIEW ({reason}: stored rows carry it)"
            differences[
                (difference.entity_type, difference.field, difference.kind, reason)
            ] += 1
    return {
        "rows_scanned": scanned,
        "rows_unknown_to_catalog": dict(sorted(unknown.items())),
        "unknown_rows_todays_rules_take": dict(sorted(unknown_taken_today.items())),
        "legacy_curriculum_signals_with_student_hash": legacy_signals,
        "differences": [
            {"entity_type": e, "field": f, "kind": k, "intended": r, "rows": n}
            for (e, f, k, r), n in sorted(differences.items())
        ],
        "unexpected_differences": sum(
            n for (_, _, _, r), n in differences.items() if r == "UNEXPECTED"
        ),
        "differences_to_review": sum(
            n for (_, _, _, r), n in differences.items() if r.startswith("REVIEW")
        ),
    }


def main(argv: list[str] | None = None, *, table: Any | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--table", default=DEFAULT_TABLE)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--max-pages", type=int, help="stop after this many scan pages")
    args = parser.parse_args(argv)
    if table is None:
        import boto3

        table = boto3.resource("dynamodb", region_name=args.region).Table(args.table)
    print(json.dumps(run(table, max_pages=args.max_pages), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
