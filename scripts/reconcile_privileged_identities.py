#!/usr/bin/env python3
"""Render a redacted privileged-identity reconciliation plan (dry-run by default)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from stoa.security.reconciliation import GrantSnapshot, IdentitySnapshot, reconcile_inventory


def _load(path: Path | None) -> list[IdentitySnapshot]:
    if path is None:
        return []
    rows = json.loads(path.read_text())
    return [
        IdentitySnapshot(
            provider_subject=str(row["providerSubject"]),
            issuer=str(row["issuer"]),
            groups=tuple(str(value) for value in row.get("groups", [])),
            user_id=row.get("userId"),
            profile_role=row.get("profileRole"),
            profile_status=row.get("profileStatus"),
            binding_count=int(row.get("bindingCount", 0)),
            approved=bool(row.get("approved", False)),
            grants=tuple(GrantSnapshot(**grant) for grant in row.get("grants", [])),
        )
        for row in rows
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, help="local inventory JSON; omitted means empty inventory")
    parser.add_argument("--run-id", default="phase-472-local-dry-run")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--environment")
    parser.add_argument("--confirm")
    parser.add_argument("--approved-run-id")
    args = parser.parse_args()
    if args.apply:
        raise SystemExit(
            "Apply is unavailable from this read-only CLI. Inject an approved non-production adapter programmatically."
        )
    report = reconcile_inventory(
        _load(args.input), run_id=args.run_id, apply=False,
        environment=args.environment, confirmation=args.confirm,
        approved_run_id=args.approved_run_id,
    )
    print(json.dumps(report.safe_projection(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
