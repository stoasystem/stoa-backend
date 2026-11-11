"""The owner registry's audit and backfill: one walk over the table (#397, PR 2).

Deletion is meant to find an account's rows through its derived partitions and
its registry rows (`stoa.db.owner_registry`) instead of scanning the table. That
is only as good as the registry, so one full walk - daily, never per deletion -
checks two things for every account at once:

1. **Unregistered rows.** A row that names an account (any string attribute,
   or a `#`/`:`/`/`-separated part of one, equal to an account id) in a
   partition that is neither one of that account's derived partitions nor
   registered under it. The fenced write registers the owner and its `also=`
   accounts; a row that names anyone else, or that was written before the
   dual-write or by a writer outside `fenced`, shows up here.
2. **Leftovers of deleted accounts.** A row the deletion's own matcher
   (`account_deletion_repo._targets_user`) still takes for an account whose
   fence says `deleted`, other than what deletion keeps on purpose (the fence,
   its commands, its tombstones) - plus any registry row still filed under it.

The walk is two scans. The first collects the accounts (their fence rows) and
the registry. The second checks every row and, for a backfill, writes the
missing registry rows. Both are report-only unless `write=True`; nothing is
ever deleted or re-queued here.

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

from stoa.db import owner_registry
from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo, curriculum_analytics_repo

logger = logging.getLogger(__name__)

SAMPLE_LIMIT = 20

# Partitions that hold no account's data, whatever ids they mention: evidence
# kept on purpose, the deletion's own bookkeeping, and shared content. A row
# here is neither an unregistered row nor a leftover.
NOT_OWNED_PREFIXES: tuple[str, ...] = (
    "SECURITY_AUDIT#",
    "AUDIT_RETENTION#",
    "ACCOUNT_DELETION_PENDING",
    "JOB#",
    "PRACTICE",
    "CURRICULUM_METRIC#",
    "CURRICULUM_VERSION#",
    "CURRICULUM_MANIFEST#",
    "CURRICULUM_AUDIT#",
    "CURRICULUM_POINTER#",
    "CURRICULUM_MIGRATION#",
    # The reviewed `teacher_application` exclusion: no deletion branch acts
    # on applications, invitations or activation commands (the activation
    # command carries the new teacher's `user_id`, and stays on purpose).
    "TEACHER_APPLICATION#",
    "TEACHER_INVITATION#",
    "TEACHER_ACTIVATION#",
)

# Where the daily run leaves its result: what acceptance reads before it seals
# a deletion for the registry path (#397).
RUN_MARKER_KEY = {"PK": "JOB#owner_registry_sweep", "SK": "LAST_RUN"}

# Rows deletion keeps under the deleted account's own partition.
_RETAINED_ACCOUNT_SK_PREFIXES = ("ACCOUNT_FENCE", "DELETE_COMMAND#", "DELETE_ACCOUNTING#")

# Where an id names the owner rather than someone the row only mentions.
_OWNER_ATTRIBUTES = frozenset(
    {"owner_id", "student_id", "user_id", "child_id", "child_user_id", "beneficiary_id"}
)

_SEPARATORS = ("#", ":", "/")


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
    registry_written: int = 0
    leftovers: Counter[str] = field(default_factory=Counter)
    leftover_samples: list[dict[str, str]] = field(default_factory=list)
    registry_of_deleted_accounts: int = 0
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
            "registry_written": self.registry_written,
            "leftover_rows": sum(self.leftovers.values()),
            "leftovers_by_family": dict(sorted(self.leftovers.items())),
            "leftover_samples": self.leftover_samples,
            "registry_rows_of_deleted_accounts": self.registry_of_deleted_accounts,
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
    # Curriculum signals written before the owner manifest name their student
    # only as `metadata.studentHash`, a hash of the id; deletion matches them
    # by that hash, so the sweep does too.
    legacy_hashes: Mapping[str, str] = field(default_factory=dict)

    @property
    def accounts(self) -> frozenset[str]:
        return self.active | self.deleted


def family(item: Mapping[str, Any]) -> str:
    """A key reduced to its prefixes: `CONV/MSG`, never whose conversation it is."""
    pk = str(item.get("PK") or "")
    sk = str(item.get("SK") or "")
    return f"{pk.split('#')[0] or '?'}/{sk.split('#')[0] or '?'}"


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
    hashes = {
        curriculum_analytics_repo._legacy_student_hash(account): account
        for account in active | deleted
    }
    return Census(frozenset(active), frozenset(deleted), frozenset(registry), hashes)


def _legacy_signal_account(item: Mapping[str, Any], seen: Census) -> str | None:
    if item.get("entity_type") != curriculum_analytics_repo.SIGNAL_ENTITY:
        return None
    metadata = item.get("metadata")
    digest = metadata.get("studentHash") if isinstance(metadata, Mapping) else None
    return seen.legacy_hashes.get(digest) if isinstance(digest, str) else None


def named_accounts(item: Mapping[str, Any], accounts: frozenset[str]) -> dict[str, str]:
    """Every account the row names, each with the role it is named in."""
    found: dict[str, str] = {}

    def visit(value: object, attribute: str, depth: int) -> None:
        if isinstance(value, str):
            for token in _tokens(value):
                if token in accounts:
                    role = (
                        owner_registry.ROLE_OWNER
                        if attribute in _OWNER_ATTRIBUTES
                        else owner_registry.ROLE_REFERENCE
                    )
                    if found.get(token) != owner_registry.ROLE_OWNER:
                        found[token] = role
        elif depth < 4 and isinstance(value, Mapping):
            for name, member in value.items():
                if isinstance(name, str) and name in accounts:
                    found.setdefault(name, owner_registry.ROLE_REFERENCE)
                visit(member, attribute, depth + 1)
        elif depth < 4 and isinstance(value, (list, tuple, set, frozenset)):
            for member in value:
                visit(member, attribute, depth + 1)

    for name, value in item.items():
        if name == "PK":
            continue
        visit(value, name, 0)
    return found


def _tokens(value: str) -> set[str]:
    parts = {value}
    for separator in _SEPARATORS:
        parts = {piece for part in parts for piece in part.split(separator)}
    return parts | {value}


def _not_owned(pk: str) -> bool:
    return pk.startswith(NOT_OWNED_PREFIXES)


def check_row(
    item: Mapping[str, Any], seen: Census
) -> tuple[list[tuple[str, str]], bool]:
    """The registry rows this row lacks, and whether it is a deleted account's leftover."""
    pk = str(item.get("PK") or "")
    if not pk or _not_owned(pk) or owner_registry.is_registry_row(item):
        return [], False
    missing: list[tuple[str, str]] = []
    named = named_accounts(item, seen.active)
    legacy = _legacy_signal_account(item, seen)
    if legacy in seen.active:
        named[legacy] = owner_registry.ROLE_OWNER
    for account, role in named.items():
        if owner_registry.is_derived_for(pk, account) or (account, pk) in seen.registry:
            continue
        missing.append((account, role))
    leftover = legacy in seen.deleted or any(
        _is_leftover(item, account) for account in seen.deleted
    )
    return missing, leftover


