#!/usr/bin/env python3
"""Give the curriculum rows written before #661 their names in every language.

A topic, unit or lesson row carries `titles` - its name in German, English,
French and Italian - from the backend release that writes them (the seed, the
knowledge-base import and the curriculum migrations and authoring). Rows written
before that have only their German `title`; their English, French and Italian
names are in `curriculum_translations.TITLE_TRANSLATIONS`, which
`curriculum_names` still reads for them. This script writes those names onto the
rows, so that the table entries can go (#661) and a reader sees, word for word,
the names they see today.

    python scripts/backfill_content_titles.py            # dry run: counts, writes nothing
    python scripts/backfill_content_titles.py --apply    # writes the rows the dry run counted
    python scripts/backfill_content_titles.py --verify   # reads the rows back, writes nothing

A row's names are its own where it has them, else the translations, and German
is its `title`: what `curriculum_names` shows today. A row that already names
itself in every language the translations do is left alone. Each write is one
`UpdateItem` that sets `titles` and nothing else, on condition that the row's
`title` is still what was read and that it still has no `titles` (or still has
some, when it is adding to them): a row a publish rewrote meanwhile is left
alone and counted, and the next dry run says whether anything is left. Then the
catalog stamp is written, so every container reads the curriculum again.

`--verify` counts, per kind, the rows named in all four languages, and lists every
row a reader would see in German once the table entries are gone although the
table names it in their language today. It must list none before #661's second
step removes them.
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

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parent.parent
for folder in (ROOT, ROOT / "src"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from stoa.security.aws_operator_identity import require_sso_operator_session  # noqa: E402
from stoa.services import curriculum_cache, curriculum_names, curriculum_translations  # noqa: E402

DEFAULT_AWS_ACCOUNT_ID = "562923011260"

#: The content rows, by sort key prefix, and the field holding each one's id.
KINDS = {"TOPIC": "topic_id", "UNIT": "unit_id", "LESSON": "lesson_id"}
#: The languages the translation table holds; German is the row's own `title`.
TRANSLATED = tuple(locale for locale in curriculum_names.LOCALES if locale != "de")


def _kind(row: Mapping[str, Any]) -> str:
    return str(row.get("SK") or "").split("#", 1)[0]


def _content_id(row: Mapping[str, Any]) -> str:
    return str(row.get(KINDS[_kind(row)]) or "")


def content_rows(table: Any) -> Iterator[dict[str, Any]]:
    """Every topic, unit and lesson row of the practice partition, page by page."""
    for kind in KINDS:
        request: dict[str, Any] = {
            "KeyConditionExpression": Key("PK").eq("PRACTICE") & Key("SK").begins_with(f"{kind}#")
        }
        while True:
            response = table.query(**request)
            yield from response.get("Items", [])
            last = response.get("LastEvaluatedKey")
            if not last:
                break
            request["ExclusiveStartKey"] = last


def translations(content_id: str) -> dict[str, str]:
    """The English, French and Italian names the table holds for `content_id`."""
    held = curriculum_translations.TITLE_TRANSLATIONS.get(content_id) or {}
    return {locale: held[locale] for locale in TRANSLATED if isinstance(held.get(locale), str)}


def names_for(row: Mapping[str, Any]) -> dict[str, str]:
    """The `titles` the row should carry: its own names where it has them, else the
    table's translations, and German its `title` - what a reader is shown today."""
    own = curriculum_names.normalized_titles(row.get("titles"))
    return curriculum_names.normalized_titles(
        {**translations(_content_id(row)), **own}, german=row.get("title")
    )


@dataclass
class Plan:
    """What a run would write: the rows with their names, and a count per kind and outcome."""

    writes: list[tuple[dict[str, Any], dict[str, str]]] = field(default_factory=list)
    counts: Counter[tuple[str, str]] = field(default_factory=Counter)
    #: The rows the table has no translation for: named in German in every
    #: language today, and after the backfill.
    german_only: list[str] = field(default_factory=list)

    def report(self) -> str:
        lines = []
        for kind in KINDS:
            parts = [
                f"{outcome} {self.counts[(kind, outcome)]}"
                for outcome in ("rows", "named already", "to write", "of them German only")
            ]
            lines.append(f"{kind}: " + " | ".join(parts))
        lines.append(f"Rows to write: {len(self.writes)}")
        if self.german_only:
            lines.append("German only (shown in German in every language, before and after):")
            lines.extend(f"  {line}" for line in self.german_only[:50])
        return "\n".join(lines)


