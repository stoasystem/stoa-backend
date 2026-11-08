import base64
from datetime import datetime, timezone
import json

import pytest
from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from audit_helpers import MemoryAuthorizationAuditSink
from fakes import student_evidence as fake_evidence
from stoa.config import Settings
from stoa.db.repositories import report_repo
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.routers import admin as admin_router, parents
from stoa.security.authorization import AuthorizationFacts, ParentAuthorizationFacts
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.security.route_authorization import get_authorization_fact_repository
from stoa.services.account_errors import AccountViolation
from stoa.services.current_relationship import SOURCE_LINK, Standing, Verdict


def _settings() -> Settings:
    return Settings(
        aws_region="eu-central-2",
        cognito_user_pool_id="pool-id",
        cognito_student_client_id="student-client",
        cognito_parent_client_id="parent-client",
        cognito_teacher_client_id="teacher-client",
        cognito_admin_client_id="admin-client",
    )


def _app_for_user(user: dict) -> FastAPI:
    role = CanonicalRole(user["role"])
    actor_id = "parent-local" if role is CanonicalRole.PARENT else str(user["sub"])
    actor = Actor(
        actor_id,
        "https://identity.test",
        f"{user['sub']}-subject",
        role,
        AccountStatus.ACTIVE,
        role.value,
    )

    class _Facts:
        async def facts_for(self, current_actor, resource, *_args):
            if user.get("factsOutage"):
                raise TimeoutError("authorization canary")
            if current_actor.role is not CanonicalRole.PARENT or not user.get("bound", True):
                return AuthorizationFacts()
            return AuthorizationFacts(
                parent=ParentAuthorizationFacts(
                    Verdict(
                        Standing.CURRENT,
                        current_actor.user_id,
                        resource.student_id,
                        relationship="child",
                        status="active",
                        source=SOURCE_LINK,
                    ),
                    {
                        "user_id": current_actor.user_id,
                        "role": "parent",
                        "account_status": "active",
                    },
                    {
                        "user_id": resource.student_id,
                        "role": "student",
                        "account_status": "active",
                    },
                )
            )

    app = FastAPI()
    app.include_router(parents.router, prefix="/parents")
    app.dependency_overrides[get_actor] = lambda: actor
    app.dependency_overrides[get_authorization_fact_repository] = _Facts
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return app


@pytest.fixture(autouse=True)
def _current_link(monkeypatch, link_rows):
    # One current parent-local -> child-1 link, read by the relationship judge
    # the children list asks.
    link_rows.link("parent-local", "child-1")

    def get_user(user_id, **_kwargs):
        if user_id == "parent-local":
            return {
                "user_id": user_id,
                "role": "parent",
                "account_status": "active",
                "email": "p@example.com",
            }
        return {
            **_child_profile(),
            "user_id": user_id,
            "role": "student",
            "account_status": "active",
        }

    monkeypatch.setattr(parents.user_repo, "get_user", get_user)
    return link_rows


def _child_profile() -> dict:
    return {
        "user_id": "child-1",
        "name": "Anna Keller",
        "email": "anna@example.com",
        "grade": "Grade 8",
        "primary_subjects": ["Mathematics"],
    }


def _report(student_id: str = "child-1") -> dict:
    return {
        "report_id": f"report-{student_id}",
        "parent_id": "parent-local",
        "student_id": student_id,
        "week_start": "2026-06-01",
        "usage_count": 3,
        "ai_resolved": 2,
        "teacher_resolved": 1,
        "weak_knowledge_points": ["fractions", "geometry"],
        "recommendations": "Practice fractions.",
        "created_at": "2026-06-02T08:00:00+00:00",
    }


def _generated_report(student_id: str = "child-1", status: str = "email_sent") -> dict:
    report = _report(student_id)
    report.update(
        {
            "week_end": "2026-06-07",
            "status": status,
            "email_status": "failed" if status == "email_failed" else "sent",
            "generated_at": "2026-06-08T06:00:00+00:00",
            "stats": {
                "questionsAsked": 4,
                "aiResolved": 3,
                "teacherHelpRequests": 1,
                "practiceLessonsCompleted": 2,
                "mistakesLogged": 1,
            },
            "summary": "Anna made steady progress this week.",
            "strengths": ["Completed practice."],
            "weak_topics": [{"topic": "fractions", "note": "Review equivalent fractions."}],
            "recommendation_items": ["Practice fractions for ten minutes.", "Review one mistake together."],
            "teacher_note": "Teacher help was requested.",
            "s3_key": "weekly-reports/parent-local/child-1/2026-06-01/report.html",
            "html_s3_key": "weekly-reports/parent-local/child-1/2026-06-01/report.html",
            "json_s3_key": "weekly-reports/parent-local/child-1/2026-06-01/report.json",
            "email_error_class": "MessageRejected" if status == "email_failed" else None,
            "email_error_message": "SES rejected recipient" if status == "email_failed" else None,
        }
    )
    if status == "generation_failed":
        report.update(
            {
                "email_status": "not_started",
                "generation_error_class": "RuntimeError",
                "generation_error_message": "generation failed",
            }
        )
    if status == "generation_claimed":
        report.update({"email_status": "not_started"})
    return report


