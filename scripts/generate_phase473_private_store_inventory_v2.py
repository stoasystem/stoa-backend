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
- `supersedes` names v1 by its schema and sha-256, and `seal_rule` states which
  commands run under which inventory.

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
