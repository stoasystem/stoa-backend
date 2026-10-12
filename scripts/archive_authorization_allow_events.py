#!/usr/bin/env python
"""Archive the authorization allow stream out of the table it is suffocating.

`security_audit_repo.append_event` writes one row per sensitive authorization
decision and gives it no `expires_at`, and nothing anywhere deletes one. The
attachment code reads the table with `list_owner_attachment_items`, an
unfiltered strongly consistent scan capped at 100 pages of 100 items. On
2026-10-10 the table passed 10,000 items, the scan started falling out of its
loop, and every attachment operation began answering 503 - including sending a
message with an attachment, and including the attachment half of account
deletion.

This is the stopgap, not the fix. The fix is to stop scanning the whole table
to find one owner's rows; see card 127 step 2. All this buys is the headroom to
do that properly.

What it removes is narrow on purpose:

  * `authorization_sensitive_allowed` -> archived, then deleted. 7,294 rows
    saying a permitted actor did a permitted thing. This is the volume.
  * `authorization_denied`            -> archived, kept. A refusal is the row
    an investigation actually opens, and 2,584 of them cost little.
  * everything else                   -> archived, kept. 37 rows recording
    account assignment, capability grants, admin reconciliation and the like.
    These are the audit trail in the sense the word usually means.

Every security audit row is archived, including the ones that stay, so the
bucket holds a whole copy of the stream as of this run rather than a hole-punched
one. The archive goes to the evidence bucket, which carries Object Lock in
GOVERNANCE mode for 365 days, and nothing is deleted until the object has been
read back and its digest matched.

Usage:
    python scripts/archive_authorization_allow_events.py                 # report only
    python scripts/archive_authorization_allow_events.py --archive-only  # write the copy
    python scripts/archive_authorization_allow_events.py --apply         # and delete
"""

from __future__ import annotations

import argparse
import base64
import collections
import datetime as dt
import decimal
import hashlib
import json
import sys

import boto3
from botocore.exceptions import ClientError

TABLE = "stoa-main"
REGION = "eu-central-2"
BUCKET = "stoa-immutable-evidence-562923011260"
AUDIT_ENTITY = "security_audit_event"
DELETABLE = "authorization_sensitive_allowed"


class _Numbers(json.JSONEncoder):
    """DynamoDB hands numbers back as `Decimal`; the archive keeps them exact."""

    def default(self, o):
        if isinstance(o, decimal.Decimal):
            return int(o) if o == o.to_integral_value() else float(o)
        return super().default(o)


def read_audit_rows(table) -> tuple[list[dict], int]:
    """Every security audit row, and how many items the table really holds.

    The table's own `item_count` is refreshed about every six hours, which is
    useless next to a cap this run exists to get back under, so both numbers
    come from the same pass.
    """
    rows: list[dict] = []
    total = 0
    request: dict = {}
    while True:
        response = table.scan(**request)
        total += len(response["Items"])
        rows.extend(
            item
            for item in response["Items"]
            if item.get("entity_type") == AUDIT_ENTITY
        )
        cursor = response.get("LastEvaluatedKey")
        if cursor is None:
            return rows, total
        request["ExclusiveStartKey"] = cursor


def describe(rows: list[dict]) -> tuple[collections.Counter, collections.Counter]:
    kinds = collections.Counter(str(row.get("event_type") or "(none)") for row in rows)
    days = collections.Counter(str(row.get("created_at") or "")[:10] for row in rows)
    return kinds, days


def archive(s3, rows: list[dict], stamp: str) -> tuple[str, str]:
    """Write the whole stream as NDJSON, then read it back and match the digest."""
    body = "".join(
        json.dumps(row, cls=_Numbers, sort_keys=True, ensure_ascii=False) + "\n"
        for row in sorted(rows, key=lambda r: (str(r.get("PK")), str(r.get("SK"))))
    ).encode("utf-8")
    digest = hashlib.sha256(body).hexdigest()
    key = f"security-audit-archive/{stamp}/security_audit_event.ndjson"
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=body,
        ContentType="application/x-ndjson",
        ChecksumSHA256=base64.b64encode(bytes.fromhex(digest)).decode(),
        Metadata={"rows": str(len(rows)), "sha256": digest},
    )
    stored = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
    if hashlib.sha256(stored).hexdigest() != digest:
        raise SystemExit("archive read back with a different digest; nothing deleted")
    if sum(1 for line in stored.splitlines() if line.strip()) != len(rows):
        raise SystemExit("archive read back with a different row count; nothing deleted")
    return key, digest


def delete(table, rows: list[dict]) -> int:
    done = 0
    with table.batch_writer() as batch:
        for row in rows:
            batch.delete_item(Key={"PK": row["PK"], "SK": row["SK"]})
            done += 1
    return done


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="archive to the evidence bucket, verify it, then delete the allow stream",
    )
    parser.add_argument(
        "--archive-only",
        action="store_true",
        help="write and verify the archive, delete nothing",
    )
    args = parser.parse_args()

    session = boto3.Session(region_name=REGION)
    identity = session.client("sts").get_caller_identity()
    if identity["Account"] != "562923011260":
        raise SystemExit(f"wrong account: {identity['Account']}")
    print(f"account {identity['Account']}  {identity['Arn']}")

    table = session.resource("dynamodb").Table(TABLE)
    rows, total = read_audit_rows(table)
    doomed = [row for row in rows if row.get("event_type") == DELETABLE]
    kept = len(rows) - len(doomed)

    kinds, days = describe(rows)
    print(f"\ntable holds {total} items; {len(rows)} are {AUDIT_ENTITY}")
    print("\n-- event_type --")
    for kind, count in kinds.most_common():
        mark = "DELETE" if kind == DELETABLE else "keep"
        print(f"{count:7d}  {mark:6s}  {kind}")
    print(f"\nspanning {min(days)} .. {max(days)} over {len(days)} days")
    print(f"\narchive {len(rows)} rows, delete {len(doomed)}, keep {kept} in the table")
    print(f"table would hold about {total - len(doomed)} items, against a 10000 scan cap")

    if not args.apply and not args.archive_only:
        print("\nreport only; --archive-only writes the archive, --apply also deletes")
        return 0

    stamp = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    key, digest = archive(session.client("s3"), rows, stamp)
    print(f"\narchived s3://{BUCKET}/{key}")
    print(f"sha256 {digest}  (read back and matched)")

    if args.archive_only:
        print("\narchive only; nothing deleted")
        return 0

    try:
        removed = delete(table, doomed)
    except ClientError as exc:
        raise SystemExit(f"delete stopped: {exc}; the archive is complete and keyed above")
    print(f"deleted {removed} rows")

    left, after = read_audit_rows(table)
    still = sum(1 for row in left if row.get("event_type") == DELETABLE)
    print(f"table now holds {after} items")
    print(f"{len(left)} {AUDIT_ENTITY} rows remain, {still} of them {DELETABLE}")
    return 0 if still == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