def test_parent_children_list_requires_matching_active_bidirectional_binding(link_rows):
    response = TestClient(
        _app_for_user({"sub": "parent-local", "role": "parent"})
    ).get("/parents/me/children")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == ["child-1"]

    # The student's side records a different write than the parent's side.
    link_rows.link("parent-local", "child-1", student_side_stamp="2026-10-01T09:00:00+00:00")
    denied = TestClient(
        _app_for_user({"sub": "parent-local", "role": "parent"})
    ).get("/parents/me/children")
    assert denied.status_code == 200
    assert denied.json() == {"items": []}


def test_parent_children_list_ignores_legacy_profile_parent_id(monkeypatch, link_rows):
    link_rows.unlink("parent-local", "child-1")
    monkeypatch.setattr(
        parents.user_repo,
        "get_user",
        lambda user_id, **_kwargs: {
            "user_id": user_id,
            "role": "student",
            "account_status": "active",
            "parent_id": "parent-local",
        },
    )

    response = TestClient(
        _app_for_user({"sub": "parent-local", "role": "parent"})
    ).get("/parents/me/children")

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_parent_legacy_identifier_routes_are_removed():
    client = TestClient(_app_for_user({"sub": "parent-local", "role": "parent"}))

    assert client.get("/parents/parent-local/children").status_code == 404
    assert client.get("/parents/parent-local/reports/2026-06-01").status_code == 404


def test_parent_child_authorization_outage_prevents_data_reads(monkeypatch):
    reads = []
    monkeypatch.setattr(
        parents.question_repo,
        "list_by_student",
        lambda *_args, **_kwargs: reads.append("question") or {"Items": []},
    )
    response = TestClient(
        _app_for_user(
            {"sub": "parent-local", "role": "parent", "factsOutage": True}
        )
    ).get("/parents/me/children/child-1/summary")

    assert response.status_code == 503
    assert reads == []


def test_report_repo_list_reports_for_parent_queries_parent_gsi(monkeypatch):
    class FakeQueryTable:
        def __init__(self):
            self.calls = []

        def query(self, **kwargs):
            self.calls.append(kwargs)
            return {"Items": [_report()], "LastEvaluatedKey": {"PK": "REPORT#1"}}

    table = FakeQueryTable()
    monkeypatch.setattr(report_repo, "get_table", lambda: table)

    result = report_repo.list_reports_for_parent(
        "parent-local",
        limit=7,
        last_key={"PK": "REPORT#0"},
    )

    assert result["Items"][0]["student_id"] == "child-1"
    assert table.calls == [
        {
            "IndexName": "GSI-ParentId",
            "KeyConditionExpression": table.calls[0]["KeyConditionExpression"],
            "FilterExpression": table.calls[0]["FilterExpression"],
            "Limit": 7,
            "ScanIndexForward": False,
            "ExclusiveStartKey": {"PK": "REPORT#0"},
        }
    ]


# The report listings' page tokens: made and read by the table gateway (#298),
# each listing's rule - its scope, and the partition its key must stay in -
# held by the admin router that serves it.


def _round_trip(scope, key, **rule):
    return admin_router._start_key(
        admin_router._next_token(scope, {"LastEvaluatedKey": key}), scope, **rule
    )


def _audit_rule(partition):
    return {"within": admin_router._in_partition(partition, "AUDIT#")}


def test_admin_report_page_token_round_trips_scan_key():
    key = {"PK": "PRACTICE", "SK": "CHALLENGE#fractions"}

    assert _round_trip(admin_router.ADMIN_REPORTS_SCAN_SCOPE, key) == key


def test_admin_report_page_token_from_before_the_gateway_is_refused():
    legacy = base64.urlsafe_b64encode(
        json.dumps({"scope": "admin_reports", "key": {"PK": "REPORT#1", "SK": "SUMMARY"}}).encode()
    ).decode()

    with pytest.raises(AccountViolation):
        admin_router._start_key(legacy, admin_router.ADMIN_REPORTS_SCAN_SCOPE)


def test_audit_page_token_round_trips_report_key():
    key = {"PK": "REPORT#report-1", "SK": "AUDIT#2026-06-04T10:00:00+00:00#event-1"}

    scope = "report_audit:REPORT#report-1"
    assert _round_trip(scope, key, **_audit_rule("REPORT#report-1")) == key


def test_audit_page_token_round_trips_recovery_job_key():
    key = {"PK": "REPORT_RECOVERY_JOB#job-1", "SK": "AUDIT#2026-06-04T10:00:00+00:00#event-1"}

    scope = "report_audit:REPORT_RECOVERY_JOB#job-1"
    assert _round_trip(scope, key, **_audit_rule("REPORT_RECOVERY_JOB#job-1")) == key


def test_audit_page_token_rejects_summary_key():
    scope = "report_audit:REPORT#report-1"

    with pytest.raises(AccountViolation):
        _round_trip(
            scope, {"PK": "REPORT#report-1", "SK": "SUMMARY"}, **_audit_rule("REPORT#report-1")
        )


def test_audit_page_token_rejects_another_timeline():
    # #91: a token continues only the partition it came from.
    key = {"PK": "REPORT#report-1", "SK": "AUDIT#2026-06-04T10:00:00+00:00#event-1"}
    token = admin_router._next_token("report_audit:REPORT#report-1", {"LastEvaluatedKey": key})

    for partition in ("REPORT#report-2", "REPORT_RECOVERY_JOB#report-1"):
        with pytest.raises(AccountViolation):
            admin_router._start_key(token, f"report_audit:{partition}", **_audit_rule(partition))


