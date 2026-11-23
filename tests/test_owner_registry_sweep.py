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
from stoa.db import data_catalog, owner_registry
from stoa.db import table as db_table
from stoa.jobs import account_deletion as account_deletion_job
from stoa.services import owner_registry_sweep as sweep

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "backfill_owner_registry.py"

STUDENT = "8a1f0c52-0000-4000-8000-000000000001"
TEACHER = "8a1f0c52-0000-4000-8000-000000000002"
GONE = "8a1f0c52-0000-4000-8000-000000000003"
PARENT = "8a1f0c52-0000-4000-8000-000000000004"


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
        # A help request's teacher is a reviewed reference: the teacher's own
        # deletion takes the row.
        {"PK": "TEACHER_SUPPORT_CASE#k", "SK": "CASE", "student_id": STUDENT,
         "teacher_id": TEACHER, "entity_type": "help_request"},
        # The student's notification that went to the teacher: registered for
        # its owner, and no branch of the teacher's deletion takes it.
        {"PK": "NOTIFICATION#n1", "SK": "META", "entity_type": "notification_event",
         "owner_id": STUDENT, "recipient_id": TEACHER},
        owner_registry.registry_item(STUDENT, "NOTIFICATION#n1"),
        # Already registered.
        {"PK": "REPORT#r1", "SK": "META", "student_id": STUDENT},
        owner_registry.registry_item(STUDENT, "REPORT#r1"),
        # A student named by a scope string: a teacher's grant for them, in
        # the teacher's partition.
        {"PK": f"USER#{TEACHER}", "SK": "CAPABILITY_CURRENT#c#s", "user_id": TEACHER,
         "entity_type": "capability_grant_current", "scope": f"student:{STUDENT}"},
        # Not owned, whatever it mentions.
        {"PK": "SECURITY_AUDIT#abc", "SK": "EVENT#1", "user_id": STUDENT},
        # A deleted account: a leftover, a tombstone, its kept rows, a registry row.
        {"PK": "UPLOAD#u9", "SK": "META", "owner_id": GONE, "entity_type": "upload_intent"},
        {"PK": f"USER#{GONE}", "SK": "PROFILE", "user_id": GONE, "status": "deleted",
         "owner_deletion_generation": 2},
        {"PK": f"USER#{GONE}", "SK": "DELETE_COMMAND#x", "user_id": GONE},
        # Its invitation names it by `account_id` only, and holds an address and a name.
        {"PK": "ACCOUNT_INVITATION#d9", "SK": "META", "entity_type": "account_invitation",
         "account_id": GONE, "email": "gone@example.invalid", "full_name": "Gone Person"},
        {"PK": f"USER#{GONE}", "SK": "PROVIDER_REVOKE#00000000000000000002", "user_id": GONE,
         "generation": 2, "status": "complete"},
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
    assert result["unregistered_by_family"] == {"CONV/CONV": 1, "USER/CAPABILITY_CURRENT": 1,
                                                "TEACHER_SUPPORT_CASE/CASE": 2}
    assert {(s["account"], s["PK"], s["role"]) for s in result["unregistered_samples"]} == {
        (STUDENT, "CONV#c1", "owner"),
        (STUDENT, "TEACHER_SUPPORT_CASE#k", "owner"),
        (TEACHER, "TEACHER_SUPPORT_CASE#k", "reference"),
        (STUDENT, f"USER#{TEACHER}", "reference"),
    }
    assert table.calls["put_item"] == table.calls["transact_write_items"] == 0


def test_a_row_no_deletion_branch_takes_is_a_mention_not_a_missing_registration(table):
    """What closes the registry path is what it would miss, not every id in a row.

    The teacher's deletion leaves the student's notification alone on either
    path, so its `recipient_id` is no gap in the registry - while the same
    teacher on a help request is, because that deletion does take the request.
    """
    result = sweep.run(table=table).as_dict()

    assert result["unmatched_mentions"] == 1
    assert result["unmatched_mentions_by_family"] == {"NOTIFICATION/META": 1}
    assert result["unmatched_mention_samples"] == [
        {"PK": "NOTIFICATION#n1", "SK": "META", "account": TEACHER, "role": "reference"}
    ]
    assert (TEACHER, "TEACHER_SUPPORT_CASE#k") in {
        (sample["account"], sample["PK"]) for sample in result["unregistered_samples"]
    }


