"""T-472-03 semantic terminology gate and fail-closed mutation coverage."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check_teacher_terminology.py"
LEGACY_TERM = "tu" + "tor"
ALLOWLIST = ROOT / "docs" / "security" / f"{LEGACY_TERM}-term-allowlist.json"


def _run_checker(root: Path, allowlist: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(CHECKER),
            "--root",
            str(root),
            "--allowlist",
            str(allowlist),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_semantic_gate_uses_every_exact_negative_and_historical_allowlist_entry():
    result = _run_checker(ROOT, ALLOWLIST)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "allowlist entries used: 13" in result.stdout
    assert result.stdout.rstrip().endswith("PASS")


@pytest.mark.parametrize(
    ("relative_path", "active_contract"),
    [
        ("src/stoa/routers/active.py", f'ROUTE = "/{LEGACY_TERM}s"\n'),
        ("src/stoa/models/active.py", f'class Role:\n    LEGACY = "{LEGACY_TERM}"\n'),
        ("src/stoa/security/active.py", f'ALIASES = {{"{LEGACY_TERM}": "teacher"}}\n'),
        ("src/stoa/services/active.py", f'def output():\n    return {{"role": "{LEGACY_TERM}"}}\n'),
        ("tests/test_active.py", f'def test_positive():\n    user = {{"role": "{LEGACY_TERM}"}}\n'),
        (f"src/stoa/routers/{LEGACY_TERM}s.py", "router = object()\n"),
    ],
)
def test_semantic_gate_mutation_rejects_new_active_contracts(
    tmp_path, relative_path, active_contract
):
    target = tmp_path / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(active_contract, encoding="utf-8")
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(json.dumps({"version": 1, "entries": []}), encoding="utf-8")

    result = _run_checker(tmp_path, allowlist)

    assert result.returncode == 1
    assert "ACTIVE" in result.stdout
    assert result.stdout.rstrip().endswith("FAIL")


@pytest.mark.parametrize("value", ["tutor", "Tutor", "TUTOR"], ids=lambda value: f"negative-{value}")
def test_legacy_teacher_role_is_rejected_not_normalized(value):
    from stoa.security.identity import CanonicalRole

    with pytest.raises(ValueError):
        CanonicalRole(value)
