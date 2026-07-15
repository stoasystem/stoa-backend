#!/usr/bin/env python3
"""Render a redacted privileged-identity reconciliation plan (dry-run by default)."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
from typing import Any

from stoa.security.reconciliation import (
    GrantSnapshot,
    IdentitySnapshot,
    RepositoryTighteningAdapter,
    reconcile_inventory,
)


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


def _load_adapter(factory_path: str, config: Path) -> Any:
    module_name, separator, attribute = factory_path.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError("adapter factory must use module:function format")
    factory = getattr(importlib.import_module(module_name), attribute)
    adapter = factory(config)
    if not isinstance(adapter, RepositoryTighteningAdapter):
        raise ValueError("adapter factory must return RepositoryTighteningAdapter")
    return adapter


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, help="local inventory JSON; omitted means empty inventory")
    parser.add_argument("--run-id", default="phase-472-local-dry-run")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--environment")
    parser.add_argument("--confirm")
    parser.add_argument("--approved-run-id")
    parser.add_argument("--adapter-factory")
    parser.add_argument("--adapter-config", type=Path)
    args = parser.parse_args(argv)
    adapter = None
    if args.apply:
        if args.environment != "non-production":
            raise SystemExit("Apply requires --environment non-production")
        if args.confirm != "APPLY_TIGHTENING":
            raise SystemExit("Apply requires --confirm APPLY_TIGHTENING")
        if not args.run_id or args.approved_run_id != args.run_id:
            raise SystemExit("Apply requires --approved-run-id exactly equal to --run-id")
        if not args.adapter_factory or args.adapter_config is None:
            raise SystemExit("Apply requires --adapter-factory and --adapter-config")
        try:
            adapter = _load_adapter(args.adapter_factory, args.adapter_config)
        except Exception as exc:
            raise SystemExit("Apply adapter construction failed before reconciliation") from exc
    report = reconcile_inventory(
        _load(args.input), run_id=args.run_id, apply=args.apply,
        environment=args.environment, confirmation=args.confirm,
        approved_run_id=args.approved_run_id,
        adapter=adapter,
    )
    print(json.dumps(report.safe_projection(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
