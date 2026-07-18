"""Plan 473-33 contracts for learning-store writer fencing and deletion."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import pytest

from stoa.db.repositories import (
    adaptive_learning_repo,
    ai_teacher_tools_repo,
    curriculum_analytics_repo,
    practice_repo,
)
from stoa.services import account_deletion_service


STUDENT_ID = "student-learning-delete"
GENERATION = 7
NOW = "2026-07-18T10:00:00+00:00"


def _contract(module: Any, name: str) -> Any:
    value = getattr(module, name, None)
    if value is None:
        pytest.fail(f"Plan 473-33 contract {module.__name__}.{name} is not implemented")
    return value


def _fence(operation: dict[str, Any]) -> dict[str, Any]:
    check = operation["ConditionCheck"]
    assert check["Key"] == {"PK": f"USER#{STUDENT_ID}", "SK": "ACCOUNT_FENCE"}
    assert check["ExpressionAttributeValues"][":generation"] == GENERATION
    return check


def test_source_registry_closes_learning_rows_writers_and_private_fields() -> None:
    practice_rows = _contract(practice_repo, "PRACTICE_PRIVATE_ROW_REGISTRY")
    adaptive_rows = _contract(adaptive_learning_repo, "ADAPTIVE_PRIVATE_ROW_REGISTRY")
    draft_rows = _contract(ai_teacher_tools_repo, "AI_DRAFT_PRIVATE_ROW_REGISTRY")
    writers = (
        set(_contract(practice_repo, "PRACTICE_WRITER_REGISTRY"))
        | set(_contract(adaptive_learning_repo, "ADAPTIVE_WRITER_REGISTRY"))
        | set(_contract(ai_teacher_tools_repo, "AI_DRAFT_WRITER_REGISTRY"))
        | set(_contract(curriculum_analytics_repo, "CURRICULUM_SIGNAL_WRITER_REGISTRY"))
    )
    private = (
        set(_contract(practice_repo, "PRACTICE_PRIVATE_FIELDS"))
        | set(_contract(adaptive_learning_repo, "ADAPTIVE_PRIVATE_FIELDS"))
        | set(_contract(ai_teacher_tools_repo, "AI_DRAFT_PRIVATE_FIELDS"))
        | set(_contract(curriculum_analytics_repo, "CURRICULUM_SIGNAL_PRIVATE_FIELDS"))
    )
    assert {"progress", "attempt", "legacy_mistake", "usage"} <= set(practice_rows)
    assert {"assignment", "learning_memory"} <= set(adaptive_rows)
    assert {"ai_teacher_draft"} <= set(draft_rows)
    assert {
        "put_attempt",
        "mark_lesson_completed",
        "put_assignment",
        "put_assignment_if_absent",
        "update_assignment",
        "put_memory_snapshot",
        "put_draft",
        "update_draft",
        "record_curriculum_signal",
    } <= writers
    assert {
        "submitted_answer",
        "standard_answer",
        "explanation",
        "items",
        "answer_key",
        "student_answer",
        "completion_result",
        "recommendations",
        "session_summary",
        "studentHash",
        "metadata",
    } <= private


def test_every_learning_write_builder_starts_with_exact_account_fence() -> None:
    builders = (
        (
            _contract(practice_repo, "build_practice_write_transaction"),
            {"PK": f"ATTEMPTS#{STUDENT_ID}", "SK": "ATTEMPT#a", "student_id": STUDENT_ID},
            "put",
        ),
        (
            _contract(adaptive_learning_repo, "build_adaptive_write_transaction"),
            {"PK": "ASSIGNMENT#a", "SK": "META", "student_id": STUDENT_ID},
            "put",
        ),
        (
            _contract(ai_teacher_tools_repo, "build_ai_draft_write_transaction"),
            {"PK": "AI_TEACHER_DRAFT#a", "SK": "META", "student_id": STUDENT_ID},
            "put",
        ),
    )
    for builder, item, mode in builders:
        operations = builder(
            item=item,
            owner_id=STUDENT_ID,
            generation=GENERATION,
            mode=mode,
        )
        _fence(operations[0])
        mutation = operations[1]["Put"]
        assert mutation["Item"]["owner_id"] == STUDENT_ID
        assert mutation["Item"]["account_fence_generation"] == GENERATION


def test_existing_assignment_and_draft_updates_require_owner_and_row() -> None:
    assignment_ops = _contract(
        adaptive_learning_repo, "build_adaptive_write_transaction"
    )(
        item={"PK": "ASSIGNMENT#a", "SK": "META", "student_id": STUDENT_ID},
        owner_id=STUDENT_ID,
        generation=GENERATION,
        mode="update",
        updates={"status": "completed"},
    )
    draft_ops = _contract(ai_teacher_tools_repo, "build_ai_draft_write_transaction")(
        item={"PK": "AI_TEACHER_DRAFT#a", "SK": "META", "student_id": STUDENT_ID},
        owner_id=STUDENT_ID,
        generation=GENERATION,
        mode="update",
        updates={"status": "accepted"},
    )
    for operations in (assignment_ops, draft_ops):
        _fence(operations[0])
        update = operations[1]["Update"]
        condition = update["ConditionExpression"]
        assert "attribute_exists(PK)" in condition
        assert "owner_id=:owner" in condition


def test_curriculum_signal_is_random_owner_manifested_and_fenced_without_student_hash() -> None:
    build = _contract(curriculum_analytics_repo, "build_curriculum_signal_transaction")
    operations = build(
        student_id=STUDENT_ID,
        generation=GENERATION,
        item={
            "signal_id": "signal_opaque_random",
            "signal_type": "practice_attempt",
            "public_id": "exercise-public",
            "content_type": "exercise",
            "version_id": "v1",
            "subject_id": "math",
            "topic_id": "algebra",
            "source_type": "catalog_self_practice",
            "metadata": {"correct": False, "studentHash": "student:legacy"},
            "created_at": NOW,
        },
    )
    _fence(operations[0])
    signal = operations[1]["Put"]["Item"]
    manifest = operations[2]["Put"]["Item"]
    assert "student_id" not in signal and "owner_id" not in signal
    assert "studentHash" not in repr(signal)
    assert signal["signal_id"] == manifest["signal_id"]
    assert manifest["PK"] == f"CURRICULUM_SIGNAL_OWNER#{STUDENT_ID}"
    assert manifest["account_fence_generation"] == GENERATION
    assert "Update" in operations[3]


def test_private_scans_are_strong_paginated_and_scrubs_are_strict_allowlists() -> None:
    families = (
        (
            practice_repo,
            "scan_practice_private_rows",
            "scrub_practice_private_row",
            "PRACTICE_TOMBSTONE_ALLOWLIST",
            {
                "PK": f"ATTEMPTS#{STUDENT_ID}",
                "SK": "ATTEMPT#a",
                "student_id": STUDENT_ID,
                "submitted_answer": "private-answer-canary",
                "standard_answer": "private-standard-canary",
            },
        ),
        (
            adaptive_learning_repo,
            "scan_adaptive_private_rows",
            "scrub_adaptive_private_row",
            "ADAPTIVE_TOMBSTONE_ALLOWLIST",
            {
                "PK": "ASSIGNMENT#a",
                "SK": "META",
                "student_id": STUDENT_ID,
                "items": [{"prompt": "private-item-canary"}],
                "answer_key": [{"answer": "private-key-canary"}],
            },
        ),
        (
            ai_teacher_tools_repo,
            "scan_ai_draft_private_rows",
            "scrub_ai_draft_private_row",
            "AI_DRAFT_TOMBSTONE_ALLOWLIST",
            {
                "PK": "AI_TEACHER_DRAFT#a",
                "SK": "META",
                "student_id": STUDENT_ID,
                "session_summary": "private-summary-canary",
                "answer_key": [{"answer": "private-draft-key"}],
            },
        ),
    )
    for module, scan_name, scrub_name, allowlist_name, row in families:
        calls: list[dict[str, Any]] = []
        tombstones: list[dict[str, Any]] = []

        class _Table:
            def scan(self, **kwargs: Any) -> dict[str, Any]:
                calls.append(kwargs)
                return {"Items": [row]}

            def replace_learning_tombstone(self, _original: Any, tombstone: Any, *_args: Any) -> None:
                tombstones.append(tombstone)

        page = _contract(module, scan_name)(STUDENT_ID, table=_Table(), maximum_pages=1)
        for item in page.items:
            _contract(module, scrub_name)(
                item,
                owner_id=STUDENT_ID,
                generation=GENERATION,
                now_iso=NOW,
                table=_Table(),
            )
        allowlist = _contract(module, allowlist_name)
        assert all(call.get("ConsistentRead") is True and "IndexName" not in call for call in calls)
        assert tombstones and set(tombstones[0]) <= allowlist
        assert "private-" not in repr(tombstones)


def test_curriculum_reconciliation_is_exact_once_across_retry() -> None:
    reconcile = _contract(curriculum_analytics_repo, "reconcile_curriculum_signal")
    calls: list[list[dict[str, Any]]] = []

    class _Table:
        def transact_account_deletion(self, operations: list[dict[str, Any]]) -> None:
            calls.append(operations)

    manifest = {
        "PK": f"CURRICULUM_SIGNAL_OWNER#{STUDENT_ID}",
        "SK": "SIGNAL#signal_opaque_random",
        "signal_id": "signal_opaque_random",
        "signal_pk": "CURRICULUM_SIGNAL#exercise-public",
        "signal_sk": f"SIGNAL#{NOW}#signal_opaque_random",
        "metric_pk": "CURRICULUM_METRIC#exercise#exercise-public",
        "metric_sk": "VERSION#v1",
        "signal_type": "practice_attempt",
        "source_type": "catalog_self_practice",
        "account_fence_generation": GENERATION,
    }
    first = reconcile(
        manifest,
        owner_id=STUDENT_ID,
        generation=GENERATION,
        now_iso=NOW,
        table=_Table(),
    )
    assert first == "reconciled"
    assert len(calls) == 1
    assert sum("Update" in operation for operation in calls[0]) >= 1
    assert sum("Delete" in operation for operation in calls[0]) == 2


def test_five_restartable_branches_are_registered_and_require_later_zero_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = {
        "practice_progress",
        "adaptive_assignment",
        "learning_memory",
        "ai_teacher_draft",
        "curriculum_signal",
    }
    assert expected <= set(account_deletion_service.BRANCH_HANDLERS)
    page_type = _contract(practice_repo, "PracticePrivatePage")
    pages = [
        page_type(items=({"PK": f"PROGRESS#{STUDENT_ID}", "SK": "LESSON#late"},)),
        page_type(items=()),
        page_type(items=()),
    ]
    monkeypatch.setattr(practice_repo, "scan_practice_private_rows", lambda *_a, **_k: pages.pop(0))
    monkeypatch.setattr(practice_repo, "scrub_practice_private_row", lambda *_a, **_k: None)
    branch = account_deletion_service.BRANCH_HANDLERS["practice_progress"]
    command = {"user_id": STUDENT_ID, "generation": GENERATION}
    first = branch(command=command, previous={})
    second = branch(command=command, previous=asdict(first))
    third = branch(command=command, previous=asdict(second))
    assert first.status == "retryable" and first.epoch == 0
    assert second.status == "retryable" and second.epoch == 1
    assert third.status == "complete" and third.quiescent is True and third.epoch == 2