def test_report_repo_put_report_audit_event_uses_conditional_append(monkeypatch):
    class FakePutTable:
        def __init__(self):
            self.calls = []

        def put_item(self, **kwargs):
            self.calls.append(kwargs)

    table = FakePutTable()
    monkeypatch.setattr(report_repo, "get_table", lambda: table)

    report_repo.put_report_audit_event(
        "report-1",
        {
            "event_id": "event-1",
            "event_at": "2026-06-04T10:00:00+00:00",
            "action": "resend_email",
            "result": "success",
        },
    )

    assert table.calls == [
        {
            "Item": {
                "PK": "REPORT#report-1",
                "SK": "AUDIT#2026-06-04T10:00:00+00:00#event-1",
                "entity_type": "REPORT_AUDIT_EVENT",
                "event_id": "event-1",
                "event_at": "2026-06-04T10:00:00+00:00",
                "action": "resend_email",
                "result": "success",
            },
            "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
        }
    ]


def test_report_repo_put_recovery_job_audit_event_uses_conditional_append(monkeypatch):
    class FakePutTable:
        def __init__(self):
            self.calls = []

        def put_item(self, **kwargs):
            self.calls.append(kwargs)

    table = FakePutTable()
    monkeypatch.setattr(report_repo, "get_table", lambda: table)

    report_repo.put_recovery_job_audit_event(
        "job-1",
        {
            "event_id": "event-1",
            "event_at": "2026-06-04T10:00:00+00:00",
            "action": "bulk_resend",
            "result": "started",
        },
    )

    assert table.calls == [
        {
            "Item": {
                "PK": "REPORT_RECOVERY_JOB#job-1",
                "SK": "AUDIT#2026-06-04T10:00:00+00:00#event-1",
                "entity_type": "REPORT_RECOVERY_JOB_AUDIT_EVENT",
                "event_id": "event-1",
                "event_at": "2026-06-04T10:00:00+00:00",
                "action": "bulk_resend",
                "result": "started",
            },
            "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
        }
    ]


def test_recovery_job_page_token_round_trips_job_key():
    key = {"PK": "REPORT_RECOVERY_JOB#job-1", "SK": "SUMMARY"}

    assert _round_trip(admin_router.RECOVERY_JOBS_SCOPE, key) == key


def test_recovery_job_page_token_continues_from_any_row_the_scan_stopped_on():
    # #90: the job list is a filtered scan, so its page may end on a report row.
    key = {"PK": "REPORT#report-1", "SK": "SUMMARY"}

    assert _round_trip(admin_router.RECOVERY_JOBS_SCOPE, key) == key


def test_recovery_job_target_token_stays_within_its_job():
    key = {"PK": "REPORT_RECOVERY_JOB#job-1", "SK": "TARGET#00000#report-1"}

    def rule(job_id):
        return {"within": admin_router._in_partition(f"REPORT_RECOVERY_JOB#{job_id}", "TARGET#")}

    token = admin_router._next_token("recovery_job_targets:job-1", {"LastEvaluatedKey": key})
    assert admin_router._start_key(token, "recovery_job_targets:job-1", **rule("job-1")) == key
    with pytest.raises(AccountViolation):
        admin_router._start_key(token, "recovery_job_targets:job-2", **rule("job-2"))
    with pytest.raises(AccountViolation):
        _round_trip(
            "recovery_job_targets:job-1", {"PK": "REPORT#report-1", "SK": "SUMMARY"}, **rule("job-1")
        )
    with pytest.raises(AccountViolation):
        admin_router._start_key(
            admin_router._next_token(admin_router.RECOVERY_JOBS_SCOPE, {"LastEvaluatedKey": key}),
            "recovery_job_targets:job-1",
            **rule("job-1"),
        )


def test_report_repo_put_recovery_job_persists_summary_and_targets(monkeypatch):
    class FakePutTable:
        def __init__(self):
            self.calls = []

        def put_item(self, **kwargs):
            self.calls.append(kwargs)

    table = FakePutTable()
    monkeypatch.setattr(report_repo, "get_table", lambda: table)

    report_repo.put_recovery_job(
        {
            "job_id": "job-1",
            "job_type": "resend_email",
            "status": "queued",
        },
        [
            {
                "target_id": "report-1",
                "report_id": "report-1",
                "parent_id": "parent-1",
                "student_id": "student-1",
                "week_start": "2026-06-01",
                "result": "pending",
            }
        ],
    )

    assert table.calls[0] == {
        "Item": {
            "PK": "REPORT_RECOVERY_JOB#job-1",
            "SK": "SUMMARY",
            "entity_type": "REPORT_RECOVERY_JOB",
            "job_id": "job-1",
            "job_type": "resend_email",
            "status": "queued",
        },
        "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
    }
    assert table.calls[1] == {
        "Item": {
            "PK": "REPORT_RECOVERY_JOB#job-1",
            "SK": "TARGET#00000#report-1",
            "entity_type": "REPORT_RECOVERY_JOB_TARGET",
            "job_id": "job-1",
            "target_index": 0,
            "target_id": "report-1",
            "report_id": "report-1",
            "parent_id": "parent-1",
            "student_id": "student-1",
            "week_start": "2026-06-01",
            "result": "pending",
        },
        "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
    }


