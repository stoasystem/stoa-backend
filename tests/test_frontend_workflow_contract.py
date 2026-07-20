"""Closed contract for the frontend formal-release workflow caller."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
import subprocess
from typing import Any

import pytest
import yaml


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _resolve_frontend_root(backend_root: Path) -> Path:
    matches: list[Path] = []
    for name in ("stoa-frontend", "frontend"):
        candidate = backend_root.parent / name
        marker = candidate / "package.json"
        if (
            candidate.is_symlink()
            or not candidate.is_dir()
            or marker.is_symlink()
            or not marker.is_file()
        ):
            continue
        try:
            manifest = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(manifest, dict) and manifest.get("name") == "stoa-frontend":
            matches.append(candidate)
    if len(matches) != 1:
        raise RuntimeError("exactly one canonical frontend repository root is required")
    return matches[0]


FRONTEND_ROOT = _resolve_frontend_root(BACKEND_ROOT)
WORKFLOW_DIR = FRONTEND_ROOT / ".github" / "workflows"
WORKFLOW_PATH = WORKFLOW_DIR / "frontend-ci.yml"

CHECKOUT_ACTION = "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd"
PYTHON_ACTION = "actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405"
UV_ACTION = "astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b"


class WorkflowLoader(yaml.SafeLoader):
    """YAML loader with Actions-compatible booleans and no duplicate keys."""


for first_character, resolvers in deepcopy(WorkflowLoader.yaml_implicit_resolvers).items():
    WorkflowLoader.yaml_implicit_resolvers[first_character] = [
        resolver for resolver in resolvers if resolver[0] != "tag:yaml.org,2002:bool"
    ]

WorkflowLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|false)$"),
    list("tf"),
)


def _construct_mapping(
    loader: WorkflowLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[str, Any]:
    loader.flatten_mapping(node)
    result: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise yaml.constructor.ConstructorError(
                "while constructing a workflow mapping",
                node.start_mark,
                "workflow mapping keys must be strings",
                key_node.start_mark,
            )
        if key in result:
            raise yaml.constructor.ConstructorError(
                "while constructing a workflow mapping",
                node.start_mark,
                f"duplicate key: {key}",
                key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


WorkflowLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _validation_run() -> str:
    return (
        "set -euo pipefail\n"
        "sha_pattern='^[0-9a-f]{40}$'\n"
        'for sha in "$BACKEND_SHA" "$FRONTEND_SHA" "$INFRA_SHA" "$WORKFLOW_SHA"; do\n'
        '  [[ "$sha" =~ $sha_pattern ]] || exit 1\n'
        "done\n"
        '[[ "$FRONTEND_SHA" == "$WORKFLOW_SHA" ]]\n'
    )


def _identity_run() -> str:
    return (
        "set -euo pipefail\n"
        'test "$(git -C "$GITHUB_WORKSPACE/stoa-backend" rev-parse HEAD)" '
        '= "$BACKEND_SHA"\n'
        'test "$(git -C "$GITHUB_WORKSPACE/stoa-frontend" rev-parse HEAD)" '
        '= "$FRONTEND_SHA"\n'
        'test "$(git -C "$GITHUB_WORKSPACE/stoa-infra" rev-parse HEAD)" '
        '= "$INFRA_SHA"\n'
    )


def _namespace_run() -> str:
    return (
        "set -euo pipefail\n"
        "if [[ -e /proc/sys/kernel/apparmor_restrict_unprivileged_userns ]]; then\n"
        "  sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0\n"
        "fi\n"
        "if [[ -e /proc/sys/kernel/unprivileged_userns_clone ]]; then\n"
        "  sudo sysctl -w kernel.unprivileged_userns_clone=1\n"
        "fi\n"
        "/usr/bin/unshare --user --map-root-user --net -- true\n"
        "/usr/bin/unshare --user --map-root-user --pid --fork --mount-proc \\\n"
        "  --kill-child=SIGKILL -- /usr/bin/dash -c 'test \"$$\" -eq 1'\n"
    )


def _evidence_run() -> str:
    return (
        "set -euo pipefail\n"
        "umask 077\n"
        'evidence_dir="$(mktemp -d "$RUNNER_TEMP/stoa-formal-evidence.XXXXXX")"\n'
        'chmod 0700 "$evidence_dir"\n'
        'test "$(stat -c %a "$evidence_dir")" = "700"\n'
        "printf 'EVIDENCE_DIR=%s\\n' \"$evidence_dir\" >> \"$GITHUB_ENV\"\n"
    )


def _candidate_run() -> str:
    return (
        "set -euo pipefail\n"
        "python scripts/release_gate.py candidate \\\n"
        '  --backend-root "$GITHUB_WORKSPACE/stoa-backend" \\\n'
        '  --frontend-root "$GITHUB_WORKSPACE/stoa-frontend" \\\n'
        '  --infra-root "$GITHUB_WORKSPACE/stoa-infra" \\\n'
        '  --output "$EVIDENCE_DIR/candidate.json"\n'
    )


def _formal_run() -> str:
    return (
        "set -euo pipefail\n"
        "python scripts/release_gate.py formal \\\n"
        '  --candidate "$EVIDENCE_DIR/candidate.json" \\\n'
        '  --backend-root "$GITHUB_WORKSPACE/stoa-backend" \\\n'
        '  --frontend-root "$GITHUB_WORKSPACE/stoa-frontend" \\\n'
        '  --infra-root "$GITHUB_WORKSPACE/stoa-infra" \\\n'
        '  --output "$EVIDENCE_DIR/formal.json"\n'
    )


def _checkout(component: str, repository: str) -> dict[str, Any]:
    return {
        "name": f"Check out {component}",
        "uses": CHECKOUT_ACTION,
        "with": {
            "repository": repository,
            "ref": f"${{{{ inputs.{component}_sha }}}}",
            "path": f"stoa-{component}",
            "fetch-depth": 1,
            "persist-credentials": False,
        },
    }


def _expected_workflow() -> dict[str, Any]:
    inputs = {
        component: {
            "description": f"Exact {component.removesuffix('_sha')} commit SHA",
            "required": True,
            "type": "string",
        }
        for component in ("backend_sha", "frontend_sha", "infra_sha")
    }
    steps = [
        {
            "name": "Validate immutable source refs",
            "shell": "bash",
            "env": {
                "BACKEND_SHA": "${{ inputs.backend_sha }}",
                "FRONTEND_SHA": "${{ inputs.frontend_sha }}",
                "INFRA_SHA": "${{ inputs.infra_sha }}",
                "WORKFLOW_SHA": "${{ github.sha }}",
            },
            "run": _validation_run(),
        },
        _checkout("backend", "stoasystem/stoa-backend"),
        _checkout("frontend", "stoasystem/stoa-frontend"),
        _checkout("infra", "stoasystem/stoa-infra"),
        {
            "name": "Set up Python",
            "uses": PYTHON_ACTION,
            "with": {"python-version": "3.12.13"},
        },
        {
            "name": "Set up uv",
            "uses": UV_ACTION,
            "with": {"version": "0.11.16", "enable-cache": False},
        },
        {
            "name": "Verify checkout identities",
            "shell": "bash",
            "env": {
                "BACKEND_SHA": "${{ inputs.backend_sha }}",
                "FRONTEND_SHA": "${{ inputs.frontend_sha }}",
                "INFRA_SHA": "${{ inputs.infra_sha }}",
            },
            "run": _identity_run(),
        },
        {
            "name": "Prepare and prove Linux namespaces",
            "shell": "bash",
            "run": _namespace_run(),
        },
        {
            "name": "Create private evidence directory",
            "shell": "bash",
            "run": _evidence_run(),
        },
        {
            "name": "Issue release candidate",
            "working-directory": "stoa-backend",
            "shell": "bash",
            "run": _candidate_run(),
        },
        {
            "name": "Run fixed formal aggregate",
            "working-directory": "stoa-backend",
            "shell": "bash",
            "run": _formal_run(),
        },
    ]
    return {
        "name": "Formal Release Verification",
        "on": {"workflow_dispatch": {"inputs": inputs}},
        "permissions": {"contents": "read"},
        "env": {"UV_PYTHON_DOWNLOADS": "never"},
        "jobs": {
            "formal": {
                "name": "Fixed formal candidate verification",
                "runs-on": "ubuntu-24.04",
                "timeout-minutes": 180,
                "steps": steps,
            }
        },
    }


def _load_workflow() -> tuple[str, dict[str, Any]]:
    raw = WORKFLOW_PATH.read_text(encoding="utf-8")
    value = yaml.load(raw, Loader=WorkflowLoader)
    assert isinstance(value, dict)
    return raw, value


def test_loader_rejects_duplicate_workflow_keys() -> None:
    with pytest.raises(yaml.constructor.ConstructorError, match="duplicate key: permissions"):
        yaml.load("permissions: {}\npermissions: {}\n", Loader=WorkflowLoader)


@pytest.mark.parametrize("name", ["stoa-frontend", "frontend"])
def test_frontend_root_resolution_supports_only_canonical_layouts(
    tmp_path: Path,
    name: str,
) -> None:
    backend = tmp_path / "backend-root"
    backend.mkdir()
    frontend = tmp_path / name
    frontend.mkdir()
    (frontend / "package.json").write_text(
        json.dumps({"name": "stoa-frontend"}),
        encoding="utf-8",
    )

    assert _resolve_frontend_root(backend) == frontend


def test_frontend_root_resolution_rejects_zero_multiple_and_symlink_matches(
    tmp_path: Path,
) -> None:
    backend = tmp_path / "backend-root"
    backend.mkdir()
    with pytest.raises(RuntimeError, match="exactly one"):
        _resolve_frontend_root(backend)

    canonical = tmp_path / "frontend"
    canonical.mkdir()
    (canonical / "package.json").write_text(
        json.dumps({"name": "wrong-project"}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="exactly one"):
        _resolve_frontend_root(backend)

    (canonical / "package.json").write_text(
        json.dumps({"name": "stoa-frontend"}),
        encoding="utf-8",
    )
    second = tmp_path / "stoa-frontend"
    second.mkdir()
    (second / "package.json").write_text(
        json.dumps({"name": "stoa-frontend"}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="exactly one"):
        _resolve_frontend_root(backend)

    for path in (canonical, second):
        (path / "package.json").unlink()
        path.rmdir()
    canonical.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(RuntimeError, match="exactly one"):
        _resolve_frontend_root(backend)


def test_frontend_has_exactly_one_regular_workflow() -> None:
    assert not WORKFLOW_DIR.is_symlink()
    assert WORKFLOW_DIR.is_dir()
    entries = sorted(WORKFLOW_DIR.iterdir(), key=lambda path: path.name)
    assert [path.name for path in entries] == ["frontend-ci.yml"]
    assert WORKFLOW_PATH.is_file()
    assert not WORKFLOW_PATH.is_symlink()


def test_workflow_matches_the_complete_fixed_contract() -> None:
    _, workflow = _load_workflow()
    assert workflow == _expected_workflow()


@pytest.mark.parametrize(
    ("backend", "frontend", "infra", "workflow_sha", "expected"),
    [
        ("a" * 40, "b" * 40, "c" * 40, "b" * 40, 0),
        ("a" * 40, "b" * 39, "c" * 40, "b" * 39, 1),
        ("a" * 40, "B" * 40, "c" * 40, "B" * 40, 1),
        ("a" * 40, "main", "c" * 40, "main", 1),
        ("a" * 40, "b;exit 0" + "b" * 32, "c" * 40, "b" * 40, 1),
        ("a" * 40, "b" * 40, "c" * 40, "a" * 40, 1),
    ],
)
def test_ref_validation_script_fails_closed(
    backend: str,
    frontend: str,
    infra: str,
    workflow_sha: str,
    expected: int,
) -> None:
    completed = subprocess.run(
        ["bash", "-c", _validation_run()],
        check=False,
        env={
            "BACKEND_SHA": backend,
            "FRONTEND_SHA": frontend,
            "INFRA_SHA": infra,
            "WORKFLOW_SHA": workflow_sha,
        },
        capture_output=True,
        text=True,
    )
    assert completed.returncode == expected


def test_workflow_has_no_mutation_or_alternate_gate_vocabulary() -> None:
    raw, _ = _load_workflow()
    lowered = raw.lower()
    forbidden = (
        "push:",
        "pull_request",
        "schedule:",
        "workflow_call",
        "id-token",
        "secrets.",
        "aws",
        "gcp",
        "azure",
        "oidc",
        "s3",
        "cloudfront",
        "artifact",
        "docker",
        "kubectl",
        "terraform",
        "cdk",
        "setup-node",
        "npm ",
        "pnpm ",
        "yarn ",
        "pytest",
        "ruff",
        "mypy",
        "pip-audit",
        " build",
        "deploy",
        "smoke",
        "rollback",
        "mobile",
        "native",
        "--gate",
        "--skip",
        "--only",
        "--order",
        "--argv",
        "continue-on-error",
        "|| true",
        "${{ inputs.",
    )
    shell_runs = [
        step["run"]
        for step in _expected_workflow()["jobs"]["formal"]["steps"]
        if "run" in step
    ]
    assert not [token for token in forbidden[:-1] if token in lowered]
    assert all(forbidden[-1] not in run for run in shell_runs)


def test_every_run_step_is_valid_bash() -> None:
    steps = _expected_workflow()["jobs"]["formal"]["steps"]
    for step in steps:
        run = step.get("run")
        if not isinstance(run, str):
            continue
        completed = subprocess.run(
            ["bash", "-n", "-c", run],
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
