#!/usr/bin/env python3
"""Seal one owner-approved source tuple and admit two fixed formal runs."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tomllib
from typing import Any, Mapping, Sequence

try:
    from scripts import release_gate as gate
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    import release_gate as gate  # type: ignore[no-redef]


ROOT = Path(__file__).resolve().parents[1]
HANDOFF_SCHEMA = "stoa.release.source-handoff.v1"
ADMISSION_SCHEMA = "stoa.release.source-handoff-admission.v1"
HANDOFF_PATH = "evidence/phase-474/final-source-handoff.json"
SUMMARY_PATH = (
    ".planning/phases/474-deterministic-verification-and-gated-delivery/"
    "474-93-SUMMARY.md"
)
PRODUCTION_NOT_RUN = {
    "infrastructure": "NOT RUN",
    "deploy": "NOT RUN",
    "smoke": "NOT RUN",
    "rollback": "NOT RUN",
}
PUBLICATION_CHANGES = (
    {"path": HANDOFF_PATH, "status": "A", "mode": "100644"},
    {"path": SUMMARY_PATH, "status": "A", "mode": "100644"},
    {"path": ".planning/ROADMAP.md", "status": "M", "mode": "100644"},
    {"path": ".planning/STATE.md", "status": "M", "mode": "100644"},
)
REPOSITORY_CONTRACTS = (
    ("backend", "uv.lock", "pyproject.toml", "stoa-backend"),
    ("frontend", "package-lock.json", "package.json", "stoa-frontend"),
    ("infra", "uv.lock", "pyproject.toml", "stoa-infra"),
)
NORMALIZATION_POINTERS = (
    "/runtime/clock",
    "/started_at",
    "/ended_at",
    "/receipt_sha256",
    "/children/0/runtime/clock",
    "/children/0/started_at",
    "/children/0/ended_at",
    "/children/0/receipt_sha256",
    "/children/0/result/stdout_sha256",
    "/children/0/result/stderr_sha256",
    "/children/1/runtime/clock",
    "/children/1/started_at",
    "/children/1/ended_at",
    "/children/1/receipt_sha256",
    "/children/1/result/stdout_sha256",
    "/children/1/result/stderr_sha256",
    "/children/1/gate_evidence/receiptSha256",
    *tuple(
        f"/children/1/gate_evidence/steps/{index}/{field}"
        for index in range(5)
        for field in ("stdoutSha256", "stderrSha256")
    ),
)

_HANDOFF_KEYS = {
    "schema",
    "identity_source",
    "repositories",
    "publication_policy",
    "production",
    "tuple_sha256",
}
_REPOSITORY_KEYS = {"name", "commit", "tree", "lock_path", "lock_sha256"}
_POLICY_KEYS = {"path", "status", "mode"}
_GIT_SHA = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_UTC = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?Z"
)
_MAX_HANDOFF_BYTES = 1024 * 1024
_RUN_LOCAL_SENTINEL = "<validated-run-local>"


class HandoffPolicyError(ValueError):
    """The source handoff or formal-run admission contract was rejected."""


def _canonical_value_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise HandoffPolicyError("value is not canonical JSON") from exc


def canonical_json_bytes(value: object) -> bytes:
    """Return the one accepted handoff serialization."""
    return _canonical_value_bytes(value) + b"\n"


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise HandoffPolicyError(f"duplicate JSON field: {key}")
        value[key] = item
    return value


def _reject_nonfinite(value: str) -> None:
    raise HandoffPolicyError(f"non-finite JSON is forbidden: {value}")


def _load_canonical_json_bytes(data: bytes, *, label: str) -> dict[str, Any]:
    if not data or len(data) > _MAX_HANDOFF_BYTES:
        raise HandoffPolicyError(f"{label} size is invalid")
    try:
        value = json.loads(
            data.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except HandoffPolicyError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise HandoffPolicyError(f"{label} is malformed") from exc
    if not isinstance(value, dict):
        raise HandoffPolicyError(f"{label} must be an object")
    if data != canonical_json_bytes(value):
        raise HandoffPolicyError(f"{label} bytes are not canonical")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise HandoffPolicyError(f"{label} fields are not closed")


def _require_sha(value: Any, label: str, *, git_sha: bool = False) -> str:
    pattern = _GIT_SHA if git_sha else _SHA256
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise HandoffPolicyError(f"{label} is malformed")
    return value


def _git_bytes(root: Path, *argv: str, check: bool = True) -> bytes:
    try:
        completed = subprocess.run(
            gate._git_command("-C", str(root.resolve()), *argv),
            check=False,
            capture_output=True,
            env=gate._scrubbed_git_environment(),
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise HandoffPolicyError("immutable Git object command is unavailable") from exc
    if check and completed.returncode:
        raise HandoffPolicyError("required immutable Git object is unavailable")
    return completed.stdout


def _git_text(root: Path, *argv: str) -> str:
    try:
        return _git_bytes(root, *argv).decode("utf-8", errors="strict").rstrip("\n")
    except UnicodeError as exc:
        raise HandoffPolicyError("Git object output is not UTF-8") from exc


def _exact_commit(root: Path, value: Any, label: str) -> str:
    commit = _require_sha(value, label, git_sha=True)
    resolved = _git_text(root, "rev-parse", "--verify", f"{commit}^{{commit}}")
    if resolved != commit:
        raise HandoffPolicyError(f"{label} does not resolve exactly")
    return commit


def _require_complete_object_closure(root: Path, commit: str) -> None:
    if _git_text(root, "rev-parse", "--is-shallow-repository") != "false":
        raise HandoffPolicyError("shallow Git repositories cannot authorize source")
    reachable = _git_bytes(
        root,
        "rev-list",
        "--objects",
        "--missing=print",
        commit,
    )
    if any(line.startswith(b"?") for line in reachable.splitlines()):
        raise HandoffPolicyError("reachable Git object closure is incomplete")


def _commit_headers(root: Path, commit: str) -> tuple[str, tuple[str, ...]]:
    raw = _git_bytes(root, "cat-file", "commit", commit)
    header = raw.split(b"\n\n", 1)[0]
    tree: str | None = None
    parents: list[str] = []
    for line in header.splitlines():
        if line.startswith(b"tree "):
            tree = line[5:].decode("ascii", errors="strict")
        elif line.startswith(b"parent "):
            parents.append(line[7:].decode("ascii", errors="strict"))
    if tree is None or _GIT_SHA.fullmatch(tree) is None:
        raise HandoffPolicyError("commit tree header is malformed")
    if any(_GIT_SHA.fullmatch(parent) is None for parent in parents):
        raise HandoffPolicyError("commit parent header is malformed")
    _git_bytes(root, "cat-file", "-e", f"{tree}^{{tree}}")
    return tree, tuple(parents)


def _tree_entry(root: Path, commit: str, path: str) -> tuple[str, str, str]:
    raw = _git_bytes(root, "ls-tree", "-z", commit, "--", path)
    records = [record for record in raw.split(b"\0") if record]
    if len(records) != 1:
        raise HandoffPolicyError(f"immutable Git path is missing or ambiguous: {path}")
    try:
        metadata, encoded_path = records[0].split(b"\t", 1)
        mode, object_type, oid = metadata.decode("ascii").split(" ")
        decoded_path = encoded_path.decode("utf-8", errors="strict")
    except (ValueError, UnicodeError) as exc:
        raise HandoffPolicyError(f"immutable Git path is malformed: {path}") from exc
    if decoded_path != path or _GIT_SHA.fullmatch(oid) is None:
        raise HandoffPolicyError(f"immutable Git path identity mismatch: {path}")
    return mode, object_type, oid


def _path_exists(root: Path, commit: str, path: str) -> bool:
    return bool(_git_bytes(root, "ls-tree", "-z", commit, "--", path))


def _regular_blob(root: Path, commit: str, path: str) -> tuple[str, bytes]:
    mode, object_type, oid = _tree_entry(root, commit, path)
    if mode != "100644" or object_type != "blob":
        raise HandoffPolicyError(f"immutable Git path is not a regular 100644 blob: {path}")
    data = _git_bytes(root, "cat-file", "blob", oid)
    return oid, data


def _marker_name(name: str, marker_path: str, data: bytes) -> str:
    try:
        if name == "frontend":
            value = json.loads(
                data.decode("utf-8", errors="strict"),
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_nonfinite,
            )
        else:
            value = tomllib.loads(data.decode("utf-8", errors="strict"))
    except HandoffPolicyError:
        raise
    except (UnicodeError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        raise HandoffPolicyError(f"repository marker is malformed: {marker_path}") from exc
    if not isinstance(value, dict):
        raise HandoffPolicyError(f"repository marker is malformed: {marker_path}")
    if name == "frontend":
        marker = value.get("name")
    else:
        project = value.get("project")
        marker = project.get("name") if isinstance(project, dict) else None
    if not isinstance(marker, str):
        raise HandoffPolicyError(f"repository marker is malformed: {marker_path}")
    return marker


def _tuple_sha256(repositories: Sequence[Mapping[str, Any]]) -> str:
    projection = {
        "schema": HANDOFF_SCHEMA,
        "identity_source": "owner-approved-immutable-git-objects",
        "repositories": list(repositories),
    }
    return sha256(_canonical_value_bytes(projection)).hexdigest()


def _verify_immutable_repository(
    row: Mapping[str, Any],
    *,
    root: Path,
    contract: tuple[str, str, str, str],
) -> None:
    name, lock_path, marker_path, marker_name = contract
    _exact_keys(row, _REPOSITORY_KEYS, f"{name} handoff repository")
    if row.get("name") != name or row.get("lock_path") != lock_path:
        raise HandoffPolicyError(f"{name} handoff repository identity is invalid")
    commit = _exact_commit(root, row.get("commit"), f"{name} commit")
    _require_complete_object_closure(root, commit)
    tree, _ = _commit_headers(root, commit)
    if row.get("tree") != tree:
        raise HandoffPolicyError(f"{name} tree identity mismatch")
    _require_sha(row.get("lock_sha256"), f"{name} lock digest")
    _, lock = _regular_blob(root, commit, lock_path)
    if sha256(lock).hexdigest() != row["lock_sha256"]:
        raise HandoffPolicyError(f"{name} lock identity mismatch")
    _, marker = _regular_blob(root, commit, marker_path)
    if _marker_name(name, marker_path, marker) != marker_name:
        raise HandoffPolicyError(f"{name} repository marker mismatch")
    if name == "infra" and _path_exists(root, commit, ".DS_Store"):
        raise HandoffPolicyError("infra .DS_Store cannot be tracked")


def validate_handoff(handoff: Mapping[str, Any], workspace: gate.WorkspaceRoots) -> None:
    """Validate a B/F/I handoff entirely from immutable Git objects."""
    _exact_keys(handoff, _HANDOFF_KEYS, "source handoff")
    if handoff.get("schema") != HANDOFF_SCHEMA:
        raise HandoffPolicyError("source handoff schema is invalid")
    if handoff.get("identity_source") != "owner-approved-immutable-git-objects":
        raise HandoffPolicyError("source handoff identity source is invalid")
    repositories = handoff.get("repositories")
    if not isinstance(repositories, list) or len(repositories) != len(REPOSITORY_CONTRACTS):
        raise HandoffPolicyError("source handoff repositories are incomplete")
    for row, contract in zip(repositories, REPOSITORY_CONTRACTS, strict=True):
        if not isinstance(row, dict):
            raise HandoffPolicyError("source handoff repository is malformed")
        _verify_immutable_repository(
            row,
            root=workspace.require(contract[0]),
            contract=contract,
        )
    policy = handoff.get("publication_policy")
    if not isinstance(policy, list) or len(policy) != len(PUBLICATION_CHANGES):
        raise HandoffPolicyError("source handoff publication policy is incomplete")
    for actual, expected in zip(policy, PUBLICATION_CHANGES, strict=True):
        if not isinstance(actual, dict):
            raise HandoffPolicyError("source handoff publication policy is malformed")
        _exact_keys(actual, _POLICY_KEYS, "source handoff publication change")
        if actual != expected:
            raise HandoffPolicyError("source handoff publication policy mismatch")
    if handoff.get("production") != PRODUCTION_NOT_RUN:
        raise HandoffPolicyError("source handoff production state is invalid")
    _require_sha(handoff.get("tuple_sha256"), "source tuple digest")
    if handoff["tuple_sha256"] != _tuple_sha256(repositories):
        raise HandoffPolicyError("source tuple digest mismatch")

    backend = repositories[0]
    implementation = str(backend["commit"])
    backend_root = workspace.require("backend")
    for change in PUBLICATION_CHANGES:
        path = change["path"]
        exists = _path_exists(backend_root, implementation, path)
        if change["status"] == "A" and exists:
            raise HandoffPolicyError("implementation already contains publication output")
        if change["status"] == "M":
            _regular_blob(backend_root, implementation, path)


def issue_handoff(
    workspace: gate.WorkspaceRoots,
    operations: gate.GateOperations,
) -> dict[str, Any]:
    """Issue a non-self-referential handoff for the exact live B/F/I roots."""
    try:
        candidate = gate.issue_live_candidate(workspace=workspace, operations=operations)
    except gate.GatePolicyError as exc:
        raise HandoffPolicyError("live source tuple is not clean and complete") from exc
    repositories = [
        {
            "name": row["name"],
            "commit": row["head"],
            "tree": row["tree"],
            "lock_path": row["lock_path"],
            "lock_sha256": row["lock_sha256"],
        }
        for row in candidate["repositories"]
    ]
    handoff: dict[str, Any] = {
        "schema": HANDOFF_SCHEMA,
        "identity_source": "owner-approved-immutable-git-objects",
        "repositories": repositories,
        "publication_policy": [dict(change) for change in PUBLICATION_CHANGES],
        "production": dict(PRODUCTION_NOT_RUN),
        "tuple_sha256": _tuple_sha256(repositories),
    }
    validate_handoff(handoff, workspace)
    return handoff


def _publication_diff(root: Path, implementation: str, publication: str) -> dict[str, dict[str, str]]:
    raw = _git_bytes(
        root,
        "diff-tree",
        "--no-commit-id",
        "--raw",
        "-z",
        "--no-renames",
        "-r",
        implementation,
        publication,
    )
    chunks = raw.split(b"\0")
    if chunks and chunks[-1] == b"":
        chunks.pop()
    if len(chunks) % 2:
        raise HandoffPolicyError("publication raw diff is malformed")
    result: dict[str, dict[str, str]] = {}
    pattern = re.compile(
        rb":([0-7]{6}) ([0-7]{6}) ([0-9a-f]{40}) ([0-9a-f]{40}) ([A-Z])"
    )
    for index in range(0, len(chunks), 2):
        match = pattern.fullmatch(chunks[index])
        if match is None:
            raise HandoffPolicyError("publication raw diff entry is malformed")
        try:
            path = chunks[index + 1].decode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise HandoffPolicyError("publication path is not UTF-8") from exc
        if path in result:
            raise HandoffPolicyError("publication path is duplicated")
        old_mode, new_mode, old_oid, new_oid, status_code = (
            item.decode("ascii") for item in match.groups()
        )
        result[path] = {
            "status": status_code,
            "old_mode": old_mode,
            "new_mode": new_mode,
            "old_oid": old_oid,
            "new_oid": new_oid,
        }
    return result


def _is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    try:
        completed = subprocess.run(
            gate._git_command(
                "-C",
                str(root.resolve()),
                "merge-base",
                "--is-ancestor",
                ancestor,
                descendant,
            ),
            check=False,
            capture_output=True,
            env=gate._scrubbed_git_environment(),
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise HandoffPolicyError("publication ancestry is unavailable") from exc
    if completed.returncode not in (0, 1):
        raise HandoffPolicyError("publication ancestry is unverifiable")
    return completed.returncode == 0


def verify_publication(
    publication: str,
    workspace: gate.WorkspaceRoots,
) -> dict[str, Any]:
    """Verify explicit P, derive B/F/I from P, and return the approved handoff."""
    backend_root = workspace.require("backend")
    publication = _exact_commit(backend_root, publication, "publication commit")
    _require_complete_object_closure(backend_root, publication)
    _, parents = _commit_headers(backend_root, publication)
    if len(parents) != 1:
        raise HandoffPolicyError("publication must have exactly one parent")

    handoff_oid, handoff_bytes = _regular_blob(backend_root, publication, HANDOFF_PATH)
    handoff = _load_canonical_json_bytes(handoff_bytes, label="source handoff")
    validate_handoff(handoff, workspace)
    implementation = str(handoff["repositories"][0]["commit"])
    _exact_commit(backend_root, implementation, "implementation commit")
    if parents[0] != implementation:
        raise HandoffPolicyError("publication is not the direct implementation child")

    expected = {change["path"]: change for change in PUBLICATION_CHANGES}
    actual = _publication_diff(backend_root, implementation, publication)
    if set(actual) != set(expected):
        raise HandoffPolicyError("publication changed paths are not exact")
    zero_oid = "0" * 40
    for path, change in expected.items():
        row = actual[path]
        old_mode = "000000" if change["status"] == "A" else "100644"
        old_oid_zero = change["status"] == "A"
        if (
            row["status"] != change["status"]
            or row["old_mode"] != old_mode
            or row["new_mode"] != change["mode"]
            or (row["old_oid"] == zero_oid) is not old_oid_zero
            or row["new_oid"] == zero_oid
        ):
            raise HandoffPolicyError("publication status or mode is invalid")
        oid, _ = _regular_blob(backend_root, publication, path)
        if oid != row["new_oid"]:
            raise HandoffPolicyError("publication blob identity mismatch")

    current_head = _exact_commit(
        backend_root,
        _git_text(backend_root, "rev-parse", "HEAD"),
        "current backend HEAD",
    )
    if not _is_ancestor(backend_root, publication, current_head):
        raise HandoffPolicyError("current HEAD does not descend from publication")
    current_oid, current_bytes = _regular_blob(backend_root, current_head, HANDOFF_PATH)
    if current_oid != handoff_oid or current_bytes != handoff_bytes:
        raise HandoffPolicyError("source handoff changed after publication")
    return {
        "publication": publication,
        "implementation": implementation,
        "handoff_blob_oid": handoff_oid,
        "handoff_blob_sha256": sha256(handoff_bytes).hexdigest(),
        "handoff": handoff,
    }


def _replace_pointer(value: Any, pointer: str) -> None:
    current = value
    tokens = pointer.removeprefix("/").split("/")
    for token in tokens[:-1]:
        if isinstance(current, list):
            try:
                current = current[int(token)]
            except (IndexError, ValueError, TypeError) as exc:
                raise HandoffPolicyError(f"normalization pointer is unavailable: {pointer}") from exc
        elif isinstance(current, dict) and token in current:
            current = current[token]
        else:
            raise HandoffPolicyError(f"normalization pointer is unavailable: {pointer}")
    final = tokens[-1]
    if isinstance(current, list):
        try:
            current[int(final)] = _RUN_LOCAL_SENTINEL
        except (IndexError, ValueError, TypeError) as exc:
            raise HandoffPolicyError(f"normalization pointer is unavailable: {pointer}") from exc
    elif isinstance(current, dict) and final in current:
        current[final] = _RUN_LOCAL_SENTINEL
    else:
        raise HandoffPolicyError(f"normalization pointer is unavailable: {pointer}")


def stable_formal_projection(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Replace only the reviewed run-local JSON pointers in a validated receipt."""
    try:
        projection = deepcopy(dict(receipt))
    except Exception as exc:  # pragma: no cover - defensive for hostile mappings
        raise HandoffPolicyError("formal receipt cannot be frozen") from exc
    for pointer in NORMALIZATION_POINTERS:
        _replace_pointer(projection, pointer)
    return projection