def test_report_repo_try_claim_report_resend_claims_failed_report(monkeypatch):
    class FakeUpdateTable:
        def __init__(self):
            self.calls = []

        def update_item(self, **kwargs):
            self.calls.append(kwargs)

    table = FakeUpdateTable()
    monkeypatch.setattr(report_repo, "get_table", lambda: table)

    claimed = report_repo.try_claim_report_resend(
        "report-1",
        operator="admin-sub",
        attempted_at="2026-06-04T10:00:00+00:00",
    )

    assert claimed is True
    assert table.calls[0]["Key"] == {"PK": "REPORT#report-1", "SK": "SUMMARY"}
    assert table.calls[0]["ConditionExpression"] == "#status = :email_failed OR email_status = :failed"
    assert table.calls[0]["ExpressionAttributeValues"][":resending"] == "email_resending"


def test_report_repo_try_claim_report_resend_returns_false_when_not_failed(monkeypatch):
    class FakeUpdateTable:
        def update_item(self, **kwargs):
            raise ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException"}},
                "UpdateItem",
            )

    monkeypatch.setattr(report_repo, "get_table", lambda: FakeUpdateTable())

    claimed = report_repo.try_claim_report_resend(
        "report-1",
        operator="admin-sub",
        attempted_at="2026-06-04T10:00:00+00:00",
    )

    assert claimed is False


def test_report_repo_list_reports_for_admin_uses_parent_gsi(monkeypatch):
    class FakeQueryTable:
        def __init__(self):
            self.calls = []

        def query(self, **kwargs):
            self.calls.append(kwargs)
            return {"Items": [_report()], "LastEvaluatedKey": {"PK": "REPORT#1"}}

    table = FakeQueryTable()
    monkeypatch.setattr(report_repo, "get_table", lambda: table)

    result = report_repo.list_reports_for_admin(
        parent_id="parent-local",
        status="email_failed",
        week_start="2026-06-01",
        student_id="child-1",
        limit=9,
        last_key={"PK": "REPORT#0", "SK": "SUMMARY"},
    )

    assert result["Items"][0]["student_id"] == "child-1"
    assert table.calls == [
        {
            "IndexName": "GSI-ParentId",
            "KeyConditionExpression": table.calls[0]["KeyConditionExpression"],
            "Limit": 9,
            "ScanIndexForward": False,
            "FilterExpression": table.calls[0]["FilterExpression"],
            "ExclusiveStartKey": {"PK": "REPORT#0", "SK": "SUMMARY"},
        }
    ]


def test_report_repo_list_reports_for_admin_uses_bounded_scan_without_parent(monkeypatch):
    class FakeScanTable:
        def __init__(self):
            self.calls = []

        def scan(self, **kwargs):
            self.calls.append(kwargs)
            return {"Items": [_report()], "LastEvaluatedKey": {"PK": "REPORT#1"}}

    table = FakeScanTable()
    monkeypatch.setattr(report_repo, "get_table", lambda: table)

    result = report_repo.list_reports_for_admin(
        status="generation_failed",
        week_start="2026-06-01",
        student_id="child-1",
        limit=11,
        last_key={"PK": "REPORT#0", "SK": "SUMMARY"},
    )

    assert result["Items"][0]["student_id"] == "child-1"
    assert table.calls == [
        {
            "FilterExpression": table.calls[0]["FilterExpression"],
            "Limit": 11,
            "ExclusiveStartKey": {"PK": "REPORT#0", "SK": "SUMMARY"},
        }
    ]


def test_report_repo_update_report_status_updates_summary_item(monkeypatch):
    class FakeUpdateTable:
        def __init__(self):
            self.calls = []

        def update_item(self, **kwargs):
            self.calls.append(kwargs)

    table = FakeUpdateTable()
    monkeypatch.setattr(report_repo, "get_table", lambda: table)

    report_repo.update_report_status(
        "report-1",
        "email_failed",
        email_status="failed",
        email_error_class="RuntimeError",
    )

    assert table.calls == [
        {
            "Key": {"PK": "REPORT#report-1", "SK": "SUMMARY"},
            "UpdateExpression": "SET #f0 = :v0, #f1 = :v1, #f2 = :v2",
            "ExpressionAttributeNames": {
                "#f0": "status",
                "#f1": "email_status",
                "#f2": "email_error_class",
            },
            "ExpressionAttributeValues": {
                ":v0": "email_failed",
                ":v1": "failed",
                ":v2": "RuntimeError",
            },
        }
    ]


def test_report_repo_try_start_generation_retry_claims_failed_report(monkeypatch):
    class FakeUpdateTable:
        def __init__(self):
            self.calls = []

        def update_item(self, **kwargs):
            self.calls.append(kwargs)

    table = FakeUpdateTable()
    monkeypatch.setattr(report_repo, "get_table", lambda: table)

    claimed = report_repo.try_start_generation_retry(
        "report-1",
        operator="admin-sub",
        attempted_at="2026-06-04T10:00:00+00:00",
    )

    assert claimed is True
    assert table.calls == [
        {
            "Key": {"PK": "REPORT#report-1", "SK": "SUMMARY"},
            "UpdateExpression": (
                "SET #status = :retrying, "
                "generation_retry_attempted_at = :attempted_at, "
                "last_operation = :operation, "
                "last_operation_at = :attempted_at, "
                "last_operation_by = :operator, "
                "last_operation_result = :in_progress, "
                "updated_at = :attempted_at"
            ),
            "ConditionExpression": "#status = :expected",
            "ExpressionAttributeNames": {"#status": "status"},
            "ExpressionAttributeValues": {
                ":retrying": "generation_retrying",
                ":expected": "generation_failed",
                ":attempted_at": "2026-06-04T10:00:00+00:00",
                ":operation": "retry_generation",
                ":operator": "admin-sub",
                ":in_progress": "in_progress",
            },
        }
    ]


