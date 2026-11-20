"""Cross-repository contract for the infrastructure repository's workflows.

The backend's test gate checks infra out beside it (see deploy-production.yml),
so it can hold infra's one production workflow to a diff before every deploy.
"""

from __future__ import annotations

from pathlib import Path
import re
import tomllib

import pytest
from workflow_helpers import WorkflowLoader, reads_secrets
import yaml


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
DEPLOY_WORKFLOW_PATH = WORKFLOW_DIR / "deploy-production.yml"


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


def test_infra_has_only_the_production_deploy_workflow() -> None:
    assert not WORKFLOW_DIR.is_symlink()
    assert WORKFLOW_DIR.is_dir()
    entries = sorted(WORKFLOW_DIR.iterdir(), key=lambda path: path.name)
    assert [path.name for path in entries] == ["deploy-production.yml"]
    for path in entries:
        assert path.is_file()
        assert not path.is_symlink()


PRODUCTION_STACKS = (
    "StoaAuthStack",
    "StoaDatabaseStack",
    "StoaStorageStack",
    "StoaNotificationStack",
    "StoaAiStack",
    "StoaApiStack",
    "StoaMonitoringStack",
    "StoaFrontendStack",
    "StoaReleaseDeliveryStack",
)


def test_production_deploy_workflow_deploys_named_stacks_after_a_diff() -> None:
    raw = DEPLOY_WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = yaml.load(raw, Loader=WorkflowLoader)
    assert isinstance(workflow, dict)
    assert workflow["on"] == {"push": {"branches": ["main"]}, "workflow_dispatch": None}
    assert workflow["permissions"] == {"contents": "read", "id-token": "write"}
    assert list(workflow["jobs"]) == ["deploy"]
    assert workflow["concurrency"] == {
        "group": "infra-production-deploy",
        "cancel-in-progress": False,
    }

    job = workflow["jobs"]["deploy"]
    assert job["runs-on"] == "ubuntu-24.04-arm"
    commands = " ".join(
        step["run"] for step in job["steps"] if isinstance(step.get("run"), str)
    )
    assert "cdk diff" in commands
    assert "cdk deploy" in commands
    assert "--require-approval never" in commands
    for stack in PRODUCTION_STACKS:
        assert stack in commands
    for token in ("cdk destroy", "cdk import", "|| true", "StoaSandbox"):
        assert token not in commands
    assert "snapshot_lambda_environment.py" in commands
    assert not reads_secrets(workflow)

    for step in job["steps"]:
        reference = step.get("uses")
        if isinstance(reference, str):
            assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", reference), reference