def test_a_mention_alone_leaves_the_registry_complete_and_is_never_backfilled():
    double = FakeTable()
    double.seed(
        _fence(STUDENT),
        _fence(TEACHER),
        {"PK": "NOTIFICATION#n1", "SK": "META", "entity_type": "notification_event",
         "owner_id": STUDENT, "recipient_id": TEACHER},
        owner_registry.registry_item(STUDENT, "NOTIFICATION#n1"),
    )
    before = _registry(double)

    report = sweep.run(table=double, write=True)

    assert report.registry_complete and report.registry_written == 0
    assert sum(report.mentions.values()) == 1
    assert _registry(double) == before


def test_a_row_the_catalog_names_below_the_top_level_is_a_missing_registration():
    """The scans are asked, and they read the data type catalog (#588).

    A recovery job's summary names the student only in its filters; the
    catalog says it is the student's, so deletion takes it and its partition
    has to be registered.
    """
    double = FakeTable()
    row = {
        "PK": "REPORT_RECOVERY_JOB#j1",
        "SK": "SUMMARY",
        "entity_type": "REPORT_RECOVERY_JOB",
        "filters": {"student_id": STUDENT},
    }
    double.seed(_fence(STUDENT), row)
    assert data_catalog.owns(row, STUDENT)

    report = sweep.run(table=double)

    assert report.unregistered == {"REPORT_RECOVERY_JOB/SUMMARY": 1}
    assert not report.mentions


def _recovery_target_event(parent: str, student: str) -> dict:
    return {
        "event_id": "e1",
        "event_at": "2026-11-21T10:00:00+00:00",
        "job_id": "j1",
        "action": "resend_email_target",
        "result": "success",
        "metadata": {"target_id": "t1", "parent_id": parent, "student_id": student},
    }


def test_a_recovery_audit_event_naming_a_parent_needs_its_registration():
    """The report branch takes the event for the parent its metadata names (#573)."""
    double = FakeTable()
    row = {
        "PK": "REPORT_RECOVERY_JOB#j1",
        "SK": "AUDIT#2026-11-21T10:00:00+00:00#e1",
        "entity_type": "REPORT_RECOVERY_JOB_AUDIT_EVENT",
        **_recovery_target_event(PARENT, STUDENT),
    }
    double.seed(
        _fence(STUDENT),
        _fence(PARENT),
        row,
        owner_registry.registry_item(STUDENT, "REPORT_RECOVERY_JOB#j1"),
    )

    report = sweep.run(table=double)

    assert report.unregistered == {"REPORT_RECOVERY_JOB/AUDIT": 1}
    assert report.unregistered_samples == [
        {"PK": row["PK"], "SK": row["SK"], "account": PARENT, "role": "reference"}
    ]


def test_a_recovery_job_and_its_audit_events_are_complete_without_a_backfill():
    """A parent named only as a target is registered by the event that names it (#573)."""
    from stoa.db.repositories import report_repo

    double = FakeTable()
    double.seed(_fence(STUDENT), _fence(PARENT))
    db_table.install(double)
    try:
        report_repo.put_recovery_job(
            {"job_id": "j1", "status": "queued", "filters": {"status": "failed"}},
            [{"target_id": "t1", "student_id": STUDENT, "parent_id": PARENT}],
        )
        report_repo.put_recovery_job_audit_event("j1", _recovery_target_event(PARENT, STUDENT))
    finally:
        db_table.install(None)

    report = sweep.run(table=double)

    assert report.registry_complete, report.as_dict()
    assert not report.unregistered


def test_a_scan_that_cannot_judge_the_row_counts_as_taking_it(monkeypatch):
    def refuses(account, *, table, maximum_pages):
        raise RuntimeError("cannot read this row")

    monkeypatch.setattr(sweep, "DELETION_SCANS", (refuses,))

    assert sweep.deletion_takes({"PK": "X#1", "SK": "META"}, STUDENT, table=FakeTable())


