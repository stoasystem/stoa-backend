import pytest
from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.config import Settings
from stoa.db.repositories import report_repo
from stoa.deps import get_current_user
from stoa.routers import parents


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
    app = FastAPI()
    app.include_router(parents.router, prefix="/parents")
    app.dependency_overrides[get_current_user] = lambda: user
    return app


class FakeTable:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def scan(self, **kwargs):
        self.calls.append(kwargs)
        return self.pages.pop(0)


def _resolved_parent() -> parents.ResolvedParent:
    return parents.ResolvedParent(
        claims_sub="cognito-sub",
        email="p@example.com",
        parent_user_id="parent-local",
        profile={"user_id": "parent-local", "role": "parent"},
    )


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


def test_resolve_parent_profile_direct_lookup(monkeypatch):
    profile = {"user_id": "parent-local", "email": "p@example.com", "role": "parent"}
    monkeypatch.setattr(parents.user_repo, "get_user", lambda user_id: profile)

    def fail_get_user_by_email(email):
        raise AssertionError("email fallback should not run")

    monkeypatch.setattr(parents.user_repo, "get_user_by_email", fail_get_user_by_email)

    resolved = parents._resolve_parent_profile(
        {"sub": "parent-local", "username": "cognito-user", "role": "parent"},
        _settings(),
    )

    assert resolved.claims_sub == "parent-local"
    assert resolved.email == "p@example.com"
    assert resolved.parent_user_id == "parent-local"
    assert resolved.profile == profile


def test_resolve_parent_profile_cognito_email_fallback(monkeypatch):
    profile = {"user_id": "parent-local", "email": "p@example.com", "role": "parent"}
    monkeypatch.setattr(parents.user_repo, "get_user", lambda user_id: None)
    monkeypatch.setattr(parents.user_repo, "get_user_by_email", lambda email: profile)

    class FakeCognito:
        def admin_get_user(self, **kwargs):
            assert kwargs["UserPoolId"] == "pool-id"
            assert kwargs["Username"] == "cognito-user"
            return {"UserAttributes": [{"Name": "email", "Value": "p@example.com"}]}

    monkeypatch.setattr(parents.boto3, "client", lambda service, region_name: FakeCognito())

    resolved = parents._resolve_parent_profile(
        {"sub": "cognito-sub", "username": "cognito-user", "role": "parent"},
        _settings(),
    )

    assert resolved.claims_sub == "cognito-sub"
    assert resolved.email == "p@example.com"
    assert resolved.parent_user_id == "parent-local"


def test_resolve_parent_profile_non_parent_raises_403(monkeypatch):
    profile = {"user_id": "student-local", "email": "s@example.com", "role": "student"}
    monkeypatch.setattr(parents.user_repo, "get_user", lambda user_id: profile)

    with pytest.raises(parents.HTTPException) as exc:
        parents._resolve_parent_profile(
            {"sub": "student-local", "username": "cognito-user", "role": "parent"},
            _settings(),
        )

    assert exc.value.status_code == 403


def test_scan_children_for_parent_paginates(monkeypatch):
    table = FakeTable(
        [
            {
                "Items": [{"user_id": "child-1", "role": "student", "parent_id": "parent"}],
                "LastEvaluatedKey": {"PK": "USER#child-1", "SK": "PROFILE"},
            },
            {"Items": [{"user_id": "child-2", "role": "student", "parent_id": "parent"}]},
        ]
    )
    monkeypatch.setattr(parents, "get_table", lambda: table)

    children = parents._scan_children_for_parent("parent")

    assert [child["user_id"] for child in children] == ["child-1", "child-2"]
    assert table.calls[0]["ExpressionAttributeValues"] == {":pid": "parent", ":role": "student"}
    assert table.calls[1]["ExclusiveStartKey"] == {"PK": "USER#child-1", "SK": "PROFILE"}


