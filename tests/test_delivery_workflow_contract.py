"""Closed contract for the backend-owned immutable delivery DAG."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from test_backend_workflow_contract import WorkflowLoader
import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "deploy.yml"
POLICY_PATH = ROOT / "docs" / "security" / "phase-474-workflow-policy.json"


def _workflow() -> tuple[str, dict[str, Any]]:
    raw = WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = yaml.load(raw, Loader=WorkflowLoader)
    assert isinstance(workflow, dict)
    return raw, workflow


def _policy() -> dict[str, Any]:
    value = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_backend_is_the_single_dependency_closed_delivery_authority() -> None:
    _, workflow = _workflow()
    jobs = workflow["jobs"]
    assert list(jobs) == [
        "formal",
        "immutable_build",
        "staging_substrate",
        "staging_deploy",
        "staging_smoke",
        "production_eligibility",
        "production_not_run",
    ]
    assert jobs["formal"].get("environment") is None
    assert jobs["formal"].get("permissions") is None
    assert jobs["immutable_build"]["needs"] == ["formal"]
    assert jobs["staging_substrate"]["needs"] == ["immutable_build"]
    assert jobs["staging_deploy"]["needs"] == ["staging_substrate"]
    assert jobs["staging_smoke"]["needs"] == ["staging_deploy"]
    assert jobs["production_eligibility"]["needs"] == ["staging_smoke"]


def test_staging_only_credentials_follow_all_required_gates() -> None:
    raw, workflow = _workflow()
    jobs = workflow["jobs"]
    for name in ("staging_substrate", "staging_deploy", "staging_smoke"):
        job = jobs[name]
        assert job["environment"] in {"staging", "staging-smoke"}
        assert job["permissions"] == {"contents": "read", "id-token": "write"}
    assert "id-token" not in raw.split("staging_substrate:", maxsplit=1)[0]
    assert "configure-aws-credentials" not in raw
    assert "secrets." not in raw


def test_failure_tamper_or_missing_receipt_cuts_all_delivery_edges() -> None:
    _, workflow = _workflow()
    jobs = workflow["jobs"]
    for name in ("immutable_build", "staging_substrate", "staging_deploy", "staging_smoke"):
        serialized = json.dumps(jobs[name], sort_keys=True)
        assert "always()" not in serialized
        assert "continue-on-error" not in serialized
    for name in ("staging_substrate", "staging_deploy", "staging_smoke"):
        run = jobs[name]["steps"][0]["run"]
        assert "test -f" in run
        assert "sha256sum" in run
        assert "release_environment.py" in run


def test_production_is_approval_eligible_but_exactly_not_run() -> None:
    raw, workflow = _workflow()
    eligibility = workflow["jobs"]["production_eligibility"]
    assert eligibility["environment"] == "production"
    assert eligibility["permissions"] == {"contents": "read"}
    production = workflow["jobs"]["production_not_run"]
    assert production["needs"] == ["production_eligibility"]
    assert "production-infrastructure=NOT RUN" in production["steps"][0]["run"]
    assert "production-deploy=NOT RUN" in production["steps"][0]["run"]
    assert "production-smoke=NOT RUN" in production["steps"][0]["run"]
    assert "production-rollback=NOT RUN" in production["steps"][0]["run"]
    assert not re.search(r"\b(?:aws|cdk)\s+(?:deploy|destroy|rollback)", raw)


def test_workflow_policy_is_closed_and_matches_the_delivery_dag() -> None:
    policy = _policy()
    assert policy == {
        "schema": "stoa.release.workflow-policy.v1",
        "authority_repository": "stoasystem/stoa-backend",
        "required_jobs": [
            "formal",
            "immutable_build",
            "staging_substrate",
            "staging_deploy",
            "staging_smoke",
            "production_eligibility",
            "production_not_run",
        ],
        "staging_environments": ["staging", "staging-smoke"],
        "sole_owner_self_approval": True,
        "build_once": True,
        "production_mutation": "NOT RUN",
        "forbidden": ["continue-on-error", "always()", "configure-aws-credentials", "secrets."],
    }