def _parse_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or _UTC.fullmatch(value) is None:
        raise HandoffPolicyError(f"{label} is not canonical UTC")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HandoffPolicyError(f"{label} is not canonical UTC") from exc


def _require_complete_pass(receipt: Mapping[str, Any]) -> None:
    result = receipt.get("result")
    if not isinstance(result, dict) or result != {
        "status": "PASS",
        "classification": "COMPLETE_PASS",
        "exit_code": 0,
        "reason_code": None,
        "obligations": {
            "total": 2,
            "passed": 2,
            "policy_rejected": 0,
            "execution_failed": 0,
            "not_run": 0,
        },
    }:
        raise HandoffPolicyError("formal receipt is not a complete two-child PASS")
    children = receipt.get("children")
    if not isinstance(children, list) or len(children) != 2:
        raise HandoffPolicyError("formal receipt children are incomplete")
    for child in children:
        child_result = child.get("result") if isinstance(child, dict) else None
        if not isinstance(child_result, dict) or (
            child_result.get("status"),
            child_result.get("classification"),
            child_result.get("exit_code"),
            child_result.get("reason_code"),
        ) != ("PASS", "COMPLETE_PASS", 0, None):
            raise HandoffPolicyError("formal child is not PASS")
    if receipt.get("production") != PRODUCTION_NOT_RUN:
        raise HandoffPolicyError("formal production evidence is not exact NOT RUN")