def test_scan_children_for_parent_empty(monkeypatch):
    monkeypatch.setattr(parents, "get_table", lambda: FakeTable([{"Items": []}]))

    assert parents._scan_children_for_parent("parent") == []


def test_parents_me_children_returns_items(monkeypatch):
    parent = parents.ResolvedParent(
        claims_sub="cognito-sub",
        email="p@example.com",
        parent_user_id="parent-local",
        profile={"user_id": "parent-local", "role": "parent"},
    )
    monkeypatch.setattr(parents, "_resolve_parent_profile", lambda user, settings: parent)
    monkeypatch.setattr(
        parents,
        "_scan_children_for_parent",
        lambda parent_user_id: [
            {
                "user_id": "child-1",
                "name": "Anna Keller",
                "email": "anna@example.com",
                "grade": "Grade 8",
                "primary_subjects": ["Mathematics"],
            }
        ],
    )

    client = TestClient(_app_for_user({"sub": "cognito-sub", "role": "parent"}))
    response = client.get("/parents/me/children")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": "child-1",
                "userId": "child-1",
                "name": "Anna Keller",
                "email": "anna@example.com",
                "grade": "Grade 8",
                "subjects": ["Mathematics"],
                "relationship": "child",
            }
        ]
    }


def test_parents_me_children_returns_empty_items(monkeypatch):
    parent = parents.ResolvedParent(
        claims_sub="cognito-sub",
        email="p@example.com",
        parent_user_id="parent-local",
        profile={"user_id": "parent-local", "role": "parent"},
    )
    monkeypatch.setattr(parents, "_resolve_parent_profile", lambda user, settings: parent)
    monkeypatch.setattr(parents, "_scan_children_for_parent", lambda parent_user_id: [])

    client = TestClient(_app_for_user({"sub": "cognito-sub", "role": "parent"}))
    response = client.get("/parents/me/children")

    assert response.status_code == 200
    assert response.json() == {"items": []}


@pytest.mark.parametrize("role", ["student", "teacher", "tutor", "admin"])
def test_parents_me_children_rejects_non_parent_roles(role):
    client = TestClient(_app_for_user({"sub": f"{role}-sub", "role": role}))

    response = client.get("/parents/me/children")

    assert response.status_code == 403


def test_legacy_children_allows_local_parent_id_when_sub_differs(monkeypatch):
    parent = parents.ResolvedParent(
        claims_sub="cognito-sub",
        email="p@example.com",
        parent_user_id="parent-local",
        profile={"user_id": "parent-local", "role": "parent"},
    )
    monkeypatch.setattr(parents, "_resolve_parent_profile", lambda user, settings: parent)
    monkeypatch.setattr(
        parents,
        "_scan_children_for_parent",
        lambda parent_user_id: [
            {
                "user_id": "child-1",
                "email": "child@example.com",
                "grade": "Grade 8",
                "subjects": ["Mathematics"],
            }
        ],
    )

    client = TestClient(_app_for_user({"sub": "cognito-sub", "role": "parent"}))
    response = client.get("/parents/parent-local/children")

    assert response.status_code == 200
    assert response.json() == [
        {
            "user_id": "child-1",
            "email": "child@example.com",
            "grade": "Grade 8",
            "subjects": ["Mathematics"],
        }
    ]


def test_legacy_children_rejects_other_parent(monkeypatch):
    parent = parents.ResolvedParent(
        claims_sub="cognito-sub",
        email="p@example.com",
        parent_user_id="parent-local",
        profile={"user_id": "parent-local", "role": "parent"},
    )
    monkeypatch.setattr(parents, "_resolve_parent_profile", lambda user, settings: parent)

    client = TestClient(_app_for_user({"sub": "cognito-sub", "role": "parent"}))
    response = client.get("/parents/other-parent/children")

    assert response.status_code == 403


def test_legacy_children_allows_admin(monkeypatch):
    monkeypatch.setattr(parents, "_scan_children_for_parent", lambda parent_user_id: [])

    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))
    response = client.get("/parents/parent-local/children")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("role", ["student", "teacher", "tutor"])
