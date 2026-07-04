from fastapi import FastAPI
from fastapi.testclient import TestClient

from stoa.deps import get_current_user
from stoa.routers import admin
from stoa.services import curriculum_migration_service, curriculum_ops_service


def _app_for_user(user: dict) -> FastAPI:
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def _operator_user(*capabilities: str, role: str = "tutor", sub: str = "migration-operator-1") -> dict:
    return {
        "sub": sub,
        "role": role,
        "capabilities": {capability: "granted" for capability in capabilities},
    }


def _manifest(
    *,
    public_id: str = "lesson-migration-1",
    expected_published_version_id=None,
    publish: bool = True,
    explanation: str | None = "Subtract 2 from both sides.",
) -> dict:
    row = {
        "publicLessonId": public_id,
        "title": "Migration lesson",
        "objective": "Solve migration equations.",
        "description": "Imported from approved source material.",
        "subjectId": "math",
        "topicId": "linear-equations",
        "unitId": "unit-linear",
        "gradeLevel": "lower_secondary",
        "difficulty": "standard",
        "estimatedMinutes": 15,
        "language": "neutral",
        "publish": publish,
        "rollbackHint": "restore previous published pointer",
        "exercises": [
            {
                "exerciseId": "exercise-migration-1",
                "prompt": "Solve x + 2 = 7.",
                "answerKey": "x = 5",
                "explanation": explanation,
                "difficulty": "standard",
                "order": 1,
            }
        ],
    }
    if expected_published_version_id is not ...:
        row["expectedPublishedVersionId"] = expected_published_version_id
    return {
        "source": {
            "sourceId": "approved-curriculum-pack",
            "sourceVersion": "2026-07",
            "sourceType": "manifest",
        },
        "operatorNote": "approved import",
        "lessons": [row],
    }


def _install_curriculum_repo(monkeypatch):
    versions: dict[tuple[str, str], dict] = {}
    pointers: dict[str, dict] = {}
    manifests: list[dict] = []
    projections: list[tuple[dict, dict]] = []
    audits: list[tuple[str, dict]] = []
    evidence: dict[str, dict] = {}
    analytics: list[tuple[dict, str]] = []
    repo = curriculum_migration_service.curriculum_ops_repo

    def put_version(item):
        versions[(item["public_id"], item["version_id"])] = dict(item)

    def get_version(public_id, version_id):
        item = versions.get((public_id, version_id))
        return dict(item) if item else None

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
    monkeypatch.setattr(repo, "get_pointer", lambda public_id: dict(pointers.get(public_id, {})))
    monkeypatch.setattr(repo, "set_published_pointer", set_published_pointer)
    monkeypatch.setattr(repo, "put_manifest", lambda item: manifests.append(dict(item)))
    monkeypatch.setattr(
        repo,
        "put_published_projection",
        lambda version, manifest: projections.append((dict(version), dict(manifest))),
    )
    monkeypatch.setattr(repo, "append_audit_event", lambda public_id, event: audits.append((public_id, dict(event))))
    monkeypatch.setattr(repo, "put_migration_evidence", lambda item: evidence.update({item["migration_id"]: dict(item)}))
    monkeypatch.setattr(repo, "get_migration_evidence", lambda migration_id: evidence.get(migration_id))
    monkeypatch.setattr(
        curriculum_migration_service.curriculum_analytics_service,
        "record_publish_event",
        lambda version, operation: analytics.append((dict(version), operation)),
    )
    return {
        "versions": versions,
        "pointers": pointers,
        "manifests": manifests,
        "projections": projections,
        "audits": audits,
        "evidence": evidence,
        "analytics": analytics,
    }


def test_curriculum_migration_dry_run_is_non_mutating(monkeypatch):
    state = _install_curriculum_repo(monkeypatch)
    client = TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.MIGRATION_OPERATOR_CAPABILITY))
    )

    response = client.post("/admin/curriculum/migrations/dry-run", json=_manifest())

    assert response.status_code == 200
    body = response.json()
    assert body["publishReady"] is True
    assert body["summary"] == {"total": 1, "creates": 1, "updates": 0, "skips": 0, "conflicts": 0, "errors": 0}
    assert body["rows"][0]["action"] == "create"
    assert state["versions"] == {}
    assert state["pointers"] == {}
    assert state["projections"] == []
    assert state["evidence"] == {}


def test_curriculum_migration_requires_operator_or_publisher_capability(monkeypatch):
    state = _install_curriculum_repo(monkeypatch)
    ordinary_teacher = TestClient(_app_for_user({"sub": "teacher-1", "role": "teacher"}))
    student_with_capability = TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.MIGRATION_OPERATOR_CAPABILITY, role="student"))
    )

    denied_teacher = ordinary_teacher.post("/admin/curriculum/migrations/dry-run", json=_manifest())
    denied_student = student_with_capability.post("/admin/curriculum/migrations/dry-run", json=_manifest())

    assert denied_teacher.status_code == 403
    assert denied_teacher.json()["detail"]["code"] == "curriculum_capability_required"
    assert denied_student.status_code == 403
    assert state["versions"] == {}