def _validate_candidate_source(
    approved: Mapping[str, Any],
    candidate: Mapping[str, Any],
    workspace: gate.WorkspaceRoots,
    operations: gate.GateOperations,
) -> None:
    try:
        gate.validate_candidate(candidate)
        gate.validate_live_candidate(candidate, workspace=workspace, operations=operations)
    except gate.GatePolicyError as exc:
        raise HandoffPolicyError("candidate is not the exact clean live P/F/I source") from exc
    if (workspace.require("infra") / ".DS_Store").exists():
        raise HandoffPolicyError("admission workspace contains infra .DS_Store")
    candidate_rows = candidate.get("repositories")
    handoff_rows = approved["handoff"]["repositories"]
    if not isinstance(candidate_rows, list) or len(candidate_rows) != 3:
        raise HandoffPolicyError("candidate repositories are incomplete")
    expected_heads = [
        approved["publication"],
        handoff_rows[1]["commit"],
        handoff_rows[2]["commit"],
    ]
    if [row.get("head") for row in candidate_rows] != expected_heads:
        raise HandoffPolicyError("candidate does not use the approved P/F/I tuple")
    publication_tree, _ = _commit_headers(
        workspace.require("backend"), str(approved["publication"])
    )
    if candidate_rows[0].get("tree") != publication_tree:
        raise HandoffPolicyError("candidate backend publication tree mismatch")
    for index, handoff_row in enumerate(handoff_rows):
        candidate_row = candidate_rows[index]
        if (
            candidate_row.get("name") != handoff_row["name"]
            or candidate_row.get("lock_path") != handoff_row["lock_path"]
            or candidate_row.get("lock_sha256") != handoff_row["lock_sha256"]
        ):
            raise HandoffPolicyError("candidate lock or repository identity mismatch")
        if index and candidate_row.get("tree") != handoff_row["tree"]:
            raise HandoffPolicyError("candidate frontend or infra tree mismatch")


