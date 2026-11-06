#!/usr/bin/env python3
"""Write docs/security/client-error-actions.json from the rule violation registry.

Every code the application registers (`stoa.rule_violation.register_codes`)
is listed with what its contract tells a client: the status, the action, the
catalog key its message is rendered from, and whether it may be retried. The
application is imported, as the OpenAPI snapshot does, so a domain that
registers codes is listed without being named here. The import is offline;
the credentials below are placeholders.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

for name, value in (
    ("AWS_EC2_METADATA_DISABLED", "true"),
    ("AWS_ACCESS_KEY_ID", "testing"),
    ("AWS_SECRET_ACCESS_KEY", "testing"),
    ("AWS_SESSION_TOKEN", "testing"),
    ("AWS_DEFAULT_REGION", "eu-central-2"),
):
    os.environ.setdefault(name, value)

import stoa.main  # noqa: E402,F401  (registers every domain's codes)
from stoa.rule_violation import catalog_key, registered_codes  # noqa: E402

SCHEMA_VERSION = "211.2"
DEFAULT_OUTPUT = Path("docs/security/client-error-actions.json")


def document() -> dict[str, object]:
    errors: dict[str, object] = {}
    for value, (domain, code) in sorted(registered_codes().items()):
        contract = code.contract
        errors[value] = {
            "domain": domain,
            "http_status": contract.http_status,
            "action": None if contract.action is None else str(contract.action),
            "message_key": catalog_key(code),
            "retry": {
                "retryable": contract.retryable,
                "idempotent_only": contract.idempotent_only,
                "max_attempts": contract.max_attempts,
                "retry_after_seconds": contract.retry_after_seconds,
            },
            "public_fields": sorted(contract.public_fields),
        }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "source": "Generated from the rule violation code registry (stoa.rule_violation) "
        "by scripts/generate_client_error_actions.py; do not edit by hand.",
        "errors": errors,
    }


def render() -> str:
    return json.dumps(document(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else None
        return 0 if current == render() else 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
