#!/usr/bin/env python3
"""Generate the registered FastAPI route authorization inventory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from stoa.main import app
from stoa.security.route_inventory import inventory_projection


def render_inventory() -> str:
    return json.dumps(inventory_projection(app), indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--output", type=Path, default=Path("docs/security/route-authorization-inventory.json")
    )
    args = parser.parse_args()
    rendered = render_inventory()
    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else None
        return 0 if current == rendered else 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # The same unspelled encoding that corrupted the OpenAPI snapshot on a
    # Windows run. This file is the authorization inventory, and the frontend's
    # contract gate reads it from main: it stays ASCII today, but a single
    # non-ASCII path or purpose name would break it the same way.
    args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