def admit_formal_runs(
    publication: str,
    candidate: Mapping[str, Any],
    receipts: Sequence[Mapping[str, Any]],
    workspace: gate.WorkspaceRoots,
    operations: gate.GateOperations,
) -> dict[str, Any]:
    """Admit exactly two fully validated sequential Linux formal PASS receipts."""
    approved = verify_publication(publication, workspace)
    _validate_candidate_source(approved, candidate, workspace, operations)
    if len(receipts) != 2 or any(not isinstance(receipt, dict) for receipt in receipts):
        raise HandoffPolicyError("admission requires exactly two formal receipts")

    frozen = [dict(receipt) for receipt in receipts]
    for receipt in frozen:
        try:
            gate.validate_formal_receipt(
                receipt,
                candidate=candidate,
                registry=gate.default_registry(),
                workspace=workspace,
            )
        except gate.GatePolicyError as exc:
            raise HandoffPolicyError("formal receipt failed complete semantic validation") from exc
        _require_complete_pass(receipt)

    digests = [_require_sha(receipt.get("receipt_sha256"), "formal receipt digest") for receipt in frozen]
    if digests[0] == digests[1]:
        raise HandoffPolicyError("formal receipts are not distinct")
    runtimes = [receipt.get("runtime") for receipt in frozen]
    if any(not isinstance(runtime, dict) for runtime in runtimes):
        raise HandoffPolicyError("formal runtime identity is malformed")
    platforms = [runtime.get("platform") for runtime in runtimes]
    if platforms[0] != platforms[1] or platforms[0] not in {
        "linux-aarch64",
        "linux-x86_64",
    }:
        raise HandoffPolicyError("formal receipts are not on one approved Linux platform")
    if any(runtime.get("python") != "3.12.13" for runtime in runtimes):
        raise HandoffPolicyError("formal receipts do not use Python 3.12.13")

    starts = [_parse_utc(receipt.get("started_at"), "formal start") for receipt in frozen]
    ends = [_parse_utc(receipt.get("ended_at"), "formal end") for receipt in frozen]
    if ends[0] > starts[1]:
        raise HandoffPolicyError("formal receipt windows overlap or are out of order")

    projections = [stable_formal_projection(receipt) for receipt in frozen]
    projection_bytes = [_canonical_value_bytes(projection) for projection in projections]
    if projection_bytes[0] != projection_bytes[1]:
        raise HandoffPolicyError("formal receipt semantic projections differ")
    stable_digest = sha256(projection_bytes[0]).hexdigest()
    admission: dict[str, Any] = {
        "schema": ADMISSION_SCHEMA,
        "status": "PASS",
        "publication": {
            "commit": approved["publication"],
            "parent": approved["implementation"],
            "handoff_blob_oid": approved["handoff_blob_oid"],
            "handoff_blob_sha256": approved["handoff_blob_sha256"],
        },
        "approved_source": {
            "tuple_sha256": approved["handoff"]["tuple_sha256"],
            "repositories": deepcopy(approved["handoff"]["repositories"]),
        },
        "candidate_source": {
            "candidate_identity": candidate["execution_identity"],
            "repositories": deepcopy(candidate["repositories"]),
        },
        "formal_receipts": [
            {
                "sequence": index,
                "receipt_sha256": receipt["receipt_sha256"],
                "started_at": receipt["started_at"],
                "ended_at": receipt["ended_at"],
                "stable_sha256": stable_digest,
            }
            for index, receipt in enumerate(frozen, start=1)
        ],
        "normalization": {
            "method": "fixed-json-pointer-replacement-v1",
            "pointers": list(NORMALIZATION_POINTERS),
            "canonical_sha256": stable_digest,
        },
        "production": dict(PRODUCTION_NOT_RUN),
    }
    admission["admission_sha256"] = sha256(_canonical_value_bytes(admission)).hexdigest()
    return admission


