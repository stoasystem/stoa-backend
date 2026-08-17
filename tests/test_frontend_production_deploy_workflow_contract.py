"""Contract for the frontend push-to-production delivery workflow."""

from __future__ import annotations

import re
import subprocess
from typing import Any

from test_backend_workflow_contract import WorkflowLoader
from test_frontend_workflow_contract import FRONTEND_ROOT
import yaml


WORKFLOW_PATH = FRONTEND_ROOT / ".github" / "workflows" / "deploy-production.yml"
DEPLOY_ROLE = "arn:aws:iam::562923011260:role/stoa-github-frontend-deploy"
SHA_PINNED = re.compile(r"^[^@]+@[0-9a-f]{40}$")


def _workflow() -> tuple[str, dict[str, Any]]:
    raw = WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = yaml.load(raw, Loader=WorkflowLoader)
    assert isinstance(workflow, dict)
    return raw, workflow


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    steps = job["steps"]
    assert isinstance(steps, list)
    return steps


def _run_steps(job: dict[str, Any]) -> list[str]:
    return [step["run"] for step in _steps(job) if isinstance(step.get("run"), str)]


def test_deploys_only_on_pushes_to_main() -> None:
    raw, workflow = _workflow()
    assert workflow["on"] == {"push": {"branches": ["main"]}}
    assert workflow["concurrency"] == {
        "group": "frontend-production-deploy",
        "cancel-in-progress": False,
    }
    assert list(workflow["jobs"]) == ["verify", "deploy"]
    assert workflow["jobs"]["deploy"]["needs"] == "verify"
    assert "environment" not in workflow["jobs"]["deploy"]
    assert "secrets." not in raw


def test_gate_runs_lint_tests_and_the_publisher_suite() -> None:
    _, workflow = _workflow()
    commands = " ".join(_run_steps(workflow["jobs"]["verify"]))
    assert "npm ci" in commands
    assert "npm run lint" in commands
    assert "npm run typecheck" in commands
    assert "npm test" in commands
    assert "npm run test:release" in commands
    assert "publish-web-release.test.mjs" in commands


def test_only_the_deploy_job_obtains_aws_credentials() -> None:
    raw, workflow = _workflow()
    assert workflow["jobs"]["verify"].get("permissions") is None
    assert workflow["jobs"]["deploy"]["permissions"] == {
        "contents": "read",
        "id-token": "write",
    }
    assert raw.count("id-token") == 1
    credentials = next(
        step
        for step in _steps(workflow["jobs"]["deploy"])
        if isinstance(step.get("uses"), str) and "configure-aws-credentials" in step["uses"]
    )
    assert credentials["with"] == {
        "role-to-assume": DEPLOY_ROLE,
        "aws-region": "eu-central-2",
    }


def test_publish_script_runs_after_the_build_and_is_bounded_to_the_spa_bucket() -> None:
    _, workflow = _workflow()
    commands = " ".join(_run_steps(workflow["jobs"]["deploy"]))
    assert "npm run build" in commands
    assert "scripts/publish-web-release.mjs" in commands
    assert "cdk deploy" not in commands
    assert "aws s3 sync" not in commands


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
