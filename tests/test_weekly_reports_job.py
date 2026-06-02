from datetime import datetime, timezone

import pytest

from stoa.jobs import weekly_reports


class FakeTable:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def scan(self, **kwargs):
        self.calls.append(kwargs)
        return self.pages.pop(0)


def test_previous_zurich_week_start_from_current_time():
    result = weekly_reports.previous_zurich_week_start(
        datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)
    )

    assert result.isoformat() == "2026-05-25"


def test_target_week_start_accepts_explicit_event_override():
    assert weekly_reports.target_week_start_from_event({"weekStart": "2026-06-01"}) == "2026-06-01"
    assert weekly_reports.target_week_start_from_event({"week_start": "2026-05-25"}) == "2026-05-25"


def test_target_week_start_uses_eventbridge_time():
    result = weekly_reports.target_week_start_from_event({"time": "2026-06-02T01:00:00Z"})

    assert result == "2026-05-25"


def test_discover_linked_parent_student_pairs_pages(monkeypatch):
    table = FakeTable(
        [
            {
                "Items": [
                    {"user_id": "student-1", "parent_id": "parent-1", "role": "student"},
                    {"user_id": "missing-parent", "role": "student"},
                ],
                "LastEvaluatedKey": {"PK": "USER#student-1"},
            },
            {"Items": [{"id": "student-2", "parent_id": "parent-2", "role": "student"}]},
        ]
    )
    monkeypatch.setattr(weekly_reports, "get_table", lambda: table)

    pairs = weekly_reports.discover_linked_parent_student_pairs()

    assert pairs == [
        {"parent_id": "parent-1", "student_id": "student-1"},
        {"parent_id": "parent-2", "student_id": "student-2"},
    ]
    assert table.calls[1]["ExclusiveStartKey"] == {"PK": "USER#student-1"}


@pytest.mark.parametrize("status", ["generated", "email_sent"])
def test_run_weekly_report_job_skips_existing_reports(monkeypatch, status):
    monkeypatch.setattr(
        weekly_reports,
        "discover_linked_parent_student_pairs",
        lambda: [{"parent_id": "parent-1", "student_id": "student-1"}],
    )
    monkeypatch.setattr(
        weekly_reports.report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week_start: {"status": status},
    )

    def fail(*args, **kwargs):
        raise AssertionError("generation pipeline should not run")

    monkeypatch.setattr(weekly_reports.report_service, "build_weekly_learning_payload", fail)

    result = weekly_reports.run_weekly_report_job({"week_start": "2026-06-01"})

    assert result == {
        "status": "completed",
        "week_start": "2026-06-01",
        "attempted": 0,
        "generated": 0,
        "skipped_existing": 1,
        "email_sent": 0,
        "failed": 0,
    }


def test_run_weekly_report_job_counts_existing_email_failed(monkeypatch):
    monkeypatch.setattr(
        weekly_reports,
        "discover_linked_parent_student_pairs",
        lambda: [{"parent_id": "parent-1", "student_id": "student-1"}],
    )
    monkeypatch.setattr(
        weekly_reports.report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week_start: {"status": "email_failed"},
    )

    def fail(*args, **kwargs):
        raise AssertionError("generation pipeline should not run")

    monkeypatch.setattr(weekly_reports.report_repo, "try_claim_report_generation", fail)
    monkeypatch.setattr(weekly_reports.report_service, "build_weekly_learning_payload", fail)

    result = weekly_reports.run_weekly_report_job({"week_start": "2026-06-01"})

    assert result["attempted"] == 0
    assert result["skipped_existing"] == 1
    assert result["failed"] == 1


def test_run_weekly_report_job_skips_when_atomic_claim_fails(monkeypatch):
    monkeypatch.setattr(
        weekly_reports,
        "discover_linked_parent_student_pairs",
        lambda: [{"parent_id": "parent-1", "student_id": "student-1"}],
    )
    monkeypatch.setattr(
        weekly_reports.report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week_start: None,
    )
    monkeypatch.setattr(weekly_reports.report_repo, "try_claim_report_generation", lambda claim: False)

    def fail(*args, **kwargs):
        raise AssertionError("generation pipeline should not run")

    monkeypatch.setattr(weekly_reports.report_service, "build_weekly_learning_payload", fail)

    result = weekly_reports.run_weekly_report_job({"week_start": "2026-06-01"})

    assert result["attempted"] == 0
    assert result["skipped_existing"] == 1
    assert result["generated"] == 0
    assert result["failed"] == 0


