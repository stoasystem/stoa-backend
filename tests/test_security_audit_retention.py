"""The allow stream leaves the table only after a verified archive (card 129)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import BytesIO
import hashlib
import json

import pytest

from fakes.s3 import MultipartS3
from stoa import aws
from stoa.aws import Kind
from stoa.config import Settings
from stoa.services import security_audit_retention as retention


BUCKET = "stoa-immutable-evidence-test"
NOW = datetime(2026, 11, 9, 7, 0, tzinfo=UTC)


def _settings(**overrides: object) -> Settings:
    fields: dict[str, object] = {
        "immutable_audit_storage_mode": "cdk_managed",
        "immutable_audit_storage_resource": BUCKET,
        "immutable_audit_storage_prefix": "audit-retention/",
    }
    fields.update(overrides)
    return Settings(**fields)


def _event(
    fingerprint: str,
    event_id: str,
    *,
    age_days: float,
    event_type: str = retention.ARCHIVED_EVENT_TYPE,
    dated: bool = True,
) -> dict[str, object]:
    row = {
        "PK": f"SECURITY_AUDIT#{fingerprint}",
        "SK": f"EVENT#{event_id}",
        "entity_type": "security_audit_event",
        "event_id": event_id,
        "event_type": event_type,
        "actor_fingerprint": fingerprint,
        "action": "read",
        "purpose": "support",
        "result_code": "allowed" if event_type == retention.ARCHIVED_EVENT_TYPE else "denied",
    }
    if dated:
        row["created_at"] = (NOW - timedelta(days=age_days)).isoformat()
    return row


def _keys(table: object) -> set[tuple[str, str]]:
    return set(table.rows)


def _archived(bucket: MultipartS3) -> list[dict[str, object]]:
    (stored,) = bucket.objects.values()
    return [json.loads(line) for line in stored["data"].decode().splitlines() if line.strip()]


def test_due_allow_rows_are_archived_and_leave_the_table(fake_table):
    old = [_event("a", f"old-{index}", age_days=120) for index in range(3)]
    recent = _event("a", "recent", age_days=10)
    denial = _event("b", "denied", age_days=200, event_type="authorization_denied")
    fake_table.seed(*old, recent, denial)
    bucket = MultipartS3(BUCKET)

    summary = retention.archive_due_events(s3=bucket, settings=_settings(), now=NOW)

    assert (summary.due, summary.archived, summary.deleted, summary.refused) == (3, 3, 3, 0)
    assert summary.truncated is False
    assert sorted(row["event_id"] for row in _archived(bucket)) == ["old-0", "old-1", "old-2"]
    assert _keys(fake_table) == {
        ("SECURITY_AUDIT#a", "EVENT#recent"),
        ("SECURITY_AUDIT#b", "EVENT#denied"),
    }
    assert summary.key.startswith("audit-retention/security-audit/2026/")
    assert summary.digest == hashlib.sha256(
        next(iter(bucket.objects.values()))["data"]
    ).hexdigest()


def test_the_archive_holds_the_row_as_the_table_gave_it(fake_table):
    fake_table.seed(_event("a", "old", age_days=120))
    bucket = MultipartS3(BUCKET)

    retention.archive_due_events(s3=bucket, settings=_settings(), now=NOW)

    (row,) = _archived(bucket)
    assert row == {
        "PK": "SECURITY_AUDIT#a",
        "SK": "EVENT#old",
        "entity_type": "security_audit_event",
        "event_id": "old",
        "event_type": retention.ARCHIVED_EVENT_TYPE,
        "actor_fingerprint": "a",
        "action": "read",
        "purpose": "support",
        "result_code": "allowed",
        "created_at": (NOW - timedelta(days=120)).isoformat(),
    }


def test_without_a_bucket_nothing_is_read_or_deleted(fake_table):
    fake_table.seed(_event("a", "old", age_days=120))
    bucket = MultipartS3(BUCKET)

    summary = retention.archive_due_events(
        s3=bucket,
        settings=_settings(immutable_audit_storage_resource="", immutable_audit_storage_mode="disabled"),
        now=NOW,
    )

    assert summary.storage == "disabled"
    assert (summary.scanned, summary.archived, summary.deleted) == (0, 0, 0)
    assert bucket.objects == {}
    assert _keys(fake_table) == {("SECURITY_AUDIT#a", "EVENT#old")}


def test_an_archive_that_reads_back_differently_deletes_nothing(fake_table):
    fake_table.seed(*[_event("a", f"old-{index}", age_days=120) for index in range(3)])

    class Tampered(MultipartS3):
        """Hands back as many rows as were written, with one word changed."""

        def get_object(self, **kwargs: object) -> dict[str, object]:
            answer = super().get_object(**kwargs)
            body = answer["Body"].read().replace(b'"purpose": "support"', b'"purpose": "payroll"')
            answer["Body"] = BytesIO(body)
            return answer

    bucket = Tampered(BUCKET)

    with pytest.raises(retention.ArchiveNotVerified):
        retention.archive_due_events(s3=bucket, settings=_settings(), now=NOW)

    assert len(_keys(fake_table)) == 3


def test_an_archive_missing_a_row_deletes_nothing(fake_table):
    """Fewer rows than were handed over, and the read-back is a plausible archive."""
    fake_table.seed(*[_event("a", f"old-{index}", age_days=120) for index in range(3)])

    class Dropping(MultipartS3):
        def get_object(self, **kwargs: object) -> dict[str, object]:
            answer = super().get_object(**kwargs)
            lines = answer["Body"].read().splitlines(keepends=True)
            answer["Body"] = BytesIO(b"".join(lines[:-1]))
            return answer

    bucket = Dropping(BUCKET)

    with pytest.raises(retention.ArchiveNotVerified):
        retention.archive_due_events(s3=bucket, settings=_settings(), now=NOW)

    assert len(_keys(fake_table)) == 3


def test_each_delete_is_conditional_on_the_row_archived(fake_table):
    fake_table.seed(_event("a", "old", age_days=120))
    bucket = MultipartS3(BUCKET)

    retention.archive_due_events(s3=bucket, settings=_settings(), now=NOW)

    deletes = [request for name, request in fake_table.requests if name == "delete_item"]
    assert deletes and all("ConditionExpression" in request for request in deletes)


def test_a_batch_is_capped_and_says_more_are_waiting(fake_table):
    fake_table.seed(*[_event("a", f"old-{index}", age_days=120) for index in range(5)])
    bucket = MultipartS3(BUCKET)

    summary = retention.archive_due_events(s3=bucket, settings=_settings(), now=NOW, limit=2)

    assert (summary.due, summary.deleted, summary.truncated) == (2, 2, True)
    assert len(_keys(fake_table)) == 3


def test_a_row_without_a_date_stays(fake_table):
    fake_table.seed(_event("a", "undated", age_days=0, dated=False))
    bucket = MultipartS3(BUCKET)

    summary = retention.archive_due_events(s3=bucket, settings=_settings(), now=NOW)

    assert (summary.due, summary.deleted) == (0, 0)
    assert bucket.objects == {}
    assert _keys(fake_table) == {("SECURITY_AUDIT#a", "EVENT#undated")}


def test_a_row_inside_the_retention_stays(fake_table):
    inside = retention.RETENTION - timedelta(days=1)
    fake_table.seed(_event("a", "young", age_days=inside.days))
    bucket = MultipartS3(BUCKET)

    summary = retention.archive_due_events(s3=bucket, settings=_settings(), now=NOW)

    assert (summary.due, summary.deleted) == (0, 0)
    assert _keys(fake_table) == {("SECURITY_AUDIT#a", "EVENT#young")}


def test_the_body_is_one_line_per_row_in_key_order():
    rows = [
        {"PK": "SECURITY_AUDIT#b", "SK": "EVENT#2"},
        {"PK": "SECURITY_AUDIT#a", "SK": "EVENT#1"},
    ]
    body = retention.ndjson(rows)

    assert body.decode().splitlines() == [
        '{"PK": "SECURITY_AUDIT#a", "SK": "EVENT#1"}',
        '{"PK": "SECURITY_AUDIT#b", "SK": "EVENT#2"}',
    ]
    assert retention.ndjson(list(reversed(rows))) == body


def test_a_row_rewritten_since_the_scan_is_not_deleted(fake_table):
    """The archive holds what was read; a row written since is left alone."""
    fake_table.seed(_event("a", "old", age_days=120))

    class Rewriting(MultipartS3):
        """Something appends the key again while the archive is being written."""

        def put_object(self, **kwargs: object) -> dict[str, object]:
            fake_table.seed(_event("a", "old", age_days=0))
            return super().put_object(**kwargs)

    bucket = Rewriting(BUCKET)
    summary = retention.archive_due_events(s3=bucket, settings=_settings(), now=NOW)

    assert (summary.archived, summary.deleted, summary.refused) == (1, 0, 1)
    assert _keys(fake_table) == {("SECURITY_AUDIT#a", "EVENT#old")}
    assert fake_table.rows[("SECURITY_AUDIT#a", "EVENT#old")]["created_at"] == NOW.isoformat()


def test_a_scan_that_runs_out_of_pages_says_more_are_waiting(fake_table, monkeypatch):
    """Page budget spent is reported, not raised: what was archived is already safe."""
    monkeypatch.setattr(retention, "PAGE_BUDGET", 1)
    fake_table.page_item_cap = 2
    fake_table.seed(*[_event("a", f"old-{index}", age_days=120) for index in range(5)])
    bucket = MultipartS3(BUCKET)

    summary = retention.archive_due_events(s3=bucket, settings=_settings(), now=NOW)

    assert summary.truncated is True
    assert summary.deleted == 2, "only the rows the one page held"
    assert len(_keys(fake_table)) == 3


def test_the_job_clamps_the_batch_it_is_asked_for(monkeypatch):
    """The schedule's `limit` is bounded before it reaches a ten-minute function."""
    from stoa.jobs import security_audit_retention as job

    asked: list[int] = []

    def spy(*, s3, settings, now, limit):
        asked.append(limit)
        return retention.AuditArchiveSummary(storage="disabled")

    monkeypatch.setattr(job.security_audit_retention, "archive_due_events", spy)
    aws.install({Kind.S3: object()})

    assert job.handler({"limit": 10_000}, None)["storage"] == "disabled"
    job.handler({"limit": 0}, None)
    job.handler({}, None)

    assert asked == [2_000, 1, retention.ROWS_PER_RUN]


def test_the_schedule_reaches_the_job(monkeypatch):
    from stoa.jobs import account_deletion, security_audit_retention as job

    seen: dict[str, object] = {}

    def spy(event: dict[str, object], _context: object) -> dict[str, object]:
        seen["event"] = event
        return {"ok": True}

    monkeypatch.setattr(job, "handler", spy)

    answer = account_deletion.handler(
        {"source": "stoa.scheduler", "job": "security_audit_retention", "limit": 50}, None
    )

    assert answer == {"ok": True}
    assert seen["event"]["limit"] == 50
