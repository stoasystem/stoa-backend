#!/usr/bin/env python3
"""Write the app's OpenAPI document to docs/api/openapi.json, or check it is current.

The frontend validates its e2e mocks against this snapshot, fetched from `main`
(stoasystem/stoa-backend#80), so the path is fixed. The export is offline: no
AWS call is made, and the credentials below are the same placeholders the test
suite uses, only so that importing the app does not look for real ones.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

for name, value in (
    ("AWS_EC2_METADATA_DISABLED", "true"),
    ("AWS_ACCESS_KEY_ID", "testing"),
    ("AWS_SECRET_ACCESS_KEY", "testing"),
    ("AWS_SESSION_TOKEN", "testing"),
    ("AWS_DEFAULT_REGION", "eu-central-2"),
):
    os.environ.setdefault(name, value)

from stoa.main import app  # noqa: E402

DEFAULT_OUTPUT = Path("docs/api/openapi.json")


def render_snapshot() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    rendered = render_snapshot()
    if args.check:
        if args.output.exists() and args.output.read_text() == rendered:
            return 0
        print(
            f"{args.output} is not what the app serves; "
            "run scripts/generate_openapi_snapshot.py and commit the result",
            file=sys.stderr,
        )
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
