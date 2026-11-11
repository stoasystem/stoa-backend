"""The owner registry's backfill script and daily sweep (#397, PR 2).

Both run the same two-scan walk against the in-memory table: report-only by
default, writing registry rows only when asked, resumable from a saved key.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from fakes.dynamodb import FakeTable
from stoa.db import owner_registry
from stoa.db import table as db_table
from stoa.jobs import account_deletion as account_deletion_job
from stoa.services import owner_registry_sweep as sweep

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "backfill_owner_registry.py"

STUDENT = "8a1f0c52-0000-4000-8000-000000000001"
TEACHER = "8a1f0c52-0000-4000-8000-000000000002"
GONE = "8a1f0c52-0000-4000-8000-000000000003"


def _fence(user_id: str, status: str = "active") -> dict:
    return {"PK": f"USER#{user_id}", "SK": "ACCOUNT_FENCE", "status": status, "generation": 2}


def _script():
    spec = importlib.util.spec_from_file_location("backfill_owner_registry", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def table() -> FakeTable:
    double = FakeTable(page_item_cap=3)
    double.seed(
        _fence(STUDENT),
        _fence(TEACHER),
        _fence(GONE, status="deleted"),
        # Derived: nothing to register.
        {"PK": f"USER#{STUDENT}", "SK": "PROFILE", "user_id": STUDENT},
        {"PK": f"ATTEMPTS#{STUDENT}", "SK": "ATTEMPT#1", "student_id": STUDENT},
        # Written before the dual-write: owner and reference unregistered.
        {"PK": "CONV#c1", "SK": "CONV", "owner_id": STUDENT, "entity_type": "conversation"},
        {"PK": "CONV#c1", "SK": "MSG#1", "entity_type": "message"},
        {"PK": "TEACHER_SUPPORT_CASE#k", "SK": "CASE", "student_id": STUDENT,
         "teacher_id": TEACHER},
        # Already registered.
        {"PK": "REPORT#r1", "SK": "META", "student_id": STUDENT},
        owner_registry.registry_item(STUDENT, "REPORT#r1"),
        # Ids inside a nested list and a scope string.
        {"PK": "MODERATION#m1", "SK": "CASE", "scope": f"student:{STUDENT}"},
        # Not owned, whatever it mentions.
        {"PK": "SECURITY_AUDIT#abc", "SK": "EVENT#1", "user_id": STUDENT},
        # A deleted account: a leftover, a tombstone, its kept rows, a registry row.
        {"PK": "UPLOAD#u9", "SK": "META", "owner_id": GONE},
        {"PK": f"USER#{GONE}", "SK": "PROFILE", "user_id": GONE, "status": "deleted",
         "owner_deletion_generation": 2},
        {"PK": f"USER#{GONE}", "SK": "DELETE_COMMAND#x", "user_id": GONE},
        owner_registry.registry_item(GONE, "UPLOAD#u9"),
    )
    return double


def _registry(table: FakeTable) -> set[tuple[str, str]]:
    return {key for key, row in table.rows.items() if owner_registry.is_registry_row(row)}


def test_a_dry_run_reports_and_writes_nothing(table):
    before = dict(table.rows)

    report = sweep.run(table=table)

    assert table.rows == before
    assert report.complete and not report.registry_complete
    result = report.as_dict()
    assert result["missing_registrations"] == 4
    assert result["unregistered_by_family"] == {"CONV/CONV": 1, "MODERATION/CASE": 1,
                                                "TEACHER_SUPPORT_CASE/CASE": 2}
    assert {(s["account"], s["PK"], s["role"]) for s in result["unregistered_samples"]} == {
        (STUDENT, "CONV#c1", "owner"),
        (STUDENT, "TEACHER_SUPPORT_CASE#k", "owner"),
        (TEACHER, "TEACHER_SUPPORT_CASE#k", "reference"),
        (STUDENT, "MODERATION#m1", "reference"),
    }
    assert table.calls["put_item"] == table.calls["transact_write_items"] == 0


def test_the_sweep_finds_a_deleted_accounts_leftovers_and_registry(table):
    report = sweep.run(table=table)

    assert report.leftovers == {"UPLOAD/META": 1}
    assert report.leftover_samples == [{"PK": "UPLOAD#u9", "SK": "META"}]
    assert report.registry_of_deleted_accounts == 1
    assert report.deleted_accounts == 1 and report.accounts == 3


def test_apply_writes_exactly_the_missing_rows_and_is_idempotent(table):
    first = sweep.run(table=table, write=True)
    written = _registry(table)

    assert first.registry_written == 4
    assert (f"USER#{STUDENT}", "OWNS#CONV#c1") in written
    assert (f"USER#{TEACHER}", "REFERENCED_IN#TEACHER_SUPPORT_CASE#k") in written
    assert (f"USER#{STUDENT}", "REFERENCED_IN#MODERATION#m1") in written

    second = sweep.run(table=table, write=True)
    assert second.registry_written == 0
    assert second.registry_complete
    assert _registry(table) == written


def test_a_run_stopped_part_way_resumes_from_its_last_key(table):
    partial = sweep.run(table=table, write=True, max_pages=2)
    assert not partial.complete and partial.last_key is not None

    rest = sweep.run(table=table, write=True, start=partial.last_key)

    assert rest.complete
    assert partial.registry_written + rest.registry_written == 4
    assert sweep.run(table=table).registry_complete


def test_the_sweep_only_reads_strongly_and_never_an_index(table):
    sweep.run(table=table)

    reads = [request for name, request in table.requests if name in {"scan", "query"}]
    assert reads and all(request.get("ConsistentRead") is True for request in reads)
    assert not any("IndexName" in request for request in reads)


def test_rows_from_the_dual_write_are_complete_without_a_backfill():
    double = FakeTable()
    double.seed(_fence(STUDENT), _fence(TEACHER))
    db_table.fenced(
        STUDENT,
        [{"Put": {"Item": {"PK": "TEACHER_SUPPORT_CASE#k", "SK": "CASE",
                           "student_id": STUDENT, "teacher_id": TEACHER}}}],
        also={TEACHER: None},
        table=double,
    )

    assert sweep.run(table=double).registry_complete


# -- the script ----------------------------------------------------------------------


def test_the_script_is_dry_run_by_default(table, capsys):
    before = dict(table.rows)

    assert _script().main([], table=table) == 0

    assert table.rows == before
    printed = json.loads(capsys.readouterr().out)
    assert printed["mode"] == "dry-run"
    assert printed["missing_registrations"] == 4


def test_the_script_applies_only_with_the_flag_and_resumes_from_its_state(table, tmp_path, capsys):
    state = tmp_path / "run.json"
    module = _script()

    assert module.main(["--apply", "--state", str(state), "--max-pages", "2"], table=table) == 0
    saved = json.loads(state.read_text())
    assert saved["complete"] is False and saved["last_key"]

    assert module.main(["--apply", "--state", str(state)], table=table) == 0
    assert json.loads(state.read_text())["complete"] is True
    assert sweep.run(table=table).registry_complete

    capsys.readouterr()
    assert module.main(["--apply", "--state", str(state)], table=table) == 0
    assert json.loads(capsys.readouterr().out)["complete"] is True


# -- the job ---------------------------------------------------------------------------


def test_the_daily_job_is_report_only_and_logs_findings(table, caplog):
    db_table.install(table)
    try:
        before = dict(table.rows)
        with caplog.at_level("WARNING"):
            summary = account_deletion_job.handler({"job": "owner_registry_sweep"}, None)
    finally:
        db_table.install(None)

    # Its one write is its own result row, counts only.
    marker = table.rows.pop((sweep.RUN_MARKER_KEY["PK"], sweep.RUN_MARKER_KEY["SK"]))
    assert table.rows == before
    assert marker["complete"] is True
    assert marker["missing_registrations"] == 4 and marker["leftover_rows"] == 1
    assert summary["missing_registrations"] == 4 and summary["leftover_rows"] == 1
    assert "owner_registry_sweep_findings" in caplog.text
    assert STUDENT not in json.dumps(marker, default=str)
    # Keys and counts only: no row contents in what is logged.
    assert "owner_id" not in caplog.text


# -- what the audit added -----------------------------------------------------------------


def _legacy_signal(student: str, public_id: str) -> dict:
    from stoa.db.repositories import curriculum_analytics_repo

    return {
        "PK": f"CURRICULUM_SIGNAL#{public_id}", "SK": "SIGNAL#2026#s1",
        "entity_type": curriculum_analytics_repo.SIGNAL_ENTITY,
        "metadata": {"studentHash": curriculum_analytics_repo._legacy_student_hash(student)},
    }


def test_legacy_curriculum_signals_are_found_by_their_student_hash():
    double = FakeTable()
    double.seed(_fence(STUDENT), _fence(GONE, status="deleted"),
                _legacy_signal(STUDENT, "p1"), _legacy_signal(GONE, "p2"))

    report = sweep.run(table=double, write=True)

    assert report.unregistered == {"CURRICULUM_SIGNAL/SIGNAL": 1}
    assert report.leftovers == {"CURRICULUM_SIGNAL/SIGNAL": 1}
    assert (f"USER#{STUDENT}", "OWNS#CURRICULUM_SIGNAL#p1") in _registry(double)
    assert sweep.run(table=double).registry_complete


def test_teacher_activation_commands_are_a_reviewed_exclusion():
    double = FakeTable()
    double.seed(_fence(TEACHER), _fence(GONE, status="deleted"),
                {"PK": "TEACHER_ACTIVATION#c1", "SK": "COMMAND", "user_id": TEACHER,
                 "entity_type": "teacher_activation_command"},
                {"PK": "TEACHER_ACTIVATION#c2", "SK": "COMMAND", "user_id": GONE,
                 "entity_type": "teacher_activation_command"})

    report = sweep.run(table=double)

    assert not report.unregistered and not report.leftovers
