"""Plan 473-31 contracts for fenced report artifacts, delivery, and purge."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import pytest

from stoa.db.repositories import report_repo
from stoa.services import account_deletion_service


STUDENT_ID = "student-report-delete"
REPORT_ID = "report-private"
NOW = "2026-07-18T00:00:00+00:00"


def _contract(name: str) -> Any:
    value = getattr(report_repo, name, None)
    if value is None:
        pytest.fail(f"report deletion contract {name} is not implemented")
    return value


def _report_row(sk: str = "SUMMARY", **overrides: Any) -> dict[str, Any]:
    item = {
        "PK": f"REPORT#{REPORT_ID}",
        "SK": sk,
        "entity_type": "WEEKLY_REPORT" if sk == "SUMMARY" else "REPORT_AUDIT_EVENT",
        "report_id": REPORT_ID,
        "student_id": STUDENT_ID,
        "account_fence_generation": 7,
        "status": "generated",
        "summary": "private report summary canary",
        "student_name": "Private Student",
        "parent_email": "private-parent@example.test",
        "teacher_note": "private teacher note canary",
        "json_s3_key": "weekly-reports/private/report.json",
        "html_s3_key": "weekly-reports/private/report.html",
        "created_at": NOW,
        "updated_at": NOW,
    }
    item.update(overrides)
    return item


def test_report_source_registry_closes_rows_writers_providers_and_branches() -> None:
    rows = _contract("REPORT_PRIVATE_ROW_REGISTRY")
    writers = _contract("REPORT_WRITER_REGISTRY")
    providers = _contract("REPORT_PROVIDER_REGISTRY")
    private_fields = _contract("REPORT_PRIVATE_FIELDS")

    assert {
        "report_summary",
        "edit_draft",
        "artifact_edit_draft",
        "artifact_rollback_preview",
        "report_audit",
        "recovery_summary",
        "recovery_target",
        "recovery_audit",
        "retention_manifest",
        "retention_audit",
        "support_audit",
        "support_delivery",
        "support_delivery_audit",
        "support_crm_message",
        "support_delivery_feed",
        "support_crm_feed",
        "report_object_intent",
        "report_email_intent",
    } <= set(rows)
    assert {"put_report", "update_report_status", "put_recovery_job", "put_support_crm_message_event"} <= writers
    assert providers == {"s3_put_object", "s3_delete_object", "ses_send_email", "crm_send"}
    assert {"summary", "student_name", "parent_email", "teacher_note", "reason", "before", "after"} <= private_fields
    assert {"report_records", "report_artifacts", "support_recovery_feed"} <= set(
        account_deletion_service.ACCOUNT_DELETION_BRANCH_IDS
    )


def test_object_intent_is_owner_partitioned_and_fenced_before_provider() -> None:
    register = _contract("register_report_object_intent")
    captured: list[list[dict[str, Any]]] = []

    class _Table:
        def transact_account_deletion(self, operations: list[dict[str, Any]]) -> None:
            captured.append(operations)

    body = b'{"private":"report"}'
    intent = register(
        owner_id=STUDENT_ID,
        generation=7,
        operation_id="operation-1",
        artifact_kind="json",
        report_id=REPORT_ID,
        object_key="weekly-reports/private/report.json",
        body=body,
        now_iso=NOW,
        table=_Table(),
    )

    assert intent["PK"] == f"USER#{STUDENT_ID}"
    assert intent["SK"] == "REPORT_OBJECT#operation-1#json"
    assert intent["body_length"] == len(body)
    assert len(intent["body_sha256"]) == 64
    assert intent["state"] == "registered"
    fence = captured[0][0]["ConditionCheck"]
    assert fence["Key"] == {"PK": f"USER#{STUDENT_ID}", "SK": "ACCOUNT_FENCE"}
    assert fence["ExpressionAttributeValues"][":generation"] == 7


def test_object_provider_ack_is_strict_and_lost_response_reconciles_exact_version() -> None:
    parse = _contract("parse_report_object_ack")
    reconcile = _contract("reconcile_report_object_version")
    with pytest.raises(Exception):
        parse({"VersionId": "", "ETag": 12})

    pages = [
        {
            "Versions": [{"Key": "other", "VersionId": "v0", "ETag": '"bad"'}],
            "DeleteMarkers": [],
            "IsTruncated": True,
            "NextKeyMarker": "weekly-reports/private/report.json",
            "NextVersionIdMarker": "v1",
        },
        {
            "Versions": [
                {
                    "Key": "weekly-reports/private/report.json",
                    "VersionId": "v2",
                    "ETag": '"abc"',
                }
            ],
            "DeleteMarkers": [],
            "IsTruncated": False,
        },
    ]

    class _S3:
        def list_object_versions(self, **_kwargs: Any) -> dict[str, Any]:
            return pages.pop(0)

        def head_object(self, **kwargs: Any) -> dict[str, Any]:
            assert kwargs["VersionId"] == "v2"
            return {
                "VersionId": "v2",
                "ETag": '"abc"',
                "ContentLength": 20,
                "Metadata": {"operation-id": "operation-1", "body-sha256": "a" * 64},
            }

    result = reconcile(
        s3_client=_S3(),
        bucket="private",
        object_key="weekly-reports/private/report.json",
        operation_id="operation-1",
        body_sha256="a" * 64,
        body_length=20,
    )
    assert result == {"version_id": "v2", "etag": "abc"}


def test_email_intent_claim_rechecks_fence_and_provider_unknown_is_terminal() -> None:
    register = _contract("register_report_email_intent")
    claim = _contract("claim_report_email_intent")
    classify = _contract("classify_report_delivery_outcome")
    transitions: list[str] = []

    class _Table:
        def register_report_email_intent(self, item: dict[str, Any]) -> dict[str, Any]:
            transitions.append(item["state"])
            return item

        def claim_report_email_intent(self, _key: dict[str, str], _generation: int, _lease: str) -> dict[str, Any]:
            return {"state": "claimed", "lease_id": "lease-1"}

    intent = register(
        owner_id=STUDENT_ID,
        generation=7,
        operation_id="email-1",
        report_id=REPORT_ID,
        recipient="private-parent@example.test",
        subject="Private subject",
        body="Private body",
        now_iso=NOW,
        table=_Table(),
    )
    assert set(intent).isdisjoint({"recipient", "subject", "body"})
    assert {"recipient_digest", "content_digest"} <= set(intent)
    assert claim(intent, lease_id="lease-1", table=_Table())["state"] == "claimed"
    assert classify(response=None, error=TimeoutError("commit then raise")) == "provider_acceptance_unknown"
    assert classify(response={"MessageId": "accepted"}, error=None) == "accepted"
    assert transitions == ["registered"]


def test_report_discovery_is_strong_paginated_and_scrub_is_allowlisted() -> None:
    scan = _contract("scan_report_private_rows")
    scrub = _contract("scrub_report_private_row")
    pages = [
        {"Items": [_report_row()], "LastEvaluatedKey": {"PK": f"REPORT#{REPORT_ID}", "SK": "SUMMARY"}},
        {"Items": [_report_row("AUDIT#1#event", before={"canary": "private"}, after={"canary": "private"})]},
    ]
    calls: list[dict[str, Any]] = []
    tombstones: list[dict[str, Any]] = []

    class _Table:
        def scan(self, **kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return pages.pop(0)

        def scrub_report_private_row(self, _original: dict[str, Any], tombstone: dict[str, Any], *_args: Any) -> None:
            tombstones.append(tombstone)

    table = _Table()
    first = scan(STUDENT_ID, table=table, maximum_pages=1)
    second = scan(STUDENT_ID, table=table, cursor=first.cursor, maximum_pages=1)
    for row in (*first.items, *second.items):
        scrub(row, owner_id=STUDENT_ID, generation=7, now_iso=NOW, table=table)

    allowlist = _contract("REPORT_TOMBSTONE_ALLOWLIST")
    assert all(call.get("ConsistentRead") is True and "IndexName" not in call for call in calls)
    assert all(set(row) <= allowlist for row in tombstones)
    serialized = repr(tombstones)
    assert "private report summary canary" not in serialized
    assert "private-parent@example.test" not in serialized


def test_exact_version_absence_requires_all_pages_and_held_artifact_blocks() -> None:
    prove_absent = _contract("prove_report_object_version_absent")
    classify = _contract("classify_report_retention")
    pages = [
        {
            "Versions": [{"Key": "other", "VersionId": "v0"}],
            "DeleteMarkers": [],
            "IsTruncated": True,
            "NextKeyMarker": "k",
            "NextVersionIdMarker": "m",
        },
        {
            "Versions": [],
            "DeleteMarkers": [],
            "IsTruncated": False,
        },
    ]

    class _S3:
        def list_object_versions(self, **_kwargs: Any) -> dict[str, Any]:
            return pages.pop(0)

    assert prove_absent(
        s3_client=_S3(), bucket="private", object_key="target", version_id="v1"
    ) is True
    held = classify(
        {"legal_hold_active": True, "policy_authority": "statute", "hold_expires_at": "2028-01-01"}
    )
    assert held["status"] == "legal_retention_blocked"
    assert held["quiescent"] is False
    assert held["purged_count"] == 0


def test_report_branches_restart_and_require_two_later_clean_epochs(monkeypatch: pytest.MonkeyPatch) -> None:
    branch = getattr(account_deletion_service, "_report_records_branch", None)
    if branch is None:
        pytest.fail("report_records branch is not implemented")
    page_type = _contract("ReportPrivatePage")
    pages = [
        page_type((_report_row(),), {"PK": f"REPORT#{REPORT_ID}", "SK": "SUMMARY"}, 0),
        page_type((), None, 0),
        page_type((), None, 0),
    ]
    monkeypatch.setattr(report_repo, "scan_report_private_rows", lambda *_args, **_kwargs: pages.pop(0))
    monkeypatch.setattr(report_repo, "scrub_report_private_row", lambda *_args, **_kwargs: None)
    previous: dict[str, Any] = {}
    results = []
    for _ in range(3):
        result = branch(command={"user_id": STUDENT_ID, "generation": 7}, previous=previous)
        results.append(result)
        previous = result.persisted(NOW)
    assert [item.epoch for item in results] == [0, 1, 2]
    assert results[-1].quiescent is True
    assert asdict(results[-1])["debt_counts"] == {}
