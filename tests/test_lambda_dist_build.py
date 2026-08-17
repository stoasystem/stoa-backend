from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
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
    (root / "src" / "stoa" / "main.py").write_text(
        "def handler(event, context):\n    return {'ok': True}\n",
        encoding="utf-8",
    )
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
    assert manifest["platform"] == "manylinux_2_28_aarch64"
    assert manifest["architecture"] == "arm64"
    assert verified["source_tree_hash"] == manifest["source_tree_hash"]
    assert verified["uv_lock_hash"] == builder.sha256_file(tmp_path / "uv.lock")
    assert len(verified["distribution_tree_hash"]) == 64
    assert len(verified["cdk_asset_hash"]) == 64
    assert verified["handler_inventory"]["stoa.main.handler"]["has_attr"] is True
    assert verified["handler_inventory"]["stoa.jobs.weekly_reports.handler"]["has_attr"] is True


def _commit_everything(root: Path) -> None:
    run = lambda *args: subprocess.run(args, cwd=root, check=True, capture_output=True)  # noqa: E731
    run("git", "init", "-q")
    run("git", "add", "-A")
    run(
        "git",
        "-c",
        "user.email=test@stoa.invalid",
        "-c",
        "user.name=test",
        "commit",
        "-q",
        "-m",
        "initial",
    )


def test_zip_written_beside_the_repo_keeps_the_tree_provenance_clean(tmp_path, monkeypatch):
    # The deploy job builds with `--zip lambda.zip` at the repo root, then
    # re-verifies. An unignored archive makes git call the tree dirty, so the
    # freshly computed manifest disagrees with the one written seconds earlier.
    # The shipped ignore rules are copied in so removing the entry fails here.
    builder = _load_builder()
    _write_minimal_repo(tmp_path)
    _stub_locked_export(builder, monkeypatch, tmp_path)
    shutil.copyfile(Path(__file__).resolve().parents[1] / ".gitignore", tmp_path / ".gitignore")
    _commit_everything(tmp_path)
    dist_dir = tmp_path / "dist"

    manifest = builder.build_dist(tmp_path, dist_dir, skip_install=True)
    builder.zip_dist(dist_dir, tmp_path / "lambda.zip")

    assert manifest["source_git_dirty"] is False
    assert builder.validate_manifest(tmp_path, dist_dir)["source_git_dirty"] is False


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


def test_locked_export_accepts_only_uv_output_destination_header_drift(tmp_path, monkeypatch):
    builder = _load_builder()
    _write_minimal_repo(tmp_path)
    body = b"fastapi==0.115.0\n"
    committed = (
        builder.UV_HEADER
        + next(line for line in builder.UV_EXPORT_COMMANDS if b"--output-file" in line)
        + body
    )
    exported = (
        builder.UV_HEADER
        + next(line for line in builder.UV_EXPORT_COMMANDS if b"--output-file" not in line)
        + body
    )
    (tmp_path / "requirements.txt").write_bytes(committed)
    monkeypatch.setattr(builder, "export_locked_requirements", lambda repo_root: exported)

    assert builder.verify_locked_requirements(tmp_path) == exported

    monkeypatch.setattr(
        builder,
        "export_locked_requirements",
        lambda repo_root: b"# generated some other way\n" + body,
    )
    with pytest.raises(builder.DistVerificationError, match="locked export"):
        builder.verify_locked_requirements(tmp_path)


def test_locked_export_mismatch_reports_the_offending_lines(tmp_path, monkeypatch):
    # This verifier also runs inside CDK synth, where nothing but the exception
    # text survives, so the message has to carry the drift itself.
    builder = _load_builder()
    _write_minimal_repo(tmp_path)
    header = builder.UV_HEADER + next(iter(builder.UV_EXPORT_COMMANDS))
    (tmp_path / "requirements.txt").write_bytes(header + b"fastapi==0.115.0\n")
    monkeypatch.setattr(
        builder,
        "export_locked_requirements",
        lambda repo_root: header + b"fastapi==0.136.3\n",
    )

    with pytest.raises(builder.DistVerificationError) as failure:
        builder.verify_locked_requirements(tmp_path)

    detail = str(failure.value)
    assert "-fastapi==0.136.3" in detail
    assert "+fastapi==0.115.0" in detail


def test_locked_export_mismatch_detail_is_bounded(tmp_path, monkeypatch):
    # A full 400-line requirements diff would bury the CDK traceback that
    # follows it.
    builder = _load_builder()
    _write_minimal_repo(tmp_path)
    (tmp_path / "requirements.txt").write_bytes(
        b"".join(f"pkg{index}==1.0.0\n".encode() for index in range(400))
    )
    monkeypatch.setattr(
        builder,
        "export_locked_requirements",
        lambda repo_root: b"".join(f"pkg{index}==2.0.0\n".encode() for index in range(400)),
    )

    with pytest.raises(builder.DistVerificationError) as failure:
        builder.verify_locked_requirements(tmp_path)

    assert len(str(failure.value).splitlines()) <= 26
    assert "truncated" in str(failure.value)


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


