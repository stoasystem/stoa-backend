#!/usr/bin/env python3
"""Generate the deterministic client error-action contract."""

from __future__ import annotations

import argparse
from pathlib import Path

from stoa.security.client_error_actions import render_client_error_actions


DEFAULT_OUTPUT = Path("docs/security/client-error-actions.json")


def render() -> str:
    return render_client_error_actions()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        return 0 if args.output.exists() and args.output.read_text() == render() else 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
