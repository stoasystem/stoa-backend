"""Cross-repository contract for the frontend's workflows.

The backend's test gate checks the frontend out beside it (see
deploy-production.yml), so it can hold the frontend to one route to production.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


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


#: The only workflow that may publish to the production web surface.
DELIVERY_WORKFLOW = "deploy-production.yml"
#: What publishing to production looks like, whatever the workflow calls itself.
PRODUCTION_TARGETS = ("stoa-frontend-562923011260", "E27CVAMQHDMW80")


def test_only_the_production_workflow_publishes_to_production() -> None:
    """The delivery workflow is present, and nothing else delivers.

    An exact directory listing cannot tell a harmless addition (the redesign
    branch gate, a preview publisher) from a second route to `app.stoaedu.ch`:
    it goes red for the harmless case while a cleverly named addition reads as
    just another entry. So this checks the thing worth defending: every other
    workflow is free of the production bucket and distribution.
    """
    assert not WORKFLOW_DIR.is_symlink()
    assert WORKFLOW_DIR.is_dir()
    entries = sorted(WORKFLOW_DIR.iterdir(), key=lambda path: path.name)
    delivery = WORKFLOW_DIR / DELIVERY_WORKFLOW
    assert delivery.is_file()
    assert not delivery.is_symlink()

    for path in entries:
        if path.name == DELIVERY_WORKFLOW:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for target in PRODUCTION_TARGETS:
                if target not in line:
                    continue
                # Naming it to refuse it is the point of the guard in
                # `deploy-preview.yml`; naming it anywhere else is a second
                # route to production.
                assert "!=" in line, (
                    f"{path.name}:{number} names the production {target} "
                    f"outside a refusal; only {DELIVERY_WORKFLOW} may "
                    "publish to app.stoaedu.ch"
                )
