"""Closed contract for the thin infrastructure staging-eligibility workflow."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tomllib
from typing import Any

import pytest
import yaml

import test_frontend_workflow_contract as shared


BACKEND_ROOT = Path(__file__).resolve().parents[1]

CHECKOUT_ACTION = "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd"
PYTHON_ACTION = "actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405"
UV_ACTION = "astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b"


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
        "digest_pattern='^[0-9a-f]{64}$'\n"
        'for sha in "$BACKEND_SHA" "$INFRA_SHA" "$WORKFLOW_SHA"; do\n'
        '  [[ "$sha" =~ $sha_pattern ]] || exit 1\n'
        "done\n"
        '[[ "$INFRA_SHA" == "$WORKFLOW_SHA" ]] || exit 1\n'
        '[[ "$TRANSACTION_SHA256" =~ $digest_pattern ]] || exit 1\n'
        '[[ "$TRANSACTION_PATH" =~ ^receipts/staging/[A-Za-z0-9][A-Za-z0-9._/-]{0,240}\\.json$ ]] || exit 1\n'
        '[[ "$TRANSACTION_PATH" != *".."* ]] || exit 1\n'
    )


def _identity_run() -> str:
    return (
        "set -euo pipefail\n"
        'test "$(git -C "$GITHUB_WORKSPACE/stoa-backend" rev-parse HEAD)" = "$BACKEND_SHA"\n'
        'test "$(git -C "$GITHUB_WORKSPACE/stoa-infra" rev-parse HEAD)" = "$INFRA_SHA"\n'
    )


def _evidence_run() -> str:
    return (
        "set -euo pipefail\n"
        "umask 077\n"
        'evidence_dir="$(mktemp -d "$RUNNER_TEMP/stoa-infra-release.XXXXXX")"\n'
        'chmod 0700 "$evidence_dir"\n'
        'test "$(stat -c %a "$evidence_dir")" = "700"\n'
        "printf 'EVIDENCE_DIR=%s\\n' \"$evidence_dir\" >> \"$GITHUB_ENV\"\n"
    )


def _infra_preflight_run() -> str:
    return (
        "set -euo pipefail\n"
        "uv sync --frozen\n"
        "uv run pytest -q tests/test_release_topology.py\n"
        "uv run cdk synth > /dev/null\n"
        "uv run cdk diff --no-change-set > /dev/null\n"
    )


def _delivery_run() -> str:
    return """set -euo pipefail
transaction="$GITHUB_WORKSPACE/stoa-backend/$TRANSACTION_PATH"
test -f "$transaction"
test ! -L "$transaction"
test "$(sha256sum "$transaction" | cut -d " " -f 1)" = "$TRANSACTION_SHA256"
python scripts/release_gate.py delivery-validate \\
  --transaction "$transaction" \\
  --output "$EVIDENCE_DIR/delivery-validation.json"
"""


def _not_run_run() -> str:
    return """set -euo pipefail
printf '%s\\n' \\
  'production-infrastructure=NOT RUN' \\
  'production-deploy=NOT RUN' \\
  'production-smoke=NOT RUN' \\
  'production-rollback=NOT RUN'
"""


def _staging_boundary_run() -> str:
    return """set -euo pipefail
printf '%s\\n' \\
  'staging-authority=controller-owned' \\
  'deployed-state-read=NOT RUN: Plan 32 protected inventory/controller'
