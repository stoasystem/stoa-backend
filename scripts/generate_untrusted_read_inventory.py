#!/usr/bin/env python3
"""Generate and semantically check Phase 473 untrusted-read boundaries."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any, Iterable


SCHEMA_VERSION = "phase-473-boundary-inventory.v1"
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
    # Where the read lives now, as (file, symbol), when refactoring moved it
    # after the candidate was sealed. The candidate is still read at the
    # registered location; a tree without it must hold the read here, in a
    # symbol that makes the registered client call, or in the flow's named
    # parser when the flow is registered at that parser.
    successor: tuple[str, str] | None = None


def _flows(
    *,
    file: str,
    symbol: str,
    call: str,
    fields: tuple[tuple[str, str, str, str], ...],
    fake: str,
    selector: str,
    decisions: tuple[str, ...],
    transport: str | None = None,
    successor: tuple[str, str] | None = None,
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
            successor=successor,
        )
        for field, expected, parser, validator in fields
    ]


REVIEWED_FLOWS: tuple[ReviewedFlow, ...] = tuple(
    _flows(
        file="src/stoa/services/attachment_service.py",
        symbol="_reconcile_provider_part",
        call="s3.list_parts",
        # The chunk route went in #251; completion lists the parts S3 holds here,
        # in the upload package since #252.
        successor=("src/stoa/services/uploads/_lifecycle.py", "_provider_parts"),
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
        selector="tests/test_upload_provider_state_machine.py::test_reconcile_provider_part_list_parts_rejects_malformed_success_scalars",
        decisions=("D-05", "D-08", "D-16", "D-17"),
    )
    + _flows(
        file="src/stoa/services/attachment_service.py",
        symbol="_exact_multipart_absence",
        # Moved with the rest of an upload's life into the upload package (#252).
        successor=("src/stoa/services/uploads/_lifecycle.py", "_exact_multipart_absence"),
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
        selector="tests/test_upload_provider_cleanup.py::test_malformed_or_repeating_pagination_is_incomplete_and_redacted",
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
        selector="tests/test_upload_provider_state_machine.py::test_object_versions_rejects_malformed_marker_pair",
        decisions=("D-07", "D-09", "D-10", "D-12", "D-17"),
    )
    + [
        ReviewedFlow(
            file="src/stoa/services/attachment_service.py",
            symbol="_exact_object_digest",
            # Moved with the rest of an upload's life into the upload package (#252).
            successor=("src/stoa/services/uploads/_lifecycle.py", "_exact_object_digest"),
            client_call="s3.get_object",
            field=None,
            body_operation="Body.read+Body.close",
            expected_type="bounded_byte_stream",
            parser="_provider_mapping",
            validator="bounded_stream_with_best_effort_close",
            lower_fake="src/stoa/services/attachment_service.py:s3.get_object.Body",
            malformed_selector="tests/test_document_upload_limits.py::test_extraction_reasserts_exact_immutable_etag_and_closes_body",
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
        selector="tests/test_conversation_replay.py::test_batch_get_rejects_every_partial_duplicate_extra_or_malformed_shape",
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
        selector="tests/test_practice_receipt_snapshot.py::test_challenge_lists_reject_duplicate_ids_versions_and_stalled_markers",
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
        selector="tests/test_document_upload_limits.py::test_parser_input_and_decoded_output_limits_are_category_only",
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
        selector="tests/test_report_deletion.py::test_object_provider_ack_is_strict_and_lost_response_reconciles_exact_version",
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
        selector="tests/test_practice_receipt_snapshot.py::test_partial_attempt_route_reveals_no_answer",
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
        selector="tests/test_practice_teacher_authorization.py::test_missing_or_malformed_loaded_challenge_is_hidden_before_fact_load",
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
            # The quick replies (#443): read by `_quick_replies` in ask_answer;
            # the row stays with the flow's registered parser like the rest.
            ("quick_replies", "list[str]", "_parse_ai_response", "closed_ai_projection"),
            # The common mistakes (#444): read by `_common_mistakes` in
            # ask_answer, each entry an object of a text and a category.
            ("common_mistakes", "list[object]", "_parse_ai_response", "closed_ai_projection"),
        ),
        fake="src/stoa/services/ai_service.py:bedrock.invoke_model.Body",
        selector="tests/test_conversation_replay.py::test_terminal_parser_failure_is_closed_and_never_embedded_in_context",
        decisions=("D-03", "D-05", "D-10", "D-17"),
        # The Ask reply's checks moved beside the prompt (#437).
        successor=("src/stoa/services/ask_answer.py", "_parse_ai_response"),
    )
    + _flows(
        file="src/stoa/routers/conversations.py",
        symbol="send_message",
        call="attachment_repo.read_message_command_result",
        fields=(("status", "closed_disposition", "_coerce_command_result", "typed_command_state"),),
        fake="src/stoa/routers/conversations.py:attachment_repo.read_message_command_result",
        selector="tests/test_conversation_message_command.py::test_regular_and_sse_replay_exact_durable_rejection",
        decisions=("D-07", "D-08", "D-10", "D-13", "D-17"),
        transport="regular",
    )
    + _flows(
        file="src/stoa/routers/conversations.py",
        symbol="stream_message",
        call="attachment_repo.read_message_command_result",
        fields=(("status", "closed_disposition", "_coerce_command_result", "typed_command_state"),),
        fake="src/stoa/routers/conversations.py:attachment_repo.read_message_command_result",
        selector="tests/test_conversation_message_command.py::test_regular_and_sse_replay_exact_durable_rejection",
        decisions=("D-07", "D-08", "D-10", "D-13", "D-17"),
        transport="sse",
    )
    + _flows(
        file="src/stoa/db/repositories/account_deletion_repo.py",
        symbol="_claim_from_command",
        call="dynamodb.update_item.Attributes",
        fields=(
            ("lease_expires_at", "positive_int", "_positive_int", "type_is_int_not_bool_positive"),
            ("command_version", "positive_int", "_positive_int", "type_is_int_not_bool_positive"),
            ("branch_results_digest", "sha256_hex", "_claim_from_command", "exact_64_hex_digest"),
        ),
        fake="src/stoa/db/repositories/account_deletion_repo.py:table.update_item",
        selector="tests/test_account_deletion_claim_race.py::test_claim_compares_stored_expiry_with_distinct_current_epoch",
        decisions=("D-10", "D-16", "D-17"),
    )
    + _flows(
        file="src/stoa/db/repositories/account_deletion_repo.py",
        symbol="claim_deletion_command",
        call="scheduler explicit clock",
        fields=(("now_epoch", "positive_int", "_positive_int", "type_is_int_not_bool_positive"),),
        fake="src/stoa/db/repositories/account_deletion_repo.py:table.update_item",
        selector="tests/test_account_deletion_claim_race.py::test_claim_compares_stored_expiry_with_distinct_current_epoch",
        decisions=("D-10", "D-16", "D-17"),
    )
    + _flows(
        file="src/stoa/db/repositories/account_deletion_repo.py",
        symbol="scrub_parent_profile_child",
        call="dynamodb strong parent profile",
        fields=(("version", "positive_int", "_positive_int", "type_is_int_not_bool_positive"),),
        fake="src/stoa/db/repositories/account_deletion_repo.py:table.transact",
        selector="tests/test_profile_version_cas.py::test_real_locale_writer_races_real_scrub_and_preserves_exact_latest_bytes",
        decisions=("D-10", "D-16", "D-17"),
    )
    + _flows(
        file="src/stoa/db/repositories/notification_repo.py",
        symbol="_intent_claim",
        call="dynamodb delivery intent row",
        fields=(
            ("lease_expires_at", "positive_int", "_intent_claim", "closed_positive_int"),
            ("intent_version", "positive_int", "_intent_claim", "closed_positive_int"),
            ("scope_digest", "sha256_hex", "_intent_claim", "exact_64_hex_digest"),
            ("payload_digest", "sha256_hex", "_intent_claim", "exact_64_hex_digest"),
        ),
        fake="src/stoa/db/repositories/notification_repo.py:table.get_item",
        selector="tests/test_notification_delivery_intent_recovery.py::test_stale_claim_version_cannot_begin_complete_cancel_or_recover",
        decisions=("D-10", "D-16", "D-17"),
    )
    + _flows(
        file="src/stoa/db/repositories/notification_repo.py",
        symbol="claim_delivery_intent",
        call="dynamodb delivery intent row",
        fields=(("effect_state", "closed_state", "claim_delivery_intent", "registered_or_expired_pre_effect_only"),),
        fake="src/stoa/db/repositories/notification_repo.py:table.update_item",
        selector="tests/test_notification_delivery_intent_recovery.py::test_repository_claim_uses_explicit_current_time_not_proposed_expiry",
        decisions=("D-10", "D-16", "D-17"),
    )
    + _flows(
        file="src/stoa/services/notification_service.py",
        symbol="resolve_delivery_ownership",
        call="notification_repo.load_delivery_event_strong",
        fields=(
            ("owner_id", "nonblank_str", "resolve_delivery_ownership", "persisted_private_owner_only"),
            ("account_fence_generation", "positive_int", "resolve_delivery_ownership", "type_is_int_not_bool_positive"),
            ("event_version", "positive_int", "resolve_delivery_ownership", "type_is_int_not_bool_positive"),
        ),
        fake="src/stoa/db/repositories/notification_repo.py:table.get_item.ConsistentRead",
        selector="tests/test_notification_delivery_fencing.py::test_private_push_rejects_missing_malformed_or_stale_persisted_generation",
        decisions=("D-10", "D-16", "D-17"),
        successor=("src/stoa/services/notifications/_ledger.py", "resolve_delivery_ownership"),
    )
    + _flows(
        file="src/stoa/db/repositories/notification_repo.py",
        symbol="validate_global_nonprivate_event",
        call="notification_repo.load_delivery_event_strong",
        fields=(
            ("classification_contract", "closed_literal", "validate_global_nonprivate_event", "registered_contract_only"),
            ("classification_digest", "sha256_hex", "validate_global_nonprivate_event", "exact_content_seal"),
        ),
        fake="src/stoa/db/repositories/notification_repo.py:table.get_item.ConsistentRead",
        selector="tests/test_notification_delivery_fencing.py::test_global_nonprivate_requires_exact_persisted_contract_digest",
        decisions=("D-10", "D-16", "D-17"),
    )
)


FINDING_REGISTRY = (
    {
        "finding_id": "CR-01",
        "lower_fake_target": "src/stoa/db/repositories/account_deletion_repo.py:table.update_item",
        "runtime_selector": "tests/test_account_deletion_claim_race.py::test_lease_renewal_requires_owner_version_digest_and_returns_next_claim",
        "observed_assertion": "owner/version/digest/current-lease conditions and advancing claim",
    },
    {
        "finding_id": "CR-02",
        "lower_fake_target": "src/stoa/db/repositories/notification_repo.py:table.get_item.ConsistentRead",
        "runtime_selector": "tests/test_notification_delivery_fencing.py::test_private_push_rejects_missing_malformed_or_stale_persisted_generation",
        "observed_assertion": "strong canonical load and zero provider calls for invalid scope",
    },
    {
        "finding_id": "WR-01",
        "lower_fake_target": "src/stoa/db/repositories/account_deletion_repo.py:_valid_lifecycle_timestamp",
        "runtime_selector": "tests/test_account_deletion_claim_race.py::test_repository_rejects_invalid_lifecycle_timestamps",
        "observed_assertion": "blank naive malformed and non-string lifecycle values rejected",
    },
    {
        "finding_id": "WR-02",
        "lower_fake_target": "src/stoa/db/repositories/account_deletion_repo.py:table.transact",
        "runtime_selector": "tests/test_profile_version_cas.py::test_real_locale_writer_races_real_scrub_and_preserves_exact_latest_bytes",
        "observed_assertion": "real locale writer and narrow scrub share row-version CAS while exact concurrent preference bytes survive",
    },
    {
        "finding_id": "WR-03",
        "lower_fake_target": "src/stoa/db/repositories/notification_repo.py:table.update_item",
        "runtime_selector": "tests/test_notification_delivery_intent_recovery.py::test_repository_claim_uses_explicit_current_time_not_proposed_expiry",
        "observed_assertion": "only expired pre-effect claims are recoverable",
    },
)


def _symbol_nodes(tree: ast.AST) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _stable_ast_dump(value: Any) -> str:
    """Match Python 3.13+'s reviewed ``ast.dump(show_empty=False)`` bytes."""
    if isinstance(value, ast.AST):
        fields: list[str] = []
        for name in value._fields:
            field = getattr(value, name, None)
            literal_none = isinstance(value, (ast.Constant, ast.MatchSingleton)) and name == "value"
            if (field is None and not literal_none) or (isinstance(field, list) and not field):
                continue
            fields.append(f"{name}={_stable_ast_dump(field)}")
        return f"{type(value).__name__}({', '.join(fields)})"
    if isinstance(value, list):
        return "[" + ", ".join(_stable_ast_dump(item) for item in value) + "]"
    return repr(value)