def plan(rows: Iterable[Mapping[str, Any]]) -> Plan:
    """Which rows lack names a reader is shown today."""
    result = Plan()
    for row in rows:
        kind = _kind(row)
        if kind not in KINDS or not _content_id(row):
            continue
        result.counts[(kind, "rows")] += 1
        names = names_for(row)
        if row.get("titles") == names:
            result.counts[(kind, "named already")] += 1
            continue
        result.counts[(kind, "to write")] += 1
        if set(names) <= {"de"}:
            result.counts[(kind, "of them German only")] += 1
            state = row.get("rollout_state") or "-"
            result.german_only.append(f"{row['SK']} {state}: {row.get('title')}")
        result.writes.append((dict(row), names))
    return result


def update_request(row: Mapping[str, Any], names: Mapping[str, str]) -> dict[str, Any]:
    """The conditional `UpdateItem` that gives `row` its names and changes nothing else."""
    names_ = {"#titles": "titles", "#title": "title"}
    values: dict[str, Any] = {":titles": dict(names)}
    conditions = ["attribute_exists(SK)"]
    if "title" in row:
        values[":title"] = row["title"]
        conditions.append("#title = :title")
    else:
        conditions.append("attribute_not_exists(#title)")
    conditions.append("attribute_exists(#titles)" if "titles" in row else "attribute_not_exists(#titles)")
    return {
        "Key": {"PK": row["PK"], "SK": row["SK"]},
        "UpdateExpression": "SET #titles = :titles",
        "ConditionExpression": " AND ".join(conditions),
        "ExpressionAttributeNames": names_,
        "ExpressionAttributeValues": values,
    }


def apply(table: Any, planned: Plan) -> Counter[str]:
    """Write every planned row; a row changed since it was read is skipped."""
    outcome: Counter[str] = Counter()
    for row, names in planned.writes:
        try:
            table.update_item(**update_request(row, names))
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
            outcome["changed meanwhile, skipped"] += 1
            continue
        outcome["written"] += 1
    if outcome["written"]:
        curriculum_cache.touch_catalog_stamp(table)
    return outcome


@dataclass
class Check:
    """Each kind's rows by how many languages name them, and the names a reader would lose."""

    counts: Counter[tuple[str, str]] = field(default_factory=Counter)
    lost: list[str] = field(default_factory=list)

    def report(self) -> str:
        lines = []
        for kind in KINDS:
            parts = [
                f"{outcome} {self.counts[(kind, outcome)]}"
                for outcome in ("rows", "all four languages", "some", "no titles")
            ]
            lines.append(f"{kind}: " + " | ".join(parts))
        lines.append(f"Names a reader would lose without the table: {len(self.lost)}")
        lines.extend(f"  {line}" for line in self.lost[:50])
        return "\n".join(lines)


def check(rows: Iterable[Mapping[str, Any]]) -> Check:
    """Whether every row names itself in each language the table names it in."""
    result = Check()
    for row in rows:
        kind = _kind(row)
        if kind not in KINDS or not _content_id(row):
            continue
        result.counts[(kind, "rows")] += 1
        own = curriculum_names.normalized_titles(row.get("titles"))
        if "titles" not in row:
            result.counts[(kind, "no titles")] += 1
        elif not curriculum_names.missing_locales(own):
            result.counts[(kind, "all four languages")] += 1
        else:
            result.counts[(kind, "some")] += 1
        for locale, name in translations(_content_id(row)).items():
            if locale not in own:
                result.lost.append(f"{row['SK']} {locale}: {name}")
    return result


def run(table: Any, *, apply_writes: bool, verify_rows: bool) -> int:
    rows = list(content_rows(table))
    if verify_rows:
        checked = check(rows)
        print(checked.report())
        return 1 if checked.lost else 0
    planned = plan(rows)
    print(planned.report())
    if not apply_writes:
        print("[DRY RUN] Nothing written. Run again with --apply to write these rows.")
        return 0
    outcome = apply(table, planned)
    print(" | ".join(f"{name}: {count}" for name, count in sorted(outcome.items())) or "Nothing to write.")
    print("Now run it again with --verify.")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--table", default=os.environ.get("STOA_TABLE", "stoa-main"))
    parser.add_argument("--region", default=os.environ.get("AWS_DEFAULT_REGION", "eu-central-2"))
    parser.add_argument("--profile", default=os.environ.get("AWS_PROFILE", "stoa"))
    parser.add_argument(
        "--account-id", default=os.environ.get("AWS_ACCOUNT_ID", DEFAULT_AWS_ACCOUNT_ID)
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="write the rows the dry run counts")
    mode.add_argument("--verify", action="store_true", help="read the rows back, write nothing")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    session = require_sso_operator_session(
        profile_name=args.profile,
        region_name=args.region,
        expected_account_id=args.account_id,
    )
    table = session.resource("dynamodb", region_name=args.region).Table(args.table)
    return run(table, apply_writes=args.apply, verify_rows=args.verify)


if __name__ == "__main__":
    raise SystemExit(main())
