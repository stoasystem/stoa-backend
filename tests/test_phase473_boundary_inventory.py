from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "generate_phase473_boundary_inventory.py"
INVENTORY = ROOT / "docs" / "security" / "phase-473-boundary-inventory.json"
PRIVATE_INVENTORY = ROOT / "docs" / "security" / "phase-473-private-store-inventory.json"

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

REQUIRED_ROW_FIELDS = {
    "boundary_id",
    "source",
    "client_call",
    "tainted_response_root",
    "alias_chain",
    "consumed_field_path",
    "body_operation",
    "expected_type",
    "named_parser",
    "strict_validator",
    "trust_direction",
    "lower_fake_target",
    "malformed_selector",
    "decision_ids",
    "requirement_ids",
}


def _generator_module():
    assert GENERATOR.is_file(), "Plan 473-27 generator has not been implemented"
    spec = importlib.util.spec_from_file_location("phase473_boundary_inventory", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GENERATOR), *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def test_schema_is_per_consumption_and_source_relative():
    module = _generator_module()
    payload = json.loads(INVENTORY.read_text())
    assert payload["schema_version"] == "phase-473-boundary-inventory.v1"
    assert payload["rows"]
    assert len({row["boundary_id"] for row in payload["rows"]}) == len(payload["rows"])
    for row in payload["rows"]:
        assert REQUIRED_ROW_FIELDS <= row.keys()
        assert set(row["source"]) == {
            "file",
            "symbol",
            "span",
            "normalized_ast_sha256",
        }
        assert not Path(row["source"]["file"]).is_absolute()
        assert str(ROOT) not in json.dumps(row, sort_keys=True)
        assert row["trust_direction"] == "untrusted_to_application"
        assert row["consumed_field_path"] or row["body_operation"]
        assert row["requirement_ids"]
        assert row["decision_ids"]
    assert callable(module.discover_dataflows)
    assert callable(module.validate_taint_semantics)


def test_one_response_with_multiple_fields_has_one_exact_row_per_consumption():
    payload = json.loads(INVENTORY.read_text())
    rows = [
        row
        for row in payload["rows"]
        if row["source"]["file"] == "src/stoa/services/attachment_service.py"
        and row["source"]["symbol"] == "_reconcile_provider_part"
    ]
    fields = {row["consumed_field_path"] for row in rows}
    assert {
        "Parts",
        "Parts[].PartNumber",
        "Parts[].Size",
        "Parts[].ETag",
        "Parts[].ChecksumSHA256",
        "IsTruncated",
        "NextPartNumberMarker",
    } <= fields
    assert len({(row["client_call"], row["consumed_field_path"]) for row in rows}) == len(rows)


@pytest.mark.parametrize(
    "unsafe",
    [
        'str(response.get("ETag"))',
        'int(response["Count"])',
        'bool(response.get("IsTruncated"))',
        "response and True",
        "list(response)",
        'response.get("Count") > 0',
        'response.get("Count") + 1',
        'response.get("UnknownField")',
    ],
)
def test_taint_mutations_fail_inside_registered_parser_even_after_regeneration(
    tmp_path: Path, unsafe: str
):
    _generator_module()
    target = tmp_path / "src" / "stoa" / "services" / "attachment_service.py"
    target.parent.mkdir(parents=True)
    source = (ROOT / "src" / "stoa" / "services" / "attachment_service.py").read_text()
    source = source.replace(
        "    response = _gateway_call(operation)\n",
        f"    response = _gateway_call(operation)\n    unsafe = {unsafe}\n",
        1,
    )
    target.write_text(source)
    result = _run("--root", str(tmp_path), "--output", str(tmp_path / "regenerated.json"))
    assert result.returncode == 1
    assert "unsafe tainted response consumption" in result.stderr.lower()


@pytest.mark.parametrize(
    ("parser", "invalid"),
    [
        ("_required_provider_coordinate", None),
        ("_required_provider_coordinate", {"ETag": 1}),
        ("_positive_provider_integer", True),
        ("_positive_provider_integer", "1"),
        ("_provider_truncation", 1),
        ("_provider_truncation", "false"),
    ],
)
def test_strict_provider_parsers_reject_partial_malformed_and_bool_as_int(
    parser: str, invalid: object
):
    from stoa.services import attachment_service

    function = getattr(attachment_service, parser)
    with pytest.raises(Exception):
        if parser == "_required_provider_coordinate":
            function(invalid, "ETag")
        else:
            function(invalid)