def _normalized_digest(node: ast.AST) -> str:
    return sha256(_stable_ast_dump(node).encode()).hexdigest()


def _makes_call(symbol: ast.AST, client_call: str) -> bool:
    """Whether `symbol` calls the method `client_call` names (`s3.list_parts`)."""
    method = client_call.rsplit(".", 1)[-1]
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == method
        for node in ast.walk(symbol)
    )


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
    deletion = root / "src/stoa/db/repositories/account_deletion_repo.py"
    if deletion.exists():
        source = deletion.read_text()
        functions = _symbol_nodes(ast.parse(source, filename=deletion.as_posix()))
        claim_node = functions.get("_claim_from_command")
        claim = ast.get_source_segment(source, claim_node) if claim_node is not None else None
        # The coercion this forbids is a bare `int(...)`, matched as a call to the
        # builtin rather than as text: `stored_int(` ends in `int(` and read as a
        # substring it fails a reader that is doing the right thing.
        bare_int_coercion = claim_node is not None and any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "int"
            and any(
                "command_version" in (ast.get_source_segment(source, arg) or "")
                for arg in node.args
            )
            for node in ast.walk(claim_node)
        )
        if (
            not claim
            or 'command.get("command_version") or command.get("version")' not in claim
            or bare_int_coercion
        ):
            raise BoundaryViolation(
                "unsafe authority-bearing read: deletion command version"
            )
    # `notification_service.py` until the notification package (#686).
    notification = root / "src/stoa/services/notifications/_ledger.py"
    if notification.exists():
        source = notification.read_text()
        functions = _symbol_nodes(ast.parse(source, filename=notification.as_posix()))
        resolver_node = functions.get("resolve_delivery_ownership")
        resolver = (
            ast.get_source_segment(source, resolver_node)
            if resolver_node is not None
            else None
        )
        if (
            not resolver
            or 'classification = event.get("owner_classification")' not in resolver
            or "return resolve_legacy_delivery_owner(event, table=table)" not in resolver
            or any(
                marker in resolver
                for marker in ("recipient_id", "actor_id", "metadata", "event_type")
            )
        ):
            raise BoundaryViolation(
                "unsafe authority-bearing read: delivery ownership inference"
            )


