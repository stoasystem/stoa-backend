from __future__ import annotations

from argparse import Namespace
import importlib.util
from pathlib import Path


def _load_script():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "provision_production_admin.py"
    spec = importlib.util.spec_from_file_location("provision_production_admin", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeTable:
    def __init__(self, existing=None):
        self.existing = existing
        self.put_items = []

    def query(self, **_kwargs):
        return {"Items": [self.existing]} if self.existing else {"Items": []}

    def get_item(self, *, Key):
        for item in self.put_items:
            if item["PK"] == Key["PK"] and item["SK"] == Key["SK"]:
                return {"Item": item}
        return {}

    def put_item(self, *, Item, **_kwargs):
        self.put_items.append(Item)


def test_validate_inputs_requires_explicit_production_confirmation(monkeypatch):
    script = _load_script()
    monkeypatch.setenv("ADMIN_PASSWORD", "Validpass1")
    args = Namespace(
        confirm_production=False,
        password_env="ADMIN_PASSWORD",
        purpose="first_admin",
        incident_reason="initial operator",
    )

    try:
        script.validate_inputs(args)
    except script.ProvisioningError as exc:
        assert "--confirm-production" in str(exc)
    else:
        raise AssertionError("missing production confirmation should fail")


def test_validate_inputs_reads_password_from_named_env(monkeypatch):
    script = _load_script()
    monkeypatch.setenv("ADMIN_PASSWORD", "Validpass1")
    args = Namespace(
        confirm_production=True,
        password_env="ADMIN_PASSWORD",
        purpose="first_admin",
        incident_reason="initial operator",
    )

    assert script.validate_inputs(args) == "Validpass1"


def test_ensure_dynamodb_profile_creates_admin_profile():
    script = _load_script()
    table = FakeTable()

    status = script.ensure_dynamodb_profile(
        table,
        email="admin@example.com",
        name="Admin User",
        update_existing_profile=False,
        dry_run=False,
    )

    assert status == "created"
    assert len(table.put_items) == 1
    item = table.put_items[0]
    assert item["PK"] == f"USER#{item['user_id']}"
    assert item["SK"] == "PROFILE"
    assert item["email"] == "admin@example.com"
    assert item["name"] == "Admin User"
    assert item["role"] == "admin"
    assert item["account_status"] == "active"


def test_ensure_dynamodb_profile_rejects_existing_non_admin_profile():
    script = _load_script()
    table = FakeTable(existing={"user_id": "user-1", "email": "admin@example.com", "role": "parent"})

    try:
        script.ensure_dynamodb_profile(
            table,
            email="admin@example.com",
            name="Admin User",
            update_existing_profile=False,
            dry_run=False,
        )
    except script.ProvisioningError as exc:
        assert "conflicting role" in str(exc)
    else:
        raise AssertionError("existing non-admin profile should fail")

    assert table.put_items == []


def test_validate_inputs_requires_bootstrap_purpose_and_incident_reason(monkeypatch):
    script = _load_script()
    monkeypatch.setenv("ADMIN_PASSWORD", "Validpass1")
    for purpose, reason in [("routine_admin", "change"), ("first_admin", "")]:
        args = Namespace(
            confirm_production=True,
            password_env="ADMIN_PASSWORD",
            purpose=purpose,
            incident_reason=reason,
        )
        try:
            script.validate_inputs(args)
        except script.ProvisioningError:
            pass
        else:
            raise AssertionError("routine or unexplained bootstrap must fail")


def test_bootstrap_dry_run_writes_nothing_and_evidence_is_redacted():
    script = _load_script()
    table = FakeTable()
    status = script.ensure_identity_binding_and_evidence(
        table,
        user_id="admin-1",
        issuer="https://identity.test/primary",
        subject="subject-1",
        purpose="disaster_recovery",
        incident_reason="incident secret detail",
        dry_run=True,
    )
    assert status == "would_reconcile"
    assert table.put_items == []

    status = script.ensure_identity_binding_and_evidence(
        table,
        user_id="admin-1",
        issuer="https://identity.test/primary",
        subject="subject-1",
        purpose="disaster_recovery",
        incident_reason="incident secret detail",
        dry_run=False,
    )
    assert status == "reconciled"
    audit = next(item for item in table.put_items if item["entity_type"] == "security_audit_event")
    assert "email" not in repr(audit).lower()
    assert "incident secret detail" not in repr(audit)
    assert "capabilities" not in audit


def test_引导脚本发得出第一个管理能力(monkeypatch):
    """The genesis the capability system cannot perform on itself.

    Every account-opening endpoint asks for `admin_identity_manager`, and the
    only in-product issuer asks for it too, so a fresh administrator is refused
    everywhere with no path that would ever change it. Production ran for
    months with zero capability rows and every opening answering 403, while the
    suite stayed green because its administrators are built already holding it.
    """
    script = _load_script()
    from stoa.db.repositories import capability_repo

    issued: list[dict] = []
    monkeypatch.setattr(capability_repo, "get_current_grants", lambda *a, **k: [])
    monkeypatch.setattr(
        capability_repo, "current_lineage_generation", lambda *a, **k: 0
    )

    def refusing_like_the_store(**kwargs):
        # The double refuses what the store refuses. The first run of this
        # passed the account fence generation, which is a different number the
        # store rejects -- and a double that accepted anything let it through.
        if kwargs["expected_generation"] != 0:
            raise capability_repo.CapabilityVersionConflict(
                "stale expected capability generation"
            )
        issued.append(kwargs)

    monkeypatch.setattr(capability_repo, "grant_capability", refusing_like_the_store)

    assert script.ensure_identity_manager_grant(FakeTable(), user_id="admin-1") == "issued"
    assert len(issued) == 1
    assert issued[0]["capability"] == capability_repo.ADMIN_IDENTITY_MANAGER
    assert issued[0]["scope"] == "global"
    assert issued[0]["user_id"] == "admin-1"
    assert issued[0]["expected_generation"] == 0


def test_已经持有的管理员不会被重复发放(monkeypatch):
    """Re-running the bootstrap is how anyone checks the first run worked."""
    script = _load_script()
    from stoa.db.repositories import capability_repo

    monkeypatch.setattr(
        capability_repo,
        "get_current_grants",
        lambda *a, **k: [
            {"capability": capability_repo.ADMIN_IDENTITY_MANAGER, "status": "active"}
        ],
    )
    monkeypatch.setattr(
        capability_repo,
        "grant_capability",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("must not reissue")),
    )

    assert script.ensure_identity_manager_grant(FakeTable(), user_id="admin-1") == "present"


def test_产品内的发放入口要求的正是它自己发放的那个能力():
    """Why the step above has to exist at all, asserted rather than remembered.

    If this ever stops holding, the in-product path can bootstrap itself and
    the script's genesis becomes optional. Until then it is load-bearing.
    """
    import inspect

    from stoa.db.repositories import capability_repo
    from stoa.services import privileged_identity_service

    source = inspect.getsource(privileged_identity_service._require_manager)
    assert "ADMIN_IDENTITY_MANAGER" in source
    assert "_require_manager" in inspect.getsource(
        privileged_identity_service.grant_capability
    )
    assert capability_repo.ADMIN_IDENTITY_MANAGER == "admin_identity_manager"


def test_引导流程真的走了那一步():
    """The function existing is not the same as the bootstrap calling it.

    Removing the call from `main` left every other assertion here green, which
    is the same shape of hole this card exists to close.
    """
    import ast
    import inspect

    script = _load_script()
    tree = ast.parse(inspect.getsource(script.main))
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "ensure_identity_manager_grant" in called