def test_report_repo_try_start_generation_retry_returns_false_when_claimed(monkeypatch):
    class FakeUpdateTable:
        def update_item(self, **kwargs):
            raise ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException"}},
                "UpdateItem",
            )

    monkeypatch.setattr(report_repo, "get_table", lambda: FakeUpdateTable())

    claimed = report_repo.try_start_generation_retry(
        "report-1",
        operator="admin-sub",
        attempted_at="2026-06-04T10:00:00+00:00",
    )

    assert claimed is False


def test_report_repo_try_claim_report_generation_uses_conditional_put(monkeypatch):
    class FakePutTable:
        def __init__(self):
            self.calls = []

        def put_item(self, **kwargs):
            self.calls.append(kwargs)

    table = FakePutTable()
    monkeypatch.setattr(report_repo, "get_table", lambda: table)

    claimed = report_repo.try_claim_report_generation({"report_id": "report-1", "status": "generation_claimed"})

    assert claimed is True
    assert table.calls == [
        {
            "Item": {
                "PK": "REPORT#report-1",
                "SK": "SUMMARY",
                "report_id": "report-1",
                "status": "generation_claimed",
            },
            "ConditionExpression": "attribute_not_exists(PK)",
        }
    ]


def test_report_repo_try_claim_report_generation_returns_false_on_existing(monkeypatch):
    class FakePutTable:
        def put_item(self, **kwargs):
            raise ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException", "Message": "exists"}},
                "PutItem",
            )

    monkeypatch.setattr(report_repo, "get_table", lambda: FakePutTable())

    claimed = report_repo.try_claim_report_generation({"report_id": "report-1"})

    assert claimed is False


def test_report_repo_get_report_for_child_by_week_filters_same_week_siblings(monkeypatch):
    class FakeQueryTable:
        def __init__(self):
            self.calls = []
            self.pages = [
                {"Items": [{**_report("sibling"), "SK": "SUMMARY"}], "LastEvaluatedKey": {"PK": "REPORT#sibling"}},
                {"Items": [{**_report("child-1"), "SK": "SUMMARY"}]},
            ]

        def query(self, **kwargs):
            self.calls.append(kwargs)
            return self.pages.pop(0)

    table = FakeQueryTable()
    monkeypatch.setattr(report_repo, "get_table", lambda: table)

    report = report_repo.get_report_for_child_by_week("parent-local", "child-1", "2026-06-01")

    assert report["student_id"] == "child-1"
    assert table.calls[0]["IndexName"] == "GSI-ParentId"
    assert table.calls[1]["ExclusiveStartKey"] == {"PK": "REPORT#sibling"}


def test_report_repo_get_report_for_child_by_week_ignores_child_entities(monkeypatch):
    draft = {
        **_report("child-1"),
        "SK": "ARTIFACT_EDIT_DRAFT#draft-1",
        "entity_type": "REPORT_ARTIFACT_EDIT_DRAFT",
        "updated_at": "2026-06-06T18:41:08+00:00",
    }
    summary = {**_report("child-1"), "SK": "SUMMARY"}

    monkeypatch.setattr(
        report_repo,
        "list_reports_for_parent_week",
        lambda parent_id, week_start, last_key=None: {"Items": [draft, summary]},
    )

    report = report_repo.get_report_for_child_by_week("parent-local", "child-1", "2026-06-01")

    assert report == summary


def test_parent_child_week_report_available_when_same_week_sibling_first(monkeypatch):
    app = _app_for_user({"sub": "parent-local", "role": "parent"})
    app.dependency_overrides[parents.get_settings] = _settings
    client = TestClient(app)

    monkeypatch.setattr(
        parents.report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week: _report("child-1"),
    )

    response = client.get("/parents/me/children/child-1/reports/2026-06-01")

    assert response.status_code == 200
    assert response.json()["status"] == "available"
    assert response.json()["report"]["studentId"] == "child-1"


def test_latest_report_for_child_pages_and_filters(monkeypatch):
    calls = []
    pages = [
        {"Items": [_report("sibling")], "LastEvaluatedKey": {"PK": "REPORT#sibling"}},
        {"Items": [_report("child-1")]},
    ]

    def list_reports(parent_id, limit=25, last_key=None):
        calls.append((parent_id, limit, last_key))
        return pages.pop(0)

    monkeypatch.setattr(parents.report_repo, "list_reports_for_parent", list_reports)

    report = parents._latest_report_for_child("parent-local", "child-1")

    assert report["student_id"] == "child-1"
    assert calls == [
        ("parent-local", 25, None),
        ("parent-local", 25, {"PK": "REPORT#sibling"}),
    ]