def test_locked_export_survives_a_colourising_exporter(tmp_path, monkeypatch):
    # Under CDK synth the exporter wrapped its comment lines in ANSI escapes,
    # which made an unchanged requirements.txt look drifted. Colour is a display
    # concern, so it must not decide provenance.
    builder = _load_builder()
    _write_minimal_repo(tmp_path)
    plain = (
        builder.UV_HEADER
        + next(iter(builder.UV_EXPORT_COMMANDS))
        + b"fastapi==0.115.0 \\\n    --hash=sha256:abc\n    # via stoa\n"
    )
    (tmp_path / "requirements.txt").write_bytes(plain)
    coloured = b"".join(
        b"\x1b[32m" + line.rstrip(b"\n") + b"\x1b[39m\n" if line.lstrip().startswith(b"#") else line
        for line in plain.splitlines(keepends=True)
    )
    assert coloured != plain
    monkeypatch.setattr(
        builder.subprocess,
        "run",
        lambda argv, **kwargs: builder.subprocess.CompletedProcess(argv, 0, stdout=coloured, stderr=b""),
    )

    assert builder.verify_locked_requirements(tmp_path) == plain


def test_locked_export_strips_inherited_colour_forcing(tmp_path, monkeypatch):
    # The CDK CLI exports FORCE_COLOR to the interpreter it spawns for synth. uv
    # honours it by wrapping exported comment lines in ANSI escapes, which made
    # the committed file look drifted only when the check ran under CDK.
    builder = _load_builder()
    _write_minimal_repo(tmp_path)
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.setenv("CLICOLOR_FORCE", "1")
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
    observed = {}

    def fake_run(argv, **kwargs):
        observed["env"] = kwargs["env"]
        return builder.subprocess.CompletedProcess(argv, 0, stdout=b"fastapi==0.115.0\n", stderr=b"")

    monkeypatch.setattr(builder.subprocess, "run", fake_run)
    builder.export_locked_requirements(tmp_path)

    env = observed["env"]
    assert "FORCE_COLOR" not in env
    assert "CLICOLOR_FORCE" not in env
    assert env["NO_COLOR"] == "1"
    # uv still has to be locatable, so the rest of the environment is preserved.
    assert env["PATH"] == os.environ["PATH"]


def test_dependency_install_uses_closed_al2023_arm64_compatibility_ladder(
    tmp_path, monkeypatch
):
    builder = _load_builder()
    observed = {}

    def fake_run(argv, **kwargs):
        observed["argv"] = argv
        observed["kwargs"] = kwargs
        return builder.subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(builder.subprocess, "run", fake_run)

    builder.install_dependencies(tmp_path, tmp_path / "dist")

    platforms = [
        observed["argv"][index + 1]
        for index, argument in enumerate(observed["argv"])
        if argument == "--platform"
    ]
    assert platforms == [
        "manylinux_2_28_aarch64",
        "manylinux_2_27_aarch64",
        "manylinux_2_26_aarch64",
        "manylinux_2_25_aarch64",
        "manylinux_2_24_aarch64",
        "manylinux_2_23_aarch64",
        "manylinux_2_22_aarch64",
        "manylinux_2_21_aarch64",
        "manylinux_2_20_aarch64",
        "manylinux_2_19_aarch64",
        "manylinux_2_18_aarch64",
        "manylinux_2_17_aarch64",
        "manylinux2014_aarch64",
    ]
    assert "manylinux_2_29_aarch64" not in platforms
    assert all(platform.endswith("_aarch64") for platform in platforms)
    assert observed["argv"][0:4] == [
        builder.sys.executable,
        "-m",
        "pip",
        "install",
    ]
    assert observed["argv"][observed["argv"].index("--python-version") + 1] == "3.12"
    assert observed["argv"][observed["argv"].index("--only-binary") + 1] == ":all:"
    assert observed["kwargs"] == {"cwd": tmp_path, "check": True}


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


def test_zip_orders_entries_the_way_the_archive_validator_reads_them(tmp_path):
    builder = _load_builder()
    dist = tmp_path / "dist"
    # Every pip install produces this shape: a package directory beside a longer
    # sibling. "pkg/mod.py" precedes "pkg-1.0.dist-info/RECORD" when Path objects
    # are compared by parts, but follows it in byte order, which is what
    # validate_archive_identity requires.
    (dist / "pkg").mkdir(parents=True)
    (dist / "pkg" / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
    (dist / "pkg-1.0.dist-info").mkdir()
    (dist / "pkg-1.0.dist-info" / "RECORD").write_text("pkg/mod.py,,\n", encoding="utf-8")
    archive_path = tmp_path / "lambda.zip"

    builder.zip_dist(dist, archive_path)

    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
    assert names == ["pkg-1.0.dist-info/RECORD", "pkg/mod.py"]
    assert names == sorted(names)


def test_repeated_builds_from_same_source_and_lock_are_byte_identical(tmp_path, monkeypatch):
    builder = _load_builder()
    _write_minimal_repo(tmp_path)
    _stub_locked_export(builder, monkeypatch, tmp_path)

    first_dist = tmp_path / "first-dist"
    second_dist = tmp_path / "second-dist"
    first_manifest = builder.build_dist(tmp_path, first_dist, skip_install=True)
    second_manifest = builder.build_dist(tmp_path, second_dist, skip_install=True)
    first_zip = tmp_path / "first-build.zip"
    second_zip = tmp_path / "second-build.zip"
    first_identity = builder.zip_dist(first_dist, first_zip)
    second_identity = builder.zip_dist(second_dist, second_zip)

    assert first_manifest == second_manifest
    assert first_identity == second_identity
    assert first_zip.read_bytes() == second_zip.read_bytes()


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
