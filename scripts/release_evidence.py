#!/usr/bin/env python3
"""Validate release evidence and inspect safe-fixture metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stoa.services import release_evidence_service  # noqa: E402


def load_json(path: str | None) -> object:
    if not path or path == "-":
        return json.load(sys.stdin)
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(payload: object, path: str | None) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path:
        Path(path).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def command_validate(args: argparse.Namespace) -> int:
    bundle = load_json(args.input)
    if not isinstance(bundle, dict):
        raise SystemExit("release evidence input must be a JSON object")
    result = release_evidence_service.validate_release_bundle(bundle)
    write_json(result, args.output)
    return 0 if result["status"] == "passed" else 2


def command_fixture_status(args: argparse.Namespace) -> int:
    report = load_json(args.report_json) if args.report_json else None
    if report is not None and not isinstance(report, dict):
        raise SystemExit("fixture report input must be a JSON object")
    audit_events = load_json(args.audit_json) if args.audit_json else []
    if not isinstance(audit_events, list):
        raise SystemExit("fixture audit input must be a JSON array")
    result = release_evidence_service.build_fixture_inventory_response(
        fixture_name=args.fixture_name,
        report=report,
        audit_events=audit_events,
        expected_artifact_version_id=args.expected_artifact_version,
    )
    write_json(result, args.output)
    return 0 if result["privacy"]["passed"] else 2


def command_check_mutation(args: argparse.Namespace) -> int:
    reasons = release_evidence_service.mutation_refusal_reasons(
        fixture_name=args.fixture_name,
        mutation_mode=args.mutation_mode,
        fixture_status=args.fixture_status,
        privacy_passed=not args.privacy_failed,
    )
    result = {
        "allowed": not reasons,
        "refusal_reasons": reasons,
    }
    write_json(result, args.output)
    return 0 if not reasons else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate and redact a release evidence JSON bundle")
    validate.add_argument("--input", "-i", required=True, help="Evidence JSON path or '-' for stdin")
    validate.add_argument("--output", "-o", help="Output JSON path; defaults to stdout")
    validate.set_defaults(func=command_validate)

    fixture = subparsers.add_parser("fixture-status", help="Render sanitized safe-fixture inventory")
    fixture.add_argument("--fixture-name", required=True)
    fixture.add_argument("--report-json", help="Report metadata JSON path")
    fixture.add_argument("--audit-json", help="Report audit events JSON array path")
    fixture.add_argument("--expected-artifact-version")
    fixture.add_argument("--output", "-o", help="Output JSON path; defaults to stdout")
    fixture.set_defaults(func=command_fixture_status)

    mutation = subparsers.add_parser("check-mutation", help="Check fixture mutation refusal rules")
    mutation.add_argument("--fixture-name")
    mutation.add_argument("--mutation-mode")
    mutation.add_argument("--fixture-status", default="unknown")
    mutation.add_argument("--privacy-failed", action="store_true")
    mutation.add_argument("--output", "-o", help="Output JSON path; defaults to stdout")
    mutation.set_defaults(func=command_check_mutation)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
