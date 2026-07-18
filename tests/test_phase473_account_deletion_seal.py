from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from stoa.db.repositories import account_deletion_repo
from stoa.services import account_deletion_service


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "docs" / "security" / "phase-473-private-store-inventory.json"
EXPECTED_BRANCHES = (
    "account_profile", "identity_cross_account", "capability_scope",
    "question_ocr_session", "attachments", "moderation", "report_records",
    "report_artifacts", "support_recovery_feed", "conversation_messages",
    "practice_progress", "adaptive_assignment", "learning_memory",
    "ai_teacher_draft", "curriculum_signal", "notification_device_realtime",
    "external_delivery_debt",
)


def _seal_api():
    loader = getattr(account_deletion_service, "load_private_store_seal", None)
    validator = getattr(account_deletion_service, "validate_deletion_seal", None)
    assert callable(loader), "private-store runtime seal loader is missing"
    assert callable(validator), "aggregate deletion seal validator is missing"
    return loader, validator


def _ready_fixture():
    loader, _validator = _seal_api()
    seal = loader(INVENTORY_PATH)
    generation = 7
    results = {
        branch["branch_id"]: {
            "status": "complete", "quiescent": True, "epoch": 2,
            "generation": generation, "handler_version": branch["handler_version"],
            "subfamilies": list(branch["subfamilies"]), "cursor": None,
            "debt_counts": {}, "legal_retention_blocked": 0,
        }
        for branch in seal["branches"]
    }
    command = {
        "PK": "USER#student-1", "SK": "DELETE_COMMAND#command-1",
        "entity_type": "account_deletion_command", "command_id": "command-1",
        "user_id": "student-1", "generation": generation, "version": 11,
        "status": "running", "inventory_sha256": seal["inventory_sha256"],
        "branch_ids": list(EXPECTED_BRANCHES), "branch_contracts": seal["branch_contracts"],
        "branch_results": results, "accepted_at": "2026-07-18T00:00:00+00:00",
    }
    fence = {"PK": "USER#student-1", "SK": "ACCOUNT_FENCE", "status": "deletion_pending",
             "generation": generation, "version": 4, "command_id": "command-1"}
    return seal, command, fence


def test_runtime_registry_is_exactly_the_source_sealed_seventeen_branches():
    seal, _command, _fence = _ready_fixture()
    assert account_deletion_service.ACCOUNT_DELETION_BRANCH_IDS == EXPECTED_BRANCHES
    assert tuple(account_deletion_service.BRANCH_HANDLERS) == EXPECTED_BRANCHES
    assert tuple(branch["branch_id"] for branch in seal["branches"]) == EXPECTED_BRANCHES
    assert seal["inventory_sha256"] == sha256(INVENTORY_PATH.read_bytes()).hexdigest()
    assert set(seal["branch_contracts"]) == set(EXPECTED_BRANCHES)


@pytest.mark.parametrize("mutation", [
    "missing_branch", "extra_branch", "duplicate_branch_binding", "stale_generation",
    "stale_handler", "incomplete_subfamily", "cursor_remaining", "ordinary_debt",
    "legal_hold", "pending_external_delivery", "one_zero_epoch",
    "accepted_mislabeled_purged", "inventory_drift",
])
def test_finalizer_rejects_every_incomplete_or_dishonest_seal(mutation: str):
    seal, command, fence = _ready_fixture()
    _loader, validator = _seal_api()
    if mutation == "missing_branch":
        command["branch_results"].pop(EXPECTED_BRANCHES[0])
    elif mutation == "extra_branch":
        command["branch_results"]["surprise"] = deepcopy(
            command["branch_results"][EXPECTED_BRANCHES[0]]
        )
    elif mutation == "duplicate_branch_binding":
        command["branch_ids"][-1] = command["branch_ids"][0]
    elif mutation == "stale_generation":
        command["branch_results"][EXPECTED_BRANCHES[0]]["generation"] -= 1
    elif mutation == "stale_handler":
        command["branch_results"][EXPECTED_BRANCHES[0]]["handler_version"] = "old"
    elif mutation == "incomplete_subfamily":
        branch = next(item for item in seal["branches"] if item["subfamilies"])
        command["branch_results"][branch["branch_id"]]["subfamilies"] = []
    elif mutation == "cursor_remaining":
        command["branch_results"][EXPECTED_BRANCHES[0]]["cursor"] = {
            "PK": "x",
            "SK": "y",
        }
    elif mutation == "ordinary_debt":
        command["branch_results"][EXPECTED_BRANCHES[0]]["debt_counts"] = {
            "dependency": 1
        }
    elif mutation == "legal_hold":
        command["branch_results"]["report_artifacts"][
            "legal_retention_blocked"
        ] = 1
    elif mutation == "pending_external_delivery":
        command["branch_results"]["external_delivery_debt"]["debt_counts"] = {
            "pending": 1
        }
    elif mutation == "one_zero_epoch":
        command["branch_results"][EXPECTED_BRANCHES[0]]["epoch"] = 1
    elif mutation == "accepted_mislabeled_purged":
        command["branch_results"]["external_delivery_debt"][
            "external_receipts"
        ] = [{"status": "purged"}]
    elif mutation == "inventory_drift":
        command["inventory_sha256"] = "0" * 64
    assert validator(command=command, fence=fence, seal=seal) is False


