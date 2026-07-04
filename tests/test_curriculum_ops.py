from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from stoa.deps import get_current_user
from stoa.routers import admin
from stoa.services import curriculum_ops_service


def _app_for_user(user: dict) -> FastAPI:
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def _operator_user(*capabilities: str, role: str = "tutor", sub: str = "operator-1") -> dict:
    return {
        "sub": sub,
        "role": role,
        "capabilities": {capability: "granted" for capability in capabilities},
    }


def _draft_payload(public_id: str = "lesson-linear-ops") -> dict:
    return {
        "publicLessonId": public_id,
        "title": "Linear equations operations",
        "objective": "Solve one-step equations safely.",
        "description": "Use inverse operations.",
        "subjectId": "math",
        "topicId": "linear-equations",
        "unitId": "unit-linear",
        "gradeLevel": "lower_secondary",
        "difficulty": "standard",
        "estimatedMinutes": 12,
        "language": "neutral",
        "exercises": [
            {
                "exerciseId": "exercise-linear-ops-1",
                "prompt": "Solve x + 4 = 9.",
                "answerKey": "x = 5",
                "explanation": "Subtract 4 from both sides.",
                "difficulty": "standard",
                "order": 1,
            }
        ],
    }


def _install_curriculum_ops_repo(monkeypatch, active_refs=None):
    versions: dict[tuple[str, str], dict] = {}
    pointers: dict[str, dict] = {}
    manifests: list[dict] = []
    projections: list[tuple[dict, dict]] = []
    audits: list[tuple[str, dict]] = []
    refs = list(active_refs or [])
    repo = curriculum_ops_service.curriculum_ops_repo

    def put_version(item):
        versions[(item["public_id"], item["version_id"])] = dict(item)

    def get_version(public_id, version_id):
        item = versions.get((public_id, version_id))
        return dict(item) if item else None

    def put_pointer(item):
        current = pointers.get(item["public_id"], {})
        pointers[item["public_id"]] = {**current, **dict(item)}

    def set_published_pointer(
        *,
        public_id,
        version_id,
        manifest_id,
        expected_published_version_id,
        actor_id,
        updated_at,
    ):
        current = pointers.get(public_id, {"public_id": public_id})
        current_published = current.get("published_version_id")
        if expected_published_version_id != current_published:
            raise repo.StalePointerError("stale")
        updated = {
            **current,
            "public_id": public_id,
            "published_version_id": version_id,
            "manifest_id": manifest_id,
            "updated_by": actor_id,
            "updated_at": updated_at,
        }
        pointers[public_id] = updated
        return dict(updated)

    monkeypatch.setattr(repo, "put_version", put_version)
    monkeypatch.setattr(repo, "get_version", get_version)
    monkeypatch.setattr(repo, "put_pointer", put_pointer)
    monkeypatch.setattr(repo, "get_pointer", lambda public_id: dict(pointers.get(public_id, {})))
    monkeypatch.setattr(repo, "set_published_pointer", set_published_pointer)
    monkeypatch.setattr(repo, "put_manifest", lambda item: manifests.append(dict(item)))
    monkeypatch.setattr(
        repo,
        "put_published_projection",
        lambda version, manifest: projections.append((dict(version), dict(manifest))),
    )
    monkeypatch.setattr(repo, "append_audit_event", lambda public_id, event: audits.append((public_id, dict(event))))
    monkeypatch.setattr(
        repo,
        "list_audit_events",
        lambda public_id, limit=50: [
            dict(event)
            for event_public_id, event in reversed(audits)
            if event_public_id == public_id
        ][:limit],
    )
    monkeypatch.setattr(
        repo,
        "list_worklist",
        lambda status=None, limit=100: [
            dict(item)
            for item in versions.values()
            if status is None or item.get("state") == status
        ][:limit],
    )
    monkeypatch.setattr(repo, "list_active_assignment_refs", lambda public_id: list(refs))
    return {
        "versions": versions,
        "pointers": pointers,
        "manifests": manifests,
        "projections": projections,
        "audits": audits,
        "active_refs": refs,
    }


