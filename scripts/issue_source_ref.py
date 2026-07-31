"""Issue one owner-approved, fail-closed current-source receipt."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Final


SOURCE_REF_SCHEMA: Final = "stoa.release.source-ref.v1"
_SHA40: Final = re.compile(r"^[0-9a-f]{40}$")
_SHA256: Final = re.compile(r"^[0-9a-f]{64}$")
_APPROVAL_TOKEN: Final = re.compile(r"^[a-z0-9][a-z0-9-]{2,127}$")
_ROOT_METADATA: Final = ".DS_Store"


class SourceRefPolicyError(ValueError):
    """Raised when a repository cannot provide one exact current source ref."""


def _required_lock_path(name: str) -> str:
    if name == "frontend":
        return "package-lock.json"
    if name == "infra":
        return "uv.lock"
    raise SourceRefPolicyError("source repository name is not recognized")


def _require_sha(value: str, label: str, pattern: re.Pattern[str]) -> str:
    if pattern.fullmatch(value) is None:
        raise SourceRefPolicyError(f"{label} is not an exact lowercase digest")
    return value


def _require_approval_time(value: str) -> str:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise SourceRefPolicyError("approval time must be canonical UTC") from error
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise SourceRefPolicyError("approval time must be canonical UTC")
    return value


def _require_approval_tokens(values: list[str]) -> list[str]:
    if not values or len(values) != len(set(values)):
        raise SourceRefPolicyError("approval scope must be non-empty and unique")
    if any(_APPROVAL_TOKEN.fullmatch(value) is None for value in values):
        raise SourceRefPolicyError("approval scope contains an invalid token")
    return values


def _repository_root(value: Path) -> Path:
    if not value.is_absolute() or value.is_symlink():
        raise SourceRefPolicyError("repository root must be an absolute non-symlink directory")
    try:
        root = value.resolve(strict=True)
    except OSError as error:
        raise SourceRefPolicyError("repository root is unavailable") from error
    if not root.is_dir() or not (root / ".git").exists():
        raise SourceRefPolicyError("repository root is not a Git worktree")
    return root


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise SourceRefPolicyError("Git source identity is unavailable")
    return completed.stdout.strip()


def _allowlisted_metadata_only(root: Path, name: str, lines: list[str]) -> bool:
    if name != "infra" or lines != [f"?? {_ROOT_METADATA}"]:
        return False
    metadata = root / _ROOT_METADATA
    try:
        metadata_stat = metadata.lstat()
    except OSError:
        return False
    return stat.S_ISREG(metadata_stat.st_mode) and not stat.S_ISLNK(metadata_stat.st_mode)


def _require_clean_source_worktree(root: Path, name: str) -> None:
    lines = _git(root, "status", "--porcelain=v1", "--untracked-files=all").splitlines()
    if not lines or _allowlisted_metadata_only(root, name, lines):
        return
    raise SourceRefPolicyError("source worktree has tracked or non-allowlisted untracked drift")


def _sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise SourceRefPolicyError("source lock file is unavailable") from error


def issue_source_ref(
    *,
    name: str,
    root: Path,
    expected_commit: str,
    expected_tree: str,
    expected_lock_sha256: str,
    approval_provenance: str,
    approval_at: str,
    approval_scope: list[str],
) -> dict[str, object]:
    """Validate one exact worktree and return its minimal source-bound receipt."""

    lock_path = _required_lock_path(name)
    checked_root = _repository_root(root)
    expected_commit = _require_sha(expected_commit, "expected commit", _SHA40)
    expected_tree = _require_sha(expected_tree, "expected tree", _SHA40)
    expected_lock_sha256 = _require_sha(expected_lock_sha256, "expected lock SHA-256", _SHA256)
    if _APPROVAL_TOKEN.fullmatch(approval_provenance) is None:
        raise SourceRefPolicyError("approval provenance is invalid")
    approval_at = _require_approval_time(approval_at)
    approval_scope = _require_approval_tokens(approval_scope)

    _require_clean_source_worktree(checked_root, name)
    if _git(checked_root, "rev-parse", "HEAD") != expected_commit:
        raise SourceRefPolicyError("source commit drifts from approved coordinate")
    if _git(checked_root, "rev-parse", "HEAD^{tree}") != expected_tree:
        raise SourceRefPolicyError("source tree drifts from approved coordinate")
    if _sha256_file(checked_root / lock_path) != expected_lock_sha256:
        raise SourceRefPolicyError("source lock drifts from approved coordinate")

    return {
        "schema": SOURCE_REF_SCHEMA,
        "name": name,
        "commit": expected_commit,
        "tree": expected_tree,
        "lock_path": lock_path,
        "lock_sha256": expected_lock_sha256,
        "approval": {
            "provenance": approval_provenance,
            "approved_at": approval_at,
            "scope": approval_scope,
        },
    }


def _write_receipt(path: Path, receipt: dict[str, object]) -> None:
    if not path.is_absolute() or path.exists() or path.is_symlink() or not path.parent.is_dir():
        raise SourceRefPolicyError("source-ref output must be a new absolute regular path")
    path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    issue = commands.add_parser("issue")
    issue.add_argument("--name", required=True, choices=("frontend", "infra"))
    issue.add_argument("--root", required=True, type=Path)
    issue.add_argument("--expected-commit", required=True)
    issue.add_argument("--expected-tree", required=True)
    issue.add_argument("--expected-lock-sha256", required=True)
    issue.add_argument("--approval-provenance", required=True)
    issue.add_argument("--approval-at", required=True)
    issue.add_argument("--approval-scope", required=True, action="append")
    issue.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = issue_source_ref(
            name=args.name,
            root=args.root,
            expected_commit=args.expected_commit,
            expected_tree=args.expected_tree,
            expected_lock_sha256=args.expected_lock_sha256,
            approval_provenance=args.approval_provenance,
            approval_at=args.approval_at,
            approval_scope=args.approval_scope,
        )
        _write_receipt(args.output, receipt)
        return 0
    except SourceRefPolicyError as error:
        print(f"source-ref: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