def _is_leftover(item: Mapping[str, Any], account: str) -> bool:
    if account_deletion_repo.is_deletion_tombstone(item):
        return False
    if item.get("PK") == f"USER#{account}" and str(item.get("SK") or "").startswith(
        _RETAINED_ACCOUNT_SK_PREFIXES
    ):
        return False
    try:
        return account_deletion_repo._targets_user(item, account)
    except account_deletion_repo.AccountDeletionConflict:
        return False


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
    pages = scan_pages(table=target, start=start)
    if max_pages is not None:
        pages = islice(pages, max_pages)
    for page in pages:
        for item in page.items:
            report.rows_scanned += 1
            if owner_registry.is_registry_row(item):
                pk = str(item.get("PK") or "")
                if pk.startswith("USER#") and pk[len("USER#") :] in seen.deleted:
                    report.registry_of_deleted_accounts += 1
                continue
            missing, leftover = check_row(item, seen)
            key = {"PK": str(item.get("PK")), "SK": str(item.get("SK"))}
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
            break
        if remaining_seconds is not None and remaining_seconds() < min_remaining_seconds:
            break
    logger.info(
        "owner_registry_sweep accounts=%d deleted=%d rows=%d unregistered=%d written=%d "
        "leftovers=%d deleted_registry=%d complete=%s",
        report.accounts,
        report.deleted_accounts,
        report.rows_scanned,
        sum(report.unregistered.values()),
        report.registry_written,
        sum(report.leftovers.values()),
        report.registry_of_deleted_accounts,
        report.complete,
    )
    return report
