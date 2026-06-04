#!/usr/bin/env python3
"""Build and verify the shared AWS Lambda deployment package directory."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any
import zipfile


MANIFEST_NAME = ".stoa-build-manifest.json"
RUNTIME_TARGET = "python3.12"
PYTHON_VERSION = "3.12"
PLATFORM = "manylinux2014_aarch64"
ARCHITECTURE = "arm64"
EXPECTED_HANDLERS = {
    "stoa.main.handler": "stoa/main.py",
    "stoa.jobs.weekly_reports.handler": "stoa/jobs/weekly_reports.py",
}
HASHED_SOURCE_ROOTS = ("src/stoa",)
HASHED_ROOT_FILES = ("requirements.txt", "pyproject.toml")
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", ".ruff_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


class DistVerificationError(RuntimeError):
    """Raised when a Lambda dist directory cannot be trusted."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _should_hash(path: Path) -> bool:
    return not (
        any(part in EXCLUDED_PARTS for part in path.parts)
        or path.suffix in EXCLUDED_SUFFIXES
        or path.name == ".DS_Store"
    )


def sha256_tree(root: Path, relative_roots: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for relative_root in relative_roots:
        base = root / relative_root
        if not base.exists():
            raise DistVerificationError(f"Missing source path: {relative_root}")
        for path in sorted(p for p in base.rglob("*") if p.is_file() and _should_hash(p)):
            relative = path.relative_to(root).as_posix()
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(sha256_file(path).encode("ascii"))
            digest.update(b"\0")
    return digest.hexdigest()


def git_output(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def git_sha(root: Path) -> str:
    return git_output(root, "rev-parse", "HEAD") or "unknown"


def git_dirty(root: Path) -> bool:
    status = git_output(root, "status", "--porcelain")
    return bool(status)


def handler_inventory(dist_dir: Path) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for handler, relative_file in EXPECTED_HANDLERS.items():
        path = dist_dir / relative_file
        module_attr = handler.rsplit(".", 1)[1]
        exists = path.exists()
        has_attr = False
        if exists:
            source = path.read_text(encoding="utf-8", errors="replace")
            has_attr = f"{module_attr} =" in source or f"def {module_attr}(" in source
        inventory[handler] = {
            "file": relative_file,
            "exists": exists,
            "has_attr": has_attr,
        }
    return inventory


def cdk_asset_hash(manifest: dict[str, Any]) -> str:
    stable_fields = {
        "architecture": manifest["architecture"],
        "expected_handlers": manifest["expected_handlers"],
        "handler_inventory": manifest["handler_inventory"],
        "platform": manifest["platform"],
        "pyproject_hash": manifest["pyproject_hash"],
        "python_version": manifest["python_version"],
        "requirements_hash": manifest["requirements_hash"],
        "runtime_target": manifest["runtime_target"],
        "source_tree_hash": manifest["source_tree_hash"],
    }
    encoded = json.dumps(stable_fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_manifest(
    repo_root: Path,
    dist_dir: Path,
    *,
    build_started_at: str | None = None,
) -> dict[str, Any]:
    requirements_path = repo_root / "requirements.txt"
    pyproject_path = repo_root / "pyproject.toml"
    if not requirements_path.exists():
        raise DistVerificationError("Missing requirements.txt")
    if not pyproject_path.exists():
        raise DistVerificationError("Missing pyproject.toml")

    manifest = {
        "schema_version": 1,
        "project": "stoa-backend",
        "source_git_sha": git_sha(repo_root),
        "source_git_dirty": git_dirty(repo_root),
        "source_tree_hash": sha256_tree(repo_root, HASHED_SOURCE_ROOTS),
        "requirements_hash": sha256_file(requirements_path),
        "pyproject_hash": sha256_file(pyproject_path),
        "runtime_target": RUNTIME_TARGET,
        "python_version": PYTHON_VERSION,
        "platform": PLATFORM,
        "architecture": ARCHITECTURE,
        "build_time_utc": build_started_at
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "expected_handlers": sorted(EXPECTED_HANDLERS),
        "handler_inventory": handler_inventory(dist_dir),
    }
    manifest["cdk_asset_hash"] = cdk_asset_hash(manifest)
    return manifest


def validate_manifest(repo_root: Path, dist_dir: Path) -> dict[str, Any]:
    manifest_path = dist_dir / MANIFEST_NAME
    if not manifest_path.exists():
        raise DistVerificationError(f"Missing Lambda dist manifest: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {
        "schema_version": 1,
        "project": "stoa-backend",
        "runtime_target": RUNTIME_TARGET,
        "python_version": PYTHON_VERSION,
        "platform": PLATFORM,
        "architecture": ARCHITECTURE,
        "source_tree_hash": sha256_tree(repo_root, HASHED_SOURCE_ROOTS),
        "requirements_hash": sha256_file(repo_root / "requirements.txt"),
        "pyproject_hash": sha256_file(repo_root / "pyproject.toml"),
    }
    errors: list[str] = []
    for key, expected_value in expected.items():
        actual_value = manifest.get(key)
        if actual_value != expected_value:
            errors.append(f"{key}: expected {expected_value!r}, found {actual_value!r}")

    inventory = manifest.get("handler_inventory") or {}
    current_inventory = handler_inventory(dist_dir)
    for handler, status in current_inventory.items():
        if not status["exists"]:
            errors.append(f"{handler}: missing dist file {status['file']}")
        if not status["has_attr"]:
            errors.append(f"{handler}: handler attribute missing in {status['file']}")
        recorded = inventory.get(handler) or {}
        if recorded.get("exists") is not True or recorded.get("has_attr") is not True:
            errors.append(f"{handler}: manifest does not record a valid handler")

    expected_asset_hash = cdk_asset_hash(manifest)
    if manifest.get("cdk_asset_hash") != expected_asset_hash:
        errors.append(
            "cdk_asset_hash: expected "
            f"{expected_asset_hash!r}, found {manifest.get('cdk_asset_hash')!r}"
        )

    if errors:
        joined = "\n  - ".join(errors)
        raise DistVerificationError(f"Lambda dist verification failed:\n  - {joined}")
    return manifest


def install_dependencies(repo_root: Path, dist_dir: Path) -> None:
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--platform",
        PLATFORM,
        "--implementation",
        "cp",
        "--python-version",
        PYTHON_VERSION,
        "--only-binary",
        ":all:",
        "--target",
        str(dist_dir),
        "-r",
        str(repo_root / "requirements.txt"),
    ]
    subprocess.run(cmd, cwd=repo_root, check=True)


def copy_source(repo_root: Path, dist_dir: Path) -> None:
    source = repo_root / "src" / "stoa"
    destination = dist_dir / "stoa"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))


