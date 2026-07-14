#!/usr/bin/env python3
"""Generate the deterministic client error-action contract."""

from __future__ import annotations

import argparse
from pathlib import Path

from stoa.security.client_error_actions import render_client_error_actions


DEFAULT_OUTPUT = Path("docs/security/client-error-actions.json")


def render() -> str:
    return render_client_error_actions()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(), encoding="utf-8")


if __name__ == "__main__":
    main()