def _workspace(args: argparse.Namespace) -> gate.WorkspaceRoots:
    return gate.WorkspaceRoots.from_mapping(
        {
            "backend": Path(args.backend_root),
            "frontend": Path(args.frontend_root),
            "infra": Path(args.infra_root),
        }
    )


def _load_private_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_absolute() or path.name in {"", ".", ".."}:
        raise HandoffPolicyError(f"{label} path must be absolute")
    parent_descriptor = -1
    descriptor = -1
    try:
        parent = path.parent.resolve(strict=True)
        if path.parent.is_symlink():
            raise HandoffPolicyError(f"{label} parent cannot be a symlink")
        parent_descriptor = os.open(
            parent,
            os.O_RDONLY
            | os.O_DIRECTORY
            | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0),
        )
        parent_metadata = os.fstat(parent_descriptor)
        descriptor = os.open(
            path.name,
            os.O_RDONLY
            | os.O_NONBLOCK
            | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_descriptor,
        )
        metadata = os.fstat(descriptor)
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        if parent_descriptor >= 0:
            os.close(parent_descriptor)
        raise HandoffPolicyError(f"{label} file is unavailable") from exc
    if (
        not stat.S_ISDIR(parent_metadata.st_mode)
        or stat.S_IMODE(parent_metadata.st_mode) != 0o700
        or parent_metadata.st_uid != os.getuid()
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_uid != os.getuid()
        or metadata.st_nlink != 1
        or metadata.st_size < 2
        or metadata.st_size > 16 * 1024 * 1024
    ):
        os.close(descriptor)
        os.close(parent_descriptor)
        raise HandoffPolicyError(f"{label} file is not private and regular")
    try:
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                raise HandoffPolicyError(f"{label} file read was incomplete")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise HandoffPolicyError(f"{label} file grew while read")
        final_metadata = os.fstat(descriptor)
        final_parent = os.fstat(parent_descriptor)
        final_path = os.stat(
            path.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not gate._same_file_metadata(final_metadata, metadata)
            or not gate._same_file_metadata(final_path, metadata)
            or not gate._same_file_metadata(final_parent, parent_metadata)
        ):
            raise HandoffPolicyError(f"{label} file changed while read")
        data = b"".join(chunks)
    except OSError as exc:
        raise HandoffPolicyError(f"{label} file changed while read") from exc
    finally:
        os.close(descriptor)
        os.close(parent_descriptor)
    try:
        value = json.loads(
            data.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except HandoffPolicyError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise HandoffPolicyError(f"{label} JSON is malformed") from exc
    if not isinstance(value, dict):
        raise HandoffPolicyError(f"{label} JSON must be an object")
    expected = (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    if data != expected:
        raise HandoffPolicyError(f"{label} JSON bytes are not canonical")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("issue", "verify-publication", "admit"):
        child = subparsers.add_parser(command, allow_abbrev=False)
        for name in ("backend-root", "frontend-root", "infra-root"):
            child.add_argument(f"--{name}", required=True)
        if command != "issue":
            child.add_argument("--publication", required=True)
        if command == "admit":
            child.add_argument("--candidate", required=True)
            child.add_argument("--receipt-1", required=True)
            child.add_argument("--receipt-2", required=True)
            child.add_argument("--output", required=True)
    return parser


def _execute(args: argparse.Namespace) -> int:
    workspace = _workspace(args)
    operations = gate.system_operations()
    if args.command == "issue":
        sys.stdout.buffer.write(canonical_json_bytes(issue_handoff(workspace, operations)))
        return 0
    if args.command == "verify-publication":
        approved = verify_publication(args.publication, workspace)
        sys.stdout.buffer.write(canonical_json_bytes(approved))
        return 0
    candidate = _load_private_json(Path(args.candidate), label="candidate")
    input_paths = (
        Path(args.candidate),
        Path(args.receipt_1),
        Path(args.receipt_2),
    )
    resolved_inputs = tuple(
        path.parent.resolve(strict=True) / path.name for path in input_paths
    )
    if len(set(resolved_inputs)) != len(resolved_inputs):
        raise HandoffPolicyError("candidate and formal receipt files must be distinct")
    receipts = (
        _load_private_json(input_paths[1], label="formal receipt 1"),
        _load_private_json(input_paths[2], label="formal receipt 2"),
    )
    admission = admit_formal_runs(
        args.publication,
        candidate,
        receipts,
        workspace,
        operations,
    )
    output = Path(args.output)
    resolved_output = output.resolve(strict=False)
    if not output.is_absolute() or any(
        resolved_output == root or root in resolved_output.parents
        for _, root in workspace.roots
    ) or resolved_output in resolved_inputs:
        raise HandoffPolicyError("admission output must be absolute and source-external")

    def revalidate() -> None:
        if (
            admit_formal_runs(
                args.publication,
                candidate,
                receipts,
                workspace,
                operations,
            )
            != admission
        ):
            raise HandoffPolicyError("admission changed before publication")

    gate.publish_formal_receipt(admission, output, before_replace=revalidate)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _execute(args)
    except (HandoffPolicyError, gate.GatePolicyError):
        return gate.POLICY_EXIT
    except Exception:
        return gate.EXECUTION_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
