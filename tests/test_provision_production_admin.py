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

    def put_item(self, *, Item):
        self.put_items.append(Item)


def test_validate_inputs_requires_explicit_production_confirmation(monkeypatch):
    script = _load_script()
    monkeypatch.setenv("ADMIN_PASSWORD", "Validpass1")
    args = Namespace(confirm_production=False, password_env="ADMIN_PASSWORD")

    try:
        script.validate_inputs(args)
    except script.ProvisioningError as exc:
        assert "--confirm-production" in str(exc)
    else:
        raise AssertionError("missing production confirmation should fail")


def test_validate_inputs_reads_password_from_named_env(monkeypatch):
    script = _load_script()
    monkeypatch.setenv("ADMIN_PASSWORD", "Validpass1")
    args = Namespace(confirm_production=True, password_env="ADMIN_PASSWORD")

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
        assert "role='parent'" in str(exc)
    else:
        raise AssertionError("existing non-admin profile should fail")

    assert table.put_items == []