def test_private_store_inventory_is_composed_exactly_once_and_not_duplicated():
    boundary = json.loads(INVENTORY.read_text())
    private = json.loads(PRIVATE_INVENTORY.read_text())
    composition = boundary["private_store_composition"]
    assert tuple(composition["branch_ids"]) == EXPECTED_BRANCHES
    assert composition["inventory_sha256"]
    assert composition["row_count"] == len(private["rows"])
    assert composition["write_ids"] == sorted(row["row_id"] for row in private["rows"])
    assert "private_store_rows" not in boundary
    assert {row["branch_id"] for row in private["branch_registry"]} == set(EXPECTED_BRANCHES)


def test_new_private_sink_fails_through_delegated_plan35_check(tmp_path: Path):
    _generator_module()
    for directory in ("src", "scripts", "docs", "tests"):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    target = tmp_path / "src" / "stoa" / "db" / "repositories" / "account_deletion_repo.py"
    with target.open("a", encoding="utf-8") as handle:
        handle.write(
            "\n\ndef synthetic_unreviewed_private_sink(client, private_value):\n"
            "    return client.put_item(Item={'student_id': private_value})\n"
        )
    result = _run("--root", str(tmp_path), "--output", str(tmp_path / "boundary.json"))
    assert result.returncode == 1
    assert "private-store checker failed" in result.stderr.lower()


def test_missing_or_extra_private_join_and_absent_selector_fail():
    module = _generator_module()
    private = json.loads(PRIVATE_INVENTORY.read_text())
    broken = json.loads(json.dumps(private))
    broken["rows"].pop()
    with pytest.raises(ValueError):
        module.compose_private_store_inventory(ROOT, broken)
    broken = json.loads(json.dumps(private))
    broken["rows"][0]["purge_selector"] = "tests/does_not_exist.py::test_missing"
    with pytest.raises(ValueError):
        module.compose_private_store_inventory(ROOT, broken)


def test_lower_fake_observation_rejects_high_level_only_monkeypatch():
    module = _generator_module()
    with pytest.raises(ValueError):
        module.require_lower_fake_observed(
            {
                "src/stoa/services/attachment_service.py:_gateway_call": 1,
                "src/stoa/services/attachment_service.py:s3.list_parts": 0,
            },
            "src/stoa/services/attachment_service.py:s3.list_parts",
        )


def test_generation_and_route_inventory_are_byte_deterministic(tmp_path: Path):
    first = tmp_path / "boundary-a.json"
    second = tmp_path / "boundary-b.json"
    assert _run("--root", str(ROOT), "--output", str(first)).returncode == 0
    assert _run("--root", str(ROOT), "--output", str(second)).returncode == 0
    assert first.read_bytes() == second.read_bytes() == INVENTORY.read_bytes()
    assert _run("--root", str(ROOT), "--check").returncode == 0


def test_decision_requirement_regular_sse_and_parser_coverage_is_closed():
    payload = json.loads(INVENTORY.read_text())
    rows = payload["rows"]
    decisions = {value for row in rows for value in row["decision_ids"]}
    requirements = {value for row in rows for value in row["requirement_ids"]}
    assert {f"D-{number:02d}" for number in range(1, 23)} <= decisions
    assert {"V9PRIV-01", "V9PRIV-02", "V9PRIV-03"} <= requirements
    assert {row["transport"] for row in rows if row.get("transport")} >= {"regular", "sse"}
    assert all(row["malformed_selector"].startswith("tests/") for row in rows)


def test_checked_outputs_contain_no_private_or_provider_coordinate_canaries():
    forbidden = (
        "private-question-canary",
        "student@example.invalid",
        "raw-object-key-canary",
        "multipart-upload-id-canary",
        "provider-version-id-canary",
        str(ROOT),
    )
    for path in (INVENTORY, ROOT / "docs/security/route-authorization-inventory.json"):
        text = path.read_text()
        assert not any(value in text for value in forbidden)
