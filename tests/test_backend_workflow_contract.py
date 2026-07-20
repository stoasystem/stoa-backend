"""Closed contract for the backend formal-release workflow caller."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re
import subprocess
from typing import Any

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "deploy.yml"

CHECKOUT_ACTION = "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd"
PYTHON_ACTION = "actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405"
UV_ACTION = "astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b"

REPOSITORIES = {
    "backend": "stoasystem/stoa-backend",
    "frontend": "stoasystem/stoa-frontend",
    "infra": "stoasystem/stoa-infra",
}


class WorkflowLoader(yaml.SafeLoader):
    """YAML loader that preserves Actions' `on` key and rejects duplicates."""


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


def _load_workflow() -> tuple[str, dict[str, Any]]:
    raw = WORKFLOW_PATH.read_text(encoding="utf-8")
    value = yaml.load(raw, Loader=WorkflowLoader)
    assert isinstance(value, dict)
    return raw, value


def _formal_job(workflow: dict[str, Any]) -> dict[str, Any]:
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    assert set(jobs) == {"formal"}
    job = jobs["formal"]
    assert isinstance(job, dict)
    return job


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    value = job["steps"]
    assert isinstance(value, list)
    assert all(isinstance(step, dict) for step in value)
    return value


def _step(steps: list[dict[str, Any]], name: str) -> dict[str, Any]:
    matches = [step for step in steps if step.get("name") == name]
    assert len(matches) == 1
    return matches[0]


def test_loader_rejects_duplicate_workflow_keys() -> None:
    with pytest.raises(yaml.constructor.ConstructorError, match="duplicate key: permissions"):
        yaml.load("permissions: {}\npermissions: {}\n", Loader=WorkflowLoader)


def test_workflow_is_manual_closed_and_read_only() -> None:
    _, workflow = _load_workflow()

    assert set(workflow) == {"name", "on", "permissions", "env", "jobs"}
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["env"] == {
        "EVIDENCE_DIR": "${{ runner.temp }}/stoa-formal-evidence",
        "UV_PYTHON_DOWNLOADS": "never",
    }

    triggers = workflow["on"]
    assert isinstance(triggers, dict)
    assert set(triggers) == {"workflow_dispatch"}
    dispatch = triggers["workflow_dispatch"]
    assert isinstance(dispatch, dict)
    assert set(dispatch) == {"inputs"}
    inputs = dispatch["inputs"]
    assert isinstance(inputs, dict)
    assert set(inputs) == {"backend_sha", "frontend_sha", "infra_sha"}
    for name, specification in inputs.items():
        assert specification == {
            "description": f"Exact {name.removesuffix('_sha')} commit SHA",
            "required": True,
            "type": "string",
        }


def test_job_shape_and_runtime_are_closed() -> None:
    _, workflow = _load_workflow()
    job = _formal_job(workflow)

    assert set(job) == {"name", "runs-on", "timeout-minutes", "steps"}
    assert job["runs-on"] == "ubuntu-24.04"
    assert job["timeout-minutes"] == 180

    steps = _steps(job)
    uses = [step["uses"] for step in steps if "uses" in step]
    assert uses == [CHECKOUT_ACTION, CHECKOUT_ACTION, CHECKOUT_ACTION, PYTHON_ACTION, UV_ACTION]
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", action) for action in uses)

    python = _step(steps, "Set up Python")
    assert python == {
        "name": "Set up Python",
        "uses": PYTHON_ACTION,
        "with": {"python-version": "3.12.13", "cache": False},
    }
    uv = _step(steps, "Set up uv")
    assert uv == {
        "name": "Set up uv",
        "uses": UV_ACTION,
        "with": {"version": "0.11.16", "enable-cache": False},
    }


def test_refs_are_validated_before_any_checkout() -> None:
    _, workflow = _load_workflow()
    steps = _steps(_formal_job(workflow))
    validation = _step(steps, "Validate immutable source refs")

    assert steps.index(validation) < min(
        index for index, step in enumerate(steps) if step.get("uses") == CHECKOUT_ACTION
    )
    assert validation["shell"] == "bash"
    assert validation["env"] == {
        "BACKEND_SHA": "${{ inputs.backend_sha }}",
        "FRONTEND_SHA": "${{ inputs.frontend_sha }}",
        "INFRA_SHA": "${{ inputs.infra_sha }}",
        "WORKFLOW_SHA": "${{ github.sha }}",
    }
    run = validation["run"]
    assert isinstance(run, str)
    assert "^[0-9a-f]{40}$" in run
    assert '[[ "$BACKEND_SHA" == "$WORKFLOW_SHA" ]]' in run
    assert "${{" not in run


