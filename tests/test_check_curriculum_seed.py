"""After a production deploy, the curriculum seed in the code is compared with the
seed stamp in the table, and a table that lags is a warning, never a failure.

stoa-backend#355 (step 4 of #317). The seed is run by hand; `PRACTICE /
CURRICULUM_SEED` records the hash of what it last wrote and the knowledge-base mode
it ran in. `scripts/check_curriculum_seed.py` recomputes the hash from the
repository for that mode and reports one of four outcomes - in agreement, lagging,
no stamp, or the stamp could not be read - always with exit code 0.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from scripts import check_curriculum_seed as check

CODE_HASHES = {"off": "a" * 64, "preview": "b" * 64, "live": "c" * 64}


def _code_hash(mode: str) -> str:
    return CODE_HASHES[mode]


def _stamp(**overrides: object) -> dict:
    return {
        "PK": "PRACTICE",
        "SK": "CURRICULUM_SEED",
        "seed_hash": CODE_HASHES["off"],
        "seeded_at": "2026-11-09T10:00:00+00:00",
        "git_commit": "1234567890abcdef1234567890abcdef12345678",
        "git_dirty": False,
        "knowledge_base": "off",
        **overrides,
    }


def _wire(item: dict) -> str:
    """What `aws dynamodb get-item --output json` prints for `item`."""
    def attribute(value: object) -> dict:
        if isinstance(value, bool):
            return {"BOOL": value}
        return {"S": str(value)}

    return json.dumps({"Item": {key: attribute(value) for key, value in item.items()}})


def _run(
    *,
    stamp_output: str | None = None,
    read_error: Exception | None = None,
    summary: Path | None = None,
    argv: Sequence[str] = (),
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str, list[list[str]]]:
    calls: list[list[str]] = []

    def run(args: Sequence[str]) -> str:
        calls.append(list(args))
        if read_error is not None:
            raise read_error
        assert stamp_output is not None
        return stamp_output

    summary_args = ["--summary", str(summary)] if summary is not None else []
    code = check.main([*argv, *summary_args], run=run, code_hash=_code_hash)
    return code, capsys.readouterr().out, calls


def test_a_table_that_holds_the_code_seed_is_reported_in_agreement(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    summary = tmp_path / "summary.md"
    code, out, _ = _run(stamp_output=_wire(_stamp()), summary=summary, capsys=capsys)

    assert code == 0
    assert "::warning" not in out
    written = summary.read_text(encoding="utf-8")
    assert "Curriculum seed matches the code" in written
    assert CODE_HASHES["off"] in written
    assert "1234567890ab" in written
    assert "2026-11-09T10:00:00+00:00" in written


def test_the_code_hash_is_recomputed_in_the_mode_the_table_was_seeded_in(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stamp = _stamp(knowledge_base="live", seed_hash=CODE_HASHES["live"])
    code, out, _ = _run(stamp_output=_wire(stamp), capsys=capsys)

    assert code == 0
    assert "::warning" not in out
    assert "knowledge base: live" in out


def test_a_table_that_lags_the_code_is_a_warning_naming_both_hashes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    summary = tmp_path / "summary.md"
    stamp = _stamp(seed_hash="d" * 64, git_dirty=True)
    code, out, _ = _run(stamp_output=_wire(stamp), summary=summary, capsys=capsys)

    assert code == 0
    assert "::warning" in out
    written = summary.read_text(encoding="utf-8")
    assert "Curriculum seed lags the code" in written
    assert "scripts/seed_practice.py" in written
    assert CODE_HASHES["off"] in written
    assert "d" * 64 in written
    assert "1234567890abcdef1234567890abcdef12345678" in written
    assert "2026-11-09T10:00:00+00:00" in written
    assert "uncommitted changes" in written


def test_a_stamp_in_an_unknown_mode_lags_rather_than_crashing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    summary = tmp_path / "summary.md"
    code, out, _ = _run(
        stamp_output=_wire(_stamp(knowledge_base="sideways")), summary=summary, capsys=capsys
    )

    assert code == 0
    assert "::warning" in out
    assert "sideways" in summary.read_text(encoding="utf-8")


def test_no_stamp_row_is_a_warning_that_the_seed_never_ran(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    summary = tmp_path / "summary.md"
    code, out, _ = _run(stamp_output="{}", summary=summary, capsys=capsys)

    assert code == 0
    assert "::warning" in out
    written = summary.read_text(encoding="utf-8")
    assert "Curriculum seed lags the code" in written
    assert "no seed stamp" in written
    assert "scripts/seed_practice.py" in written
    assert CODE_HASHES["off"] in written


def test_a_read_that_fails_is_a_warning_that_says_it_is_not_a_mismatch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    summary = tmp_path / "summary.md"
    error = check.CommandError("AccessDeniedException: not authorized to perform GetItem")
    code, out, _ = _run(read_error=error, summary=summary, capsys=capsys)

    assert code == 0
    assert "::warning" in out
    written = summary.read_text(encoding="utf-8")
    assert "could not be read" in written
    assert "not a mismatch" in written
    assert "AccessDeniedException" in written
    assert "lags the code" not in written


def test_an_answer_that_is_not_json_is_a_read_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    summary = tmp_path / "summary.md"
    code, out, _ = _run(stamp_output="<html>", summary=summary, capsys=capsys)

    assert code == 0
    assert "::warning" in out
    assert "could not be read" in summary.read_text(encoding="utf-8")


def test_a_hash_that_cannot_be_computed_still_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    summary = tmp_path / "summary.md"

    def broken(_mode: str) -> str:
        raise ValueError("UNIT#x: the seed does not own colour")

    code = check.main(
        ["--summary", str(summary)], run=lambda _args: _wire(_stamp()), code_hash=broken
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "::warning" in out
    assert "the seed does not own colour" in summary.read_text(encoding="utf-8")


def test_the_stamp_is_one_consistent_get_item_on_the_production_table(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, _, calls = _run(stamp_output=_wire(_stamp()), capsys=capsys)

    [args] = calls
    assert args[:3] == ["aws", "dynamodb", "get-item"]
    assert args[args.index("--table-name") + 1] == "stoa-main"
    assert args[args.index("--region") + 1] == "eu-central-2"
    assert json.loads(args[args.index("--key") + 1]) == {
        "PK": {"S": "PRACTICE"},
        "SK": {"S": "CURRICULUM_SEED"},
    }
    assert "--consistent-read" in args
    assert "--profile" not in args


def test_an_operator_can_run_the_same_check_with_a_profile(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, _, calls = _run(
        stamp_output=_wire(_stamp()),
        argv=["--profile", "stoa", "--table", "stoa-other"],
        capsys=capsys,
    )

    [args] = calls
    assert args[args.index("--profile") + 1] == "stoa"
    assert args[args.index("--table-name") + 1] == "stoa-other"


def test_without_a_summary_file_the_result_still_goes_to_the_log(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    code, out, _ = _run(stamp_output="{}", capsys=capsys)

    assert code == 0
    assert "lags the code" in out


def test_the_summary_defaults_to_the_step_summary_of_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    summary = tmp_path / "step-summary.md"
    summary.write_text("earlier step\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    _run(stamp_output=_wire(_stamp()), capsys=capsys)

    written = summary.read_text(encoding="utf-8")
    assert written.startswith("earlier step\n")
    assert "Curriculum seed matches the code" in written


def test_the_real_code_hash_is_the_one_the_seed_prints() -> None:
    from scripts import seed_practice

    assert check.code_hash("off") == seed_practice.seed_hash(seed_practice.seed_rows())
    assert check.code_hash("live") == seed_practice.seed_hash(
        seed_practice.seed_rows(knowledge_base="live")
    )
