#!/usr/bin/env python
"""Derive the v2 private-store inventory from the sealed v1 one (#397).

v1 (`phase-473-private-store-inventory.json`, `handler_version 473-35.v1`) proves
completeness by strong full-table scans. v2 proves it over the account's derived
partitions and its owner registry (`stoa.db.owner_registry`). Everything else -
branches, rows, sinks, scrub and tombstone allowlists, quiescence - is the
reviewed v1 inventory unchanged, so v2 is a deterministic function of v1's bytes:

- `schema_version` -> `phase-473-private-store-inventory.v2`;
- every branch's `handler_version` -> `HANDLER_VERSION`;
- every row's `cursor_schema` -> `CURSOR_SCHEMA`;
- `supersedes` names v1 by its schema and sha-256, `seal_rule` states which
  commands run under which inventory, and `coverage` says plainly what v2
  inherits from v1, what it adds, and what it does not prove (the registry
  writers are listed there, not inventoried as sinks).

v1 is never rewritten: commands sealed under it (any in flight when this ships)
finish on the scan path against those exact bytes.

Usage:
    python scripts/generate_phase473_private_store_inventory_v2.py           # write
    python scripts/generate_phase473_private_store_inventory_v2.py --check   # compare
"""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "docs" / "security" / "phase-473-private-store-inventory.json"
V2 = ROOT / "docs" / "security" / "phase-473-private-store-inventory.v2.json"

SCHEMA_VERSION = "phase-473-private-store-inventory.v2"
HANDLER_VERSION = "473-36.v2"
CURSOR_SCHEMA = {
    "complete_scan_required": False,
    "fields": ["PK", "SK"],
    "partitions": "owner_registry.derived_partitions(owner_id) + USER#{owner_id}/OWNS#* + USER#{owner_id}/REFERENCED_IN#*",
    "type": "strong_owner_registry",
}
SEAL_RULE = (
    "A deletion command runs to its end under the inventory it was sealed with. "
    "inventory_sha256 equal to the v1 sha: strong full-table scan path, validated "
    "and finalized against v1. Equal to this inventory's sha: owner registry path, "
    "validated and finalized against v2. Anything else: seal drift. Which inventory "
    "a new command is sealed with is decided at acceptance only."
)


# What v2 does and does not prove, stated in the inventory itself (#397).
COVERAGE = {
    "inherited_from_v1": (
        "branches, rows, mutation sinks, scrub and tombstone allowlists and "
        "quiescence are v1's, reviewed against v1's pinned candidate commit; "
        "they are not re-derived from the current tree"
    ),
    "proven_by_v2": (
        "each branch reads only owner_registry.derived_partitions(owner_id) and "
        "the partitions registered under USER#{owner_id}, strongly and by key, "
        "and needs two clean passes over them; acceptance seals v2 only after a "
        "complete owner registry sweep with zero missing registrations in the "
        "last 36 hours"
    ),
    "not_proven": [
        "that every current writer of a row deletion acts on registers its "
        "partition: held by tests/test_owner_registry_unfenced_writers.py "
        "(reviewed list) and the daily sweep, not by this inventory",
        "rows written after the fence flips by writers outside db_table.fenced",
        "Update operations inside fenced whose values name another account "
        "(only Put items are read for mentions; the listed writers register "
        "explicitly)",
    ],
    "registry_writers": [
        "src/stoa/db/table.py:fenced",
        "src/stoa/db/repositories/account_deletion_repo.py:registry_operations_for",
        "src/stoa/db/repositories/upload_code_repo.py:put_code",
        "src/stoa/db/repositories/report_repo.py:put_recovery_job",
        "src/stoa/db/repositories/capability_repo.py:_apply",
        "src/stoa/db/repositories/parent_link_repo.py:close_link",
        "src/stoa/db/repositories/notification_repo.py:_persist_private",
        "src/stoa/services/help_requests.py:_write",
        "src/stoa/services/owner_registry_sweep.py:run (backfill --apply)",
    ],
    "registry_removers": [
        "src/stoa/db/repositories/account_deletion_repo.py:delete_owner_registry",
    ],
}


def build(v1_bytes: bytes) -> dict[str, Any]:
    payload = json.loads(v1_bytes)
    if payload.get("schema_version") != "phase-473-private-store-inventory.v1":
        raise ValueError("v2 is derived from the v1 inventory only")
    payload["schema_version"] = SCHEMA_VERSION
    for branch in payload["branch_registry"]:
        branch["handler_version"] = HANDLER_VERSION
    for row in payload["rows"]:
        row["cursor_schema"] = dict(CURSOR_SCHEMA)
    payload["supersedes"] = {
        "inventory_sha256": sha256(v1_bytes).hexdigest(),
        "schema_version": "phase-473-private-store-inventory.v1",
    }
    payload["seal_rule"] = SEAL_RULE
    payload["coverage"] = COVERAGE
    return payload


def render(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    expected = render(build(V1.read_bytes()))
    if args.check:
        if not V2.is_file() or V2.read_bytes() != expected:
            print("v2 private-store inventory is stale; regenerate it")
            return 1
        return 0
    V2.write_bytes(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
