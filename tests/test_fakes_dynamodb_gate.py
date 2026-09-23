"""No new hand-written DynamoDB table doubles.

Five production defects reached users because a double in this directory was looser
than the real store and the suite agreed with the double. `fakes/dynamodb.py` is the
one that is held to the real semantics; everything that stands in for the table is
supposed to build on it.

This gate finds every class in `tests/` that defines `scan` or `query` and does not
derive from the shared double, and requires it to be named below with a reason. The
list is closed in both directions: an entry that no longer matches a class is an
error too, so the exemptions cannot outlive the code they were written for.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


TESTS_ROOT = Path(__file__).resolve().parent
SHARED_DOUBLE = "FakeTable"

# Why each of these is not the shared double. Three kinds:
#
# "script"  - it answers a prepared sequence of pages, including deliberately
#             malformed or repeating continuation keys, to drive a repository's
#             paging logic down a path a real table cannot be made to take.
# "repo"    - the collaborator is a repository, not a table: its surface is that
#             repository's own methods and its `scan`/`query` exist only to feed
#             them.
# "pending" - an ordinary table double that could move onto the shared one and has
#             not been moved yet. These are the ones still carrying the risk; card
#             019 group A converted the doubles behind the five known incidents
#             first, and this list is what is left.
HAND_WRITTEN_DOUBLES: dict[str, str] = {
    "conftest.py::_EmptyParentLinkTable": (
        "script: holds nothing on purpose, so a test that never installed a link "
        "table fails here instead of reaching the real one"
    ),
    "test_billing_fact_repo.py::AtomicBillingTable": "repo",
    "test_conversations.py::_PagedIndexTable": "script",
    "test_identity_authorization.py::FakeTable": "repo",
    "test_parent_link_paid_downstream.py::ConditionalTable": "repo",
    "test_parent_relationship_current.py::_Empty": (
        "script: answers nothing on purpose, so a report source somebody forgot to "
        "stub is visibly empty here rather than reaching a real table"
    ),
    "test_parent_relationship_current.py::_DeletionTable": (
        "repo: stands in for the deletion branch's own `delete_owned_row`, not for a table"
    ),
    "test_parent_student_links.py::FakeLinkTable": "repo",
    "test_phase473_account_deletion.py::_PagedPrivateTable": "script",
    "test_phase473_account_deletion.py::_Malformed": "script",
    "test_phase473_account_deletion.py::_Repeating": "script",
    "test_phase473_account_deletion.py::_Commands": "script",
    "test_phase473_account_deletion.py::_ParentProfile": "script",
    "test_phase473_conversation_deletion.py::_Table": "script",
    "test_phase473_conversation_replay.py::_HistoryTable": "script",
    "test_phase473_derived_content_purge.py::_Table": "script",
    "test_phase473_derived_content_purge.py::_Malformed": "script",
    "test_phase473_derived_content_purge.py::_Repeating": "script",
    "test_phase473_derived_content_purge.py::_Unavailable": "script",
    "test_phase473_notification_deletion.py::_Table": "script",
    "test_phase473_practice_learning_deletion.py::_Table": "script",
    "test_phase473_practice_snapshot.py::_LookupTable": "script",
    "test_phase473_practice_snapshot.py::_PagedTable": "script",
    "test_phase473_provider_cleanup.py::_EligibilityRecordingTable": (
        "script: records the scan request and answers nothing; the assertion is "
        "about what was asked for, not about what comes back"
    ),
    "test_phase473_report_deletion.py::_Table": "script",
    "test_phase473_retention_reconciliation.py::_StrongPagedTable": "script",
    "test_phase475_completed_deletion_replay.py::_DeletionTable": "repo",
    "test_phase475_deletion_discovery.py::_PagedTable": "script",
    "test_phase475_deletion_discovery.py::_RepeatingCursorTable": "script",
    "test_phase475_deletion_notification_identity_scrub.py::_NotificationTable": "repo",
    "test_phase475_deletion_relationship_scrub.py::_RelationshipDeletionTable": "repo",
    "test_phase475_deletion_teacher_identity_scrub.py::_TeacherDeletionTable": "repo",
    "test_phase475_parent_binding_reconciliation.py::_RepairTable": "repo",
    "test_phase475_parent_binding_transaction.py::_AtomicRelationshipTable": "repo",
    "test_privileged_identity_reconciliation.py::CapabilityTable": "repo",
    "test_subscription_operations.py::FakeTable": "repo",
    "test_token_allowances.py::AtomicAllowanceTable": "repo",
    "test_parent_children.py::FakeTable": "script",
    "test_parent_children.py::FakeQueryTable": "script",
    "test_parent_children.py::FakeScanTable": "script",
    "test_provision_production_admin.py::FakeTable": "pending",
    "test_report_flow.py::FakeDataTable": "pending",
    "test_report_service.py::FakeTable": "pending",
    "test_teacher_reply_sla.py::FakeAdminTable": "pending",
    "test_weekly_reports_job.py::FakeTable": "script",
}


def _table_shaped_classes() -> dict[str, list[str]]:
    """Every class under `tests/` that answers `scan` or `query`, with its bases."""
    classes: dict[str, list[str]] = {}
    for path in sorted(TESTS_ROOT.rglob("*.py")):
        if "fakes" in path.relative_to(TESTS_ROOT).parts:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.ClassDef):
                continue
            methods = {
                member.name
                for member in node.body
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            if not methods & {"scan", "query"}:
                continue
            name = f"{path.relative_to(TESTS_ROOT)}::{node.name}"
            classes[name] = [ast.unparse(base) for base in node.bases]
    return classes


def _derived_from_shared(classes: dict[str, list[str]]) -> set[str]:
    """Names reaching the shared double through any chain of test-local bases.

    Resolution is by name rather than by import, which is what an AST can see. A base
    named after a class that itself derives from the shared double counts, so a file
    may specialise another file's double without losing the exemption.
    """
    derived_names = {SHARED_DOUBLE}
    settled = set()
    while True:
        grown = False
        for name, bases in classes.items():
            if name in settled:
                continue
            if any(base.split(".")[-1] in derived_names for base in bases):
                derived_names.add(name.split("::")[-1])
                settled.add(name)
                grown = True
        if not grown:
            return settled


def test_every_table_double_either_builds_on_the_shared_one_or_is_listed() -> None:
    classes = _table_shaped_classes()
    derived = _derived_from_shared(classes)

    unlisted = sorted(
        name for name in classes if name not in derived and name not in HAND_WRITTEN_DOUBLES
    )

    assert not unlisted, (
        "these table doubles are neither built on fakes.dynamodb.FakeTable nor "
        f"listed with a reason in {Path(__file__).name}: {unlisted}"
    )


def test_the_exemption_list_holds_no_entry_that_no_longer_exists() -> None:
    """A stale exemption is an exemption nobody is being asked to justify."""
    classes = _table_shaped_classes()
    derived = _derived_from_shared(classes)

    stale = sorted(
        name
        for name in HAND_WRITTEN_DOUBLES
        if name not in classes or name in derived
    )

    assert not stale, f"remove these from HAND_WRITTEN_DOUBLES: {stale}"


def test_the_shared_double_is_actually_reached_by_this_scan() -> None:
    """Negative control: the walk above must be able to see a derived double at all.

    Without it, a scan that silently found no classes - a wrong root, a parse that
    swallowed its errors - would report a clean gate.
    """
    classes = _table_shaped_classes()
    derived = _derived_from_shared(classes)

    assert "test_account_provisioning.py::FakeAccountTable" in derived
    assert len(classes) > 30, "the walk stopped finding table doubles; check the root"


@pytest.mark.parametrize("reason", sorted(set(HAND_WRITTEN_DOUBLES.values())))
def test_every_exemption_reason_is_one_of_the_documented_kinds(reason: str) -> None:
    assert reason.split(":")[0] in {"script", "repo", "pending"}, reason
