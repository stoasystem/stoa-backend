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
        return 0 if args.output.exists() and args.output.read_text() == rendered else 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
