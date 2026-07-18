from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "generate_phase473_private_store_inventory.py"
INVENTORY = ROOT / "docs" / "security" / "phase-473-private-store-inventory.json"
EVIDENCE = ROOT / "docs" / "security" / "phase-473-retained-evidence-policy.json"

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
    "row_id", "source", "sink_kind", "client_method", "store",
    "private_value_provenance", "owner_resolver", "fence_checkpoint",
    "classification", "branch_id", "subfamily", "field_scrub_allowlist",
    "tombstone_allowlist", "cursor_schema", "debt_schema", "quiescence",
    "purge_selector", "no_resurrection_selector", "lower_fake_target",
    "requirement_ids", "decision_ids",
}


def _generator_module():
    assert GENERATOR.is_file(), "Plan 473-35 generator has not been implemented"
    spec = importlib.util.spec_from_file_location("phase473_private_inventory", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GENERATOR), *args], cwd=cwd, text=True,
        capture_output=True, check=False,
    )


def test_checked_inventory_is_deterministic_complete_and_source_relative(tmp_path: Path):
    module = _generator_module()
    first, second = tmp_path / "inventory-a.json", tmp_path / "inventory-b.json"
    evidence_first, evidence_second = tmp_path / "evidence-a.json", tmp_path / "evidence-b.json"
    assert _run("--root", str(ROOT), "--output", str(first), "--evidence-output", str(evidence_first)).returncode == 0
    assert _run("--root", str(ROOT), "--output", str(second), "--evidence-output", str(evidence_second)).returncode == 0
    assert first.read_bytes() == second.read_bytes() == INVENTORY.read_bytes()
    assert evidence_first.read_bytes() == evidence_second.read_bytes() == EVIDENCE.read_bytes()
    assert _run("--root", str(ROOT), "--check").returncode == 0

    payload = json.loads(first.read_text())
    assert tuple(payload["branch_ids"]) == EXPECTED_BRANCHES
    assert {entry["branch_id"] for entry in payload["branch_registry"]} == set(EXPECTED_BRANCHES)
    assert payload["rows"]
    assert len({row["row_id"] for row in payload["rows"]}) == len(payload["rows"])
    for row in payload["rows"]:
        assert REQUIRED_ROW_FIELDS <= row.keys()
        source = row["source"]
        assert set(source) == {"file", "symbol", "span", "normalized_ast_sha256"}
        assert not Path(source["file"]).is_absolute()
        assert str(ROOT) not in json.dumps(row, sort_keys=True)
        assert row["fence_checkpoint"] == "USER#{owner_id}/ACCOUNT_FENCE:active:generation"
        assert row["classification"] in {"private_store", "retained_evidence", "reviewed_exclusion"}
    assert callable(module.discover_mutation_sinks)
    assert callable(module.validate_evidence_policy)


@pytest.mark.parametrize(
    "method",
    ["put_item", "update_item", "transact_write_items", "put_object",
     "upload_part", "send_email", "send_message", "admin_update_user_attributes",
     "post_to_connection", "invoke_model"],
)
def test_synthetic_sink_inside_registered_module_cannot_be_blessed_by_regeneration(tmp_path: Path, method: str):
    _generator_module()
    shutil.copytree(ROOT / "src", tmp_path / "src")
    target = tmp_path / "src" / "stoa" / "db" / "repositories" / "account_deletion_repo.py"
    with target.open("a", encoding="utf-8") as handle:
        handle.write("\n\ndef synthetic_unreviewed_private_sink(client, private_value):\n" f"    return client.{method}(Item={{'student_id': private_value}})\n")
    result = _run("--root", str(tmp_path), "--output", str(tmp_path / "regenerated.json"),
                  "--evidence-output", str(tmp_path / "regenerated-evidence.json"))
    assert result.returncode == 1
    assert "unreviewed mutating source" in result.stderr.lower()


def test_explicit_exclusions_are_closed_and_capability_is_never_excluded():
    _generator_module()
    payload = json.loads(INVENTORY.read_text())
    assert {row["exclusion_class"] for row in payload["exclusions"]} == {
        "teacher_application", "privileged_identity_admin",
        "authored_public_curriculum", "subscription_billing_accounting",
    }
    capability_rows = [row for row in payload["rows"] if row["source"]["file"].endswith("capability_repo.py")]
    assert capability_rows
    assert {row["classification"] for row in capability_rows} == {"private_store"}
    assert {row["branch_id"] for row in capability_rows} == {"capability_scope"}


@pytest.mark.parametrize("forbidden", ["answer", "name", "email", "subject", "note", "content_hash", "s3_key", "version_id"])
def test_retained_evidence_policy_rejects_private_fields_and_weak_governance(forbidden: str):
    module = _generator_module()
    policy = json.loads(EVIDENCE.read_text())
    broken = json.loads(json.dumps(policy))
    broken["classes"][0]["allowed_fields"].append(forbidden)
    with pytest.raises(ValueError):
        module.validate_evidence_policy(broken)
    for key in ("legal_basis", "ttl_seconds", "access_policy"):
        broken = json.loads(json.dumps(policy))
        broken["classes"][0][key] = None
        with pytest.raises(ValueError):
            module.validate_evidence_policy(broken)


def test_runtime_selectors_are_real_collected_lower_boundary_tests():
    _generator_module()
    payload = json.loads(INVENTORY.read_text())
    selectors = {selector for row in payload["rows"] for selector in (row["purge_selector"], row["no_resurrection_selector"])}
    assert selectors
    for selector in sorted(selectors):
        result = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", selector], cwd=ROOT, text=True, capture_output=True, check=False)
        assert result.returncode == 0, result.stdout + result.stderr
        assert selector in result.stdout
