"""Plan 473-31 contracts for fenced report artifacts, delivery, and purge."""

from __future__ import annotations

from typing import Any

import pytest

from stoa.db import data_catalog
from stoa.db.repositories import report_repo
from fakes.dynamodb import from_wire


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


def test_report_source_registry_closes_writers_and_providers() -> None:
    writers = _contract("REPORT_WRITER_REGISTRY")
    providers = _contract("REPORT_PROVIDER_REGISTRY")

    assert {"put_report", "update_report_status", "put_recovery_job", "put_support_crm_message_event"} <= writers
    assert providers == {"s3_put_object", "s3_delete_object", "ses_send_email", "crm_send"}


def test_object_intent_is_owner_partitioned_and_fenced_before_provider() -> None:
    register = _contract("register_report_object_intent")
    captured: list[list[dict[str, Any]]] = []

    class _Table:
        def transact_write_items(self, *, TransactItems: list[dict[str, Any]]) -> None:  # noqa: N803
            operations = from_wire(TransactItems)
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

    pages: list[dict[str, Any]] = [
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
    """The weekly report email is sent behind the student's fence, and an unknown outcome is final.

    Its name is the one the sealed private-store inventory gave it (gone with
    #642). Its report send record is gone since #687: the email crosses the
    notification ledger, and this holds the same two promises there.
    """
    from stoa import aws
    from stoa.db.repositories import account_deletion_repo
    from stoa.services import notifications

    import test_notification_email_channel as email_channel

    try:
        table, ses = email_channel.install_world()

        class _Down:
            def send_email(self, **_kwargs: Any) -> dict[str, Any]:
                raise TimeoutError("commit then raise")

        aws.install({aws.Kind.SES_NOTIFICATION: _Down()})
        unknown = email_channel.report_ready()
        aws.install({aws.Kind.SES_NOTIFICATION: ses})
        again = email_channel.report_ready()

        assert unknown.outcome is again.outcome is notifications.EmailOutcome.FAILED
        assert str(again.error) == "provider_acceptance_unknown"
        assert ses.sent == []

        table.seed(
            {
                **account_deletion_repo.account_fence_key(email_channel.STUDENT),
                "entity_type": "account_fence",
                "status": "deleting",
                "generation": email_channel.GENERATION,
            }
        )
        fenced = email_channel.report_ready(resend=1)

        assert fenced.outcome is notifications.EmailOutcome.FAILED
        assert ses.sent == []
    finally:
        aws.install(None)


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


def test_exact_object_purge_never_removes_coordinates_before_absence() -> None:
    purge = _contract("purge_report_object_intent")
    deletes: list[dict[str, Any]] = []

    class _S3:
        def delete_object(self, **kwargs: Any) -> dict[str, Any]:
            deletes.append(kwargs)
            return {"DeleteMarker": True}

        def list_object_versions(self, **_kwargs: Any) -> dict[str, Any]:
            return {"Versions": [], "DeleteMarkers": [], "IsTruncated": False}

    class _Table:
        def get_item(self, **_kwargs: Any) -> dict[str, Any]:
            return {"Item": {"status": "deletion_pending", "generation": 7}}

    intent = {
        "PK": f"USER#{STUDENT_ID}",
        "SK": "REPORT_OBJECT#operation-1#json",
        "entity_type": "report_object_intent",
        "owner_id": STUDENT_ID,
        "account_fence_generation": 7,
        "operation_id": "operation-1",
        "artifact_kind": "json",
        "report_id": REPORT_ID,
        "object_key": "weekly-reports/private/report.json",
        "body_sha256": "a" * 64,
        "body_length": 20,
        "version_id": "v1",
        "etag": "abc",
        "state": "linked",
        "created_at": NOW,
    }
    result = purge(
        intent,
        owner_id=STUDENT_ID,
        generation=7,
        bucket="private",
        s3_client=_S3(),
        table=_Table(),
    )
    assert result == {"status": "purged", "quiescent": True, "purged_count": 1}
    assert deletes == [
        {
            "Bucket": "private",
            "Key": "weekly-reports/private/report.json",
            "VersionId": "v1",
        }
    ]
    # The row is the deletion's to replace, with the catalog's tombstone (#642),
    # which keeps no object coordinate.
    keeps = data_catalog.DELETIONS["report_object_intent"].owner.keeps
    assert not {"object_key", "version_id", "etag", "body_sha256"} & keeps


def test_legal_hold_minimizes_row_and_blocks_provider_delete() -> None:
    purge = _contract("purge_report_object_intent")

    class _S3:
        def delete_object(self, **_kwargs: Any) -> dict[str, Any]:
            pytest.fail("held object must not be deleted")

    held = {
        "PK": f"USER#{STUDENT_ID}",
        "SK": "REPORT_OBJECT#held#immutable_manifest",
        "entity_type": "report_object_intent",
        "owner_id": STUDENT_ID,
        "account_fence_generation": 7,
        "operation_id": "held",
        "artifact_kind": "immutable_manifest",
        "manifest_id": "manifest-1",
        "object_key": "weekly-reports/private/manifest.json",
        "version_id": "v-held",
        "legal_hold_active": True,
        "policy_authority": "statute",
        "policy_scope": "minimum-evidence",
        "hold_expires_at": "2028-01-01",
    }
    result = purge(
        held,
        owner_id=STUDENT_ID,
        generation=7,
        bucket="private",
        s3_client=_S3(),
        table=object(),
    )
    assert result["status"] == "legal_retention_blocked"
    assert result["quiescent"] is False
    assert result["purged_count"] == 0