@pytest.mark.parametrize("role", ["admin", "tutor", "teacher"])
def test_curriculum_authoring_requires_explicit_capability(monkeypatch, role):
    _install_curriculum_ops_repo(monkeypatch)
    client = TestClient(_app_for_user({"sub": f"{role}-1", "role": role}))

    response = client.post("/admin/curriculum/lessons/drafts", json=_draft_payload())

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "curriculum_capability_required"


def test_curriculum_route_still_requires_internal_role(monkeypatch):
    _install_curriculum_ops_repo(monkeypatch)
    client = TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.AUTHOR_CAPABILITY, role="student"))
    )

    response = client.post("/admin/curriculum/lessons/drafts", json=_draft_payload())

    assert response.status_code == 403


def test_curriculum_draft_review_publish_flow_preserves_draft_isolation(monkeypatch):
    state = _install_curriculum_ops_repo(monkeypatch)
    author = TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.AUTHOR_CAPABILITY, sub="author-1"))
    )
    reviewer = TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.REVIEWER_CAPABILITY, sub="reviewer-1"))
    )
    publisher = TestClient(
        _app_for_user(
            _operator_user(curriculum_ops_service.PUBLISHER_CAPABILITY, role="admin", sub="publisher-1")
        )
    )

    created = author.post("/admin/curriculum/lessons/drafts", json=_draft_payload())

    assert created.status_code == 200
    version_id = created.json()["versionId"]
    assert created.json()["state"] == "draft"
    assert state["projections"] == []

    preview = author.get(
        "/admin/curriculum/lessons/lesson-linear-ops/preview",
        params={"versionId": version_id},
    )
    submitted = author.post(
        f"/admin/curriculum/lessons/lesson-linear-ops/drafts/{version_id}/submit-review"
    )
    approved = reviewer.post(
        f"/admin/curriculum/lessons/lesson-linear-ops/drafts/{version_id}/approve"
    )
    published = publisher.post(
        "/admin/curriculum/lessons/lesson-linear-ops/publish",
        json={"versionId": version_id, "expectedPublishedVersionId": None},
    )

    assert preview.status_code == 200
    assert preview.json()["lesson"]["lesson_id"] == "lesson-linear-ops"
    assert submitted.status_code == 200
    assert submitted.json()["state"] == "in_review"
    assert approved.status_code == 200
    assert approved.json()["state"] == "approved"
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    assert state["pointers"]["lesson-linear-ops"]["published_version_id"] == version_id
    assert len(state["projections"]) == 1
    assert state["projections"][0][0]["lesson"]["lesson_id"] == "lesson-linear-ops"
    assert [event["operation"] for _, event in state["audits"]] == [
        "create_draft",
        "submit_review",
        "approve",
        "publish",
    ]


def test_curriculum_publish_rejects_unapproved_versions(monkeypatch):
    _install_curriculum_ops_repo(monkeypatch)
    author = TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.AUTHOR_CAPABILITY, sub="author-1"))
    )
    publisher = TestClient(
        _app_for_user(
            _operator_user(curriculum_ops_service.PUBLISHER_CAPABILITY, role="admin", sub="publisher-1")
        )
    )

    created = author.post("/admin/curriculum/lessons/drafts", json=_draft_payload())
    version_id = created.json()["versionId"]
    published = publisher.post(
        "/admin/curriculum/lessons/lesson-linear-ops/publish",
        json={"versionId": version_id, "expectedPublishedVersionId": None},
    )

    assert published.status_code == 409
    assert published.json()["detail"] == "not_approved"


