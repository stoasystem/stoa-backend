from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import stat
import zipfile

import pytest


def _load_builder():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "build_lambda_dist.py"
    spec = importlib.util.spec_from_file_location("build_lambda_dist", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_minimal_repo(root: Path) -> None:
    (root / "src" / "stoa" / "jobs").mkdir(parents=True)
    (root / "requirements.txt").write_text("fastapi==0.115.0\n", encoding="utf-8")
    (root / "uv.lock").write_text("version = 1\nrevision = 3\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname = 'stoa-backend'\n", encoding="utf-8")
    (root / "src" / "stoa" / "__init__.py").write_text("", encoding="utf-8")
    (root / "src" / "stoa" / "main.py").write_text("handler = object()\n", encoding="utf-8")
    (root / "src" / "stoa" / "jobs" / "__init__.py").write_text("", encoding="utf-8")
    (root / "src" / "stoa" / "jobs" / "weekly_reports.py").write_text(
        "def handler(event, context):\n    return {'ok': True}\n",
        encoding="utf-8",
    )


def _stub_locked_export(builder, monkeypatch, root: Path) -> None:
    expected = (root / "requirements.txt").read_bytes()
    monkeypatch.setattr(builder, "export_locked_requirements", lambda repo_root: expected)


def test_build_dist_skip_install_writes_verifiable_manifest(tmp_path, monkeypatch):
    builder = _load_builder()
    _write_minimal_repo(tmp_path)
    _stub_locked_export(builder, monkeypatch, tmp_path)

    manifest = builder.build_dist(tmp_path, tmp_path / "dist", skip_install=True)
    verified = builder.validate_manifest(tmp_path, tmp_path / "dist")

    assert manifest["runtime_target"] == "python3.12"
    assert manifest["platform"] == "manylinux2014_aarch64"
    assert manifest["architecture"] == "arm64"
    assert verified["source_tree_hash"] == manifest["source_tree_hash"]
    assert verified["uv_lock_hash"] == builder.sha256_file(tmp_path / "uv.lock")
    assert len(verified["distribution_tree_hash"]) == 64
    assert len(verified["cdk_asset_hash"]) == 64
    assert verified["handler_inventory"]["stoa.main.handler"]["has_attr"] is True
    assert verified["handler_inventory"]["stoa.jobs.weekly_reports.handler"]["has_attr"] is True


def test_validate_manifest_rejects_stale_source(tmp_path, monkeypatch):
    builder = _load_builder()
    _write_minimal_repo(tmp_path)
    _stub_locked_export(builder, monkeypatch, tmp_path)
    builder.build_dist(tmp_path, tmp_path / "dist", skip_install=True)

    (tmp_path / "src" / "stoa" / "main.py").write_text("handler = None\nchanged = True\n", encoding="utf-8")

    try:
        builder.validate_manifest(tmp_path, tmp_path / "dist")
    except builder.DistVerificationError as exc:
        assert "source_tree_hash" in str(exc)
    else:
        raise AssertionError("stale source should fail dist verification")


def test_validate_manifest_rejects_missing_handler(tmp_path, monkeypatch):
    builder = _load_builder()
    _write_minimal_repo(tmp_path)
    _stub_locked_export(builder, monkeypatch, tmp_path)
    builder.build_dist(tmp_path, tmp_path / "dist", skip_install=True)
    (tmp_path / "dist" / "stoa" / "jobs" / "weekly_reports.py").unlink()

    try:
        builder.validate_manifest(tmp_path, tmp_path / "dist")
    except builder.DistVerificationError as exc:
        assert "stoa.jobs.weekly_reports.handler" in str(exc)
    else:
        raise AssertionError("missing handler should fail dist verification")


def test_build_manifest_is_independent_of_wall_clock(tmp_path, monkeypatch):
    builder = _load_builder()
    _write_minimal_repo(tmp_path)
    _stub_locked_export(builder, monkeypatch, tmp_path)
    dist_dir = tmp_path / "dist"
    builder.build_dist(tmp_path, dist_dir, skip_install=True)

    first = builder.build_manifest(tmp_path, dist_dir)
    second = builder.build_manifest(tmp_path, dist_dir)

    assert first == second
    assert "build_time_utc" not in first


def test_requirements_must_equal_fresh_locked_export(tmp_path, monkeypatch):
    builder = _load_builder()
    _write_minimal_repo(tmp_path)
    monkeypatch.setattr(
        builder,
        "export_locked_requirements",
        lambda repo_root: b"fastapi==0.116.0\n",
    )

    with pytest.raises(builder.DistVerificationError, match="locked export"):
        builder.build_dist(tmp_path, tmp_path / "dist", skip_install=True)


def test_locked_export_uses_closed_uv_command(tmp_path, monkeypatch):
    builder = _load_builder()
    _write_minimal_repo(tmp_path)
    observed = {}

    def fake_run(argv, **kwargs):
        observed["argv"] = argv
        observed["kwargs"] = kwargs
        return builder.subprocess.CompletedProcess(argv, 0, stdout=b"fastapi==0.115.0\n", stderr=b"")

    monkeypatch.setattr(builder.subprocess, "run", fake_run)

    assert builder.export_locked_requirements(tmp_path) == b"fastapi==0.115.0\n"
    assert observed["argv"] == [
        "uv",
        "export",
        "--format",
        "requirements-txt",
        "--no-dev",
        "--no-emit-project",
        "--locked",
    ]
    assert observed["kwargs"]["cwd"] == tmp_path
    assert observed["kwargs"]["check"] is True


def test_repeated_normalized_zip_is_byte_identical(tmp_path):
    builder = _load_builder()
    dist = tmp_path / "dist"
    (dist / "pkg").mkdir(parents=True)
    (dist / "pkg" / "b.py").write_text("B = 2\n", encoding="utf-8")
    (dist / "a.py").write_text("A = 1\n", encoding="utf-8")
    first_path = tmp_path / "first.zip"
    second_path = tmp_path / "second.zip"

    first = builder.zip_dist(dist, first_path)
    (dist / "a.py").chmod(0o700)
    (dist / "a.py").touch()
    second = builder.zip_dist(dist, second_path)

    assert first == second
    assert first["sha256"] == builder.sha256_file(first_path)
    assert first_path.read_bytes() == second_path.read_bytes()
    with zipfile.ZipFile(first_path) as archive:
        assert archive.namelist() == ["a.py", "pkg/b.py"]
        for info in archive.infolist():
            assert info.date_time == builder.ZIP_TIMESTAMP
            assert stat.S_IMODE(info.external_attr >> 16) == 0o644


def test_zip_rejects_symlink_and_validates_normalized_archive(tmp_path):
    builder = _load_builder()
    dist = tmp_path / "dist"
    dist.mkdir()
    target = dist / "target.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    (dist / "linked.py").symlink_to(target)

    with pytest.raises(builder.DistVerificationError, match="symlink"):
        builder.zip_dist(dist, tmp_path / "lambda.zip")


def test_distribution_tree_tamper_fails_manifest_validation(tmp_path, monkeypatch):
    builder = _load_builder()
    _write_minimal_repo(tmp_path)
    _stub_locked_export(builder, monkeypatch, tmp_path)
    dist = tmp_path / "dist"
    builder.build_dist(tmp_path, dist, skip_install=True)
    (dist / "stoa" / "__init__.py").write_text("TAMPERED = True\n", encoding="utf-8")

    with pytest.raises(builder.DistVerificationError, match="distribution_tree_hash"):
        builder.validate_manifest(tmp_path, dist)


def test_boot_smoke_isolatedly_imports_exact_handlers(tmp_path):
    builder = _load_builder()
    _write_minimal_repo(tmp_path)
    dist = tmp_path / "dist"
    builder.copy_source(tmp_path, dist)

    result = builder.boot_smoke(dist)

    assert result == {
        "runtime_target": "python3.12",
        "handler_count": 2,
        "status": "PASS",
    }


def test_boot_smoke_rejects_incompatible_runtime_or_import_failure(tmp_path, monkeypatch):
    builder = _load_builder()
    _write_minimal_repo(tmp_path)
    dist = tmp_path / "dist"
    builder.copy_source(tmp_path, dist)

    monkeypatch.setattr(builder, "current_python_version", lambda: "3.13.1")
    with pytest.raises(builder.DistVerificationError, match="Python 3.12"):
        builder.boot_smoke(dist)

    monkeypatch.setattr(builder, "current_python_version", lambda: "3.12.13")
    (dist / "stoa" / "main.py").write_text("raise RuntimeError('private')\n", encoding="utf-8")
    with pytest.raises(builder.DistVerificationError, match="boot smoke failed") as exc:
        builder.boot_smoke(dist)
    assert "private" not in str(exc.value)


def test_archive_identity_detects_changed_zip_bytes(tmp_path):
    builder = _load_builder()
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    archive = tmp_path / "lambda.zip"
    identity = builder.zip_dist(dist, archive)
    receipt = tmp_path / "archive-identity.json"
    receipt.write_text(json.dumps(identity, sort_keys=True), encoding="utf-8")
    archive.write_bytes(archive.read_bytes() + b"tamper")

    with pytest.raises(builder.DistVerificationError, match="archive digest"):
        builder.validate_archive_identity(archive, json.loads(receipt.read_text(encoding="utf-8")))
