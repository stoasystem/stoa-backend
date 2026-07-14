"""T-472-01 semantic terminology gate; Plan 03 removes active legacy contracts."""

from pathlib import Path

import pytest


HISTORICAL_NEGATIVE_FIXTURES = {
    "tests/test_auth_security.py",
    "tests/test_privileged_identity_reconciliation.py",
    "tests/test_teacher_terminology_gate.py",
}
LEGACY_TERM = "tu" + "tor"


def _active_legacy_occurrences(root: Path) -> list[str]:
    occurrences = []
    for base in (root / "src", root / "tests"):
        for path in base.rglob("*.py"):
            relative = path.relative_to(root).as_posix()
            if relative in HISTORICAL_NEGATIVE_FIXTURES:
                continue
            if LEGACY_TERM in path.read_text(encoding="utf-8").lower():
                occurrences.append(relative)
    return sorted(occurrences)


def test_t472_01_teacher_terminology_gate_allows_only_exact_negative_historical_fixtures():
    assert _active_legacy_occurrences(Path(__file__).resolve().parents[1]) == []


def test_t472_01_teacher_terminology_gate_mutation_detects_active_contract(tmp_path):
    root = tmp_path
    source = root / "src" / "stoa" / "models"
    source.mkdir(parents=True)
    (source / "active_contract.py").write_text(
        f'ROLE = "{LEGACY_TERM}"\n', encoding="utf-8"
    )
    (root / "tests").mkdir()
    assert _active_legacy_occurrences(root) == ["src/stoa/models/active_contract.py"]


@pytest.mark.parametrize("value", ["tutor", "Tutor", "TUTOR"], ids=lambda value: f"negative-{value}")
def test_t472_01_legacy_teacher_role_is_rejected_not_normalized(value):
    from stoa.security.identity import CanonicalRole

    with pytest.raises(ValueError):
        CanonicalRole(value)