def test_parent_child_summary_aggregates_real_data(monkeypatch):
    monkeypatch.setattr(
        parents.question_repo,
        "list_by_student",
        lambda child_id, limit=20, last_key=None: {
            "Items": [
                {
                    "PK": "QUESTION#q-1",
                    "SK": "META",
                    "question_id": "q-1",
                    "status": "ai_answered",
                    "prompt": "How do fractions work?",
                    "subject": "math",
                    "knowledge_points": ["fractions", "algebra"],
                    "created_at": "2026-06-02T10:00:00+00:00",
                },
                {
                    "PK": "QUESTION#q-2",
                    "SK": "META",
                    "question_id": "q-2",
                    "status": "escalated",
                    "prompt": "Need help",
                    "subject": "math",
                    "knowledge_points": ["fractions"],
                    "created_at": "2026-06-02T11:00:00+00:00",
                },
                {
                    "PK": "QUESTION#q-old",
                    "SK": "META",
                    "question_id": "q-old",
                    "status": "ai_answered",
                    "prompt": "Old question",
                    "knowledge_points": ["old-topic"],
                    "created_at": "2026-05-20T10:00:00+00:00",
                },
            ]
        },
    )
    asked = fake_evidence.install(
        monkeypatch,
        fake_evidence.evidence(
            "child-1",
            progress=[
                {
                    "lesson_id": "lesson-1",
                    "lesson_title": "Fractions",
                    "subject_id": "math",
                    "status": "completed",
                    "completed_at": "2026-06-02T09:00:00+00:00",
                },
                {
                    "lesson_id": "lesson-2",
                    "status": "in_progress",
                    "completed_at": "2026-06-02T09:30:00+00:00",
                },
            ],
            attempts=[
                {"challenge_id": "m-1", "topic_id": "geometry", "created_at": "2026-06-02T08:30:00+00:00"}
            ],
        ),
    )
    monkeypatch.setattr(
        parents,
        "_list_conversations_for_child",
        lambda child_id: [
            {
                "conversation_id": "conv-1",
                "entity_type": "conversation",
                "escalated": True,
                "last_message_preview": "Teacher follow-up needed",
                "updated_at": "2026-06-02T12:00:00+00:00",
            }
        ],
    )
    monkeypatch.setattr(parents, "_latest_report_for_child", lambda parent_id, child_id: _report())
    monkeypatch.setattr(parents, "_is_current_week", lambda value: str(value).startswith("2026-06-02"))
    monkeypatch.setattr(
        parents,
        "_current_week",
        lambda: (datetime(2026, 6, 2, tzinfo=timezone.utc), datetime(2026, 6, 3, tzinfo=timezone.utc)),
    )

    client = TestClient(_app_for_user({"sub": "cognito-sub", "role": "parent"}))
    response = client.get("/parents/me/children/child-1/summary")

    assert response.status_code == 200
    data = response.json()
    assert data["student"] == {"id": "child-1", "name": "Anna Keller", "grade": "Grade 8"}
    assert data["questionsAskedThisWeek"] == 2
    assert data["aiResolvedThisWeek"] == 1
    assert data["teacherHelpRequestsThisWeek"] == 2
    assert data["practiceLessonsCompletedThisWeek"] == 1
    assert data["weakTopics"][:3] == ["fractions", "geometry", "algebra"]
    assert [item["id"] for item in data["recentActivity"][:2]] == ["conv-1", "q-2"]
    # One evidence value serves the week, the weak topics and the activity.
    assert asked == ["child-1"]


def test_parent_child_summary_empty_state(monkeypatch):
    monkeypatch.setattr(parents.question_repo, "list_by_student", lambda child_id, limit=20, last_key=None: {"Items": []})
    fake_evidence.install(monkeypatch)
    monkeypatch.setattr(parents, "_list_conversations_for_child", lambda child_id: [])
    monkeypatch.setattr(parents, "_latest_report_for_child", lambda parent_id, child_id: None)

    client = TestClient(_app_for_user({"sub": "cognito-sub", "role": "parent"}))
    response = client.get("/parents/me/children/child-1/summary")

    assert response.status_code == 200
    assert response.json() == {
        "student": {"id": "child-1", "name": "Anna Keller", "grade": "Grade 8"},
        "questionsAskedThisWeek": 0,
        "aiResolvedThisWeek": 0,
        "teacherHelpRequestsThisWeek": 0,
        "practiceLessonsCompletedThisWeek": 0,
        "weakTopics": [],
        "recentActivity": [],
    }


def test_parent_child_summary_rejects_unlinked_before_data_reads(monkeypatch):

    def fail(*args, **kwargs):
        raise AssertionError("child data reader should not run")

    monkeypatch.setattr(parents.question_repo, "list_by_student", fail)
    monkeypatch.setattr(parents.student_evidence, "for_student", fail)
    monkeypatch.setattr(parents, "_list_conversations_for_child", fail)
    monkeypatch.setattr(parents, "_latest_report_for_child", fail)

    client = TestClient(
        _app_for_user(
            {"sub": "parent-local", "role": "parent", "bound": False}
        )
    )
    response = client.get("/parents/me/children/other-child/summary")

    assert response.status_code == 404


@pytest.mark.parametrize("role", ["student", "teacher", "admin"])
def test_parent_child_summary_rejects_non_parent_roles(role):
    client = TestClient(_app_for_user({"sub": f"{role}-sub", "role": role}))

    response = client.get("/parents/me/children/child-1/summary")

    assert response.status_code == (403 if role == "admin" else 404)


