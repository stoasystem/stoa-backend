import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.config import Settings
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
