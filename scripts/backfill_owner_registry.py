#!/usr/bin/env python
"""Give rows written before the owner registry existed their registry rows (#397).

Since the dual-write, every fenced write registers the partition it goes into
under its owner (`USER#{id}/OWNS#{partition}`) and under each `also=` account
(`USER#{id}/REFERENCED_IN#{partition}`). Rows written before that have none, and
neither do rows written outside `fenced`. This walks the table once, finds every
row that names an account in a partition that account has not registered, and -
only with `--apply` - writes the missing registry rows. Accounts and the registry
are read first (one strong scan), then the rows (a second); see
`stoa.services.owner_registry_sweep`, which the daily sweep job shares.

- Dry-run by default: prints the report and writes nothing.
- `--apply` writes the missing rows: the same unconditional, idempotent Put the
  fenced write makes, so running it twice changes nothing the second time.
- Resumable: `--state PATH` records where the row scan got to after every page;
  run again with the same `--state` and it goes on from there.

Run it from an operator shell with credentials for the target account. It is
never run by a deploy, and was not run against production by the PR that added it.

Usage:
    python scripts/backfill_owner_registry.py                    # report only
    python scripts/backfill_owner_registry.py --state run.json   # report, resumable
    python scripts/backfill_owner_registry.py --apply --state run.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from stoa.services import owner_registry_sweep  # noqa: E402


def _load_state(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("complete"):
        return {"complete": True}
    start = state.get("last_key")
    return {"last_key": start} if isinstance(start, dict) else None


def _save_state(path: Path | None, report: owner_registry_sweep.SweepReport) -> None:
    if path is None:
        return
    path.write_text(
        json.dumps({"last_key": report.last_key, "complete": report.complete}, sort_keys=True),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None, *, table: object | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the missing registry rows")
    parser.add_argument("--state", type=Path, help="resume file, updated after every page")
    parser.add_argument("--max-pages", type=int, help="stop after this many row pages")
    args = parser.parse_args(argv)

    state = _load_state(args.state)
    if state and state.get("complete"):
        print(json.dumps({"complete": True, "note": "state file says the run finished"}))
        return 0
    report = owner_registry_sweep.run(
        table=table,
        write=args.apply,
        start=(state or {}).get("last_key"),
        max_pages=args.max_pages,
        on_page=lambda current: _save_state(args.state, current),
    )
    _save_state(args.state, report)
    print(json.dumps({"mode": "apply" if args.apply else "dry-run", **report.as_dict()}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
