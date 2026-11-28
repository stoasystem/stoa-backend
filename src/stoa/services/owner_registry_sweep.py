"""The owner registry's audit and backfill: one walk over the table (#397, PR 2).

Deletion is meant to find an account's rows through its derived partitions and
its registry rows (`stoa.db.owner_registry`) instead of scanning the table. That
is only as good as the registry, so one full walk - daily, never per deletion -
checks two things for every account at once:

1. **Missing registrations.** For every row, the accounts the data type
   catalog says it points to (`data_catalog.mentions`, owner or reference:
   deletion removes the one and scrubs the other, #588), less the account's
   own derived partitions and the partitions registered under it (#590). A
   deletion reads only those, so it would never see the row. These are what
   stop new deletions being accepted (`record_run`, `registry_path_ready`) and
   raise the alarm. A field the catalog lists as no pointer (`created_by`,
   `invited_by`, `actor_id`) is a mention: no deletion acts on it, nothing
   registers it, and it is not counted (#586 decision 1).
2. **Leftovers of deleted accounts.** A row the catalog still says points to
   an account whose fence says `deleted`, other than what deletion keeps on
   purpose (the fence, its commands, its tombstones) - plus any registry row
   still filed under it.

3. **Stale references into a deleted account.** A registry row another
   account holds for one of a deleted account's derived partitions
   (`USER#{admin}/REFERENCED_IN#USER#{deleted}`): it was true while that
   account's rows named the holder, and nothing removes it when they go. It
   costs the holder's own deletion one empty read and keeps the deleted
   account's id in a key. Listed only when the walk finished and saw no row in
   that partition that still names the holder.

The walk is two scans. The first collects the accounts (their fence rows) and
the registry. The second checks every row and, for a backfill, writes the
missing registry rows. Both are report-only unless `write=True`; nothing is
deleted or re-queued here. `remove_stale_references` is the one removal, and
only the daily job calls it.

Rows of a kind the catalog does not know point to no account, so they are
never a finding; they are counted on their own line, by `entity_type` (or key
family, for a row written without one), because a kind the catalog misses is
one no deletion takes.

The report holds counts by key family (`CONV/MSG`) and up to `SAMPLE_LIMIT`
keys per finding - keys, never row contents.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from itertools import islice
from typing import Any

from stoa.db import data_catalog, owner_registry
from stoa.db import table as db_table
from stoa.db.repositories import (
    account_deletion_repo,
)

logger = logging.getLogger(__name__)

SAMPLE_LIMIT = 20

# Partitions no deletion acts on, whatever the catalog says their rows point
# to: evidence kept on purpose and the deletion's own bookkeeping. A row here
# is neither a missing registration nor a leftover. (Not a rule of whose a row
# is: that is the catalog's, and so is what a deletion does with it.)
# The shared practice content lives under the exact key `PRACTICE` and names
# no account; the old untyped `PRACTICE#` / `PRACTICE_ATTEMPT#` /
# `PRACTICE_PROGRESS#` rows do, and the deletion takes them as the catalog
# says, so they are checked like any other since #590.
NOT_OWNED_PREFIXES: tuple[str, ...] = (
    "SECURITY_AUDIT#",
    "AUDIT_RETENTION#",
    "ACCOUNT_DELETION_PENDING",
    "JOB#",
    "PRACTICE_CHALLENGE_LOOKUP",
    "CURRICULUM_METRIC#",
    "CURRICULUM_VERSION#",
    "CURRICULUM_MANIFEST#",
    "CURRICULUM_AUDIT#",
    "CURRICULUM_POINTER#",
    "CURRICULUM_MIGRATION#",
    # The reviewed `teacher_application` exclusion: no deletion acts on
    # applications, invitations or activation commands (the activation
    # command carries the new teacher's `user_id`, and stays on purpose).
    "TEACHER_APPLICATION#",
    "TEACHER_INVITATION#",
    "TEACHER_ACTIVATION#",
)

# Where the daily run leaves its result: what acceptance reads before it takes
# a new deletion (`account_deletion_service.registry_path_ready`, #397).
RUN_MARKER_KEY = {"PK": "JOB#owner_registry_sweep", "SK": "LAST_RUN"}

# Rows deletion keeps under the deleted account's own partition: its own
# bookkeeping, down to the receipt that the identity provider was told to revoke
# the account (`PROVIDER_REVOKE#{generation}` - an id, a status, no content).
_RETAINED_ACCOUNT_SK_PREFIXES = (
    "ACCOUNT_FENCE",
    "DELETE_COMMAND#",
    "DELETE_ACCOUNTING#",
    "PROVIDER_REVOKE#",
)


@dataclass
class SweepReport:
    accounts: int = 0
    deleted_accounts: int = 0
    rows_scanned: int = 0
    registry_rows: int = 0
    # Missing (account, partition) registrations, counted once each, by the
    # family of the first row that showed them.
    unregistered: Counter[str] = field(default_factory=Counter)
    unregistered_samples: list[dict[str, str]] = field(default_factory=list)
    # Rows of a kind the catalog does not know, by `entity_type` or key family.
    unknown: Counter[str] = field(default_factory=Counter)
    registry_written: int = 0
    leftovers: Counter[str] = field(default_factory=Counter)
    leftover_samples: list[dict[str, str]] = field(default_factory=list)
    registry_of_deleted_accounts: int = 0
    # Keys of registry rows that point into a deleted account's partitions.
    stale_references: list[dict[str, str]] = field(default_factory=list)
    last_key: dict[str, Any] | None = None
    complete: bool = False

    @property
    def registry_complete(self) -> bool:
        return self.complete and not self.unregistered

    @property
    def leftover_free(self) -> bool:
        return self.complete and not self.leftovers

    def as_dict(self) -> dict[str, Any]:
        return {
            "accounts": self.accounts,
            "deleted_accounts": self.deleted_accounts,
            "rows_scanned": self.rows_scanned,
            "registry_rows": self.registry_rows,
            "missing_registrations": sum(self.unregistered.values()),
            "unregistered_by_family": dict(sorted(self.unregistered.items())),
            "unregistered_samples": self.unregistered_samples,
            "rows_unknown_to_catalog": sum(self.unknown.values()),
            "unknown_to_catalog_by_kind": dict(sorted(self.unknown.items())),
            "registry_written": self.registry_written,
            "leftover_rows": sum(self.leftovers.values()),
            "leftovers_by_family": dict(sorted(self.leftovers.items())),
            "leftover_samples": self.leftover_samples,
            "registry_rows_of_deleted_accounts": self.registry_of_deleted_accounts,
            "stale_references": len(self.stale_references),
            "complete": self.complete,
            "registry_complete": self.registry_complete,
            "leftover_free": self.leftover_free,
            "last_key": self.last_key,
        }


@dataclass(frozen=True, slots=True)
class Census:
    """What the first scan learned: who the accounts are and what they registered."""

    active: frozenset[str]
    deleted: frozenset[str]
    registry: frozenset[tuple[str, str]]  # (account, registered partition)

    @property
    def accounts(self) -> frozenset[str]:
        return self.active | self.deleted


def family(item: Mapping[str, Any]) -> str:
    """A key reduced to its prefixes: `CONV/MSG`, never whose conversation it is."""
    pk = str(item.get("PK") or "")
    sk = str(item.get("SK") or "")
    return f"{pk.split('#')[0] or '?'}/{sk.split('#')[0] or '?'}"


def kind(item: Mapping[str, Any]) -> str:
    """A row's `entity_type`, or its key family for a row written without one."""
    entity_type = item.get("entity_type")
    if isinstance(entity_type, str) and entity_type:
        return entity_type
    return f"(untyped) {family(item)}"