def test_parent_child_history_returns_newest_first_with_limit(monkeypatch):
    monkeypatch.setattr(
        parents.question_repo,
        "list_by_student",
        lambda child_id, limit=20, last_key=None: {
            "Items": [
                {
                    "PK": "QUESTION#q-1",
                    "SK": "META",
                    "question_id": "q-1",
                    "status": "ai_answered",
                    "prompt": "Question",
                    "created_at": "2026-06-02T10:00:00+00:00",
                }
            ]
        },
    )
    fake_evidence.install(
        monkeypatch,
        fake_evidence.evidence(
            "child-1",
            progress=[
                {"lesson_id": "lesson-1", "status": "completed", "completed_at": "2026-06-02T09:00:00+00:00"}
            ],
            attempts=[
                {"challenge_id": "m-1", "topic_id": "geometry", "created_at": "2026-06-02T08:30:00+00:00"}
            ],
        ),
    )
    monkeypatch.setattr(
        parents,
        "_list_conversations_for_child",
        lambda child_id: [{"conversation_id": "conv-1", "updated_at": "2026-06-02T12:00:00+00:00"}],
    )
    monkeypatch.setattr(parents.report_repo, "list_reports_for_parent", lambda parent_id, limit=25, last_key=None: {"Items": [_report()]})

    client = TestClient(_app_for_user({"sub": "cognito-sub", "role": "parent"}))
    response = client.get("/parents/me/children/child-1/history?limit=2")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == ["conv-1", "q-1"]


def test_parent_child_history_names_finished_lessons_and_wrong_answers(monkeypatch):
    monkeypatch.setattr(parents.question_repo, "list_by_student", lambda *_a, **_k: {"Items": []})
    fake_evidence.install(
        monkeypatch,
        fake_evidence.evidence(
            "child-1",
            progress=[
                {"lesson_id": "lesson-1", "lesson_title": "Fractions", "subject_id": "math",
                 "status": "completed", "completed_at": "2026-06-02T09:00:00+00:00"}
            ],
            attempts=[
                {"challenge_id": "m-1", "lesson_id": "lesson-2", "topic_id": "geometry",
                 "subject_id": "math", "created_at": "2026-06-02T08:30:00+00:00"},
                {"challenge_id": "right-1", "correct": True, "created_at": "2026-06-02T10:30:00+00:00"},
            ],
        ),
    )
    monkeypatch.setattr(parents, "_list_conversations_for_child", lambda child_id: [])
    monkeypatch.setattr(parents.report_repo, "list_reports_for_parent", lambda *_a, **_k: {"Items": []})

    client = TestClient(_app_for_user({"sub": "cognito-sub", "role": "parent"}))
    response = client.get("/parents/me/children/child-1/history")

    assert response.status_code == 200
    assert [
        (item["id"], item["type"], item["summary"], item["subject"])
        for item in response.json()["items"]
    ] == [
        ("lesson-1", "practice", "Fractions", "math"),
        ("lesson-2", "practice_mistake", "geometry", "math"),
    ]


def test_parent_child_history_empty_state(monkeypatch):
    monkeypatch.setattr(parents.question_repo, "list_by_student", lambda child_id, limit=20, last_key=None: {"Items": []})
    fake_evidence.install(monkeypatch)
    monkeypatch.setattr(parents, "_list_conversations_for_child", lambda child_id: [])
    monkeypatch.setattr(parents.report_repo, "list_reports_for_parent", lambda parent_id, limit=25, last_key=None: {"Items": []})

    client = TestClient(_app_for_user({"sub": "cognito-sub", "role": "parent"}))
    response = client.get("/parents/me/children/child-1/history")

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_parent_child_history_rejects_unlinked_before_data_reads(monkeypatch):

    def fail(*args, **kwargs):
        raise AssertionError("history source should not run")

    monkeypatch.setattr(parents.question_repo, "list_by_student", fail)
    monkeypatch.setattr(parents.student_evidence, "for_student", fail)
    monkeypatch.setattr(parents, "_list_conversations_for_child", fail)
    monkeypatch.setattr(parents.report_repo, "list_reports_for_parent", fail)

    client = TestClient(
        _app_for_user(
            {"sub": "parent-local", "role": "parent", "bound": False}
        )
    )
    response = client.get("/parents/me/children/other-child/history")

    assert response.status_code == 404


@pytest.mark.parametrize("role", ["student", "teacher", "admin"])
def test_parent_child_history_rejects_non_parent_roles(role):
    client = TestClient(_app_for_user({"sub": f"{role}-sub", "role": role}))

    response = client.get("/parents/me/children/child-1/history")

    assert response.status_code == (403 if role == "admin" else 404)


def test_parent_child_report_current_available(monkeypatch):
    monkeypatch.setattr(parents, "_latest_report_for_child", lambda parent_id, child_id: _report())

    client = TestClient(_app_for_user({"sub": "cognito-sub", "role": "parent"}))
    response = client.get("/parents/me/children/child-1/report")

    assert response.status_code == 200
    assert response.json()["status"] == "available"
    assert response.json()["report"]["studentId"] == "child-1"


@pytest.mark.parametrize("latest_report", [None, _report("sibling")])
def test_parent_child_report_current_missing(monkeypatch, latest_report):
    monkeypatch.setattr(parents, "_latest_report_for_child", lambda parent_id, child_id: latest_report)

    client = TestClient(_app_for_user({"sub": "cognito-sub", "role": "parent"}))
    response = client.get("/parents/me/children/child-1/report")

    assert response.status_code == 200
    assert response.json() == {
        "status": "missing",
        "report": None,
        "message": "No weekly report is available yet.",
    }


