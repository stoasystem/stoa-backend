"""Closed contract for the infrastructure formal-release workflow caller."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import tomllib
from typing import Any

import pytest
import yaml

from tests import test_frontend_workflow_contract as shared


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _resolve_infra_root(backend_root: Path) -> Path:
    matches: list[Path] = []
    for name in ("stoa-infra", "infra"):
        candidate = backend_root.parent / name
        marker = candidate / "pyproject.toml"
        if (
            candidate.is_symlink()
            or not candidate.is_dir()
            or marker.is_symlink()
            or not marker.is_file()
        ):
            continue
        try:
            manifest = tomllib.loads(marker.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError):
            continue
        project = manifest.get("project")
        if isinstance(project, dict) and project.get("name") == "stoa-infra":
            matches.append(candidate)
    if len(matches) != 1:
        raise RuntimeError("exactly one canonical infra repository root is required")
    return matches[0]


INFRA_ROOT = _resolve_infra_root(BACKEND_ROOT)
WORKFLOW_DIR = INFRA_ROOT / ".github" / "workflows"
WORKFLOW_PATH = WORKFLOW_DIR / "deploy.yml"


def _validation_run() -> str:
    return (
        "set -euo pipefail\n"
        "sha_pattern='^[0-9a-f]{40}$'\n"
        'for sha in "$BACKEND_SHA" "$FRONTEND_SHA" "$INFRA_SHA" "$WORKFLOW_SHA"; do\n'
        '  [[ "$sha" =~ $sha_pattern ]] || exit 1\n'
        "done\n"
        '[[ "$INFRA_SHA" == "$WORKFLOW_SHA" ]]\n'
    )


def _expected_workflow() -> dict[str, Any]:
    expected = deepcopy(shared._expected_workflow())
    steps = expected["jobs"]["formal"]["steps"]
    steps[0]["run"] = _validation_run()
    return expected


def _load_workflow() -> tuple[str, dict[str, Any]]:
    raw = WORKFLOW_PATH.read_text(encoding="utf-8")
    value = yaml.load(raw, Loader=shared.WorkflowLoader)
    assert isinstance(value, dict)
    return raw, value


def test_loader_rejects_duplicate_workflow_keys() -> None:
    with pytest.raises(yaml.constructor.ConstructorError, match="duplicate key: permissions"):
        yaml.load("permissions: {}\npermissions: {}\n", Loader=shared.WorkflowLoader)


@pytest.mark.parametrize("name", ["stoa-infra", "infra"])
def test_infra_root_resolution_supports_only_canonical_layouts(
    tmp_path: Path,
    name: str,
) -> None:
    backend = tmp_path / "backend-root"
    backend.mkdir()
    infra = tmp_path / name
    infra.mkdir()
    (infra / "pyproject.toml").write_text(
        '[project]\nname = "stoa-infra"\n',
        encoding="utf-8",
    )

    assert _resolve_infra_root(backend) == infra


def test_infra_root_resolution_rejects_zero_multiple_and_symlink_matches(
    tmp_path: Path,
) -> None:
    backend = tmp_path / "backend-root"
    backend.mkdir()
    with pytest.raises(RuntimeError, match="exactly one"):
        _resolve_infra_root(backend)

    canonical = tmp_path / "infra"
    canonical.mkdir()
    (canonical / "pyproject.toml").write_text(
        '[project]\nname = "wrong-project"\n',
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="exactly one"):
        _resolve_infra_root(backend)

    (canonical / "pyproject.toml").write_text(
        '[project]\nname = "stoa-infra"\n',
        encoding="utf-8",
    )
    second = tmp_path / "stoa-infra"
    second.mkdir()
    (second / "pyproject.toml").write_text(
        '[project]\nname = "stoa-infra"\n',
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="exactly one"):
        _resolve_infra_root(backend)

    for path in (canonical, second):
        (path / "pyproject.toml").unlink()
        path.rmdir()
    canonical.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(RuntimeError, match="exactly one"):
        _resolve_infra_root(backend)


def test_infra_has_exactly_one_regular_workflow() -> None:
    assert not WORKFLOW_DIR.is_symlink()
    assert WORKFLOW_DIR.is_dir()
    entries = sorted(WORKFLOW_DIR.iterdir(), key=lambda path: path.name)
    assert [path.name for path in entries] == ["deploy.yml"]
    assert WORKFLOW_PATH.is_file()
    assert not WORKFLOW_PATH.is_symlink()


def test_workflow_matches_the_complete_fixed_contract() -> None:
    _, workflow = _load_workflow()
    assert workflow == _expected_workflow()


@pytest.mark.parametrize(
    ("backend", "frontend", "infra", "workflow_sha", "expected"),
    [
        ("a" * 40, "b" * 40, "c" * 40, "c" * 40, 0),
        ("a" * 40, "b" * 40, "c" * 39, "c" * 39, 1),
        ("a" * 40, "b" * 40, "C" * 40, "C" * 40, 1),
        ("a" * 40, "b" * 40, "main", "main", 1),
        ("a" * 40, "b" * 40, "c;exit 0" + "c" * 32, "c" * 40, 1),
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


def test_workflow_has_no_provider_mutation_or_alternate_gate_vocabulary() -> None:
    raw, _ = _load_workflow()
    lowered = raw.lower()
    forbidden = (
        "push:",
        "pull_request",
        "schedule:",
        "workflow_call",
        "id-token",
        "pull-requests",
        "github-script",
        "token:",
        "secrets.",
        "aws",
        "gcp",
        "azure",
        "oidc",
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
        " diff",
        "deploy",
        "comment",
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
    )
    assert not [token for token in forbidden if token in lowered]


def test_shell_inputs_are_indirect_and_every_run_step_is_valid_bash() -> None:
    steps = _expected_workflow()["jobs"]["formal"]["steps"]
    for step in steps:
        run = step.get("run")
        if not isinstance(run, str):
            continue
        assert "${{ inputs." not in run
        completed = subprocess.run(
            ["bash", "-n", "-c", run],
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr

