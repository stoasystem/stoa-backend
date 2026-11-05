"""Find, and on request delete, upload bytes under `objects/` that nothing references (#257).

An upload's checked bytes are copied to `objects/{random}` before the upload is
used. Until #255 the table's TTL deleted upload rows 30 minutes after they were
issued, and the sweep that would have cleaned their objects never ran (#250).
An upload that was checked but never attached to a message or reply therefore
left an object behind that no row names any more.

An object is reported when all of these hold:
- it is the current version of a key under `objects/`;
- it was last modified more than `--min-age-days` ago (default 2), so an upload
  still in flight is never touched;
- no row on the table carries its key as `immutable_object_key` - attachment
  rows of any status, and upload rows of any status, count as references.

`staging/`, `moderation/` and noncurrent versions are not looked at: the bucket's
lifecycle rules and the moderation retention job own those.

Report only (the default) prints a summary and writes the list to `--out`:
    python scripts/find_orphan_upload_objects.py --out orphans.json

Delete exactly what a reviewed list names, by version id, re-checking each key
against the table first:
    python scripts/find_orphan_upload_objects.py --apply --from orphans.json

The table, bucket and region come from the backend's settings (the
`DYNAMODB_TABLE_NAME`, `S3_IMAGES_BUCKET` and `AWS_REGION` environment), and
credentials from the usual AWS chain (`AWS_PROFILE`).
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sys
from typing import Any

OBJECTS_PREFIX = "objects/"
DEFAULT_MIN_AGE_DAYS = 2
DELETE_BATCH = 100


@dataclass(frozen=True, slots=True)
class Orphan:
    key: str
    version_id: str
    size_bytes: int
    last_modified: str


def referenced_keys(table: Any) -> set[str]:
    """Every `immutable_object_key` any row on the table still carries."""
    keys: set[str] = set()
    request: dict[str, Any] = {
        "FilterExpression": "attribute_exists(immutable_object_key)",
        "ProjectionExpression": "immutable_object_key",
    }
    while True:
        response = table.scan(**request)
        for item in response.get("Items", []):
            key = item.get("immutable_object_key")
            if isinstance(key, str) and key:
                keys.add(key)
        cursor = response.get("LastEvaluatedKey")
        if not cursor:
            return keys
        request["ExclusiveStartKey"] = cursor


def _current_versions(s3: Any, bucket: str) -> Iterator[dict[str, Any]]:
    request: dict[str, Any] = {"Bucket": bucket, "Prefix": OBJECTS_PREFIX}
    while True:
        response = s3.list_object_versions(**request)
        for version in response.get("Versions", []):
            if version.get("IsLatest"):
                yield version
        if not response.get("IsTruncated"):
            return
        request["KeyMarker"] = response.get("NextKeyMarker")
        request["VersionIdMarker"] = response.get("NextVersionIdMarker")


def find_orphans(
    *,
    s3: Any,
    bucket: str,
    referenced: set[str],
    now: datetime,
    min_age: timedelta = timedelta(days=DEFAULT_MIN_AGE_DAYS),
) -> list[Orphan]:
    cutoff = now - min_age
    orphans: list[Orphan] = []
    for version in _current_versions(s3, bucket):
        key = str(version["Key"])
        modified = version["LastModified"]
        if not key.startswith(OBJECTS_PREFIX) or key in referenced or modified > cutoff:
            continue
        orphans.append(
            Orphan(
                key=key,
                version_id=str(version["VersionId"]),
                size_bytes=int(version.get("Size") or 0),
                last_modified=modified.astimezone(UTC).isoformat(),
            )
        )
    return orphans


def summary(orphans: list[Orphan]) -> dict[str, Any]:
    dates = sorted(orphan.last_modified for orphan in orphans)
    return {
        "count": len(orphans),
        "total_bytes": sum(orphan.size_bytes for orphan in orphans),
        "oldest": dates[0] if dates else None,
        "newest": dates[-1] if dates else None,
    }


def _batches(items: list[Orphan], size: int) -> Iterable[list[Orphan]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def delete_orphans(*, s3: Any, table: Any, bucket: str, orphans: list[Orphan]) -> dict[str, int]:
    """Delete the listed versions, skipping any key a row has come to reference since."""
    referenced = referenced_keys(table)
    to_delete = [orphan for orphan in orphans if orphan.key.startswith(OBJECTS_PREFIX)]
    skipped = [orphan for orphan in to_delete if orphan.key in referenced]
    to_delete = [orphan for orphan in to_delete if orphan.key not in referenced]
    deleted = failed = 0
    for batch in _batches(to_delete, DELETE_BATCH):
        response = s3.delete_objects(
            Bucket=bucket,
            Delete={
                "Objects": [{"Key": orphan.key, "VersionId": orphan.version_id} for orphan in batch],
                "Quiet": False,
            },
        )
        deleted += len(response.get("Deleted", []))
        failed += len(response.get("Errors", []))
    return {
        "deleted": deleted,
        "failed": failed,
        "skipped_now_referenced": len(skipped),
        "skipped_outside_prefix": len(orphans) - len(skipped) - len(to_delete),
    }


def _read_list(path: Path) -> list[Orphan]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [Orphan(**row) for row in rows]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path("orphan-upload-objects.json"))
    parser.add_argument("--min-age-days", type=int, default=DEFAULT_MIN_AGE_DAYS)
    parser.add_argument("--apply", action="store_true", help="delete what --from lists")
    parser.add_argument("--from", dest="source", type=Path, help="a list written by a report run")
    args = parser.parse_args(argv)

    import boto3

    from stoa.config import settings
    from stoa.db.dynamodb import get_table

    s3 = boto3.client("s3", region_name=settings.aws_region)
    table = get_table()
    bucket = settings.s3_images_bucket

    if args.apply:
        if args.source is None:
            parser.error("--apply deletes only what a reviewed list names: pass --from")
        result = delete_orphans(s3=s3, table=table, bucket=bucket, orphans=_read_list(args.source))
        print(json.dumps({"bucket": bucket, **result}, indent=2))
        return 0 if result["failed"] == 0 else 1

    if args.min_age_days < 1:
        parser.error("--min-age-days must be at least 1")
    orphans = find_orphans(
        s3=s3,
        bucket=bucket,
        referenced=referenced_keys(table),
        now=datetime.now(UTC),
        min_age=timedelta(days=args.min_age_days),
    )
    args.out.write_text(
        json.dumps([asdict(orphan) for orphan in orphans], indent=1), encoding="utf-8"
    )
    print(json.dumps({"bucket": bucket, "list": str(args.out), **summary(orphans)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
