"""Contract for the direct production delivery workflow.

deploy.yml is the credential-free formal verification DAG and stays non-mutating;
docs/security/phase-474-workflow-policy.json describes that DAG only. Production
mutation happens in deploy-production.yml, so its gates are pinned here.
"""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
from typing import Any

from test_backend_workflow_contract import WorkflowLoader
import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "deploy-production.yml"

DEPLOY_ROLE = "arn:aws:iam::562923011260:role/stoa-github-backend-deploy"
REGION = "eu-central-2"
FUNCTIONS = ("stoa-api", "stoa-weekly-report")
SHA_PINNED = re.compile(r"^[^@]+@[0-9a-f]{40}$")


def _workflow() -> tuple[str, dict[str, Any]]:
    raw = WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = yaml.load(raw, Loader=WorkflowLoader)
    assert isinstance(workflow, dict)
    return raw, workflow


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    steps = job["steps"]
    assert isinstance(steps, list)
    assert all(isinstance(step, dict) for step in steps)
    return steps


def _run_steps(job: dict[str, Any]) -> list[str]:
    return [step["run"] for step in _steps(job) if isinstance(step.get("run"), str)]


def test_deploys_only_on_pushes_to_main_and_serialises_runs() -> None:
    _, workflow = _workflow()
    assert workflow["on"] == {"push": {"branches": ["main"]}}
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"] == {
        "group": "backend-production-deploy",
        "cancel-in-progress": False,
    }


def test_deployment_is_gated_behind_lint_and_the_full_test_suite() -> None:
    _, workflow = _workflow()
    jobs = workflow["jobs"]
    assert list(jobs) == ["verify", "deploy"]
    assert jobs["deploy"]["needs"] == "verify"

    gate = jobs["verify"]
    assert gate.get("permissions") is None
    assert gate.get("environment") is None
    commands = " ".join(_run_steps(gate))
    assert "uv sync --frozen --extra dev" in commands
    assert "ruff check" in commands
    assert "pytest" in commands


def test_gate_checks_out_the_siblings_the_cross_repo_tests_resolve() -> None:
    _, workflow = _workflow()
    checkouts = {
        step["with"].get("repository", "stoasystem/stoa-backend"): step["with"]
        for step in _steps(workflow["jobs"]["verify"])
        if isinstance(step.get("uses"), str) and "actions/checkout@" in step["uses"]
    }
    # Without the siblings in place these tests fail at collection, not on merit.
    assert {name: value["path"] for name, value in checkouts.items()} == {
        "stoasystem/stoa-backend": "stoa-backend",
        "stoasystem/stoa-frontend": "stoa-frontend",
        "stoasystem/stoa-infra": "stoa-infra",
    }
    # The phase-474 evidence suites resolve pinned historical commit objects.
    assert checkouts["stoasystem/stoa-backend"]["fetch-depth"] == 0


def test_uv_is_pinned_so_the_locked_export_stays_reproducible() -> None:
    _, workflow = _workflow()
    pins = [
        step["with"]
        for job in workflow["jobs"].values()
        for step in _steps(job)
        if isinstance(step.get("uses"), str) and "setup-uv@" in step["uses"]
    ]
    assert len(pins) == 2
    # requirements.txt is compared against a fresh export whose bytes differ
    # between uv releases, so an unpinned uv breaks provenance verification.
    for pin in pins:
        assert pin == {"version": "0.11.16", "enable-cache": False}


def test_only_the_deploy_job_can_obtain_aws_credentials() -> None:
    raw, workflow = _workflow()
    jobs = workflow["jobs"]
    assert jobs["verify"].get("permissions") is None
    assert jobs["deploy"]["permissions"] == {"contents": "read", "id-token": "write"}
    # No GitHub environment: stoa-github-backend-deploy trusts only the subject
    # repo:stoasystem/*:ref:refs/heads/main. Declaring an environment rewrites the
    # OIDC subject to :environment:<name> and the role stops being assumable.
    assert "environment" not in jobs["deploy"]
    assert raw.count("id-token") == 1
    assert "secrets." not in raw
    assert "aws-access-key-id" not in raw


def test_every_action_is_pinned_to_an_immutable_commit() -> None:
    _, workflow = _workflow()
    uses = [
        step["uses"]
        for job in workflow["jobs"].values()
        for step in _steps(job)
        if isinstance(step.get("uses"), str)
    ]
    assert uses
    for reference in uses:
        assert SHA_PINNED.match(reference), reference


def test_package_is_built_natively_so_the_boot_smoke_test_runs() -> None:
    _, workflow = _workflow()
    deploy = workflow["jobs"]["deploy"]
    assert deploy["runs-on"] == "ubuntu-24.04-arm"
    commands = " ".join(_run_steps(deploy))
    # A skipped smoke test would ship a package whose imports were never proven.
    assert "--skip-smoke" not in commands
    assert "--skip-install" not in commands


def test_provenance_is_verified_before_credentials_are_configured() -> None:
    _, workflow = _workflow()
    steps = _steps(workflow["jobs"]["deploy"])
    names = [step.get("name") for step in steps]
    verify = names.index("Verify Lambda dist provenance")
    credentials = next(
        index
        for index, step in enumerate(steps)
        if isinstance(step.get("uses"), str)
        and "configure-aws-credentials" in step["uses"]
    )
    assert verify < credentials
    assert steps[credentials]["with"] == {
        "role-to-assume": DEPLOY_ROLE,
        "aws-region": REGION,
    }


def test_mutation_is_bounded_to_the_two_known_functions() -> None:
    _, workflow = _workflow()
    commands = " ".join(_run_steps(workflow["jobs"]["deploy"]))
    assert "--dry-run" in commands
    assert "aws lambda wait function-updated" in commands
    assert "aws lambda publish-version" in commands
    assert "aws lambda update-alias" in commands
    referenced = set(re.findall(r"stoa-(?:api|weekly-report)", commands))
    assert referenced == set(FUNCTIONS)
    assert not re.search(r"\b(?:aws\s+cloudformation|cdk)\s+(?:deploy|destroy)", commands)


def test_every_run_step_is_valid_bash() -> None:
    _, workflow = _workflow()
    for job in workflow["jobs"].values():
        for command in _run_steps(job):
            subprocess.run(
                ["bash", "-n"],
                input=command,
                text=True,
                check=True,
                capture_output=True,
            )