def write_manifest(repo_root: Path, dist_dir: Path) -> dict[str, Any]:
    manifest = build_manifest(repo_root, dist_dir)
    manifest_path = dist_dir / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def build_dist(repo_root: Path, dist_dir: Path, *, skip_install: bool = False) -> dict[str, Any]:
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    dist_dir.mkdir(parents=True)
    if not skip_install:
        install_dependencies(repo_root, dist_dir)
    copy_source(repo_root, dist_dir)
    manifest = write_manifest(repo_root, dist_dir)
    validate_manifest(repo_root, dist_dir)
    return manifest


def zip_dist(dist_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(p for p in dist_dir.rglob("*") if p.is_file()):
            archive.write(path, path.relative_to(dist_dir).as_posix())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--dist", type=Path, default=None)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--skip-install", action="store_true")
    parser.add_argument("--zip", type=Path, default=None, help="Optional zip path to create after build")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    dist_dir = (args.dist or repo_root / "dist").resolve()
    try:
        if args.verify_only:
            manifest = validate_manifest(repo_root, dist_dir)
            print(
                "Lambda dist verified: "
                f"sha={manifest['source_git_sha']} "
                f"source_tree_hash={manifest['source_tree_hash'][:12]}"
            )
            return 0
        manifest = build_dist(repo_root, dist_dir, skip_install=args.skip_install)
        if args.zip:
            zip_dist(dist_dir, args.zip.resolve())
        print(
            "Lambda dist built: "
            f"sha={manifest['source_git_sha']} "
            f"source_tree_hash={manifest['source_tree_hash'][:12]}"
        )
        return 0
    except DistVerificationError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