@pytest.mark.parametrize(
    ("backend", "frontend", "infra", "workflow_sha", "expected"),
    [
        ("a" * 40, "b" * 40, "c" * 40, "a" * 40, 0),
        ("a" * 39, "b" * 40, "c" * 40, "a" * 39, 1),
        ("A" * 40, "b" * 40, "c" * 40, "A" * 40, 1),
        ("main", "b" * 40, "c" * 40, "main", 1),
        ("a" * 40, "b;exit 0" + "b" * 32, "c" * 40, "a" * 40, 1),
        ("a" * 40, "b" * 40, "c" * 40, "d" * 40, 1),
    ],
)
def test_ref_validation_script_fails_closed(
    backend: str,
    frontend: str,
    infra: str,
    workflow_sha: str,
    expected: int,
) -> None:
    _, workflow = _load_workflow()
    validation = _step(_steps(_formal_job(workflow)), "Validate immutable source refs")
    completed = subprocess.run(
        ["bash", "-c", validation["run"]],
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


def test_checkouts_are_exact_read_only_siblings() -> None:
    _, workflow = _load_workflow()
    steps = _steps(_formal_job(workflow))

    checkouts = [step for step in steps if step.get("uses") == CHECKOUT_ACTION]
    assert len(checkouts) == 3
    for component, repository in REPOSITORIES.items():
        checkout = _step(checkouts, f"Check out {component}")
        assert checkout == {
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

    identity = _step(steps, "Verify checkout identities")
    assert identity["env"] == {
        "BACKEND_SHA": "${{ inputs.backend_sha }}",
        "FRONTEND_SHA": "${{ inputs.frontend_sha }}",
        "INFRA_SHA": "${{ inputs.infra_sha }}",
    }
    run = identity["run"]
    assert isinstance(run, str)
    assert "${{" not in run
    for component in REPOSITORIES:
        assert f'git -C "$GITHUB_WORKSPACE/stoa-{component}" rev-parse HEAD' in run
        assert f'"${component.upper()}_SHA"' in run


def test_evidence_directory_is_private_and_precedes_gate() -> None:
    _, workflow = _load_workflow()
    steps = _steps(_formal_job(workflow))
    private = _step(steps, "Create private evidence directory")
    candidate = _step(steps, "Issue release candidate")

    assert steps.index(private) < steps.index(candidate)
    assert private["shell"] == "bash"
    assert private["run"] == (
        "set -euo pipefail\n"
        "umask 077\n"
        'test ! -e "$EVIDENCE_DIR"\n'
        'install -d -m 0700 "$EVIDENCE_DIR"\n'
        'test "$(stat -c %a "$EVIDENCE_DIR")" = "700"\n'
    )


def test_only_candidate_then_fixed_formal_are_invoked() -> None:
    raw, workflow = _load_workflow()
    steps = _steps(_formal_job(workflow))
    candidate = _step(steps, "Issue release candidate")
    formal = _step(steps, "Run fixed formal aggregate")

    assert steps.index(candidate) < steps.index(formal)
    assert candidate == {
        "name": "Issue release candidate",
        "working-directory": "stoa-backend",
        "shell": "bash",
        "run": (
            "set -euo pipefail\n"
            "python scripts/release_gate.py candidate \\\n"
            '  --backend-root "$GITHUB_WORKSPACE/stoa-backend" \\\n'
            '  --frontend-root "$GITHUB_WORKSPACE/stoa-frontend" \\\n'
            '  --infra-root "$GITHUB_WORKSPACE/stoa-infra" \\\n'
            '  --output "$EVIDENCE_DIR/candidate.json"\n'
        ),
    }
    assert formal == {
        "name": "Run fixed formal aggregate",
        "working-directory": "stoa-backend",
        "shell": "bash",
        "run": (
            "set -euo pipefail\n"
            "python scripts/release_gate.py formal \\\n"
            '  --candidate "$EVIDENCE_DIR/candidate.json" \\\n'
            '  --backend-root "$GITHUB_WORKSPACE/stoa-backend" \\\n'
            '  --frontend-root "$GITHUB_WORKSPACE/stoa-frontend" \\\n'
            '  --infra-root "$GITHUB_WORKSPACE/stoa-infra" \\\n'
            '  --output "$EVIDENCE_DIR/formal.json"\n'
        ),
    }
    assert len(re.findall(r"python scripts/release_gate\.py (?:candidate|formal)", raw)) == 2


def test_workflow_has_no_delivery_or_alternate_gate_authority() -> None:
    raw, workflow = _load_workflow()
    job = _formal_job(workflow)
    lowered = raw.lower()

    forbidden = (
        "id-token",
        "secrets.",
        "aws",
        "gcp",
        "azure",
        "oidc",
        "lambda",
        "cloudfront",
        "configure-credentials",
        "upload-artifact",
        "download-artifact",
        "docker",
        "kubectl",
        "terraform",
        "cdk",
        "pytest",
        "ruff",
        "mypy",
        "pip-audit",
        "npm ",
        "pnpm ",
        "yarn ",
        "--gate",
        "--skip",
        "--only",
        "--order",
        "--argv",
        "continue-on-error",
        "|| true",
    )
    assert not [token for token in forbidden if token in lowered]
    assert not (set(job) & {"environment", "container", "services"})
