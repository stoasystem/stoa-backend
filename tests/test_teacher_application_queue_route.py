"""#104: the reviewer queue is a list, so it is authorized as one.

`GET /teacher-applications` used to share the per-application reviewer dependency,
which declares `application_id` as a required parameter; every queue read answered
422 before authorization ran. These cases enter through the route.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from stoa.routers import admin, teacher_applications
from stoa.services import teacher_application_service


REVIEWER = {
    "sub": "admin-reviewer",
    "role": "admin",
    "grantCapabilities": ("teacher_identity_reviewer",),
    "grantScope": "global",
}


def _row(application_id: str, review_state: str) -> dict[str, Any]:
    return {
        "application_id": application_id,
        "version": 1,
        "status": "submitted",
        "created_at": "2026-10-10T08:00:00Z",
        "review_state": review_state,
        "verified_email": f"{application_id}@stoa.test",
        "full_name": "Ada Lovelace",
        "subjects": ["math"],
        "statement": "private statement",
    }


@pytest.fixture
def queue(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int]]:
    calls: list[tuple[str, int]] = []

    def list_by_state(review_state: str, *, limit: int = 50) -> list[dict[str, Any]]:
        calls.append((review_state, limit))
        return [_row(f"application-{review_state}", review_state)]

    repo = teacher_application_service.teacher_application_repo
    monkeypatch.setattr(repo, "list_applications_by_review_state", list_by_state)
    monkeypatch.setattr(
        repo,
        "get_application_version",
        lambda application_id, version: _row(application_id, "pending_review"),
    )
    return calls


def _client(user: dict[str, Any]) -> TestClient:
    app = FastAPI()
    app.include_router(teacher_applications.router, prefix="/teacher-applications")
    app.include_router(admin.router, prefix="/admin")
    install_actor_overrides(app, user)
    return TestClient(app)


@pytest.mark.parametrize("review_state", ["pending_review", "approved", "rejected"])
def test_reviewer_reads_the_queue_in_every_review_state(queue, review_state):
    response = _client(REVIEWER).get(
        "/teacher-applications", params={"review_state": review_state, "limit": 50}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reviewState"] == review_state
    assert body["count"] == 1
    assert body["items"][0]["applicationId"] == f"application-{review_state}"
    assert body["items"][0]["verifiedEmail"] == f"application-{review_state}@stoa.test"
    assert "statement" not in body["items"][0]
    assert queue == [(review_state, 50)]


def test_queue_still_answers_the_frontend_that_sends_a_placeholder_id(queue):
    # The admin console sends `application_id=*` to get past the old 422; it must
    # keep working until the console drops it.
    response = _client(REVIEWER).get(
        "/teacher-applications",
        params={"review_state": "pending_review", "limit": 50, "application_id": "*"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["count"] == 1


def _refusal(response) -> dict[str, Any]:
    assert response.status_code == 403, response.text
    detail = dict(response.json()["detail"])
    assert detail.pop("correlationId")
    return detail


@pytest.mark.parametrize(
    "user",
    [
        pytest.param(
            {"sub": "admin-plain", "role": "admin", "grantCapabilities": ("admin_identity_manager",)},
            id="admin-without-reviewer-grant",
        ),
        pytest.param(
            {
                "sub": "admin-one-application",
                "role": "admin",
                "grantCapabilities": ("teacher_identity_reviewer",),
                "grantScope": "resource:operator_resource:application-1",
            },
            id="reviewer-grant-for-one-application-only",
        ),
        pytest.param(
            {
                "sub": "teacher-reviewer",
                "role": "teacher",
                "grantCapabilities": ("teacher_identity_reviewer",),
                "grantScope": "global",
            },
            id="teacher-holding-the-grant",
        ),
        pytest.param(
            {"sub": "student-1", "role": "student", "grantCapabilities": ()},
            id="student",
        ),
    ],
)
def test_queue_refuses_others_as_the_admin_list_routes_do(queue, user):
    client = _client(user)

    refused = client.get("/teacher-applications", params={"review_state": "pending_review"})
    # `/admin/users` is an operator list this caller holds no grant for either.
    admin_list = client.get("/admin/users")

    assert _refusal(refused) == _refusal(admin_list)
    assert queue == []


def test_per_application_read_still_authorizes_the_named_application(queue):
    scoped = {
        "sub": "admin-one-application",
        "role": "admin",
        "grantCapabilities": ("teacher_identity_reviewer",),
        "grantScope": "resource:operator_resource:application-1",
    }
    client = _client(scoped)

    assert client.get("/teacher-applications/application-1/versions/1").status_code == 200
    assert client.get("/teacher-applications/application-2/versions/1").status_code == 403