def discover_dataflows(root: Path | str) -> list[dict[str, Any]]:
    root = Path(root).resolve()
    # A whole checkout carries the checked inventory; a partial tree a test builds
    # does not, and is read for what it holds.
    complete = (root / "docs/security/untrusted-read-inventory.json").is_file()
    parsed: dict[str, tuple[ast.Module, dict[str, ast.FunctionDef | ast.AsyncFunctionDef]]] = {}
    rows: list[dict[str, Any]] = []
    def symbol_at(file: str, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
        if file not in parsed:
            tree = ast.parse((root / file).read_text(), filename=file)
            parsed[file] = (tree, _symbol_nodes(tree))
        return parsed[file][1].get(name)

    for flow in REVIEWED_FLOWS:
        source_file, source_symbol = flow.file, flow.symbol
        path = root / flow.file
        symbol = symbol_at(flow.file, flow.symbol) if path.is_file() else None
        if symbol is None and flow.successor is not None:
            successor_file, successor_symbol = flow.successor
            if (root / successor_file).is_file():
                symbol = symbol_at(successor_file, successor_symbol)
                # A flow registered at its named parser moves with the parser,
                # which reads the response it is handed and makes no call.
                if (
                    symbol is not None
                    and successor_symbol != flow.parser
                    and not _makes_call(symbol, flow.client_call)
                ):
                    raise BoundaryViolation(
                        f"successor does not make the registered call: "
                        f"{successor_file}:{successor_symbol}:{flow.client_call}"
                    )
                source_file, source_symbol = successor_file, successor_symbol
        if not path.is_file() and symbol is None:
            if complete:
                raise BoundaryViolation(f"registered source file missing: {flow.file}")
            continue
        if symbol is None:
            raise BoundaryViolation(f"registered source symbol missing: {flow.file}:{flow.symbol}")
        row: dict[str, Any] = {
            "boundary_id": _boundary_id(flow),
            "source": {
                "file": source_file,
                "symbol": source_symbol,
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


def require_lower_fake_observed(counters: dict[str, int], target: str) -> None:
    value = counters.get(target)
    if type(value) is not int or value <= 0:
        raise ValueError(f"declared lower fake was not observed: {target}")


def build_inventory(root: Path | str) -> dict[str, Any]:
    root = Path(root).resolve()
    validate_taint_semantics(root)
    rows = discover_dataflows(root)
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
        "finding_registry": [dict(finding) for finding in FINDING_REGISTRY],
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
    output = Path(args.output) if args.output else root / "docs/security/untrusted-read-inventory.json"
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
