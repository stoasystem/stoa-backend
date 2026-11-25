"""The student curriculum, read once per container until it changes (card 133).

Every student page judged against the curriculum - the star map, its
neighbourhood, the catalog - read the whole `PRACTICE` partition on every
request: subjects, topics, units and two thousand lessons, four paged queries
that come out the same for every student. A `Snapshot` keeps those rows, and
the challenge rows of the lessons written before they carried an exercise
index, for as long as they can be trusted:

- One consistent `GetItem` of the catalog stamp (`STAMP_KEY`) per request. A
  snapshot taken under another stamp is not used: whoever changes the
  curriculum writes a new one, and the next request reads it all again.
- A snapshot is never older than `STAMPED_TTL` while the stamp exists, nor
  than `UNSTAMPED_TTL` while it does not - the bound for a writer that does not
  write the stamp.
- A snapshot belongs to the table it was read from.

Only the student view is kept. A preview reader (`include_preview`) reads the
table every time.

The rows are shared: what is handed out is built from them, never them.

`run_all` reads partitions side by side. The boto3 resource is not thread
safe, so a worker thread reads the real table through a session of its own
(`db_table.worker_table`); the read meter of the request follows each
call into its worker through a copy of the request's context.
"""

from __future__ import annotations

import contextvars
import logging
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


from stoa.db import table as db_table
from stoa.db.repositories import practice_repo
from stoa.services import practice_projection_service

STAMP_KEY = {"PK": "PRACTICE_CATALOG", "SK": "STAMP"}
STAMP_ENTITY = "curriculum_catalog_stamp"
STAMPED_TTL = 300.0
UNSTAMPED_TTL = 60.0

_clock: Callable[[], float] = time.monotonic

logger = logging.getLogger(__name__)


# -- reading side by side ----------------------------------------------------------------

POOL_SIZE = 10
_pool: ThreadPoolExecutor | None = None
_pool_lock = threading.Lock()
_local = threading.local()


def _mark_worker() -> None:
    _local.worker = True


def _executor() -> ThreadPoolExecutor:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ThreadPoolExecutor(
                max_workers=POOL_SIZE, thread_name_prefix="curriculum-read", initializer=_mark_worker
            )
        return _pool


def thread_table() -> Any | None:
    """The table a worker thread reads, when it must not share the request's.

    None outside a worker, and for a test double, which is shared as it is.
    """
    if not getattr(_local, "worker", False):
        return None
    return db_table.worker_table()


def with_table(read: Callable[..., Any], *args: Any) -> Any:
    """`read(*args)`, on this worker's own table when it has one."""
    own = thread_table()
    return read(*args) if own is None else read(*args, table=own)


def run_all(calls: Sequence[Callable[[], Any]]) -> list[Any]:
    """Each call's result, or the exception it raised, in order; side by side.

    The first runs on this thread, so it may itself read side by side.
    """
    if len(calls) < 2 or getattr(_local, "worker", False):
        return [_outcome(call) for call in calls]
    pool = _executor()
    futures = [pool.submit(contextvars.copy_context().run, _outcome, call) for call in calls[1:]]
    return [_outcome(calls[0]), *(future.result() for future in futures)]


def _outcome(call: Callable[[], Any]) -> Any:
    try:
        return call()
    except Exception as error:  # noqa: BLE001 - handed back to the caller
        return error


# -- the snapshot ------------------------------------------------------------------------


@dataclass(eq=False)
class Snapshot:
    """The student curriculum's rows as read once, and what is built from them."""

    subjects: tuple[dict[str, Any], ...]
    topics: tuple[dict[str, Any], ...]
    units: tuple[dict[str, Any], ...]
    lessons: tuple[dict[str, Any], ...]
    # A visible lesson without an exercise index: its challenge rows, or why not.
    challenges: Mapping[str, list[dict[str, Any]] | Exception]
    built: dict[Any, Any] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def lesson_challenges(self, lesson_id: str) -> list[dict[str, Any]] | None:
        """A lesson's challenge rows, when they were read with the snapshot."""
        found = self.challenges.get(lesson_id)
        if isinstance(found, Exception):
            raise found
        return found

    def once(self, key: Any, build: Callable[[], Any]) -> Any:
        with self.lock:
            if key not in self.built:
                self.built[key] = build()
            return self.built[key]


@dataclass(eq=False)
class _Kept:
    table: object
    stamp: str | None
    taken_at: float
    snapshot: Snapshot


_kept: _Kept | None = None
_kept_lock = threading.Lock()


def _stamp(table: object) -> tuple[bool, str | None]:
    """Whether the stamp could be read, and what it says."""
    try:
        row = db_table.get(table=table, Key=dict(STAMP_KEY), ConsistentRead=True)
    except Exception:  # noqa: BLE001 - then nothing kept is trusted
        return False, None
    if not isinstance(row, Mapping):
        return True, None
    value = row.get("stamp")
    return True, str(value) if value else None


def current() -> Snapshot:
    """The student curriculum: the kept snapshot while it holds, else read now."""
    global _kept
    table = db_table.table()
    readable, stamp = _stamp(table)
    now = _clock()
    kept = _kept
    if (
        readable
        and kept is not None
        and kept.table is table
        and kept.stamp == stamp
        and now - kept.taken_at < (STAMPED_TTL if stamp else UNSTAMPED_TTL)
    ):
        return kept.snapshot
    snapshot = read()
    if readable:
        with _kept_lock:
            _kept = _Kept(table=table, stamp=stamp, taken_at=now, snapshot=snapshot)
    return snapshot


def forget() -> None:
    """Drop the kept snapshot; the next request reads the curriculum again."""
    global _kept
    with _kept_lock:
        _kept = None


def touch_catalog_stamp(table: object | None = None) -> None:
    """Write a new catalog stamp after the student curriculum changed.

    A failed write is logged, never raised: the change itself has landed.
    """
    forget()
    try:
        db_table.put(
            table=table,
            Item={
                **STAMP_KEY,
                "entity_type": STAMP_ENTITY,
                "stamp": uuid.uuid4().hex,
                "updated_at": datetime.now(UTC).isoformat(),
            },
        )
    except Exception:  # noqa: BLE001 - the stamp must not fail the write it follows
        logger.warning("curriculum_catalog_stamp_failed", exc_info=True)


def read() -> Snapshot:
    """The four kinds of row side by side, then the unindexed lessons' challenges."""
    subjects, topics, units, lessons = _raised(
        run_all(
            [
                lambda: with_table(practice_repo.get_subjects),
                lambda: with_table(practice_repo.get_topics),
                lambda: with_table(practice_repo.get_all_units),
                lambda: with_table(practice_repo.get_lessons),
            ]
        )
    )
    unindexed = [
        str(lesson.get("lesson_id") or "")
        for lesson in lessons
        if practice_repo.indexed_exercises(lesson) is None
        and lesson.get("lesson_id")
        and practice_projection_service.content_state(lesson) == "active"
    ]
    found = run_all(
        [
            (lambda lesson_id=lesson_id: with_table(practice_repo.get_challenges, lesson_id))
            for lesson_id in unindexed
        ]
    )
    return Snapshot(
        subjects=tuple(subjects),
        topics=tuple(topics),
        units=tuple(units),
        lessons=tuple(lessons),
        challenges=dict(zip(unindexed, found, strict=True)),
    )


def _raised(results: list[Any]) -> list[Any]:
    for result in results:
        if isinstance(result, Exception):
            raise result
    return results