def test_curriculum_publish_uses_compare_and_set_pointer(monkeypatch):
    state = _install_curriculum_ops_repo(monkeypatch)
    state["pointers"]["lesson-linear-ops"] = {
        "public_id": "lesson-linear-ops",
        "published_version_id": "different-version",
    }
    author = TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.AUTHOR_CAPABILITY, sub="author-1"))
    )
    reviewer = TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.REVIEWER_CAPABILITY, sub="reviewer-1"))
    )
    publisher = TestClient(
        _app_for_user(
            _operator_user(curriculum_ops_service.PUBLISHER_CAPABILITY, role="admin", sub="publisher-1")
        )
    )

    created = author.post("/admin/curriculum/lessons/drafts", json=_draft_payload())
    version_id = created.json()["versionId"]
    author.post(f"/admin/curriculum/lessons/lesson-linear-ops/drafts/{version_id}/submit-review")
    reviewer.post(f"/admin/curriculum/lessons/lesson-linear-ops/drafts/{version_id}/approve")
    published = publisher.post(
        "/admin/curriculum/lessons/lesson-linear-ops/publish",
        json={"versionId": version_id, "expectedPublishedVersionId": "stale-version"},
    )

    assert published.status_code == 409
    assert published.json()["detail"] == "stale_pointer"
    assert state["pointers"]["lesson-linear-ops"]["published_version_id"] == "different-version"


def test_curriculum_archive_refuses_active_assignment_references(monkeypatch):
    state = _install_curriculum_ops_repo(
        monkeypatch,
        active_refs=[{"assignment_id": "assignment-1", "status": "assigned"}],
    )
    author = TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.AUTHOR_CAPABILITY, sub="author-1"))
    )
    publisher = TestClient(
        _app_for_user(
            _operator_user(curriculum_ops_service.PUBLISHER_CAPABILITY, role="admin", sub="publisher-1")
        )
    )

    created = author.post("/admin/curriculum/lessons/drafts", json=_draft_payload())
    version_id = created.json()["versionId"]
    archived = publisher.post(
        "/admin/curriculum/lessons/lesson-linear-ops/archive",
        json={"versionId": version_id, "reason": "cleanup"},
    )

    assert archived.status_code == 409
    assert archived.json()["detail"] == "active_assignments_block_archive"
    assert state["versions"][("lesson-linear-ops", version_id)]["state"] == "draft"
    assert state["audits"][-1][1]["operation"] == "archive_refused"


def test_curriculum_rollback_repoints_to_prior_version(monkeypatch):
    state = _install_curriculum_ops_repo(monkeypatch)
    author = TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.AUTHOR_CAPABILITY, sub="author-1"))
    )
    reviewer = TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.REVIEWER_CAPABILITY, sub="reviewer-1"))
    )
    publisher = TestClient(
        _app_for_user(
            _operator_user(curriculum_ops_service.PUBLISHER_CAPABILITY, role="admin", sub="publisher-1")
        )
    )

    first = author.post("/admin/curriculum/lessons/drafts", json=_draft_payload())
    first_version = first.json()["versionId"]
    author.post(f"/admin/curriculum/lessons/lesson-linear-ops/drafts/{first_version}/submit-review")
    reviewer.post(f"/admin/curriculum/lessons/lesson-linear-ops/drafts/{first_version}/approve")
    publisher.post(
        "/admin/curriculum/lessons/lesson-linear-ops/publish",
        json={"versionId": first_version, "expectedPublishedVersionId": None},
    )

    second_payload = _draft_payload()
    second_payload["title"] = "Linear equations operations v2"
    second = author.post("/admin/curriculum/lessons/drafts", json=second_payload)
    second_version = second.json()["versionId"]
    author.post(f"/admin/curriculum/lessons/lesson-linear-ops/drafts/{second_version}/submit-review")
    reviewer.post(f"/admin/curriculum/lessons/lesson-linear-ops/drafts/{second_version}/approve")
    publisher.post(
        "/admin/curriculum/lessons/lesson-linear-ops/publish",
        json={"versionId": second_version, "expectedPublishedVersionId": first_version},
    )

    rolled_back = publisher.post(
        "/admin/curriculum/lessons/lesson-linear-ops/rollback",
        json={
            "versionId": first_version,
            "expectedPublishedVersionId": second_version,
            "reason": "bad v2",
        },
    )

    assert rolled_back.status_code == 200
    assert rolled_back.json()["status"] == "rolled_back"
    assert state["pointers"]["lesson-linear-ops"]["published_version_id"] == first_version
    assert state["projections"][-1][0]["lesson"]["title"] == "Linear equations operations"