def census(rows: Iterable[Mapping[str, Any]]) -> Census:
    active: set[str] = set()
    deleted: set[str] = set()
    registry: set[tuple[str, str]] = set()
    for item in rows:
        pk = str(item.get("PK") or "")
        if not pk.startswith("USER#"):
            continue
        account = pk[len("USER#") :]
        if item.get("SK") == "ACCOUNT_FENCE":
            (deleted if item.get("status") == "deleted" else active).add(account)
        elif owner_registry.is_registry_row(item):
            partition = item.get("registered_pk")
            if isinstance(partition, str) and partition:
                registry.add((account, partition))
    deleted -= active
    return Census(frozenset(active), frozenset(deleted), frozenset(registry))


def _not_owned(pk: str) -> bool:
    return pk.startswith(NOT_OWNED_PREFIXES)


def check_row(
    item: Mapping[str, Any], seen: Census
) -> tuple[list[tuple[str, str]], bool]:
    """The registry rows this row lacks, and whether it is a deleted account's leftover.

    Both from the catalog alone (#590): the active accounts it points to that
    have not registered its partition, each with the role the catalog gives,
    and whether it still points to a deleted account.
    """
    pk = str(item.get("PK") or "")
    if not pk or _not_owned(pk) or owner_registry.is_registry_row(item):
        return [], False
    named = data_catalog.mentions(item)
    missing = [
        (account, str(role))
        for account, role in named.items()
        if account in seen.active
        and not owner_registry.is_derived_for(pk, account)
        and (account, pk) not in seen.registry
    ]
    leftover = any(
        _is_leftover(item, account) for account in named if account in seen.deleted
    )
    return missing, leftover