def test_legacy_children_rejects_other_roles(role):
    client = TestClient(_app_for_user({"sub": f"{role}-sub", "role": role}))

    response = client.get("/parents/parent-local/children")

    assert response.status_code == 403


def test_legacy_report_allows_local_parent_id_when_sub_differs(monkeypatch):
    parent = parents.ResolvedParent(
        claims_sub="cognito-sub",
        email="p@example.com",
        parent_user_id="parent-local",
        profile={"user_id": "parent-local", "role": "parent"},
    )
    report = {
        "report_id": "report-1",
        "parent_id": "parent-local",
        "student_id": "child-1",
        "week_start": "2026-06-01",
        "usage_count": 3,
        "ai_resolved": 2,
        "teacher_resolved": 1,
        "weak_knowledge_points": ["fractions"],
        "recommendations": "Practice fractions.",
    }
    monkeypatch.setattr(parents, "_resolve_parent_profile", lambda user, settings: parent)
    monkeypatch.setattr(parents.report_repo, "get_report_by_week", lambda parent_id, week: report)

    client = TestClient(_app_for_user({"sub": "cognito-sub", "role": "parent"}))
    response = client.get("/parents/parent-local/reports/2026-06-01")

    assert response.status_code == 200
    assert response.json()["report_id"] == "report-1"


def test_legacy_report_rejects_other_parent(monkeypatch):
    parent = parents.ResolvedParent(
        claims_sub="cognito-sub",
        email="p@example.com",
        parent_user_id="parent-local",
        profile={"user_id": "parent-local", "role": "parent"},
    )
    monkeypatch.setattr(parents, "_resolve_parent_profile", lambda user, settings: parent)

    client = TestClient(_app_for_user({"sub": "cognito-sub", "role": "parent"}))
    response = client.get("/parents/other-parent/reports/2026-06-01")

    assert response.status_code == 403


def test_legacy_report_allows_admin(monkeypatch):
    report = {
        "report_id": "report-1",
        "parent_id": "parent-local",
        "student_id": "child-1",
        "week_start": "2026-06-01",
        "usage_count": 3,
        "ai_resolved": 2,
        "teacher_resolved": 1,
        "weak_knowledge_points": [],
        "recommendations": "",
    }
    monkeypatch.setattr(parents.report_repo, "get_report_by_week", lambda parent_id, week: report)

    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))
    response = client.get("/parents/parent-local/reports/2026-06-01")

    assert response.status_code == 200


def test_legacy_report_missing_still_returns_404(monkeypatch):
    monkeypatch.setattr(parents.report_repo, "get_report_by_week", lambda parent_id, week: None)

    client = TestClient(_app_for_user({"sub": "admin-sub", "role": "admin"}))
    response = client.get("/parents/parent-local/reports/2026-06-01")

    assert response.status_code == 404


def test_get_owned_child_profile_returns_linked_child(monkeypatch):
    monkeypatch.setattr(parents, "_scan_children_for_parent", lambda parent_user_id: [_child_profile()])

    child = parents._get_owned_child_profile(_resolved_parent(), "child-1")

    assert child["user_id"] == "child-1"


def test_get_owned_child_profile_rejects_unlinked_child(monkeypatch):
    monkeypatch.setattr(parents, "_scan_children_for_parent", lambda parent_user_id: [_child_profile()])

    with pytest.raises(parents.HTTPException) as exc:
        parents._get_owned_child_profile(_resolved_parent(), "other-child")

    assert exc.value.status_code == 403


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
            "Limit": 7,
            "ScanIndexForward": False,
            "ExclusiveStartKey": {"PK": "REPORT#0"},
        }
    ]


def test_report_repo_page_token_round_trip():
    key = {"PK": "REPORT#1", "SK": "SUMMARY"}

    token = report_repo.encode_page_token(key)

    assert isinstance(token, str)
    assert report_repo.decode_page_token(token) == key