def test_parent_child_report_rejects_unlinked_before_report_read(monkeypatch):

    def fail(*args, **kwargs):
        raise AssertionError("report reader should not run")

    monkeypatch.setattr(parents, "_latest_report_for_child", fail)
    monkeypatch.setattr(parents.report_repo, "get_report_for_child_by_week", fail)

    client = TestClient(
        _app_for_user(
            {"sub": "parent-local", "role": "parent", "bound": False}
        )
    )
    response = client.get("/parents/me/children/other-child/report")

    assert response.status_code == 404


def test_parent_child_week_report_available_after_ownership(monkeypatch):
    calls = []

    def get_report(parent_id, student_id, week):
        calls.append((parent_id, student_id, week))
        return _report()

    monkeypatch.setattr(parents.report_repo, "get_report_for_child_by_week", get_report)

    client = TestClient(_app_for_user({"sub": "cognito-sub", "role": "parent"}))
    response = client.get("/parents/me/children/child-1/reports/2026-06-01")

    assert response.status_code == 200
    assert response.json()["status"] == "available"
    assert calls == [("parent-local", "child-1", "2026-06-01")]


def test_parent_child_week_report_returns_generated_detail_fields(monkeypatch):
    monkeypatch.setattr(
        parents.report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week: _generated_report(student_id),
    )

    client = TestClient(_app_for_user({"sub": "cognito-sub", "role": "parent"}))
    response = client.get("/parents/me/children/child-1/reports/2026-06-01")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "available"
    assert body["report"]["weekEnd"] == "2026-06-07"
    assert body["report"]["summary"] == "Anna made steady progress this week."
    assert body["report"]["generatedAt"] == "2026-06-08T06:00:00+00:00"
    assert body["report"]["emailStatus"] == "sent"
    assert body["report"]["stats"] == {
        "questionsAsked": 4,
        "aiResolved": 3,
        "teacherHelpRequests": 1,
        "practiceLessonsCompleted": 2,
        "mistakesLogged": 1,
    }
    assert body["report"]["weakTopics"] == [
        {"topic": "fractions", "note": "Review equivalent fractions."}
    ]
    assert body["report"]["recommendationItems"] == [
        "Practice fractions for ten minutes.",
        "Review one mistake together.",
    ]
    assert body["report"]["teacherNote"] == "Teacher help was requested."
    for forbidden_field in (
        "s3_key",
        "html_s3_key",
        "json_s3_key",
        "s3Key",
        "htmlS3Key",
        "jsonS3Key",
        "publicUrl",
        "presignedUrl",
    ):
        assert forbidden_field not in body["report"]


def test_parent_child_week_report_exposes_email_failed_state(monkeypatch):
    monkeypatch.setattr(
        parents.report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week: _generated_report(student_id, status="email_failed"),
    )

    client = TestClient(_app_for_user({"sub": "cognito-sub", "role": "parent"}))
    response = client.get("/parents/me/children/child-1/reports/2026-06-01")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "available"
    assert body["report"]["reportStatus"] == "email_failed"
    assert body["report"]["emailStatus"] == "failed"
    assert body["report"]["emailErrorClass"] == "MessageRejected"


def test_parent_child_week_report_exposes_generation_failed_state(monkeypatch):
    monkeypatch.setattr(
        parents.report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week: _generated_report(student_id, status="generation_failed"),
    )

    client = TestClient(_app_for_user({"sub": "cognito-sub", "role": "parent"}))
    response = client.get("/parents/me/children/child-1/reports/2026-06-01")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["message"] == "Weekly report generation failed."
    assert body["report"]["generationErrorClass"] == "RuntimeError"
    assert body["report"]["generationErrorMessage"] is None


def test_parent_child_week_report_exposes_generation_pending_state(monkeypatch):
    monkeypatch.setattr(
        parents.report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week: _generated_report(student_id, status="generation_claimed"),
    )

    client = TestClient(_app_for_user({"sub": "cognito-sub", "role": "parent"}))
    response = client.get("/parents/me/children/child-1/reports/2026-06-01")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["message"] == "Weekly report generation is still in progress."
    assert body["report"]["reportStatus"] == "generation_claimed"


def test_parent_child_week_report_rejects_sibling_returned_by_repo(monkeypatch):
    monkeypatch.setattr(
        parents.report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week: _generated_report("sibling"),
    )

    client = TestClient(_app_for_user({"sub": "cognito-sub", "role": "parent"}))
    response = client.get("/parents/me/children/child-1/reports/2026-06-01")

    assert response.status_code == 200
    assert response.json()["status"] == "missing"


@pytest.mark.parametrize("week_report", [None, _report("sibling")])
def test_parent_child_week_report_missing(monkeypatch, week_report):
    monkeypatch.setattr(
        parents.report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week: week_report if week_report and week_report.get("student_id") == student_id else None,
    )

    client = TestClient(_app_for_user({"sub": "cognito-sub", "role": "parent"}))
    response = client.get("/parents/me/children/child-1/reports/2026-06-01")

    assert response.status_code == 200
    assert response.json()["status"] == "missing"
    assert response.json()["report"] is None


@pytest.mark.parametrize("role", ["student", "teacher", "admin"])
def test_parent_child_report_routes_reject_non_parent_roles(role):
    client = TestClient(_app_for_user({"sub": f"{role}-sub", "role": role}))

    expected = 403 if role == "admin" else 404
    assert client.get("/parents/me/children/child-1/report").status_code == expected
    assert client.get("/parents/me/children/child-1/reports/2026-06-01").status_code == expected