def test_curriculum_migration_apply_writes_content_evidence_and_audit(monkeypatch):
    state = _install_curriculum_repo(monkeypatch)
    client = TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.MIGRATION_OPERATOR_CAPABILITY))
    )
    manifest = _manifest()

    dry_run = client.post("/admin/curriculum/migrations/dry-run", json=manifest).json()
    applied = client.post(
        f"/admin/curriculum/migrations/{dry_run['migrationId']}/apply",
        json={"manifest": manifest, "confirmationToken": dry_run["confirmationToken"]},
    )
    evidence = client.get(f"/admin/curriculum/migrations/{dry_run['migrationId']}")

    assert applied.status_code == 200
    assert applied.json()["status"] == "applied"
    assert applied.json()["idempotent"] is False
    assert state["pointers"]["lesson-migration-1"]["published_version_id"].startswith("lessonv_mig_")
    assert len(state["versions"]) == 1
    assert len(state["projections"]) == 1
    assert len(state["manifests"]) == 1
    assert len(state["audits"]) == 2
    assert state["evidence"][dry_run["migrationId"]]["rows"][0]["rollback"]["newVersionId"].startswith("lessonv_mig_")
    assert state["analytics"][0][1] == "migration_publish"
    assert evidence.status_code == 200
    assert evidence.json()["migrationId"] == dry_run["migrationId"]


def test_curriculum_migration_apply_is_idempotent_after_evidence(monkeypatch):
    state = _install_curriculum_repo(monkeypatch)
    client = TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.MIGRATION_OPERATOR_CAPABILITY))
    )
    manifest = _manifest()
    dry_run = client.post("/admin/curriculum/migrations/dry-run", json=manifest).json()
    payload = {"manifest": manifest, "confirmationToken": dry_run["confirmationToken"]}

    first = client.post(f"/admin/curriculum/migrations/{dry_run['migrationId']}/apply", json=payload)
    second = client.post(f"/admin/curriculum/migrations/{dry_run['migrationId']}/apply", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["idempotent"] is True
    assert len(state["versions"]) == 1
    assert len(state["audits"]) == 2
    assert len(state["evidence"]) == 1


def test_curriculum_migration_apply_requires_confirmation_token(monkeypatch):
    state = _install_curriculum_repo(monkeypatch)
    client = TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.MIGRATION_OPERATOR_CAPABILITY))
    )
    manifest = _manifest()
    dry_run = client.post("/admin/curriculum/migrations/dry-run", json=manifest).json()

    response = client.post(
        f"/admin/curriculum/migrations/{dry_run['migrationId']}/apply",
        json={"manifest": manifest, "confirmationToken": "wrong-token"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "migration_confirmation_mismatch"
    assert state["versions"] == {}


def test_curriculum_migration_reports_conflicts_and_blocks_apply(monkeypatch):
    state = _install_curriculum_repo(monkeypatch)
    state["pointers"]["lesson-migration-1"] = {
        "public_id": "lesson-migration-1",
        "published_version_id": "current-version",
    }
    client = TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.MIGRATION_OPERATOR_CAPABILITY))
    )
    manifest = _manifest(expected_published_version_id="stale-version")

    dry_run = client.post("/admin/curriculum/migrations/dry-run", json=manifest)
    applied = client.post(
        f"/admin/curriculum/migrations/{dry_run.json()['migrationId']}/apply",
        json={"manifest": manifest, "confirmationToken": dry_run.json()["confirmationToken"]},
    )

    assert dry_run.status_code == 200
    assert dry_run.json()["publishReady"] is False
    assert dry_run.json()["summary"]["conflicts"] == 1
    assert dry_run.json()["rows"][0]["conflicts"][0]["code"] == "published_pointer_mismatch"
    assert applied.status_code == 409
    assert state["versions"] == {}


def test_curriculum_migration_reports_validation_failures(monkeypatch):
    state = _install_curriculum_repo(monkeypatch)
    client = TestClient(
        _app_for_user(_operator_user(curriculum_ops_service.MIGRATION_OPERATOR_CAPABILITY))
    )

    response = client.post(
        "/admin/curriculum/migrations/dry-run",
        json=_manifest(explanation=None),
    )

    assert response.status_code == 200
    assert response.json()["publishReady"] is False
    assert response.json()["summary"]["errors"] == 1
    assert response.json()["rows"][0]["validationIssues"][0]["field"] == "exercises[0].explanation"
    assert state["versions"] == {}