def test_curriculum_author_can_patch_draft_and_preview_validation(monkeypatch):
    state = _install_curriculum_ops_repo(monkeypatch)
    author = TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.AUTHOR_CAPABILITY, sub="author-1"))
    )

    created = author.post("/admin/curriculum/lessons/drafts", json=_draft_payload())
    version_id = created.json()["versionId"]
    patched = author.patch(
        f"/admin/curriculum/lessons/lesson-linear-ops/drafts/{version_id}",
        json={
            "title": "Linear equations edited",
            "tags": ["algebra", "equations"],
            "exercises": [
                {
                    "exerciseId": "exercise-linear-ops-1",
                    "prompt": "Solve x + 4 = 9.",
                    "answerKey": "x = 5",
                    "difficulty": "standard",
                    "order": 1,
                }
            ],
        },
    )
    preview = author.post(
        f"/admin/curriculum/lessons/lesson-linear-ops/drafts/{version_id}/validation-preview"
    )

    assert patched.status_code == 200
    assert patched.json()["versionId"] == version_id
    assert patched.json()["lesson"]["title"] == "Linear equations edited"
    assert patched.json()["lesson"]["tags"] == ["algebra", "equations"]
    assert state["versions"][("lesson-linear-ops", version_id)]["state"] == "draft"
    assert state["projections"] == []
    assert preview.status_code == 200
    assert preview.json()["publishReady"] is False
    assert preview.json()["issues"][0]["field"] == "exercises[0].explanation"


def test_curriculum_reviewer_can_read_diff_and_audit(monkeypatch):
    state = _install_curriculum_ops_repo(monkeypatch)
    author = TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.AUTHOR_CAPABILITY, sub="author-1"))
    )
    reviewer = TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.REVIEWER_CAPABILITY, sub="reviewer-1"))
    )
    ordinary_teacher = TestClient(_app_for_user({"sub": "teacher-1", "role": "teacher"}))

    first = author.post("/admin/curriculum/lessons/drafts", json=_draft_payload())
    first_version = first.json()["versionId"]
    second_payload = _draft_payload()
    second_payload["title"] = "Linear equations reviewed diff"
    second = author.post("/admin/curriculum/lessons/drafts", json=second_payload)
    second_version = second.json()["versionId"]

    denied = ordinary_teacher.get(
        "/admin/curriculum/lessons/lesson-linear-ops/audit",
    )
    diff = reviewer.get(
        "/admin/curriculum/lessons/lesson-linear-ops/diff",
        params={"fromVersionId": first_version, "toVersionId": second_version},
    )
    audit = reviewer.get("/admin/curriculum/lessons/lesson-linear-ops/audit")

    assert denied.status_code == 403
    assert diff.status_code == 200
    assert {
        "path": "lesson.title",
        "type": "modified",
        "before": "Linear equations operations",
        "after": "Linear equations reviewed diff",
    } in diff.json()["changes"]
    assert audit.status_code == 200
    assert audit.json()["count"] == 2
    assert audit.json()["items"][0]["actorCapabilities"] == [curriculum_ops_service.AUTHOR_CAPABILITY]
    assert [event["operation"] for _, event in state["audits"]] == ["create_draft", "create_draft"]


def test_curriculum_publish_actions_require_publisher_capability(monkeypatch):
    _install_curriculum_ops_repo(monkeypatch)
    author = TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.AUTHOR_CAPABILITY, sub="author-1"))
    )
    reviewer = TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.REVIEWER_CAPABILITY, sub="reviewer-1"))
    )

    created = author.post("/admin/curriculum/lessons/drafts", json=_draft_payload())
    version_id = created.json()["versionId"]
    author.post(f"/admin/curriculum/lessons/lesson-linear-ops/drafts/{version_id}/submit-review")
    reviewer.post(f"/admin/curriculum/lessons/lesson-linear-ops/drafts/{version_id}/approve")
    published = reviewer.post(
        "/admin/curriculum/lessons/lesson-linear-ops/publish",
        json={"versionId": version_id, "expectedPublishedVersionId": None},
    )

    assert published.status_code == 403
    assert published.json()["detail"]["required"] == [curriculum_ops_service.PUBLISHER_CAPABILITY]