def test_report_repo_decode_page_token_rejects_invalid_token():
    with pytest.raises(ValueError):
        report_repo.decode_page_token("not-base64")


def test_report_repo_decode_page_token_rejects_non_report_key():
    token = report_repo.encode_page_token({"PK": "USER#1", "SK": "PROFILE"})

    with pytest.raises(ValueError):
        report_repo.decode_page_token(token)


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
                {"Items": [_report("sibling")], "LastEvaluatedKey": {"PK": "REPORT#sibling"}},
                {"Items": [_report("child-1")]},
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


def test_parent_child_week_report_available_when_same_week_sibling_first(monkeypatch):
    app = _app_for_user({"sub": "parent-local", "role": "parent"})
    app.dependency_overrides[parents.get_settings] = _settings
    client = TestClient(app)

    monkeypatch.setattr(parents, "_resolve_parent_profile", lambda user, settings: _resolved_parent())
    monkeypatch.setattr(parents, "_get_owned_child_profile", lambda resolved, child_id: _child_profile())
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
    monkeypatch.setattr(parents, "_resolve_parent_profile", lambda user, settings: _resolved_parent())
    monkeypatch.setattr(parents, "_scan_children_for_parent", lambda parent_user_id: [_child_profile()])
    monkeypatch.setattr(
        parents.question_repo,
        "list_by_student",
        lambda child_id, limit=20, last_key=None: {
            "Items": [
                {
                    "question_id": "q-1",
                    "status": "ai_answered",
                    "prompt": "How do fractions work?",
                    "subject": "math",
                    "knowledge_points": ["fractions", "algebra"],
                    "created_at": "2026-06-02T10:00:00+00:00",
                },
                {
                    "question_id": "q-2",
                    "status": "escalated",
                    "prompt": "Need help",
                    "subject": "math",
                    "knowledge_points": ["fractions"],
                    "created_at": "2026-06-02T11:00:00+00:00",
                },
                {
                    "question_id": "q-old",
                    "status": "ai_answered",
                    "prompt": "Old question",
                    "knowledge_points": ["old-topic"],
                    "created_at": "2026-05-20T10:00:00+00:00",
                },
            ]
        },
    )
    monkeypatch.setattr(
        parents.practice_repo,
        "get_progress",
        lambda child_id: [
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
    )
    monkeypatch.setattr(
        parents.practice_repo,
        "get_mistakes",
        lambda child_id: [{"challenge_id": "m-1", "topic_id": "geometry", "created_at": "2026-06-02T08:30:00+00:00"}],
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


def test_parent_child_summary_empty_state(monkeypatch):
    monkeypatch.setattr(parents, "_resolve_parent_profile", lambda user, settings: _resolved_parent())
    monkeypatch.setattr(parents, "_scan_children_for_parent", lambda parent_user_id: [_child_profile()])
    monkeypatch.setattr(parents.question_repo, "list_by_student", lambda child_id, limit=20, last_key=None: {"Items": []})
    monkeypatch.setattr(parents.practice_repo, "get_progress", lambda child_id: [])
    monkeypatch.setattr(parents.practice_repo, "get_mistakes", lambda child_id: [])
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
    monkeypatch.setattr(parents, "_resolve_parent_profile", lambda user, settings: _resolved_parent())
    monkeypatch.setattr(parents, "_scan_children_for_parent", lambda parent_user_id: [_child_profile()])

    def fail(*args, **kwargs):
        raise AssertionError("child data reader should not run")

    monkeypatch.setattr(parents.question_repo, "list_by_student", fail)
    monkeypatch.setattr(parents.practice_repo, "get_progress", fail)
    monkeypatch.setattr(parents.practice_repo, "get_mistakes", fail)
    monkeypatch.setattr(parents, "_list_conversations_for_child", fail)
    monkeypatch.setattr(parents, "_latest_report_for_child", fail)

    client = TestClient(_app_for_user({"sub": "cognito-sub", "role": "parent"}))
    response = client.get("/parents/me/children/other-child/summary")

    assert response.status_code == 403


@pytest.mark.parametrize("role", ["student", "teacher", "tutor", "admin"])
def test_parent_child_summary_rejects_non_parent_roles(role):
    client = TestClient(_app_for_user({"sub": f"{role}-sub", "role": role}))

    response = client.get("/parents/me/children/child-1/summary")

    assert response.status_code == 403


def test_parent_child_history_returns_newest_first_with_limit(monkeypatch):
    monkeypatch.setattr(parents, "_resolve_parent_profile", lambda user, settings: _resolved_parent())
    monkeypatch.setattr(parents, "_scan_children_for_parent", lambda parent_user_id: [_child_profile()])
    monkeypatch.setattr(
        parents.question_repo,
        "list_by_student",
        lambda child_id, limit=20, last_key=None: {
            "Items": [
                {
                    "question_id": "q-1",
                    "status": "ai_answered",
                    "prompt": "Question",
                    "created_at": "2026-06-02T10:00:00+00:00",
                }
            ]
        },
    )
    monkeypatch.setattr(
        parents.practice_repo,
        "get_progress",
        lambda child_id: [{"lesson_id": "lesson-1", "status": "completed", "completed_at": "2026-06-02T09:00:00+00:00"}],
    )
    monkeypatch.setattr(
        parents.practice_repo,
        "get_mistakes",
        lambda child_id: [{"challenge_id": "m-1", "topic_id": "geometry", "created_at": "2026-06-02T08:30:00+00:00"}],
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


def test_parent_child_history_empty_state(monkeypatch):
    monkeypatch.setattr(parents, "_resolve_parent_profile", lambda user, settings: _resolved_parent())
    monkeypatch.setattr(parents, "_scan_children_for_parent", lambda parent_user_id: [_child_profile()])
    monkeypatch.setattr(parents.question_repo, "list_by_student", lambda child_id, limit=20, last_key=None: {"Items": []})
    monkeypatch.setattr(parents.practice_repo, "get_progress", lambda child_id: [])
    monkeypatch.setattr(parents.practice_repo, "get_mistakes", lambda child_id: [])
    monkeypatch.setattr(parents, "_list_conversations_for_child", lambda child_id: [])
    monkeypatch.setattr(parents.report_repo, "list_reports_for_parent", lambda parent_id, limit=25, last_key=None: {"Items": []})

    client = TestClient(_app_for_user({"sub": "cognito-sub", "role": "parent"}))
    response = client.get("/parents/me/children/child-1/history")

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_parent_child_history_rejects_unlinked_before_data_reads(monkeypatch):
    monkeypatch.setattr(parents, "_resolve_parent_profile", lambda user, settings: _resolved_parent())
    monkeypatch.setattr(parents, "_scan_children_for_parent", lambda parent_user_id: [_child_profile()])

    def fail(*args, **kwargs):
        raise AssertionError("history source should not run")

    monkeypatch.setattr(parents.question_repo, "list_by_student", fail)
    monkeypatch.setattr(parents.practice_repo, "get_progress", fail)
    monkeypatch.setattr(parents.practice_repo, "get_mistakes", fail)
    monkeypatch.setattr(parents, "_list_conversations_for_child", fail)
    monkeypatch.setattr(parents.report_repo, "list_reports_for_parent", fail)

    client = TestClient(_app_for_user({"sub": "cognito-sub", "role": "parent"}))
    response = client.get("/parents/me/children/other-child/history")

    assert response.status_code == 403


@pytest.mark.parametrize("role", ["student", "teacher", "tutor", "admin"])
def test_parent_child_history_rejects_non_parent_roles(role):
    client = TestClient(_app_for_user({"sub": f"{role}-sub", "role": role}))

    response = client.get("/parents/me/children/child-1/history")

    assert response.status_code == 403


def test_parent_child_report_current_available(monkeypatch):
    monkeypatch.setattr(parents, "_resolve_parent_profile", lambda user, settings: _resolved_parent())
    monkeypatch.setattr(parents, "_scan_children_for_parent", lambda parent_user_id: [_child_profile()])
    monkeypatch.setattr(parents, "_latest_report_for_child", lambda parent_id, child_id: _report())

    client = TestClient(_app_for_user({"sub": "cognito-sub", "role": "parent"}))
    response = client.get("/parents/me/children/child-1/report")

    assert response.status_code == 200
    assert response.json()["status"] == "available"
    assert response.json()["report"]["studentId"] == "child-1"


@pytest.mark.parametrize("latest_report", [None, _report("sibling")])
def test_parent_child_report_current_missing(monkeypatch, latest_report):
    monkeypatch.setattr(parents, "_resolve_parent_profile", lambda user, settings: _resolved_parent())
    monkeypatch.setattr(parents, "_scan_children_for_parent", lambda parent_user_id: [_child_profile()])
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
    monkeypatch.setattr(parents, "_resolve_parent_profile", lambda user, settings: _resolved_parent())
    monkeypatch.setattr(parents, "_scan_children_for_parent", lambda parent_user_id: [_child_profile()])

    def fail(*args, **kwargs):
        raise AssertionError("report reader should not run")

    monkeypatch.setattr(parents, "_latest_report_for_child", fail)
    monkeypatch.setattr(parents.report_repo, "get_report_for_child_by_week", fail)

    client = TestClient(_app_for_user({"sub": "cognito-sub", "role": "parent"}))
    response = client.get("/parents/me/children/other-child/report")

    assert response.status_code == 403


def test_parent_child_week_report_available_after_ownership(monkeypatch):
    calls = []
    monkeypatch.setattr(parents, "_resolve_parent_profile", lambda user, settings: _resolved_parent())
    monkeypatch.setattr(parents, "_scan_children_for_parent", lambda parent_user_id: [_child_profile()])

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
    monkeypatch.setattr(parents, "_resolve_parent_profile", lambda user, settings: _resolved_parent())
    monkeypatch.setattr(parents, "_scan_children_for_parent", lambda parent_user_id: [_child_profile()])
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
    monkeypatch.setattr(parents, "_resolve_parent_profile", lambda user, settings: _resolved_parent())
    monkeypatch.setattr(parents, "_scan_children_for_parent", lambda parent_user_id: [_child_profile()])
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
    monkeypatch.setattr(parents, "_resolve_parent_profile", lambda user, settings: _resolved_parent())
    monkeypatch.setattr(parents, "_scan_children_for_parent", lambda parent_user_id: [_child_profile()])
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
    monkeypatch.setattr(parents, "_resolve_parent_profile", lambda user, settings: _resolved_parent())
    monkeypatch.setattr(parents, "_scan_children_for_parent", lambda parent_user_id: [_child_profile()])
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
    monkeypatch.setattr(parents, "_resolve_parent_profile", lambda user, settings: _resolved_parent())
    monkeypatch.setattr(parents, "_scan_children_for_parent", lambda parent_user_id: [_child_profile()])
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
    monkeypatch.setattr(parents, "_resolve_parent_profile", lambda user, settings: _resolved_parent())
    monkeypatch.setattr(parents, "_scan_children_for_parent", lambda parent_user_id: [_child_profile()])
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


@pytest.mark.parametrize("role", ["student", "teacher", "tutor", "admin"])
def test_parent_child_report_routes_reject_non_parent_roles(role):
    client = TestClient(_app_for_user({"sub": f"{role}-sub", "role": role}))

    assert client.get("/parents/me/children/child-1/report").status_code == 403
    assert client.get("/parents/me/children/child-1/reports/2026-06-01").status_code == 403
