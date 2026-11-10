#!/usr/bin/env python3
"""Compare the curriculum seed in the code with the seed stamp in the table.

The seed (`scripts/seed_practice.py`) is run by hand, never by a deploy. When it
has written every row it records the hash of what it wrote, and the
knowledge-base mode it ran in, in PRACTICE / CURRICULUM_SEED. After a production
deploy this script reads that row, recomputes the hash from the repository in the
same mode, and reports one of four outcomes (stoa-backend#355, step 4 of #317):

- in agreement: one line in the run summary;
- the table lags the code: a `::warning::` and a summary section asking for a
  seed run, with both hashes and the stamp's commit and time;
- no stamp row: the same warning; the seed has never stamped this table;
- the row could not be read (permissions, network): a warning that says so, and
  that it is not a mismatch.

It only warns. Whatever it finds, and whatever goes wrong, it exits 0: a table
that lags the code must not block a deploy. Recomputing the hash needs no AWS
access; reading the row is one `GetItem` through the AWS CLI, with the
environment's credentials in a deploy or an SSO profile for an operator:

    python scripts/check_curriculum_seed.py --profile stoa
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from boto3.dynamodb.types import TypeDeserializer

sys.path.insert(0, str(Path(__file__).resolve().parent))

TABLE = "stoa-main"
REGION = "eu-central-2"
STAMP_KEY = {"PK": {"S": "PRACTICE"}, "SK": {"S": "CURRICULUM_SEED"}}
#: The stamp's `knowledge_base` value, and what `seed_rows` is called with for it.
MODES: dict[str, str | None] = {"off": None, "preview": "preview", "live": "live"}
#: A stamp written before it recorded a mode, or no stamp at all, means the default run.
DEFAULT_MODE = "off"
SEED_COMMAND = "scripts/seed_practice.py"

Runner = Callable[[Sequence[str]], str]
Hasher = Callable[[str], str]


class CommandError(RuntimeError):
    """The AWS CLI did not answer."""


def _aws_cli(args: Sequence[str]) -> str:
    try:
        completed = subprocess.run(
            list(args), capture_output=True, text=True, check=False, timeout=60
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CommandError(str(error)) from error
    if completed.returncode != 0:
        raise CommandError(completed.stderr.strip() or f"exit code {completed.returncode}")
    return completed.stdout


def code_hash(mode: str) -> str:
    """The hash `seed_practice.py --print-hash` prints for this knowledge-base mode."""
    import seed_practice

    return seed_practice.seed_hash(seed_practice.seed_rows(knowledge_base=MODES[mode]))


def read_stamp(run: Runner, *, table: str, region: str, profile: str | None) -> dict | None:
    """The seed stamp, or None when the table holds no such row."""
    args = [
        "aws", "dynamodb", "get-item",
        "--table-name", table,
        "--key", json.dumps(STAMP_KEY),
        "--consistent-read",
        "--region", region,
        "--output", "json",
    ]
    if profile:
        args += ["--profile", profile]
    output = run(args)
    try:
        answer = json.loads(output or "{}")
    except json.JSONDecodeError as error:
        raise CommandError(f"the answer was not JSON: {output[:200]!r}") from error
    if not isinstance(answer, dict):
        raise CommandError(f"the answer was not an object: {output[:200]!r}")
    item = answer.get("Item")
    if item is None:
        return None
    deserializer = TypeDeserializer()
    return {key: deserializer.deserialize(value) for key, value in item.items()}


@dataclass(frozen=True)
class Outcome:
    warning: str | None
    summary: str


def _stamp_lines(stamp: dict) -> list[str]:
    dirty = " (seeded with uncommitted changes)" if stamp.get("git_dirty") else ""
    return [
        f"- Table hash: `{stamp.get('seed_hash', '(none)')}`",
        f"- Seeded from commit `{stamp.get('git_commit', 'unknown')}`{dirty}",
        f"- Seeded at {stamp.get('seeded_at', 'unknown')}",
    ]


def _lagging(reason: str, mode: str, digest: str | None, stamp: dict | None) -> Outcome:
    flag = {"off": "", "preview": " --knowledge-base", "live": " --knowledge-base-live"}
    command = f"{SEED_COMMAND}{flag.get(mode, '')}"
    lines = [
        "## :warning: Curriculum seed lags the code",
        "",
        f"{reason} Run `{command}` against production.",
        "",
        f"- Code hash (knowledge base: {mode}): `{digest or '(not computed)'}`",
    ]
    if stamp is not None:
        lines += _stamp_lines(stamp)
    return Outcome(
        warning=f"Curriculum seed lags the code: {reason} Run {command} against production.",
        summary="\n".join(lines),
    )


def compare(stamp: dict | None, hasher: Hasher) -> Outcome:
    if stamp is None:
        digest = hasher(DEFAULT_MODE)
        return _lagging(
            "The table holds no seed stamp (PRACTICE / CURRICULUM_SEED).",
            DEFAULT_MODE, digest, None,
        )
    mode = str(stamp.get("knowledge_base") or DEFAULT_MODE)
    if mode not in MODES:
        return _lagging(
            f"The stamp names a knowledge-base mode the code does not know: {mode!r}.",
            mode, None, stamp,
        )
    digest = hasher(mode)
    if stamp.get("seed_hash") != digest:
        return _lagging(
            "The table was seeded from different curriculum code.", mode, digest, stamp
        )
    commit = str(stamp.get("git_commit", "unknown"))
    dirty = ", uncommitted changes" if stamp.get("git_dirty") else ""
    return Outcome(
        warning=None,
        summary=(
            f"Curriculum seed matches the code (hash `{digest}`, knowledge base: {mode}, "
            f"seeded from commit `{commit[:12]}`{dirty} at {stamp.get('seeded_at', 'unknown')})."
        ),
    )


def _failed(what: str, error: BaseException) -> Outcome:
    detail = f"{type(error).__name__}: {error}"
    return Outcome(
        warning=f"Curriculum seed check: {what} ({detail}). This is not a mismatch.",
        summary="\n".join([
            "## :warning: Curriculum seed could not be checked",
            "",
            f"{what}. This is not a mismatch: the check did not get as far as comparing.",
            "",
            "```",
            detail,
            "```",
        ]),
    )


def check(
    run: Runner, hasher: Hasher, *, table: str, region: str, profile: str | None
) -> Outcome:
    try:
        stamp = read_stamp(run, table=table, region=region, profile=profile)
    except Exception as error:  # noqa: BLE001 - any read failure is only a warning
        return _failed("The seed stamp could not be read", error)
    try:
        return compare(stamp, hasher)
    except Exception as error:  # noqa: BLE001 - nor may a broken seed fail the deploy
        return _failed("The code's seed hash could not be computed", error)


def _annotation(text: str) -> str:
    # Workflow commands end at a newline; `%`, CR and LF are escaped as GitHub documents.
    escaped = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return f"::warning title=Curriculum seed::{escaped}"


def _write_summary(path: str, text: str) -> None:
    try:
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(text + "\n")
    except OSError as error:
        print(f"Could not write the run summary to {path}: {error}")


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--table", default=TABLE)
    parser.add_argument("--region", default=REGION)
    parser.add_argument("--profile", default=None, help="an SSO profile, for an operator")
    parser.add_argument(
        "--summary", default=os.environ.get("GITHUB_STEP_SUMMARY"),
        help="markdown file to append the result to (default: $GITHUB_STEP_SUMMARY)",
    )
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    *,
    run: Runner = _aws_cli,
    code_hash: Hasher = code_hash,
) -> int:
    args = parse_args(argv)
    outcome = check(
        run, code_hash, table=args.table, region=args.region, profile=args.profile
    )
    print(outcome.summary)
    if outcome.warning is not None:
        print(_annotation(outcome.warning))
    if args.summary:
        _write_summary(args.summary, outcome.summary)
    return 0


def _main() -> int:
    try:
        return main()
    except Exception as error:  # noqa: BLE001 - the check never fails a deploy
        print(_annotation(f"Curriculum seed check stopped: {type(error).__name__}: {error}"))
        return 0


if __name__ == "__main__":
    sys.exit(_main())
