from __future__ import annotations

import ast
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
MANIFEST = ROOT / "docs" / "security" / "phase-473-evidence-manifest.json"

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

FINDING_SELECTORS = {
    "CR-01": (
        "src/stoa/db/repositories/account_deletion_repo.py:table.update_item",
        "tests/test_phase473_account_deletion_claim_fencing.py::test_branch_result_cas_requires_owner_version_digest_and_returns_next_claim",
    ),
    "CR-02": (
        "src/stoa/services/notification_service.py:provider_call",
        "tests/test_phase473_private_delivery_fencing.py::test_private_push_rejects_missing_malformed_or_stale_persisted_generation",
    ),
    "WR-01": (
        "src/stoa/db/repositories/account_deletion_repo.py:_valid_lifecycle_timestamp",
        "tests/test_phase473_account_deletion_claim_fencing.py::test_repository_rejects_invalid_lifecycle_timestamps",
    ),
    "WR-02": (
        "src/stoa/db/repositories/account_deletion_repo.py:table.transact",
        "tests/test_phase473_account_deletion_claim_fencing.py::test_parent_scrub_is_version_cas_and_never_replaces_concurrent_preferences",
    ),
    "WR-03": (
        "src/stoa/db/repositories/notification_repo.py:table.update_item",
        "tests/test_phase473_delivery_intent_recovery.py::test_repository_claim_uses_explicit_current_time_not_proposed_expiry",
    ),
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


def _historical_candidate_root(tmp_path: Path) -> Path:
    candidate = json.loads(MANIFEST.read_text())["candidate_sha"]
    archive = subprocess.run(
        ["git", "archive", candidate], cwd=ROOT, capture_output=True, check=True
    )
    candidate_root = tmp_path / "candidate"
    candidate_root.mkdir()
    subprocess.run(
        ["tar", "-x", "-C", str(candidate_root)],
        input=archive.stdout,
        check=True,
    )
    return candidate_root


def test_checked_inventory_is_deterministic_complete_and_source_relative(tmp_path: Path):
    module = _generator_module()
    candidate_root = _historical_candidate_root(tmp_path)
    first, second = tmp_path / "inventory-a.json", tmp_path / "inventory-b.json"
    evidence_first, evidence_second = tmp_path / "evidence-a.json", tmp_path / "evidence-b.json"
    assert _run("--root", str(candidate_root), "--output", str(first), "--evidence-output", str(evidence_first)).returncode == 0
    assert _run("--root", str(candidate_root), "--output", str(second), "--evidence-output", str(evidence_second)).returncode == 0
    assert first.read_bytes() == second.read_bytes() == INVENTORY.read_bytes()
    assert evidence_first.read_bytes() == evidence_second.read_bytes() == EVIDENCE.read_bytes()
    assert _run("--root", str(candidate_root), "--check").returncode == 0
    module.validate_private_store_semantics(ROOT)

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


def test_ast_source_seal_is_stable_on_the_phase474_python_312_runtime():
    module = _generator_module()
    tree = ast.parse("client.put_item(Item={'student_id': private_value})")
    call = next(node for node in ast.walk(tree) if isinstance(node, ast.Call))

    assert module._stable_ast_dump(call) == (
        "Call(func=Attribute(value=Name(id='client', ctx=Load()), "
        "attr='put_item', ctx=Load()), keywords=[keyword(arg='Item', "
        "value=Dict(keys=[Constant(value='student_id')], "
        "values=[Name(id='private_value', ctx=Load())]))])"
    )


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


def test_all_five_findings_have_exact_lower_source_seals_and_selectors():
    payload = json.loads(INVENTORY.read_text())
    findings = {row["finding_id"]: row for row in payload["finding_registry"]}
    assert set(findings) == set(FINDING_SELECTORS)
    for finding_id, (lower_target, selector) in FINDING_SELECTORS.items():
        row = findings[finding_id]
        assert row["lower_fake_target"] == lower_target
        assert row["runtime_selector"] == selector
        assert row["source_symbols"]
        assert row["required_semantics"]
        assert row["privacy_surface"] == "bounded_noncontent_lifecycle_facts"


@pytest.mark.parametrize(
    ("relative", "before", "after"),
    [
        (
            "src/stoa/db/repositories/account_deletion_repo.py",
            "lease_expires_at<:now_epoch",
            "lease_expires_at<:expiry",
        ),
        (
            "src/stoa/db/repositories/account_deletion_repo.py",
            "AND branch_results_digest=:branch_results_digest ",
            "",
        ),
        (
            "src/stoa/db/repositories/account_deletion_repo.py",
            "now_iso = _valid_lifecycle_timestamp(now_iso)",
            "now_iso = str(now_iso)",
        ),
        (
            "src/stoa/db/repositories/account_deletion_repo.py",
            "user_id=:parent AND #version=:expected_version",
            "user_id=:parent",
        ),
        (
            "src/stoa/db/repositories/notification_repo.py",
            "(#effect=:registered OR (#effect=:pre_effect AND ",
            "(#effect=:registered OR (#effect=:inflight AND ",
        ),
        (
            "src/stoa/services/notification_service.py",
            "inflight_claim = notification_repo.begin_delivery_effect(\n"
            "            scope=scope,\n"
            "            claim=claimed,\n"
            "            now_iso=now_iso(),\n"
            "        )",
            "inflight_claim = claimed",
        ),
        (
            "src/stoa/services/websocket_service.py",
            "batch = notification_service.load_authoritative_delivery_events([event_id])",
            "batch = notification_service.AuthoritativeDeliveryBatch(events=(item,), ownership=item.get('metadata'), event_set_digest=event_id)",
        ),
    ],
)
def test_reviewed_semantics_reject_weakening_after_candidate_regeneration(
    tmp_path: Path, relative: str, before: str, after: str
):
    module = _generator_module()
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    source = (ROOT / relative).read_text()
    assert before in source
    target.write_text(source.replace(before, after, 1))
    with pytest.raises(ValueError, match="reviewed private-store semantic"):
        module.validate_private_store_semantics(tmp_path)
