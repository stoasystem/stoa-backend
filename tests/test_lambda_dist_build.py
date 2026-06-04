from __future__ import annotations

import importlib.util
from pathlib import Path


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
    (root / "pyproject.toml").write_text("[project]\nname = 'stoa-backend'\n", encoding="utf-8")
    (root / "src" / "stoa" / "__init__.py").write_text("", encoding="utf-8")
    (root / "src" / "stoa" / "main.py").write_text("handler = object()\n", encoding="utf-8")
    (root / "src" / "stoa" / "jobs" / "__init__.py").write_text("", encoding="utf-8")
    (root / "src" / "stoa" / "jobs" / "weekly_reports.py").write_text(
        "def handler(event, context):\n    return {'ok': True}\n",
        encoding="utf-8",
    )


def test_build_dist_skip_install_writes_verifiable_manifest(tmp_path):
    builder = _load_builder()
    _write_minimal_repo(tmp_path)

    manifest = builder.build_dist(tmp_path, tmp_path / "dist", skip_install=True)
    verified = builder.validate_manifest(tmp_path, tmp_path / "dist")

    assert manifest["runtime_target"] == "python3.12"
    assert manifest["platform"] == "manylinux2014_aarch64"
    assert manifest["architecture"] == "arm64"
    assert verified["source_tree_hash"] == manifest["source_tree_hash"]
    assert len(verified["cdk_asset_hash"]) == 64
    assert verified["handler_inventory"]["stoa.main.handler"]["has_attr"] is True
    assert verified["handler_inventory"]["stoa.jobs.weekly_reports.handler"]["has_attr"] is True


def test_validate_manifest_rejects_stale_source(tmp_path):
    builder = _load_builder()
    _write_minimal_repo(tmp_path)
    builder.build_dist(tmp_path, tmp_path / "dist", skip_install=True)

    (tmp_path / "src" / "stoa" / "main.py").write_text("handler = None\nchanged = True\n", encoding="utf-8")

    try:
        builder.validate_manifest(tmp_path, tmp_path / "dist")
    except builder.DistVerificationError as exc:
        assert "source_tree_hash" in str(exc)
    else:
        raise AssertionError("stale source should fail dist verification")


def test_validate_manifest_rejects_missing_handler(tmp_path):
    builder = _load_builder()
    _write_minimal_repo(tmp_path)
    builder.build_dist(tmp_path, tmp_path / "dist", skip_install=True)
    (tmp_path / "dist" / "stoa" / "jobs" / "weekly_reports.py").unlink()

    try:
        builder.validate_manifest(tmp_path, tmp_path / "dist")
    except builder.DistVerificationError as exc:
        assert "stoa.jobs.weekly_reports.handler" in str(exc)
    else:
        raise AssertionError("missing handler should fail dist verification")


def test_cdk_asset_hash_ignores_build_time(tmp_path):
    builder = _load_builder()
    _write_minimal_repo(tmp_path)
    dist_dir = tmp_path / "dist"
    builder.build_dist(tmp_path, dist_dir, skip_install=True)

    first = builder.build_manifest(tmp_path, dist_dir, build_started_at="2026-06-04T00:00:00+00:00")
    second = builder.build_manifest(tmp_path, dist_dir, build_started_at="2026-06-04T01:00:00+00:00")

    assert first["build_time_utc"] != second["build_time_utc"]
    assert first["cdk_asset_hash"] == second["cdk_asset_hash"]