"""


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
        "backend_sha": {
            "description": "Exact backend commit SHA containing the receipted transaction",
            "required": True,
            "type": "string",
        },
        "infra_sha": {
            "description": "Exact infrastructure commit SHA",
            "required": True,
            "type": "string",
        },
        "transaction_path": {
            "description": "Exact staging transaction receipt path below receipts/staging",
            "required": True,
            "type": "string",
        },
        "transaction_sha256": {
            "description": "SHA-256 of the exact staging transaction receipt bytes",
            "required": True,
            "type": "string",
        },
    }
    verify_steps = [
        {
            "name": "Validate immutable source and receipt identities",
            "shell": "bash",
            "env": {
                "BACKEND_SHA": "${{ inputs.backend_sha }}",
                "INFRA_SHA": "${{ inputs.infra_sha }}",
                "TRANSACTION_PATH": "${{ inputs.transaction_path }}",
                "TRANSACTION_SHA256": "${{ inputs.transaction_sha256 }}",
                "WORKFLOW_SHA": "${{ github.sha }}",
            },
            "run": _validation_run(),
        },
        _checkout("backend", "stoasystem/stoa-backend"),
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
                "INFRA_SHA": "${{ inputs.infra_sha }}",
            },
            "run": _identity_run(),
        },
        {
            "name": "Create private release evidence directory",
            "shell": "bash",
            "run": _evidence_run(),
        },
        {
            "name": "Run frozen infrastructure preflight",
            "working-directory": "stoa-infra",
            "shell": "bash",
            "run": _infra_preflight_run(),
        },
        {
            "name": "Validate the canonical staging transaction",
            "working-directory": "stoa-backend",
            "shell": "bash",
            "env": {
                "TRANSACTION_PATH": "${{ inputs.transaction_path }}",
                "TRANSACTION_SHA256": "${{ inputs.transaction_sha256 }}",
            },
            "run": _delivery_run(),
        },
    ]
    return {
        "name": "Infrastructure Staging Eligibility",
        "on": {"workflow_dispatch": {"inputs": inputs}},
        "permissions": {"contents": "read"},
        "env": {"UV_PYTHON_DOWNLOADS": "never"},
        "jobs": {
            "verify": {
                "name": "Verify exact release identities and infrastructure topology",
                "runs-on": "ubuntu-24.04",
                "timeout-minutes": 90,
                "steps": verify_steps,
            },
            "staging": {
                "name": "Protected staging eligibility boundary",
                "needs": ["verify"],
                "environment": "staging",
                "runs-on": "ubuntu-24.04",
                "timeout-minutes": 10,
                "permissions": {"contents": "read", "id-token": "write"},
                "steps": [
                    {
                        "name": "Retain reviewed staging authority boundary",
                        "shell": "bash",
                        "run": _staging_boundary_run(),
                    }
                ],
            },
            "production_not_run": {
                "name": "Record production operations as not run",
                "needs": ["verify"],
                "runs-on": "ubuntu-24.04",
                "timeout-minutes": 5,
                "steps": [
                    {
                        "name": "Emit exact production obligations",
                        "shell": "bash",
                        "run": _not_run_run(),
                    }
                ],
            },
        },
    }


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
    (infra / "pyproject.toml").write_text('[project]\nname = "stoa-infra"\n', encoding="utf-8")

    assert _resolve_infra_root(backend) == infra


def test_infra_root_resolution_rejects_zero_multiple_and_symlink_matches(tmp_path: Path) -> None:
    backend = tmp_path / "backend-root"
    backend.mkdir()
    with pytest.raises(RuntimeError, match="exactly one"):
        _resolve_infra_root(backend)

    canonical = tmp_path / "infra"
    canonical.mkdir()
    (canonical / "pyproject.toml").write_text(
        '[project]\nname = "wrong-project"\n', encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="exactly one"):
        _resolve_infra_root(backend)

    (canonical / "pyproject.toml").write_text('[project]\nname = "stoa-infra"\n', encoding="utf-8")
    second = tmp_path / "stoa-infra"
    second.mkdir()
    (second / "pyproject.toml").write_text('[project]\nname = "stoa-infra"\n', encoding="utf-8")
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
    ("backend", "infra", "workflow_sha", "path", "digest", "expected"),
    [
        ("a" * 40, "c" * 40, "c" * 40, "receipts/staging/txn-1.json", "d" * 64, 0),
        ("a" * 40, "c" * 39, "c" * 39, "receipts/staging/txn-1.json", "d" * 64, 1),
        ("a" * 40, "C" * 40, "C" * 40, "receipts/staging/txn-1.json", "d" * 64, 1),
        ("a" * 40, "c" * 40, "a" * 40, "receipts/staging/txn-1.json", "d" * 64, 1),
        ("a" * 40, "c" * 40, "c" * 40, "../txn.json", "d" * 64, 1),
        ("a" * 40, "c" * 40, "c" * 40, "receipts/staging/../txn.json", "d" * 64, 1),
        ("a" * 40, "c" * 40, "c" * 40, "receipts/staging/txn-1.json", "D" * 64, 1),
    ],
)
def test_identity_validation_script_fails_closed(
    backend: str,
    infra: str,
    workflow_sha: str,
    path: str,
    digest: str,
    expected: int,
) -> None:
    completed = subprocess.run(
        ["bash", "-c", _validation_run()],
        check=False,
        env={
            "BACKEND_SHA": backend,
            "INFRA_SHA": infra,
            "WORKFLOW_SHA": workflow_sha,
            "TRANSACTION_PATH": path,
            "TRANSACTION_SHA256": digest,
        },
        capture_output=True,
        text=True,
    )
    assert completed.returncode == expected


def test_workflow_keeps_verification_credential_free_and_staging_dependency_closed() -> None:
    raw, workflow = _load_workflow()
    assert "id-token" not in raw.split("staging:", maxsplit=1)[0]
    assert workflow["jobs"]["staging"]["needs"] == ["verify"]
    assert workflow["jobs"]["staging"]["environment"] == "staging"
    assert workflow["jobs"]["staging"]["permissions"] == {
        "contents": "read",
        "id-token": "write",
    }


def test_credential_free_diff_defers_deployed_state_reads_to_plan32_controller() -> None:
    _, workflow = _load_workflow()
    verify = workflow["jobs"]["verify"]
    assert verify.get("permissions") is None
    assert "environment" not in verify
    preflight = verify["steps"][7]
    assert preflight["name"] == "Run frozen infrastructure preflight"
    assert "uv run cdk diff --no-change-set > /dev/null" in preflight["run"]

    staging_run = workflow["jobs"]["staging"]["steps"][0]["run"]
    assert "deployed-state-read=NOT RUN: Plan 32 protected inventory/controller" in staging_run


def test_workflow_has_only_the_canonical_gate_and_no_production_mutation() -> None:
    raw, workflow = _load_workflow()
    lowered = raw.lower()
    forbidden = (
        "push:",
        "pull_request",
        "schedule:",
        "workflow_call",
        "secrets.",
        "access-key",
        "secret-key",
        "configure-aws-credentials",
        "aws ",
        "s3 ",
        "lambda ",
        "cloudformation",
        "cdk deploy",
        "cdk destroy",
        "--allow-stale",
        "allow_stale_lambda_dist",
        "candidate ",
        " formal",
        " quality",
        "--gate",
        "--skip",
        "--only",
        "--order",
        "--argv",
        "continue-on-error",
        "|| true",
    )
    assert not [token for token in forbidden if token in lowered]
    assert "delivery-validate" in raw
    production = workflow["jobs"]["production_not_run"]
    assert production["needs"] == ["verify"]
    assert production.get("environment") is None
    assert production.get("permissions") is None
    assert production["steps"][0]["run"] == _not_run_run()


def test_shell_inputs_are_indirect_and_every_run_step_is_valid_bash() -> None:
    workflow = _expected_workflow()
    for job in workflow["jobs"].values():
        steps = job.get("steps")
        assert isinstance(steps, list)
        for step in steps:
            run = step.get("run")
            if not isinstance(run, str):
                continue
            assert "${{ inputs." not in run
            completed = subprocess.run(
                ["bash", "-n", "-c", run], check=False, capture_output=True, text=True
            )
            assert completed.returncode == 0, completed.stderr
