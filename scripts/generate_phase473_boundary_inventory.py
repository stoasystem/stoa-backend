#!/usr/bin/env python3
"""Generate and semantically check Phase 473 untrusted-read boundaries."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterable


SCHEMA_VERSION = "phase-473-boundary-inventory.v1"
PRIVATE_SCHEMA_VERSION = "phase-473-private-store-inventory.v1"
EXPECTED_BRANCHES = (
    "account_profile",
    "identity_cross_account",
    "capability_scope",
    "question_ocr_session",
    "attachments",
    "moderation",
    "report_records",
    "report_artifacts",
    "support_recovery_feed",
    "conversation_messages",
    "practice_progress",
    "adaptive_assignment",
    "learning_memory",
    "ai_teacher_draft",
    "curriculum_signal",
    "notification_device_realtime",
    "external_delivery_debt",
)
REQUIREMENTS = ("V9PRIV-01", "V9PRIV-02", "V9PRIV-03")


class BoundaryViolation(ValueError):
    """One reviewed trust-boundary invariant was violated."""


@dataclass(frozen=True, slots=True)
class ReviewedFlow:
    file: str
    symbol: str
    client_call: str
    field: str | None
    body_operation: str | None
    expected_type: str
    parser: str
    validator: str
    lower_fake: str
    malformed_selector: str
    decisions: tuple[str, ...]
    requirements: tuple[str, ...] = REQUIREMENTS
    transport: str | None = None


def _flows(
    *,
    file: str,
    symbol: str,
    call: str,
    fields: tuple[tuple[str, str, str], ...],
    fake: str,
    selector: str,
    decisions: tuple[str, ...],
    transport: str | None = None,
) -> list[ReviewedFlow]:
    return [
        ReviewedFlow(
            file=file,
            symbol=symbol,
            client_call=call,
            field=field,
            body_operation=None,
            expected_type=expected,
            parser=parser,
            validator=validator,
            lower_fake=fake,
            malformed_selector=selector,
            decisions=decisions,
            transport=transport,
        )
        for field, expected, parser, validator in fields
    ]


REVIEWED_FLOWS: tuple[ReviewedFlow, ...] = tuple(
    _flows(
        file="src/stoa/services/attachment_service.py",
        symbol="_reconcile_provider_part",
        call="s3.list_parts",
        fields=(
            ("Parts", "list[object]", "_provider_mapping", "exact_list_of_mappings"),
            ("Parts[].PartNumber", "positive_int", "_positive_provider_integer", "type_is_int_not_bool"),
            ("Parts[].Size", "positive_int", "_positive_provider_integer", "type_is_int_not_bool"),
            ("Parts[].ETag", "nonblank_str", "_required_provider_coordinate", "type_is_str_nonblank"),
            ("Parts[].ChecksumSHA256", "canonical_base64_sha256", "_provider_sha256", "strict_base64_sha256"),
            ("IsTruncated", "bool", "_provider_truncation", "type_is_bool"),
            ("NextPartNumberMarker", "positive_int", "_positive_provider_integer", "type_is_int_not_bool"),
        ),
        fake="src/stoa/services/attachment_service.py:s3.list_parts",
        selector="tests/test_phase473_provider_state_machine.py::test_reconcile_provider_part_list_parts_rejects_malformed_success_scalars",
        decisions=("D-05", "D-08", "D-16", "D-17"),
    )
    + _flows(
        file="src/stoa/services/attachment_service.py",
        symbol="_exact_multipart_absence",
        call="s3.list_multipart_uploads",
        fields=(
            ("Uploads", "list[object]", "_provider_mapping", "exact_list_of_mappings"),
            ("Uploads[].Key", "nonblank_str", "_required_provider_coordinate", "type_is_str_nonblank"),
            ("Uploads[].UploadId", "nonblank_str", "_required_provider_coordinate", "type_is_str_nonblank"),
            ("IsTruncated", "bool", "_provider_truncation", "type_is_bool"),
            ("NextKeyMarker", "nonblank_str", "_required_provider_coordinate", "type_is_str_nonblank"),
            ("NextUploadIdMarker", "nonblank_str", "_required_provider_coordinate", "type_is_str_nonblank"),
        ),
        fake="src/stoa/services/attachment_service.py:s3.list_multipart_uploads",
        selector="tests/test_phase473_provider_cleanup.py::test_malformed_or_repeating_pagination_is_incomplete_and_redacted",
        decisions=("D-06", "D-08", "D-09", "D-15", "D-17"),
    )
    + _flows(
        file="src/stoa/services/attachment_service.py",
        symbol="_exact_version_absence",
        call="s3.list_object_versions",
        fields=(
            ("Versions", "list[object]", "_provider_mapping", "exact_list_of_mappings"),
            ("DeleteMarkers", "list[object]", "_provider_mapping", "exact_list_of_mappings"),
            ("Versions[].Key", "nonblank_str", "_required_provider_coordinate", "type_is_str_nonblank"),
            ("Versions[].VersionId", "nonblank_str", "_required_provider_coordinate", "type_is_str_nonblank"),
            ("Versions[].ETag", "nonblank_str", "_required_provider_coordinate", "type_is_str_nonblank"),
            ("IsTruncated", "bool", "_provider_truncation", "type_is_bool"),
            ("NextKeyMarker", "nonblank_str", "_required_provider_coordinate", "type_is_str_nonblank"),
            ("NextVersionIdMarker", "nonblank_str", "_required_provider_coordinate", "type_is_str_nonblank"),
        ),
        fake="src/stoa/services/attachment_service.py:s3.list_object_versions",
        selector="tests/test_phase473_provider_state_machine.py::test_object_versions_rejects_malformed_marker_pair",
        decisions=("D-07", "D-09", "D-10", "D-12", "D-17"),
    )
    + [
        ReviewedFlow(
            file="src/stoa/services/attachment_service.py",
            symbol="_exact_object_digest",
            client_call="s3.get_object",
            field=None,
            body_operation="Body.read+Body.close",
            expected_type="bounded_byte_stream",
            parser="_provider_mapping",
            validator="bounded_stream_with_best_effort_close",
            lower_fake="src/stoa/services/attachment_service.py:s3.get_object.Body",
            malformed_selector="tests/test_phase473_document_boundary.py::test_extraction_reasserts_exact_immutable_etag_and_closes_body",
            decisions=("D-01", "D-02", "D-03", "D-04", "D-05", "D-11", "D-13", "D-17"),
        )
    ]
    + _flows(
        file="src/stoa/db/repositories/attachment_repo.py",
        symbol="get_attachments",
        call="dynamodb.batch_get_item",
        fields=(
            ("Responses", "mapping[str,list[object]]", "get_attachments", "exact_batch_response_mapping"),
            ("Responses[].PK", "nonblank_str", "get_attachments", "exact_requested_key"),
            ("Responses[].SK", "nonblank_str", "get_attachments", "exact_requested_key"),
            ("UnprocessedKeys", "mapping", "get_attachments", "bounded_exact_retry_set"),
        ),
        fake="src/stoa/db/repositories/attachment_repo.py:dynamodb.batch_get_item",
        selector="tests/test_phase473_conversation_replay.py::test_batch_get_rejects_every_partial_duplicate_extra_or_malformed_shape",
        decisions=("D-07", "D-10", "D-12", "D-13", "D-14", "D-17"),
    )
    + _flows(
        file="src/stoa/db/repositories/practice_repo.py",
        symbol="_query_all_challenge_pages",
        call="dynamodb.query",
        fields=(
            ("Items", "list[object]", "_query_all_challenge_pages", "exact_list"),
            ("LastEvaluatedKey", "mapping_or_none", "_query_all_challenge_pages", "progressing_exact_cursor"),
        ),
        fake="src/stoa/db/repositories/practice_repo.py:dynamodb.query",
        selector="tests/test_phase473_practice_snapshot.py::test_challenge_lists_reject_duplicate_ids_versions_and_stalled_markers",
        decisions=("D-18", "D-19", "D-20"),
    )
    + _flows(
        file="src/stoa/services/document_parser_worker.py",
        symbol="_validated_payload",
        call="multiprocessing.Connection.recv",
        fields=(
            ("text", "str_or_none", "_validated_payload", "exact_closed_payload_shape"),
            ("category", "closed_category", "_validated_payload", "closed_category_or_none"),
        ),
        fake="src/stoa/services/document_parser_worker.py:Connection.recv",
        selector="tests/test_phase473_document_boundary.py::test_parser_input_and_decoded_output_limits_are_category_only",
        decisions=("D-03", "D-04", "D-05", "D-16", "D-17"),
    )
    + _flows(
        file="src/stoa/db/repositories/report_repo.py",
        symbol="parse_report_object_ack",
        call="s3.put_object",
        fields=(
            ("VersionId", "nonblank_str", "parse_report_object_ack", "_required_private_string"),
            ("ETag", "nonblank_str", "parse_report_object_ack", "_required_private_string"),
        ),
        fake="src/stoa/db/repositories/report_repo.py:s3.put_object",
        selector="tests/test_phase473_report_deletion.py::test_object_provider_ack_is_strict_and_lost_response_reconciles_exact_version",
        decisions=("D-10", "D-13", "D-17"),
    )
    + _flows(
        file="src/stoa/services/account_deletion_service.py",
        symbol="load_private_store_seal",
        call="json.loads",
        fields=(
            ("schema_version", "literal", "load_private_store_seal", "exact_schema_version"),
            ("branch_ids", "exact_list[str]", "load_private_store_seal", "exact_17_branch_order"),
            ("branch_registry", "list[object]", "load_private_store_seal", "closed_branch_contract"),
        ),
        fake="src/stoa/services/account_deletion_service.py:Path.read_bytes",
        selector="tests/test_phase473_account_deletion_seal.py::test_finalizer_rejects_every_incomplete_or_dishonest_seal",
        decisions=("D-10", "D-13", "D-17"),
    )
    + _flows(
        file="src/stoa/services/practice_projection_service.py",
        symbol="build_attempt_result",
        call="practice_repo.get_attempt_receipt",
        fields=(
            ("student_id", "nonblank_str", "build_attempt_result", "complete_receipt_required_text"),
            ("challenge_id", "nonblank_str", "build_attempt_result", "complete_receipt_required_text"),
            ("correct", "bool", "build_attempt_result", "type_is_bool"),
            ("standard_answer", "str", "build_attempt_result", "snapshot_only_projection"),
            ("explanation", "str", "build_attempt_result", "snapshot_only_projection"),
        ),
        fake="src/stoa/services/practice_projection_service.py:practice_repo.get_attempt_receipt",
        selector="tests/test_phase473_practice_snapshot.py::test_partial_attempt_route_reveals_no_answer",
        decisions=("D-18", "D-19", "D-20", "D-22"),
    )
    + _flows(
        file="src/stoa/services/practice_projection_service.py",
        symbol="build_privileged_answer",
        call="practice authorization dependency",
        fields=(
            ("course_id", "nonblank_str", "build_privileged_answer", "exact_loaded_challenge_scope"),
            ("class_id", "nonblank_str", "build_privileged_answer", "exact_loaded_challenge_scope"),
            ("correct_answer", "str", "build_privileged_answer", "privileged_read_projection"),
            ("explanation", "str", "build_privileged_answer", "privileged_read_projection"),
        ),
        fake="src/stoa/services/practice_projection_service.py:practice authorization dependency",
        selector="tests/test_phase473_practice_authorization.py::test_missing_or_malformed_loaded_challenge_is_hidden_before_fact_load",
        decisions=("D-18", "D-20", "D-21", "D-22"),
    )
    + _flows(
        file="src/stoa/services/ai_service.py",
        symbol="_parse_ai_response",
        call="bedrock.invoke_model.Body.read",
        fields=(
            ("steps", "list[str]", "_parse_ai_response", "closed_ai_projection"),
            ("answer", "str", "_parse_ai_response", "closed_ai_projection"),
            ("suggest_teacher", "bool", "_parse_ai_response", "closed_ai_projection"),
        ),
        fake="src/stoa/services/ai_service.py:bedrock.invoke_model.Body",
        selector="tests/test_phase473_conversation_replay.py::test_terminal_parser_failure_is_closed_and_never_embedded_in_context",
        decisions=("D-03", "D-05", "D-10", "D-17"),
    )
    + _flows(
        file="src/stoa/routers/conversations.py",
        symbol="send_message",
        call="attachment_repo.read_message_command_result",
        fields=(("status", "closed_disposition", "_coerce_command_result", "typed_command_state"),),
        fake="src/stoa/routers/conversations.py:attachment_repo.read_message_command_result",
        selector="tests/test_phase473_message_command.py::test_regular_and_sse_replay_exact_durable_rejection",
        decisions=("D-07", "D-08", "D-10", "D-13", "D-17"),
        transport="regular",
    )
    + _flows(
        file="src/stoa/routers/conversations.py",
        symbol="stream_message",
        call="attachment_repo.read_message_command_result",
        fields=(("status", "closed_disposition", "_coerce_command_result", "typed_command_state"),),
        fake="src/stoa/routers/conversations.py:attachment_repo.read_message_command_result",
        selector="tests/test_phase473_conversation_replay.py::test_regular_and_sse_share_one_closed_executor_boundary",
        decisions=("D-07", "D-08", "D-10", "D-13", "D-17"),
        transport="sse",
    )
)


def _symbol_nodes(tree: ast.AST) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _normalized_digest(node: ast.AST) -> str:
    return sha256(ast.dump(node, annotate_fields=True, include_attributes=False).encode()).hexdigest()


def _boundary_id(flow: ReviewedFlow) -> str:
    identity = "\0".join(
        (flow.file, flow.symbol, flow.client_call, flow.field or flow.body_operation or "", flow.transport or "")
    )
    return sha256(identity.encode()).hexdigest()[:24]


def _unsafe_provider_mapping_uses(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(), filename=str(path))
    function = _symbol_nodes(tree).get("_provider_mapping")
    if function is None:
        raise BoundaryViolation("registered parser _provider_mapping is missing")
    parent: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(function):
        for child in ast.iter_child_nodes(node):
            parent[child] = node
    unsafe: list[int] = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Name) or node.id != "response" or not isinstance(node.ctx, ast.Load):
            continue
        direct = parent.get(node)
        if isinstance(direct, ast.Return):
            continue
        if isinstance(direct, ast.Call) and isinstance(direct.func, ast.Name) and direct.func.id == "isinstance":
            continue
        unsafe.append(node.lineno)
    return unsafe


def validate_taint_semantics(root: Path | str) -> None:
    """Re-run semantic rules independently of the checked digest."""
    root = Path(root).resolve()
    attachment = root / "src/stoa/services/attachment_service.py"
    if attachment.exists():
        unsafe = _unsafe_provider_mapping_uses(attachment)
        if unsafe:
            joined = ",".join(str(value) for value in unsafe)
            raise BoundaryViolation(f"unsafe tainted response consumption at {attachment.name}:{joined}")


def discover_dataflows(root: Path | str) -> list[dict[str, Any]]:
    root = Path(root).resolve()
    complete = (root / "docs/security/phase-473-private-store-inventory.json").is_file()
    parsed: dict[str, tuple[ast.Module, dict[str, ast.FunctionDef | ast.AsyncFunctionDef]]] = {}
    rows: list[dict[str, Any]] = []
    for flow in REVIEWED_FLOWS:
        path = root / flow.file
        if not path.is_file():
            if complete:
                raise BoundaryViolation(f"registered source file missing: {flow.file}")
            continue
        if flow.file not in parsed:
            tree = ast.parse(path.read_text(), filename=flow.file)
            parsed[flow.file] = (tree, _symbol_nodes(tree))
        symbol = parsed[flow.file][1].get(flow.symbol)
        if symbol is None:
            raise BoundaryViolation(f"registered source symbol missing: {flow.file}:{flow.symbol}")
        row: dict[str, Any] = {
            "boundary_id": _boundary_id(flow),
            "source": {
                "file": flow.file,
                "symbol": flow.symbol,
                "span": [symbol.lineno, symbol.end_lineno],
                "normalized_ast_sha256": _normalized_digest(symbol),
            },
            "client_call": flow.client_call,
            "tainted_response_root": "raw_response",
            "alias_chain": ["raw_response", flow.parser],
            "consumed_field_path": flow.field,
            "body_operation": flow.body_operation,
            "expected_type": flow.expected_type,
            "named_parser": flow.parser,
            "strict_validator": flow.validator,
            "trust_direction": "untrusted_to_application",
            "lower_fake_target": flow.lower_fake,
            "malformed_selector": flow.malformed_selector,
            "decision_ids": list(flow.decisions),
            "requirement_ids": list(flow.requirements),
        }
        if flow.transport is not None:
            row["transport"] = flow.transport
        rows.append(row)
    rows.sort(key=lambda row: row["boundary_id"])
    if complete and len(rows) != len(REVIEWED_FLOWS):
        raise BoundaryViolation("read mapping cardinality drift")
    if len({row["boundary_id"] for row in rows}) != len(rows):
        raise BoundaryViolation("duplicate boundary id")
    return rows


def _selector_exists(root: Path, selector: str) -> bool:
    file_name, separator, node = selector.partition("::")
    if not separator or not node or "[" in node:
        return False
    path = root / file_name
    if not path.is_file():
        return False
    try:
        functions = _symbol_nodes(ast.parse(path.read_text(), filename=file_name))
    except (OSError, SyntaxError):
        return False
    return node in functions


def compose_private_store_inventory(root: Path | str, payload: dict[str, Any]) -> dict[str, Any]:
    root = Path(root).resolve()
    checked_path = root / "docs/security/phase-473-private-store-inventory.json"
    if not checked_path.is_file():
        raise ValueError("checked private-store inventory is missing")
    checked = json.loads(checked_path.read_text())
    if payload.get("schema_version") != PRIVATE_SCHEMA_VERSION:
        raise ValueError("private-store schema mismatch")
    if tuple(payload.get("branch_ids", ())) != EXPECTED_BRANCHES:
        raise ValueError("private-store branch set mismatch")
    expected_ids = sorted(row["row_id"] for row in checked.get("rows", ()))
    actual_rows = payload.get("rows")
    if not isinstance(actual_rows, list):
        raise ValueError("private-store rows missing")
    actual_ids = sorted(row.get("row_id") for row in actual_rows)
    if actual_ids != expected_ids or len(actual_ids) != len(set(actual_ids)):
        raise ValueError("private-store read/write join mismatch")
    for row in actual_rows:
        for key in ("source", "store", "owner_resolver", "fence_checkpoint", "purge_selector", "no_resurrection_selector"):
            if not row.get(key):
                raise ValueError(f"private-store join missing {key}")
        if row.get("classification") == "private_store" and not row.get("branch_id"):
            raise ValueError("private-store join missing branch_id")
        for selector_key in ("purge_selector", "no_resurrection_selector"):
            if not _selector_exists(root, row[selector_key]):
                raise ValueError(f"private-store selector missing: {row[selector_key]}")
    registry = payload.get("branch_registry")
    if not isinstance(registry, list) or [row.get("branch_id") for row in registry] != list(EXPECTED_BRANCHES):
        raise ValueError("private-store branch registry drift")
    return {
        "schema_version": PRIVATE_SCHEMA_VERSION,
        "inventory_sha256": sha256(checked_path.read_bytes()).hexdigest(),
        "row_count": len(actual_rows),
        "write_ids": actual_ids,
        "branch_ids": list(EXPECTED_BRANCHES),
        "source_digests": sorted(
            {
                row["source"]["normalized_ast_sha256"]
                for row in actual_rows
                if isinstance(row.get("source"), dict)
            }
        ),
    }


def _run_private_checker(root: Path) -> None:
    checker = root / "scripts/generate_phase473_private_store_inventory.py"
    inventory = root / "docs/security/phase-473-private-store-inventory.json"
    if not checker.is_file() or not inventory.is_file():
        return
    result = subprocess.run(
        [sys.executable, str(checker), "--root", str(root), "--check"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise BoundaryViolation(f"private-store checker failed: {detail}")


def require_lower_fake_observed(counters: dict[str, int], target: str) -> None:
    value = counters.get(target)
    if type(value) is not int or value <= 0:
        raise ValueError(f"declared lower fake was not observed: {target}")


def build_inventory(root: Path | str) -> dict[str, Any]:
    root = Path(root).resolve()
    validate_taint_semantics(root)
    rows = discover_dataflows(root)
    private_path = root / "docs/security/phase-473-private-store-inventory.json"
    composition: dict[str, Any] | None = None
    if private_path.is_file():
        _run_private_checker(root)
        composition = compose_private_store_inventory(root, json.loads(private_path.read_text()))
    source_files = [
        {
            "file": file,
            "boundary_count": sum(row["source"]["file"] == file for row in rows),
            "symbol_digests": sorted(
                {
                    row["source"]["normalized_ast_sha256"]
                    for row in rows
                    if row["source"]["file"] == file
                }
            ),
        }
        for file in sorted({row["source"]["file"] for row in rows})
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "rows": rows,
        "source_files": source_files,
        "private_store_composition": composition,
    }


def _render(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def _default_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(_default_root()))
    parser.add_argument("--output")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = Path(args.root).resolve()
    output = Path(args.output) if args.output else root / "docs/security/phase-473-boundary-inventory.json"
    try:
        rendered = _render(build_inventory(root))
    except (BoundaryViolation, ValueError, OSError, json.JSONDecodeError, SyntaxError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.check:
        return 0 if output.is_file() and output.read_bytes() == rendered else 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
