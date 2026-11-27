#!/usr/bin/env python3
"""Count the attachments whose upload row does not name them, before upload cleanup trusts it (#654).

Upload cleanup stops scanning the table for attachments made from an upload and
reads the upload's own `durable_attachment_id` instead: while the attachment it
names is there, the upload's bytes are that attachment's and the cleanup leaves
them. That is safe only if every upload row an attachment was made from names
that attachment. This script reads every attachment row (`ATTACHMENT#` /
`META`) and every upload row (`UPLOAD#` / `META`) and counts, for each
attachment:

- `named`: its source upload row is there and names it - safe;
- `upload gone`: its source upload row has left by TTL - nothing left to clean;
- `upload names none`: the source upload row is there without
  `durable_attachment_id` - the cleanup could delete this attachment's bytes;
- `upload names another`: it is there and names a different attachment - same risk;
- `shared object`: another upload row (not its source) holds the same immutable
  object, which the old Scan also matched - same risk;
- `no source upload`: the attachment row names no source upload.

The last four must be 0, or each one explained, before the change merges. Each
of them is listed with its attachment id, upload id and both rows' status, and
nothing else: no owner ids, file names or object keys.

    python scripts/check_upload_attachment_links.py --profile stoa

Read-only: one consistent Scan of the table, filtered to those two row kinds.
It writes nothing and calls no S3. Rows the application changes while it runs
may show up as a difference; run it again to see whether one stays.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from boto3.dynamodb.conditions import Attr

ROOT = Path(__file__).resolve().parent.parent
for folder in (ROOT, ROOT / "src"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from stoa.security.aws_operator_identity import require_sso_operator_session  # noqa: E402

DEFAULT_AWS_ACCOUNT_ID = "562923011260"

SAFE = ("named", "upload gone")
RISKS = ("upload names none", "upload names another", "shared object", "no source upload")

_PROJECTION = (
    "PK, SK, #status, attachment_id, source_upload_id, upload_id, durable_attachment_id, "
    "immutable_object_key, immutable_version_id"
)


def meta_rows(table: Any) -> Iterator[dict[str, Any]]:
    """Every attachment and upload row (`ATTACHMENT#` or `UPLOAD#`, `META`), page by page."""
    request: dict[str, Any] = {
        "FilterExpression": (
            (Attr("PK").begins_with("ATTACHMENT#") | Attr("PK").begins_with("UPLOAD#"))
            & Attr("SK").eq("META")
        ),
        "ProjectionExpression": _PROJECTION,
        "ExpressionAttributeNames": {"#status": "status"},
        "ConsistentRead": True,
    }
    while True:
        response = table.scan(**request)
        yield from response.get("Items", [])
        last = response.get("LastEvaluatedKey")
        if not last:
            return
        request["ExclusiveStartKey"] = last


@dataclass
class Report:
    counts: Counter[str] = field(default_factory=Counter)
    findings: list[str] = field(default_factory=list)

    @property
    def risky(self) -> int:
        return sum(self.counts[name] for name in RISKS)

    def text(self) -> str:
        lines = [f"Attachments: {sum(self.counts[name] for name in SAFE + RISKS)}"]
        lines += [f"  {name}: {self.counts[name]}" for name in SAFE + RISKS]
        lines.append(f"To explain before upload cleanup trusts durable_attachment_id: {self.risky}")
        lines += [f"  {line}" for line in self.findings]
        return "\n".join(lines)


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def check(rows: Iterable[Mapping[str, Any]]) -> Report:
    """Sort every attachment by what its upload rows say about it."""
    attachments: list[Mapping[str, Any]] = []
    uploads: dict[str, Mapping[str, Any]] = {}
    by_object: dict[tuple[str, str], list[str]] = {}
    for row in rows:
        pk = _text(row.get("PK"))
        if pk.startswith("ATTACHMENT#"):
            attachments.append(row)
        elif pk.startswith("UPLOAD#"):
            upload_id = pk.removeprefix("UPLOAD#")
            uploads[upload_id] = row
            stored = (_text(row.get("immutable_object_key")), _text(row.get("immutable_version_id")))
            if all(stored):
                by_object.setdefault(stored, []).append(upload_id)
    report = Report()
    for attachment in attachments:
        attachment_id = _text(attachment.get("attachment_id")) or _text(
            attachment.get("PK")
        ).removeprefix("ATTACHMENT#")
        source = _text(attachment.get("source_upload_id"))
        status = _text(attachment.get("status")) or "-"
        stored = (
            _text(attachment.get("immutable_object_key")),
            _text(attachment.get("immutable_version_id")),
        )
        sharing = by_object.get(stored, []) if all(stored) else []
        for upload_id in sharing:
            if upload_id == source:
                continue
            if _text(uploads[upload_id].get("durable_attachment_id")) == attachment_id:
                continue
            report.counts["shared object"] += 1
            report.findings.append(
                f"shared object: attachment {attachment_id} ({status}), upload {upload_id} "
                f"({_text(uploads[upload_id].get('status')) or '-'})"
            )
        if not source:
            outcome = "no source upload"
        elif source not in uploads:
            outcome = "upload gone"
        else:
            named = _text(uploads[source].get("durable_attachment_id"))
            outcome = (
                "named" if named == attachment_id
                else "upload names none" if not named
                else "upload names another"
            )
        report.counts[outcome] += 1
        if outcome in RISKS:
            upload_status = _text(uploads.get(source, {}).get("status")) or "-"
            report.findings.append(
                f"{outcome}: attachment {attachment_id} ({status}), "
                f"upload {source or '-'} ({upload_status})"
            )
    return report


def run(table: Any) -> int:
    report = check(meta_rows(table))
    print(report.text())
    print("[READ ONLY] Nothing written.")
    return 1 if report.risky else 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--table", default=os.environ.get("STOA_TABLE", "stoa-main"))
    parser.add_argument("--region", default=os.environ.get("AWS_DEFAULT_REGION", "eu-central-2"))
    parser.add_argument("--profile", default=os.environ.get("AWS_PROFILE", "stoa"))
    parser.add_argument(
        "--account-id", default=os.environ.get("AWS_ACCOUNT_ID", DEFAULT_AWS_ACCOUNT_ID)
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    session = require_sso_operator_session(
        profile_name=args.profile,
        region_name=args.region,
        expected_account_id=args.account_id,
    )
    table = session.resource("dynamodb", region_name=args.region).Table(args.table)
    return run(table)


if __name__ == "__main__":
    raise SystemExit(main())
