"""One subject of the knowledge base goes live while the others stay in preview.

stoa-backend#106 / #422: the knowledge base stars are in production in preview
(#377), and a subject is switched live once its lessons are published (#364).
Mathematics gets its lessons first; English and physics have none yet and must
not appear on the student's map. `--knowledge-base-live mathematics` writes the
mathematics stars active and leaves the English and physics nebulae and stars in
preview, without their subject rows; `--knowledge-base-live` alone still writes
every subject live.
"""

from __future__ import annotations

import pytest

from scripts import check_curriculum_seed as check
from scripts import seed_practice
from stoa.services import knowledge_base_catalog

ALL = ("mathematics", "english", "physics")


def _states(topics: list[dict], units: list[dict]) -> dict[str, set[str]]:
    """subject id -> the rollout states its nebulae and stars are written with."""
    states: dict[str, set[str]] = {}
    for row in (*topics, *units):
        states.setdefault(row["subject_id"], set()).add(row["rollout_state"])
    return states


def test_mathematics_goes_live_and_english_and_physics_stay_hidden() -> None:
    subjects, topics, units = seed_practice.knowledge_base_rows(live={"mathematics"})

    assert subjects == []
    assert _states(topics, units) == {
        "mathematics": {"active"}, "english": {"preview"}, "physics": {"preview"},
    }


def test_a_language_goes_live_with_its_subject_row_alone() -> None:
    subjects, topics, units = seed_practice.knowledge_base_rows(live={"english"})

    assert [s["subject_id"] for s in subjects] == ["english"]
    assert _states(topics, units) == {
        "mathematics": {"preview"}, "english": {"active"}, "physics": {"preview"},
    }


def test_true_and_false_still_mean_every_subject_and_none() -> None:
    assert seed_practice.knowledge_base_rows(live=True) == seed_practice.knowledge_base_rows(live=set(ALL))
    assert seed_practice.knowledge_base_rows(live=False) == seed_practice.knowledge_base_rows(live=set())


def test_the_seed_writes_the_mode_it_is_given() -> None:
    rows = seed_practice.seed_rows(knowledge_base="live:mathematics")
    kb_units = {u["unit_id"] for u in knowledge_base_catalog.units()}
    written = {
        row["unit_id"]: row["rollout_state"]
        for row in rows if row["SK"].startswith("UNIT#") and row["unit_id"] in kb_units
    }
    subject_of = {u["unit_id"]: u["subject_id"] for u in knowledge_base_catalog.units()}

    assert {u: s for u, s in written.items() if subject_of[u] == "mathematics"}
    assert all(
        state == ("active" if subject_of[unit] == "mathematics" else "preview")
        for unit, state in written.items()
    )
    assert not [row for row in rows if row["SK"] in ("SUBJECT#english", "SUBJECT#physics")]
    hashes = {
        mode: seed_practice.seed_hash(seed_practice.seed_rows(knowledge_base=mode))
        for mode in ("preview", "live", "live:mathematics")
    }
    assert len(set(hashes.values())) == 3


@pytest.mark.parametrize(
    ("argv", "mode"),
    [
        ([], None),
        (["--knowledge-base"], "preview"),
        (["--knowledge-base-live"], "live"),
        (["--knowledge-base-live", "mathematics"], "live:mathematics"),
        (["--knowledge-base-live", "physics", "mathematics"], "live:mathematics,physics"),
        (["--knowledge-base-live", "mathematics", "english", "physics"], "live"),
    ],
)
def test_the_command_line_names_the_mode(argv: list[str], mode: str | None) -> None:
    assert seed_practice.parse_args(argv).knowledge_base == mode


@pytest.mark.parametrize(
    "argv",
    [
        ["--knowledge-base-live", "chemistry"],
        ["--knowledge-base", "--knowledge-base-live", "mathematics"],
    ],
)
def test_an_unknown_subject_or_both_flags_are_refused(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        seed_practice.parse_args(argv)


def test_an_unknown_subject_in_a_mode_is_refused() -> None:
    with pytest.raises(ValueError, match="chemistry"):
        seed_practice.seed_rows(knowledge_base="live:chemistry")


def _stamp(mode: str, seed_hash: str) -> dict:
    return {
        "seed_hash": seed_hash, "knowledge_base": mode, "git_commit": "abc",
        "seeded_at": "2026-11-12T10:00:00+00:00", "git_dirty": False,
    }


def test_the_deploy_check_recomputes_a_one_subject_mode() -> None:
    seen: list[str] = []

    def hasher(mode: str) -> str:
        seen.append(mode)
        return "e" * 64

    outcome = check.compare(_stamp("live:mathematics", "e" * 64), hasher)

    assert outcome.warning is None
    assert seen == ["live:mathematics"]
    assert "knowledge base: live:mathematics" in outcome.summary


def test_a_lagging_one_subject_table_is_told_to_reseed_that_subject() -> None:
    outcome = check.compare(_stamp("live:mathematics", "d" * 64), lambda mode: "e" * 64)

    assert outcome.warning is not None
    assert "Run `scripts/seed_practice.py --knowledge-base-live mathematics`" in outcome.summary


def test_a_stamp_naming_an_unknown_subject_is_an_unknown_mode() -> None:
    outcome = check.compare(_stamp("live:chemistry", "d" * 64), lambda mode: "e" * 64)

    assert outcome.warning is not None
    assert "does not know" in outcome.summary


def test_the_real_code_hash_of_a_one_subject_mode_is_the_seed_s() -> None:
    assert check.code_hash("live:mathematics") == seed_practice.seed_hash(
        seed_practice.seed_rows(knowledge_base="live:mathematics")
    )
