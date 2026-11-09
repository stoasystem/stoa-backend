"""The authorization allow stream leaves the table once its archive is verified.

Every sensitive route that answers "allowed" appends an audit row, and none of
them ever left: on 2026-11-03 the stream held 9,320 of the table's 15,646 items,
which is how account deletion broke - the attachment retention scan gives up
past 10,000 items and answers `dependency_failure` (#127). That day's prune was
by hand, and nothing stopped the stream coming back.

Deleting by the table's own TTL would be the wrong order: DynamoDB collects an
expired row silently and in its own time, so the evidence could leave before
anything wrote it down. Here each run takes a batch of rows past `RETENTION`,
writes them to the Object Lock bucket as NDJSON, reads that exact version back
and matches its digest, and only then deletes those rows, each delete conditional
on the row still being the one that was archived.

Only `authorization_sensitive_allowed` is archived this way. Denials,
break-glass notices and the account lifecycle stay in the table.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import decimal
import hashlib
from itertools import islice
import json
import logging
from typing import Any

from boto3.dynamodb.conditions import Attr

from stoa.config import Settings
from stoa.db import table as db_table

logger = logging.getLogger(__name__)

AUDIT_ENTITY = "security_audit_event"
#: The one event type this retention archives; every other audit row stays.
ARCHIVED_EVENT_TYPE = "authorization_sensitive_allowed"
#: How long an allow decision stays queryable in the table before its archive
#: becomes the only copy. 90 days covers the quarter a question about a
#: decision is actually asked in; the archive keeps it for good.
RETENTION = timedelta(days=90)
#: Rows one run takes. A daily pass holds the stream down at any rate the
#: platform has seen (239 a day at the 2026-11 reading) and a backlog drains
#: over a few days rather than in one ten-minute function.
ROWS_PER_RUN = 500
#: Pages one run reads looking for them. The stream has no index of its own, so
#: this is a scan; a budget spent without finding a full batch is reported, not
#: raised, because what it did archive is already safe.
PAGE_BUDGET = 200


class ArchiveNotVerified(RuntimeError):
    """The archive did not read back as written; nothing was deleted."""


@dataclass(frozen=True, slots=True)
class AuditArchiveSummary:
    """What one run did. `storage` is "disabled" where no bucket is configured."""

    scanned: int = 0
    due: int = 0
    archived: int = 0
    deleted: int = 0
    refused: int = 0
    key: str | None = None
    digest: str | None = None
    storage: str = "disabled"
    truncated: bool = False


class _Numbers(json.JSONEncoder):
    """DynamoDB hands numbers back as `Decimal`; the archive keeps them exact."""

    def default(self, o: object) -> object:
        if isinstance(o, decimal.Decimal):
            return int(o) if o == o.to_integral_value() else float(o)
        return super().default(o)


def ndjson(rows: Sequence[Mapping[str, Any]]) -> bytes:
    """The rows as one NDJSON body, in key order, so a digest is reproducible."""
    return "".join(
        json.dumps(dict(row), cls=_Numbers, sort_keys=True, ensure_ascii=False) + "\n"
        for row in sorted(rows, key=lambda row: (str(row.get("PK")), str(row.get("SK"))))
    ).encode("utf-8")


def _written_at(row: Mapping[str, Any]) -> datetime | None:
    try:
        moment = datetime.fromisoformat(str(row["created_at"]))
    except (KeyError, TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _due(row: Mapping[str, Any], *, cutoff: datetime) -> bool:
    if row.get("entity_type") != AUDIT_ENTITY or row.get("event_type") != ARCHIVED_EVENT_TYPE:
        return False
    written_at = _written_at(row)
    if written_at is None:
        # A row whose age cannot be read is not one this is sure about.
        logger.warning(
            "security_audit_retention_undated pk=%s sk=%s", row.get("PK"), row.get("SK")
        )
        return False
    return written_at < cutoff


def due_events(
    *, cutoff: datetime, limit: int = ROWS_PER_RUN, table: object | None = None
) -> tuple[list[dict[str, Any]], int, bool]:
    """A batch of rows past the cutoff, how many rows were read, and whether more wait.

    The scan is eventually consistent: a row written in the last moment is not
    one this is after, and each delete states the row it meant (see below).
    """
    due: list[dict[str, Any]] = []
    scanned = 0
    pages = db_table.pages(
        "scan",
        table=table,
        FilterExpression=(
            Attr("entity_type").eq(AUDIT_ENTITY) & Attr("event_type").eq(ARCHIVED_EVENT_TYPE)
        ),
    )
    for page in islice(pages, PAGE_BUDGET):
        scanned += len(page.items)
        for row in page.items:
            if _due(row, cutoff=cutoff):
                due.append(row)
                if len(due) >= limit:
                    return due, scanned, True
        if page.last_key is None:
            return due, scanned, False
    return due, scanned, True


def archive(
    s3: Any, rows: Sequence[Mapping[str, Any]], *, bucket: str, prefix: str, now: datetime
) -> tuple[str, str]:
    """Write the batch, read that version back, and match the digest, or raise."""
    body = ndjson(rows)
    digest = hashlib.sha256(body).hexdigest()
    stamp = now.strftime("%Y-%m-%dT%H-%M-%SZ")
    folder = f"{prefix.rstrip('/')}/" if prefix.strip("/") else ""
    key = f"{folder}security-audit/{now:%Y}/{stamp}-{digest[:12]}.ndjson"
    stored = s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentLength=len(body),
        ContentType="application/x-ndjson",
        ChecksumSHA256=base64.b64encode(bytes.fromhex(digest)).decode("ascii"),
        Metadata={"rows": str(len(rows)), "sha256": digest},
    )
    read_back = s3.get_object(Bucket=bucket, Key=key, VersionId=stored["VersionId"])[
        "Body"
    ].read()
    if hashlib.sha256(read_back).hexdigest() != digest:
        # Byte equality is the whole check: a body that holds other rows, or
        # fewer of them, cannot have this digest.
        raise ArchiveNotVerified(f"digest differs for {key}")
    return key, digest


def archive_due_events(
    *,
    s3: Any,
    settings: Settings,
    now: datetime | None = None,
    limit: int = ROWS_PER_RUN,
    table: object | None = None,
) -> AuditArchiveSummary:
    """Archive a batch of the allow stream past `RETENTION`, then delete that batch."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    bucket = settings.immutable_audit_storage_resource.strip()
    if not bucket:
        # Nowhere to put the evidence means nothing may leave the table.
        return AuditArchiveSummary(storage="disabled")
    cutoff = now - RETENTION
    rows, scanned, truncated = due_events(cutoff=cutoff, limit=limit, table=table)
    if not rows:
        return AuditArchiveSummary(
            scanned=scanned, storage=settings.immutable_audit_storage_mode, truncated=truncated
        )
    key, digest = archive(
        s3,
        rows,
        bucket=bucket,
        prefix=settings.immutable_audit_storage_prefix,
        now=now,
    )
    deleted = refused = 0
    for row in rows:
        try:
            db_table.delete(
                table=table,
                Key={"PK": row["PK"], "SK": row["SK"]},
                # The scan this batch came from is eventually consistent and an
                # event id is a hash of its decision, so the same key can be
                # written again by a decision that repeats. Pinning the moment
                # as well as the kind means a row written since is not the one
                # deleted (card 129 audit).
                ConditionExpression=(
                    Attr("event_type").eq(ARCHIVED_EVENT_TYPE)
                    & Attr("created_at").eq(row["created_at"])
                ),
            )
            deleted += 1
        except db_table.WriteRefused:
            # The row is not the one that was archived any more. It stays, and
            # the archive holds what it held.
            logger.warning(
                "security_audit_retention_delete_refused pk=%s sk=%s",
                row["PK"],
                row["SK"],
            )
            refused += 1
    logger.info(
        "security_audit_retention scanned=%d due=%d archived=%d deleted=%d refused=%d key=%s",
        scanned,
        len(rows),
        len(rows),
        deleted,
        refused,
        key,
    )
    return AuditArchiveSummary(
        scanned=scanned,
        due=len(rows),
        archived=len(rows),
        deleted=deleted,
        refused=refused,
        key=key,
        digest=digest,
        storage=settings.immutable_audit_storage_mode,
        truncated=truncated,
    )