def test_run_weekly_report_job_processes_successful_pair(monkeypatch):
    calls = []
    monkeypatch.setattr(
        weekly_reports,
        "discover_linked_parent_student_pairs",
        lambda: [{"parent_id": "parent-1", "student_id": "student-1"}],
    )
    monkeypatch.setattr(
        weekly_reports.report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week_start: None,
    )
    monkeypatch.setattr(
        weekly_reports.report_service,
        "build_weekly_report_claim",
        lambda parent_id, student_id, week_start: {
            "report_id": f"{parent_id}-{student_id}-{week_start}",
            "parent_id": parent_id,
            "student_id": student_id,
            "week_start": week_start,
        },
    )
    monkeypatch.setattr(
        weekly_reports.report_repo,
        "try_claim_report_generation",
        lambda claim: calls.append(("claim", claim["report_id"])) or True,
    )

    def build_payload(parent_id, student_id, week_start):
        calls.append(("payload", parent_id, student_id, week_start))
        return {"payload": True}

    def generate(payload):
        calls.append(("generate", payload))
        return {"summary": "ok"}

    def store(payload, generated):
        calls.append(("store", payload, generated))
        return {"status": "email_sent", "email_status": "sent"}

    monkeypatch.setattr(weekly_reports.report_service, "build_weekly_learning_payload", build_payload)
    monkeypatch.setattr(weekly_reports.report_service, "generate_weekly_report_content", generate)
    monkeypatch.setattr(weekly_reports.report_service, "store_and_send_weekly_report", store)

    result = weekly_reports.run_weekly_report_job({"week_start": "2026-06-01"})

    assert result["attempted"] == 1
    assert result["generated"] == 1
    assert result["email_sent"] == 1
    assert result["failed"] == 0
    assert calls == [
        ("claim", "parent-1-student-1-2026-06-01"),
        ("payload", "parent-1", "student-1", "2026-06-01"),
        ("generate", {"payload": True}),
        ("store", {"payload": True}, {"summary": "ok"}),
    ]


def test_run_weekly_report_job_counts_pair_failure_and_continues(monkeypatch):
    status_updates = []
    monkeypatch.setattr(
        weekly_reports,
        "discover_linked_parent_student_pairs",
        lambda: [
            {"parent_id": "parent-1", "student_id": "student-1"},
            {"parent_id": "parent-2", "student_id": "student-2"},
        ],
    )
    monkeypatch.setattr(
        weekly_reports.report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week_start: None,
    )
    monkeypatch.setattr(weekly_reports.report_repo, "try_claim_report_generation", lambda claim: True)
    monkeypatch.setattr(
        weekly_reports.report_repo,
        "update_report_status",
        lambda report_id, status, **fields: status_updates.append((report_id, status, fields)),
    )

    def build_payload(parent_id, student_id, week_start):
        if student_id == "student-1":
            raise RuntimeError("bad payload")
        return {"payload": student_id}

    monkeypatch.setattr(weekly_reports.report_service, "build_weekly_learning_payload", build_payload)
    monkeypatch.setattr(weekly_reports.report_service, "generate_weekly_report_content", lambda payload: {"summary": "ok"})
    monkeypatch.setattr(
        weekly_reports.report_service,
        "store_and_send_weekly_report",
        lambda payload, generated: {"status": "email_failed", "email_status": "failed"},
    )

    result = weekly_reports.run_weekly_report_job({"week_start": "2026-06-01"})

    assert result == {
        "status": "completed",
        "week_start": "2026-06-01",
        "attempted": 2,
        "generated": 1,
        "skipped_existing": 0,
        "email_sent": 0,
        "failed": 2,
    }
    assert status_updates == [
        (
            "weekly-report-parent-1-student-1-2026-06-01",
            "generation_failed",
            {
                "generation_failed_at": status_updates[0][2]["generation_failed_at"],
                "generation_error_class": "RuntimeError",
                "generation_error_message": "bad payload",
                "updated_at": status_updates[0][2]["updated_at"],
            },
        )
    ]


def test_handler_accepts_eventbridge_scheduled_event(monkeypatch):
    monkeypatch.setattr(
        weekly_reports,
        "discover_linked_parent_student_pairs",
        lambda: [],
    )

    result = weekly_reports.handler({"source": "aws.scheduler", "time": "2026-06-02T01:00:00Z"}, None)

    assert result == {
        "status": "completed",
        "week_start": "2026-05-25",
        "attempted": 0,
        "generated": 0,
        "skipped_existing": 0,
        "email_sent": 0,
        "failed": 0,
    }