def test_every_deletion_scan_is_asked():
    """Each function that pages through `sweep_pages` to find an account's rows.

    A new deletion branch with its own scan has to be added to `DELETION_SCANS`,
    or a row only it takes would be filed as a mention.
    """
    import ast

    # Not an account's rows: the pending-command sweep (and the helper nested
    # in it). And the attachments branch, which pages inline and takes rows by
    # `owner_id` / `student_id` as `scan_owned_private_rows` does.
    not_a_row_scan = {
        "scan_pending_deletion_commands",
        "_scan_commands",
        "_attachments_branch",
    }
    callers: set[str] = set()
    for path in (ROOT / "src" / "stoa").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for call in ast.walk(node):
                target = getattr(call, "func", None)
                name = getattr(target, "attr", None) or getattr(target, "id", None)
                if isinstance(call, ast.Call) and name == "sweep_pages":
                    callers.add(node.name)
    assert callers - not_a_row_scan == {scan.__name__ for scan in sweep.DELETION_SCANS}


def test_the_sweep_finds_a_deleted_accounts_leftovers_and_registry(table):
    report = sweep.run(table=table)

    assert report.leftovers == {"UPLOAD/META": 1, "ACCOUNT_INVITATION/META": 1}
    assert sorted(report.leftover_samples, key=lambda key: key["PK"]) == [
        {"PK": "ACCOUNT_INVITATION#d9", "SK": "META"},
        {"PK": "UPLOAD#u9", "SK": "META"},
    ]
    assert report.registry_of_deleted_accounts == 1
    assert report.deleted_accounts == 1 and report.accounts == 3


def test_apply_writes_exactly_the_missing_rows_and_is_idempotent(table):
    first = sweep.run(table=table, write=True)
    written = _registry(table)

    assert first.registry_written == 4
    assert (f"USER#{STUDENT}", "OWNS#CONV#c1") in written
    assert (f"USER#{TEACHER}", "REFERENCED_IN#TEACHER_SUPPORT_CASE#k") in written
    assert (f"USER#{STUDENT}", f"REFERENCED_IN#USER#{TEACHER}") in written

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
    assert marker["missing_registrations"] == 4 and marker["leftover_rows"] == 2
    assert marker["unmatched_mentions"] == 1
    assert summary["missing_registrations"] == 4 and summary["leftover_rows"] == 2
    assert "owner_registry_sweep_findings" in caplog.text
    assert STUDENT not in json.dumps(marker, default=str)
    # Keys and counts only: no row contents in what is logged.
    assert "owner_id" not in caplog.text


def test_the_daily_job_logs_a_mention_without_raising_a_finding(caplog):
    double = FakeTable()
    double.seed(
        _fence(STUDENT),
        _fence(TEACHER),
        {"PK": "NOTIFICATION#n1", "SK": "META", "entity_type": "notification_event",
         "owner_id": STUDENT, "recipient_id": TEACHER},
        owner_registry.registry_item(STUDENT, "NOTIFICATION#n1"),
    )
    db_table.install(double)
    try:
        with caplog.at_level("INFO"):
            summary = account_deletion_job.handler({"job": "owner_registry_sweep"}, None)
    finally:
        db_table.install(None)

    marker = double.rows[(sweep.RUN_MARKER_KEY["PK"], sweep.RUN_MARKER_KEY["SK"])]
    assert marker["missing_registrations"] == 0 and marker["unmatched_mentions"] == 1
    assert summary["registry_complete"] is True
    assert "owner_registry_sweep_mentions count=1" in caplog.text
    # The alarm's metric filter matches these three, and none was logged.
    for alarming in (
        "owner_registry_sweep_findings",
        "owner_registry_sweep_incomplete",
        "owner_registry_sweep_marker_failed",
    ):
        assert alarming not in caplog.text


# -- what the audit added -----------------------------------------------------------------


def _legacy_signal(digest: str, public_id: str) -> dict:
    from stoa.db.repositories import curriculum_analytics_repo

    return {
        "PK": f"CURRICULUM_SIGNAL#{public_id}", "SK": "SIGNAL#2026#s1",
        "entity_type": curriculum_analytics_repo.SIGNAL_ENTITY,
        "metadata": {"studentHash": digest},
    }


