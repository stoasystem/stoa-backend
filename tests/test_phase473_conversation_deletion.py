"""Plan 473-32 contracts for conversation writer fencing and deletion."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from stoa.db.repositories import attachment_repo
from stoa.services import account_deletion_service, attachment_service


STUDENT_ID = "student-conversation-delete"
CONVERSATION_ID = "conversation-private"
NOW = "2026-07-18T01:00:00+00:00"


def _contract(name: str) -> Any:
    value = getattr(attachment_repo, name, None)
    if value is None:
        pytest.fail(f"conversation deletion contract {name} is not implemented")
    return value


def _message(sk: str = "MSG#student", **overrides: Any) -> dict[str, Any]:
    item = {
        "PK": f"CONV#{CONVERSATION_ID}",
        "SK": sk,
        "entity_type": "conversation_message",
        "schema_version": "conversation-message.v1",
        "message_id": sk.split("#", 1)[-1],
        "conversation_id": CONVERSATION_ID,
        "student_id": STUDENT_ID,
        "owner_id": STUDENT_ID,
        "account_fence_generation": 7,
        "role": "student",
        "content": "private message canary",
        "attachment_ids": ["attachment-private"],
        "subject": "private subject",
        "grade": "private grade",
        "created_at": NOW,
    }
    item.update(overrides)
    return item


def test_conversation_source_registry_closes_rows_writers_and_private_fields() -> None:
    rows = _contract("CONVERSATION_PRIVATE_ROW_REGISTRY")
    writers = _contract("CONVERSATION_WRITER_REGISTRY")
    private = _contract("CONVERSATION_PRIVATE_FIELDS")
    assert {
        "conversation_header",
        "conversation_message",
        "teacher_note",
        "message_command",
        "chat_quota_operation",
        "chat_usage_event",
        "attachment_association",
    } <= set(rows)
    assert {
        "create_conversation",
        "message_command_claim",
        "message_attachment_commit",
        "ai_lease_claim",
        "ai_lease_renew",
        "ai_completion",
        "teacher_help",
        "usage_event",
    } <= set(writers)
    assert {
        "content",
        "result_json",
        "fingerprint",
        "title",
        "last_message_preview",
        "subject",
        "grade",
        "note",
        "escalation_message",
        "attachment_ids",
        "request_correlation_id",
    } <= set(private)
    assert "conversation_messages" in account_deletion_service.BRANCH_HANDLERS


def test_every_conversation_write_transaction_starts_with_exact_account_fence() -> None:
    build = _contract("build_conversation_write_transaction")
    operations = build(
        item=_message(),
        owner_id=STUDENT_ID,
        generation=7,
        mode="put",
    )
    fence = operations[0]["ConditionCheck"]
    assert fence["Key"] == {"PK": f"USER#{STUDENT_ID}", "SK": "ACCOUNT_FENCE"}
    assert fence["ExpressionAttributeValues"][":generation"] == 7
    put = operations[1]["Put"]
    assert put["Item"]["owner_id"] == STUDENT_ID
    assert put["Item"]["account_fence_generation"] == 7


def test_command_claim_and_text_only_message_commit_share_account_fence() -> None:
    command = {
        "command_id": "command-private",
        "conversation_id": CONVERSATION_ID,
        "idempotency_key": "idem",
        "fingerprint": "f" * 64,
        "created_at": NOW,
        "usage_action": "chat_message",
        "usage_idempotency_key": "usage-private",
        "usage_event_id": "event-private",
        "usage_resource_id": "request-private",
        "quota_period": "2026-07-18",
        "counter_value": 1,
        "expires_at": 100,
    }
    claim = attachment_repo.build_message_command_claim_transaction(
        command=command,
        owner_id=STUDENT_ID,
        quota_period="2026-07-18",
        expected_counter=0,
        limit=10,
        expires_at=100,
        account_fence_generation=7,
    )
    assert claim[0].kind is attachment_repo.TransactionOperationKind.ACCOUNT_RETENTION_FENCE_CHECK
    assert claim[0].item["ConditionCheck"]["ExpressionAttributeValues"][":generation"] == 7

    commit = attachment_repo.build_message_attachment_transaction(
        message=_message(),
        fresh=[],
        reused=[],
        associations=[],
        owner_id=STUDENT_ID,
        limit_bytes=100,
        now_iso=NOW,
        command={**command, "owner_id": STUDENT_ID},
        account_fence_generation=7,
    )
    assert commit[0].kind is attachment_repo.TransactionOperationKind.ACCOUNT_RETENTION_FENCE_CHECK


def test_direct_router_writes_are_forbidden_by_static_writer_gate() -> None:
    source = Path("src/stoa/routers/conversations.py").read_text()
    assert ".put_item(" not in source
    assert ".update_item(" not in source
    assert "create_conversation_record" in source
    assert "record_teacher_help_request" in source


def test_private_row_discovery_is_strong_paginated_and_scrub_is_allowlisted() -> None:
    scan = _contract("scan_conversation_private_rows")
    scrub = _contract("scrub_conversation_private_row")
    pages = [
        {
            "Items": [_message()],
            "LastEvaluatedKey": {"PK": f"CONV#{CONVERSATION_ID}", "SK": "MSG#student"},
        },
        {"Items": [_message("NOTE#late", entity_type="teacher_note", note="late private note")]},
    ]
    calls: list[dict[str, Any]] = []
    tombstones: list[dict[str, Any]] = []

    class _Table:
        def scan(self, **kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return pages.pop(0)

        def scrub_conversation_private_row(
            self, _original: dict[str, Any], tombstone: dict[str, Any], *_args: Any
        ) -> None:
            tombstones.append(tombstone)

    table = _Table()
    first = scan(STUDENT_ID, table=table, maximum_pages=1)
    second = scan(STUDENT_ID, table=table, cursor=first.cursor, maximum_pages=1)
    for item in (*first.items, *second.items):
        scrub(item, owner_id=STUDENT_ID, generation=7, now_iso=NOW, table=table)

    allowlist = _contract("CONVERSATION_TOMBSTONE_ALLOWLIST")
    assert all(call.get("ConsistentRead") is True and "IndexName" not in call for call in calls)
    assert all(set(item) <= allowlist for item in tombstones)
    assert "private message canary" not in repr(tombstones)
    assert "late private note" not in repr(tombstones)


def test_stale_command_cancel_removes_result_fingerprint_and_lease() -> None:
    cancel = _contract("cancel_stale_message_command")
    updates: list[dict[str, Any]] = []

    class _Table:
        def cancel_stale_message_command(self, **kwargs: Any) -> None:
            updates.append(kwargs)

    command = _message(
        "MESSAGE_COMMAND#idem",
        entity_type="message_command",
        status="ai_running",
        result_json='{"private":"assistant"}',
        fingerprint="f" * 64,
        leaseOwner="worker-private",
    )
    result = cancel(
        command,
        owner_id=STUDENT_ID,
        deletion_generation=7,
        now_iso=NOW,
        table=_Table(),
    )
    assert result["status"] == "canceled"
    assert updates and set(updates[0]["remove_fields"]) >= {
        "result_json",
        "fingerprint",
        "leaseOwner",
        "claimedAt",
        "expiresAt",
    }


def test_conversation_branch_releases_associations_before_scrub_and_requires_later_zero_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    branch = getattr(account_deletion_service, "_conversation_messages_branch", None)
    if branch is None:
        pytest.fail("conversation_messages branch is not implemented")
    page_type = _contract("ConversationPrivatePage")
    pages = [
        page_type(
            (_message(),),
            {"PK": f"CONV#{CONVERSATION_ID}", "SK": "MSG#student"},
            1,
        ),
        page_type((), None, 0),
        page_type((), None, 0),
        page_type((), None, 0),
    ]
    order: list[str] = []
    monkeypatch.setattr(
        attachment_repo,
        "scan_conversation_private_rows",
        lambda *_args, **_kwargs: pages.pop(0),
    )
    monkeypatch.setattr(
        attachment_service,
        "release_conversation_attachments",
        lambda **_kwargs: order.append("release") or {"released": 1, "deleted": 0},
    )
    monkeypatch.setattr(
        attachment_repo,
        "scrub_conversation_private_row",
        lambda *_args, **_kwargs: order.append("scrub"),
    )
    previous: dict[str, Any] = {}
    results = []
    for _ in range(4):
        result = branch(command={"user_id": STUDENT_ID, "generation": 7}, previous=previous)
        results.append(result)
        previous = result.persisted(NOW)
    assert order[:2] == ["release", "scrub"]
    assert [item.epoch for item in results] == [0, 0, 1, 2]
    assert results[-1].quiescent is True
    assert asdict(results[-1])["debt_counts"] == {}


def test_provider_retained_bedrock_payload_is_explicitly_outside_backend_purge() -> None:
    boundary = _contract("CONVERSATION_PROVIDER_RETENTION_BOUNDARY")
    assert boundary == {
        "bedrock_request_response": "outside_backend_deletion_control"
    }