def test_full_current_generation_seal_is_the_only_finalizable_state():
    seal, command, fence = _ready_fixture()
    _loader, validator = _seal_api()
    assert validator(command=command, fence=fence, seal=seal) is True
    assert account_deletion_service.can_finalize_account_deletion(
        command["branch_results"], sealed=True, command=command, fence=fence, seal=seal
    ) is True


class _ServiceRepository:
    def __init__(self, command: dict, fence: dict):
        self.command = deepcopy(command)
        self.fence = deepcopy(fence)
        self.finalized = 0

    def get_command_by_id(self, _command_id: str):
        return deepcopy(self.command)

    def get_account_fence(self, _user_id: str):
        return deepcopy(self.fence)

    def persist_branch_result(self, *_args):
        raise AssertionError("already sealed branches must not be rewritten")

    def finalize_account_deletion(self, *, command: dict, fence: dict, seal: dict, now_iso: str):
        self.finalized += 1
        self.command, self.fence = account_deletion_repo.finalize_account_deletion(
            command=command,
            fence=fence,
            seal=seal,
            now_iso=now_iso,
            table=_FinalizerTable(command, fence),
        )
        return deepcopy(self.command), deepcopy(self.fence)


def test_worker_revalidates_the_runtime_projection_and_invokes_only_plan35_finalizer():
    _seal, command, fence = _ready_fixture()
    repository = _ServiceRepository(command, fence)
    worker = account_deletion_service.AccountDeletionService(
        repository=repository,
        now=lambda: "2026-07-18T01:00:00+00:00",
        inventory_path=INVENTORY_PATH,
    )
    worker.continue_command(command["command_id"])
    assert repository.finalized == 1
    assert repository.command["status"] == "complete"
    assert repository.fence["status"] == "deleted"

    drifted = deepcopy(command)
    drifted["inventory_sha256"] = "f" * 64
    repository = _ServiceRepository(drifted, fence)
    worker = account_deletion_service.AccountDeletionService(
        repository=repository,
        inventory_path=INVENTORY_PATH,
    )
    with pytest.raises(account_deletion_repo.AccountDeletionConflict):
        worker.continue_command(command["command_id"])
    assert repository.finalized == 0


class _FinalizerTable:
    def __init__(self, command: dict, fence: dict):
        self.command, self.fence, self.mutations = deepcopy(command), deepcopy(fence), 0

    def finalize_account_deletion(self, expected: dict, command_item: dict, fence_item: dict):
        if self.command["status"] == "complete" and self.fence["status"] == "deleted":
            return deepcopy(self.command), deepcopy(self.fence)
        assert expected["command_version"] == self.command["version"]
        assert expected["fence_version"] == self.fence["version"]
        self.command, self.fence = deepcopy(command_item), deepcopy(fence_item)
        self.mutations += 1
        return deepcopy(self.command), deepcopy(self.fence)


def test_terminal_transaction_is_exact_once_and_replay_minimal_forever():
    seal, command, fence = _ready_fixture()
    table = _FinalizerTable(command, fence)
    finalizer = getattr(account_deletion_repo, "finalize_account_deletion", None)
    assert callable(finalizer), "same-table account terminalizer is missing"
    first_command, first_fence = finalizer(command=command, fence=fence, seal=seal, now_iso="2026-07-18T01:00:00+00:00", table=table)
    second_command, second_fence = finalizer(command=first_command, fence=first_fence, seal=seal, now_iso="2026-07-18T02:00:00+00:00", table=table)
    assert table.mutations == 1
    assert first_command == second_command and first_fence == second_fence
    assert first_command["status"] == "complete" and first_fence["status"] == "deleted"
    assert first_fence["generation"] == command["generation"] and "command_id" in first_fence
    assert "branch_results" not in first_command
    assert set(first_command) <= {
        "PK", "SK", "entity_type", "schema_version", "command_id", "user_id",
        "generation", "status", "accepted_at", "completed_at", "inventory_sha256",
        "issuer_hash", "subject_hash", "fingerprint", "method", "path",
        "request_body_sha256", "receipt", "accounting_identity", "external_receipts",
        "evidence_references", "version",
    }


def test_checked_inventory_bytes_are_valid_json_and_have_no_private_coordinates():
    _seal_api()
    encoded = json.dumps(json.loads(INVENTORY_PATH.read_text()), sort_keys=True).lower()
    assert "student-1" not in encoded and "versionid=" not in encoded and "s3://" not in encoded
