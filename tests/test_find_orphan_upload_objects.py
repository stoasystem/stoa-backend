"""The one-off finder for upload bytes nothing references any more (#257)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from typing import Any

import pytest

import find_orphan_upload_objects as finder
from fakes.dynamodb import FakeTable

NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)
OLD = NOW - timedelta(days=30)
BUCKET = "images-bucket-canary"


class _VersionedBucket:
    """Object versions as `ListObjectVersions` pages them, and `DeleteObjects` by version."""

    def __init__(self, page_size: int = 2) -> None:
        self.versions: list[dict[str, Any]] = []
        self.page_size = page_size
        self.deleted: list[dict[str, str]] = []

    def put(self, key: str, version: str, *, modified: datetime = OLD, latest: bool = True, size: int = 10) -> None:
        self.versions.append(
            {"Key": key, "VersionId": version, "IsLatest": latest, "LastModified": modified, "Size": size}
        )

    def list_object_versions(self, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["Bucket"] == BUCKET
        matching = [v for v in self.versions if v["Key"].startswith(kwargs["Prefix"])]
        start = 0
        if "KeyMarker" in kwargs:
            start = next(
                index + 1
                for index, v in enumerate(matching)
                if (v["Key"], v["VersionId"]) == (kwargs["KeyMarker"], kwargs["VersionIdMarker"])
            )
        page = matching[start : start + self.page_size]
        truncated = start + self.page_size < len(matching)
        response: dict[str, Any] = {"Versions": page, "IsTruncated": truncated}
        if truncated:
            response["NextKeyMarker"] = page[-1]["Key"]
            response["NextVersionIdMarker"] = page[-1]["VersionId"]
        return response

    def delete_objects(self, **kwargs: Any) -> dict[str, Any]:
        objects = kwargs["Delete"]["Objects"]
        self.deleted.extend(objects)
        return {"Deleted": objects}


def _attachment(table: FakeTable, n: int, key: str, status: str = "active") -> None:
    table.seed({"PK": f"ATTACHMENT#a{n}", "SK": "META", "immutable_object_key": key, "status": status})


def _upload(table: FakeTable, n: int, key: str, status: str) -> None:
    table.seed({"PK": f"UPLOAD#u{n}", "SK": "META", "immutable_object_key": key, "status": status})


def _find(bucket: _VersionedBucket, table: FakeTable, **kwargs: Any) -> list[finder.Orphan]:
    return finder.find_orphans(
        s3=bucket, bucket=BUCKET, referenced=finder.referenced_keys(table), now=NOW, **kwargs
    )


def test_only_old_current_objects_no_row_names_are_orphans() -> None:
    table = FakeTable()
    bucket = _VersionedBucket()
    _attachment(table, 1, "objects/attached")
    _attachment(table, 2, "objects/deleted-attachment", status="deleted")
    _upload(table, 1, "objects/validated-unused", "validated")
    bucket.put("objects/attached", "v1")
    bucket.put("objects/deleted-attachment", "v2")
    bucket.put("objects/validated-unused", "v3")
    bucket.put("objects/orphan", "v4", size=7)
    bucket.put("objects/young-orphan", "v5", modified=NOW - timedelta(hours=3))
    bucket.put("objects/replaced", "v6", latest=False)

    orphans = _find(bucket, table)

    assert orphans == [
        finder.Orphan(key="objects/orphan", version_id="v4", size_bytes=7, last_modified=OLD.isoformat())
    ]


def test_other_prefixes_are_never_listed() -> None:
    bucket = _VersionedBucket()
    bucket.put("staging/abc/u1.png", "v1")
    bucket.put("moderation/case-1", "v2")
    bucket.put("objects/orphan", "v3")

    orphans = _find(bucket, FakeTable())

    assert [orphan.key for orphan in orphans] == ["objects/orphan"]


def test_every_page_of_the_bucket_and_the_table_is_read() -> None:
    table = FakeTable()
    bucket = _VersionedBucket(page_size=2)
    for n in range(7):
        bucket.put(f"objects/o{n}", f"v{n}")
        if n % 2 == 0:
            _attachment(table, n, f"objects/o{n}")

    orphans = _find(bucket, table)

    assert [orphan.key for orphan in orphans] == ["objects/o1", "objects/o3", "objects/o5"]


def test_the_minimum_age_is_respected() -> None:
    bucket = _VersionedBucket()
    bucket.put("objects/five-days", "v1", modified=NOW - timedelta(days=5))

    assert _find(bucket, FakeTable(), min_age=timedelta(days=7)) == []
    assert len(_find(bucket, FakeTable(), min_age=timedelta(days=2))) == 1


def test_apply_deletes_by_version_and_skips_what_became_referenced() -> None:
    table = FakeTable()
    bucket = _VersionedBucket()
    listed = [
        finder.Orphan("objects/still-orphan", "v1", 10, OLD.isoformat()),
        finder.Orphan("objects/attached-since", "v2", 10, OLD.isoformat()),
        finder.Orphan("staging/not-ours", "v3", 10, OLD.isoformat()),
    ]
    _attachment(table, 1, "objects/attached-since")

    result = finder.delete_orphans(s3=bucket, table=table, bucket=BUCKET, orphans=listed)

    assert bucket.deleted == [{"Key": "objects/still-orphan", "VersionId": "v1"}]
    assert result == {
        "deleted": 1,
        "failed": 0,
        "skipped_now_referenced": 1,
        "skipped_outside_prefix": 1,
    }


def test_the_summary_carries_counts_and_dates_only() -> None:
    orphans = [
        finder.Orphan("objects/a", "v1", 10, "2026-10-01T00:00:00+00:00"),
        finder.Orphan("objects/b", "v2", 5, "2026-09-01T00:00:00+00:00"),
    ]

    assert finder.summary(orphans) == {
        "count": 2,
        "total_bytes": 15,
        "oldest": "2026-09-01T00:00:00+00:00",
        "newest": "2026-10-01T00:00:00+00:00",
    }
    assert finder.summary([]) == {"count": 0, "total_bytes": 0, "oldest": None, "newest": None}


def test_apply_needs_a_reviewed_list(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        finder.main(["--apply"])
    assert "--from" in capsys.readouterr().err


def test_a_written_list_reads_back(tmp_path) -> None:
    orphan = finder.Orphan("objects/a", "v1", 10, OLD.isoformat())
    path = tmp_path / "orphans.json"
    path.write_text(json.dumps([{"key": "objects/a", "version_id": "v1", "size_bytes": 10, "last_modified": OLD.isoformat()}]))

    assert finder._read_list(path) == [orphan]