def _is_leftover(item: Mapping[str, Any], account: str) -> bool:
    if account_deletion_repo.is_deletion_tombstone(item):
        return False
    return not (
        item.get("PK") == f"USER#{account}"
        and str(item.get("SK") or "").startswith(_RETAINED_ACCOUNT_SK_PREFIXES)
    )


def record_run(report: SweepReport, *, now_iso: str, table: object | None = None) -> None:
    """Leave the run's result where acceptance reads it (`RUN_MARKER_KEY`).

    Counts only, no keys. The one write the daily job makes.
    """
    db_table.put(
        table=table,
        Item={
            **RUN_MARKER_KEY,
            "entity_type": "owner_registry_sweep_run",
            "completed_at": now_iso,
            "complete": report.complete,
            "rows_scanned": report.rows_scanned,
            "missing_registrations": sum(report.unregistered.values()),
            "rows_unknown_to_catalog": sum(report.unknown.values()),
            "leftover_rows": sum(report.leftovers.values()),
        },
    )


def scan_pages(
    *, table: object | None = None, start: Mapping[str, Any] | None = None
) -> Iterator[db_table.Page]:
    """The table, strongly, one 1 MB page at a time."""
    return db_table.pages("scan", start=start, table=table, ConsistentRead=True)


def run(
    *,
    table: object | None = None,
    write: bool = False,
    start: Mapping[str, Any] | None = None,
    max_pages: int | None = None,
    on_page: Callable[[SweepReport], None] | None = None,
    remaining_seconds: Callable[[], float] | None = None,
    min_remaining_seconds: float = 30.0,
) -> SweepReport:
    """Census, then the check (and, with `write`, the backfill) from `start`.

    A backfill writes the missing registrations only, each in the role the
    catalog gives (`check_row`).

    Resumable: `report.last_key` is where the second scan stopped (`None` once
    it reached the end, with `report.complete`). Handing it back as `start`
    goes on from there; the census is always taken afresh. Idempotent: every
    write is the same unconditional registry Put the fenced write makes.
    """
    target = table if table is not None else db_table.table()
    seen = census(item for page in scan_pages(table=target) for item in page.items)
    report = SweepReport(
        accounts=len(seen.accounts),
        deleted_accounts=len(seen.deleted),
        registry_rows=len(seen.registry),
    )
    registry = set(seen.registry)
    # A deleted account's derived partitions, the registry rows other accounts
    # hold for them, and every (account, partition) some row still names.
    gone_partitions = {
        partition
        for account in seen.deleted
        for partition in owner_registry.derived_partitions(account)
    }
    held: dict[tuple[str, str], dict[str, str]] = {}
    named_in: set[tuple[str, str]] = set()
    pages = scan_pages(table=target, start=start)
    if max_pages is not None:
        pages = islice(pages, max_pages)
    for page in pages:
        for item in page.items:
            report.rows_scanned += 1
            if owner_registry.is_registry_row(item):
                pk = str(item.get("PK") or "")
                holder = pk[len("USER#") :] if pk.startswith("USER#") else ""
                if holder in seen.deleted:
                    report.registry_of_deleted_accounts += 1
                elif holder and item.get("registered_pk") in gone_partitions:
                    held[(holder, str(item["registered_pk"]))] = {
                        "PK": pk,
                        "SK": str(item.get("SK")),
                    }
                continue
            if data_catalog.data_type_of(item) is None:
                report.unknown[kind(item)] += 1
            missing, leftover = check_row(item, seen)
            key = {"PK": str(item.get("PK")), "SK": str(item.get("SK"))}
            if key["PK"] in gone_partitions:
                named_in.update(
                    (account, key["PK"])
                    for account in data_catalog.mentions(item)
                    if account in seen.active
                )
            if leftover:
                report.leftovers[family(item)] += 1
                if len(report.leftover_samples) < SAMPLE_LIMIT:
                    report.leftover_samples.append(key)
            for account, role in missing:
                if (account, key["PK"]) in registry:
                    continue
                report.unregistered[family(item)] += 1
                if len(report.unregistered_samples) < SAMPLE_LIMIT:
                    report.unregistered_samples.append({**key, "account": account, "role": role})
                if write:
                    db_table.put(
                        table=target,
                        Item=owner_registry.registry_item(account, key["PK"], role),
                    )
                    report.registry_written += 1
                registry.add((account, key["PK"]))
        report.last_key = dict(page.last_key) if page.last_key is not None else None
        if on_page is not None:
            on_page(report)
        if page.last_key is None:
            report.complete = True
            # Only a whole walk can say that nothing in the partition names the
            # holder any more; a resumed one did not see the rows before `start`.
            if start is None:
                report.stale_references = [
                    key for pair, key in sorted(held.items()) if pair not in named_in
                ]
            break
        if remaining_seconds is not None and remaining_seconds() < min_remaining_seconds:
            break
    logger.info(
        "owner_registry_sweep accounts=%d deleted=%d rows=%d unregistered=%d unknown=%d "
        "written=%d leftovers=%d deleted_registry=%d stale_references=%d complete=%s",
        report.accounts,
        report.deleted_accounts,
        report.rows_scanned,
        sum(report.unregistered.values()),
        sum(report.unknown.values()),
        report.registry_written,
        sum(report.leftovers.values()),
        report.registry_of_deleted_accounts,
        len(report.stale_references),
        report.complete,
    )
    return report


def remove_stale_references(report: SweepReport, *, table: object | None = None) -> int:
    """Delete the registry rows `report.stale_references` lists; returns how many went.

    Each delete is conditional on the row still being a registry row, so a key
    that has since become something else is left alone. Registry rows only: no
    account's data is touched, and a row removed in error would show as a
    missing registration on the next walk.
    """
    target = table if table is not None else db_table.table()
    removed = 0
    for key in report.stale_references:
        try:
            db_table.delete(
                table=target,
                Key=dict(key),
                ConditionExpression="entity_type = :registry",
                ExpressionAttributeValues={":registry": owner_registry.ENTITY_TYPE},
            )
        except db_table.WriteRefused:
            continue
        removed += 1
    return removed