def test_a_legacy_curriculum_signal_names_no_one():
    """Deletion no longer looks a signal up by its `studentHash` (#586 decision 3, #588).

    None were left in production on 2026-11-23. The sweep asks the same
    scans, so such a signal is neither a missing registration nor a leftover.
    """
    double = FakeTable()
    double.seed(_fence(STUDENT), _fence(GONE, status="deleted"),
                _legacy_signal("student:0123456789ab", "p1"),
                _legacy_signal("student:ba9876543210", "p2"))

    report = sweep.run(table=double, write=True)

    assert not report.unregistered and not report.leftovers
    assert report.registry_complete


def test_teacher_activation_commands_are_a_reviewed_exclusion():
    double = FakeTable()
    double.seed(_fence(TEACHER), _fence(GONE, status="deleted"),
                {"PK": "TEACHER_ACTIVATION#c1", "SK": "COMMAND", "user_id": TEACHER,
                 "entity_type": "teacher_activation_command"},
                {"PK": "TEACHER_ACTIVATION#c2", "SK": "COMMAND", "user_id": GONE,
                 "entity_type": "teacher_activation_command"})

    report = sweep.run(table=double)

    assert not report.unregistered and not report.leftovers


# -- stale references into a deleted account ---------------------------------------


def _with_references_into_a_deleted_account() -> FakeTable:
    double = FakeTable()
    double.seed(
        _fence(STUDENT),
        _fence(TEACHER),
        _fence(GONE, status="deleted"),
        # What deletion keeps of the account: nothing in it names anyone else.
        {"PK": f"USER#{GONE}", "SK": "PROFILE", "user_id": GONE, "status": "deleted",
         "owner_deletion_generation": 2},
        # True once, when the profile named its inviter; nothing removed it.
        owner_registry.registry_item(TEACHER, f"USER#{GONE}", owner_registry.ROLE_REFERENCE),
        # Still true: a row in the deleted account's partition names the student.
        {"PK": f"PROGRESS#{GONE}", "SK": "SHARED#1", "entity_type": "shared_note",
         "reviewer_id": STUDENT},
        owner_registry.registry_item(STUDENT, f"PROGRESS#{GONE}", owner_registry.ROLE_REFERENCE),
        # A reference into a living account's partition is not this finding.
        {"PK": f"USER#{STUDENT}", "SK": "PROFILE", "user_id": STUDENT, "invited_by": TEACHER},
        owner_registry.registry_item(TEACHER, f"USER#{STUDENT}", owner_registry.ROLE_REFERENCE),
    )
    return double


def test_the_sweep_lists_a_registry_row_that_points_into_a_deleted_account():
    table = _with_references_into_a_deleted_account()

    report = sweep.run(table=table)

    assert report.stale_references == [
        {"PK": f"USER#{TEACHER}", "SK": f"REFERENCED_IN#USER#{GONE}"}
    ]
    assert report.as_dict()["stale_references"] == 1
    assert table.calls["put_item"] == table.calls["delete_item"] == 0


def test_a_resumed_walk_lists_no_stale_reference():
    table = _with_references_into_a_deleted_account()
    table.page_item_cap = 2
    first = sweep.run(table=table, max_pages=1)

    resumed = sweep.run(table=table, start=first.last_key)

    assert resumed.complete and resumed.stale_references == []


def test_the_daily_job_removes_only_the_stale_reference():
    table = _with_references_into_a_deleted_account()
    db_table.install(table)
    try:
        before = dict(table.rows)
        summary = account_deletion_job.handler({"job": "owner_registry_sweep"}, None)
    finally:
        db_table.install(None)

    table.rows.pop((sweep.RUN_MARKER_KEY["PK"], sweep.RUN_MARKER_KEY["SK"]))
    gone = set(before) - set(table.rows)
    assert gone == {(f"USER#{TEACHER}", f"REFERENCED_IN#USER#{GONE}")}
    assert summary["stale_references_removed"] == 1
    assert sweep.run(table=table).stale_references == []
