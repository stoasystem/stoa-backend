"""Regression contract for current-source receipt issuance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
ISSUER = ROOT / "scripts" / "issue_source_ref.py"


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _repository(tmp_path: Path, name: str) -> tuple[Path, str]:
    root = tmp_path / name
    root.mkdir()
    lock_path = "package-lock.json" if name == "frontend" else "uv.lock"
    (root / lock_path).write_text('{"lockfileVersion":3}\n', encoding="utf-8")
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Source Ref Test")
    _git(root, "add", lock_path)
    _git(root, "commit", "-m", "fixture")
    return root, lock_path


def _issue(root: Path, name: str, lock_path: str, output: Path) -> subprocess.CompletedProcess[str]:
    commit = _git(root, "rev-parse", "HEAD")
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    lock_sha256 = hashlib.sha256((root / lock_path).read_bytes()).hexdigest()
    return subprocess.run(
        [
            str(ROOT / ".venv" / "bin" / "python"),
            str(ISSUER),
            "issue",
            "--name",
            name,
            "--root",
            str(root),
            "--expected-commit",
            commit,
            "--expected-tree",
            tree,
            "--expected-lock-sha256",
            lock_sha256,
            "--approval-provenance",
            "project-owner-explicit-codex-instruction",
            "--approval-at",
            "2026-07-31T12:00:00Z",
            "--approval-scope",
            "local-auditable-source-ref-receipts-only",
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_only_the_exact_infra_root_ds_store_is_allowlisted(tmp_path: Path) -> None:
    root, lock_path = _repository(tmp_path, "infra")
    (root / ".DS_Store").write_bytes(b"macos-metadata")
    output = tmp_path / "infra-source-ref.json"

    completed = _issue(root, "infra", lock_path, output)

    assert completed.returncode == 0, completed.stderr
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["name"] == "infra"
    assert receipt["approval"] == {
        "provenance": "project-owner-explicit-codex-instruction",
        "approved_at": "2026-07-31T12:00:00Z",
        "scope": ["local-auditable-source-ref-receipts-only"],
    }


@pytest.mark.parametrize(
    ("name", "path", "tracked_change"),
    [
        ("infra", Path("nested/.DS_Store"), False),
        ("infra", Path("other.txt"), False),
        ("frontend", Path(".DS_Store"), False),
        ("infra", Path("uv.lock"), True),
    ],
)
def test_nested_or_other_untracked_paths_and_tracked_changes_fail_closed(
    tmp_path: Path,
    name: str,
    path: Path,
    tracked_change: bool,
) -> None:
    root, lock_path = _repository(tmp_path, name)
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("drift\n", encoding="utf-8")
    if tracked_change:
        assert path.as_posix() == lock_path
    output = tmp_path / "source-ref.json"

    completed = _issue(root, name, lock_path, output)

    assert completed.returncode == 2
    assert not output.exists()
