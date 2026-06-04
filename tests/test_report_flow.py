import json
from datetime import datetime, timezone

import pytest

from stoa.jobs import weekly_reports
from stoa.services import notify_service, report_service


class FakeDataTable:
    def __init__(self):
        self.scans = []
        self.queries = []
        self.student = {
            "user_id": "student-1",
            "parent_id": "parent-1",
            "role": "student",
            "email": "student@example.com",
            "name": "Student One",
            "grade": "6",
        }

    def scan(self, **kwargs):
        self.scans.append(kwargs)
        names = kwargs["ExpressionAttributeNames"]
        values = kwargs["ExpressionAttributeValues"]
        assert names["#role"] == "role"
        assert values[":role"] == "student"
        if "#pid" in names:
            assert names["#pid"] == "parent_id"
            if ":pid" in values:
                assert values[":pid"] == "parent-1"
            else:
                assert "attribute_exists(#pid)" in str(kwargs["FilterExpression"])
        return {"Items": [self.student]}

    def query(self, **kwargs):
        self.queries.append(kwargs)
        assert kwargs["IndexName"] == "GSI-StudentId"
        assert kwargs["Limit"] == 100
        assert kwargs["ScanIndexForward"] is False
        return {
            "Items": [
                {
                    "conversation_id": "conv-1",
                    "student_id": "student-1",
                    "entity_type": "conversation",
                    "escalated": True,
                    "subject": "math",
                    "updated_at": "2026-06-06T08:00:00Z",
                    "last_message_preview": "Need help with fractions",
                }
            ]
        }


class FailingBedrockClient:
    def __init__(self, events):
        self.events = events

    def invoke_model(self, **kwargs):
        self.events.append(("bedrock", kwargs["modelId"]))
        raise RuntimeError("bedrock unavailable")


class RecordingS3Client:
    def __init__(self, events, *, fail_on_call: int | None = None):
        self.events = events
        self.fail_on_call = fail_on_call
        self.puts = []
        self.deletes = []

    def put_object(self, **kwargs):
        self.puts.append(kwargs)
        self.events.append(("s3", kwargs["Key"]))
        if self.fail_on_call == len(self.puts):
            raise RuntimeError("s3 unavailable")

    def delete_object(self, **kwargs):
        self.deletes.append(kwargs)
        self.events.append(("s3_delete", kwargs["Key"]))


class RecordingSESClient:
    def __init__(self, events, *, error: Exception | None = None):
        self.events = events
        self.error = error
        self.emails = []

    def send_email(self, **kwargs):
        self.emails.append(kwargs)
        self.events.append(("ses", kwargs["Destination"]["ToAddresses"]))
        if self.error:
            raise self.error


def test_backend_weekly_report_flow_generates_stores_and_emails_with_fakes(monkeypatch):
    events = []
    reports_by_id = {}
    question_last_keys = []
    data_table = FakeDataTable()
    s3 = RecordingS3Client(events)
    ses = RecordingSESClient(events)

    monkeypatch.setattr(report_service.settings, "s3_reports_bucket", "reports-bucket")
    monkeypatch.setattr(weekly_reports, "get_table", lambda: data_table)
    monkeypatch.setattr(report_service, "get_table", lambda: data_table)
    monkeypatch.setattr(
        report_service.user_repo,
        "get_user",
        lambda user_id: {"user_id": user_id, "email": "parent@example.com", "name": "Parent One"},
    )

    question_pages = [
        {
            "Items": [
                {
                    "question_id": "q1",
                    "student_id": "student-1",
                    "status": "ai_answered",
                    "subject": "math",
                    "knowledge_points": ["fractions"],
                    "created_at": "2026-06-02T10:00:00Z",
                    "summary": "Fractions question",
                }
            ],
            "LastEvaluatedKey": {"PK": "QUESTION#q1"},
        },
        {
            "Items": [
                {
                    "question_id": "q2",
                    "student_id": "student-1",
                    "status": "teacher_requested",
                    "subject": "math",
                    "knowledge_points": ["ratios"],
                    "created_at": "2026-06-03T10:00:00Z",
                    "summary": "Ratios question",
                }
            ]
        },
    ]

    def list_questions(student_id, limit=500, last_key=None):
        question_last_keys.append(last_key)
        return question_pages.pop(0)

    monkeypatch.setattr(report_service.question_repo, "list_by_student", list_questions)
    monkeypatch.setattr(
        report_service.practice_repo,
        "get_progress",
        lambda student_id: [
            {
                "lesson_id": "lesson-1",
                "status": "completed",
                "subject_id": "math",
                "topic_id": "fractions",
                "completed_at": "2026-06-04T08:00:00Z",
            }
        ],
    )
    monkeypatch.setattr(
        report_service.practice_repo,
        "get_mistakes",
        lambda student_id: [
            {
                "challenge_id": "challenge-1",
                "subject_id": "math",
                "topic_id": "fractions",
                "created_at": "2026-06-05T08:00:00Z",
            }
        ],
    )

    monkeypatch.setattr(
        weekly_reports.report_repo,
        "get_report_for_child_by_week",
        lambda parent_id, student_id, week_start: None,
    )

    def claim_report(item):
        assert item["report_id"] == "weekly-report-parent-1-student-1-2026-06-01"
        assert item["parent_id"] == "parent-1"
        assert item["student_id"] == "student-1"
        assert item["week_start"] == "2026-06-01"
        assert item["status"] == "generation_claimed"
        assert item["email_status"] == "not_started"
        events.append(("claim", item["report_id"]))
        reports_by_id[item["report_id"]] = item
        return True

    def put_report(item):
        assert item["report_id"] == "weekly-report-parent-1-student-1-2026-06-01"
        events.append(("put_report", item["status"]))
        reports_by_id[item["report_id"]] = item

    def update_report_status(report_id, status, **fields):
        assert report_id == "weekly-report-parent-1-student-1-2026-06-01"
        events.append(("update", status))
        reports_by_id[report_id] = {**reports_by_id[report_id], "status": status, **fields}

    monkeypatch.setattr(weekly_reports.report_repo, "try_claim_report_generation", claim_report)
    monkeypatch.setattr(report_service.report_repo, "put_report", put_report)
    monkeypatch.setattr(report_service.report_repo, "update_report_status", update_report_status)

    def fake_boto_client(service_name, **kwargs):
        if service_name == "bedrock-runtime":
            return FailingBedrockClient(events)
        if service_name == "s3":
            return s3
        if service_name == "ses":
            return ses
        raise AssertionError(f"unexpected boto client {service_name}")

    monkeypatch.setattr(report_service.boto3, "client", fake_boto_client)
    monkeypatch.setattr(notify_service.boto3, "client", fake_boto_client)

    result = weekly_reports.run_weekly_report_job({"week_start": "2026-06-01"})

    assert result == {
        "status": "completed",
        "week_start": "2026-06-01",
        "attempted": 1,
        "generated": 1,
        "skipped_existing": 0,
        "email_sent": 1,
        "failed": 0,
    }
    assert question_last_keys == [None, {"PK": "QUESTION#q1"}]
    assert len(data_table.scans) == 2
    assert len(data_table.queries) == 1
    assert [event[0] for event in events] == [
        "claim",
        "bedrock",
        "s3",
        "s3",
        "put_report",
        "ses",
        "update",
    ]

    report = reports_by_id["weekly-report-parent-1-student-1-2026-06-01"]
    assert report["status"] == "email_sent"
    assert report["email_status"] == "sent"
    assert report["stats"] == {
        "questionsAsked": 2,
        "aiResolved": 1,
        "teacherHelpRequests": 2,
        "practiceLessonsCompleted": 1,
        "mistakesLogged": 1,
    }
    assert report["summary"].startswith("During 2026-06-01 to 2026-06-07")
    assert report["weak_knowledge_points"][:3] == ["math", "fractions", "ratios"]
    assert len(s3.puts) == 2
    artifact = json.loads(s3.puts[0]["Body"].decode())
    assert artifact["report"]["status"] == "generated"
    assert artifact["content"]["summary"] == report["summary"]
    assert ses.emails[0]["Destination"]["ToAddresses"] == ["parent@example.com"]


def test_store_and_send_weekly_report_does_not_write_metadata_or_email_when_s3_fails(monkeypatch):
    events = []

    monkeypatch.setattr(report_service.settings, "s3_reports_bucket", "reports-bucket")
    monkeypatch.setattr(
        report_service.report_repo,
        "put_report",
        lambda item: events.append(("put_report", item["status"])),
    )
    monkeypatch.setattr(
        report_service.report_repo,
        "update_report_status",
        lambda report_id, status, **fields: events.append(("update", status)),
    )

    s3 = RecordingS3Client(events, fail_on_call=2)
    ses = RecordingSESClient(events)
    with pytest.raises(RuntimeError, match="s3 unavailable"):
        report_service.store_and_send_weekly_report(
            _sample_report_payload(),
            _generated_report_content(),
            s3_client=s3,
            ses_client=ses,
        )

    assert [event[0] for event in events] == ["s3", "s3", "s3_delete"]
    assert len(s3.puts) == 2
    assert s3.puts[0]["Key"] == "weekly-reports/parent-1/student-1/2026-06-01/report.json"
    assert s3.puts[1]["Key"] == "weekly-reports/parent-1/student-1/2026-06-01/report.html"
    assert s3.deletes == [
        {
            "Bucket": "reports-bucket",
            "Key": "weekly-reports/parent-1/student-1/2026-06-01/report.json",
        }
    ]
    assert ses.emails == []


def test_previous_zurich_week_start_uses_zurich_calendar_boundary():
    result = weekly_reports.previous_zurich_week_start(
        datetime(2026, 6, 7, 22, 30, tzinfo=timezone.utc)
    )

    assert result.isoformat() == "2026-06-01"


def _sample_report_payload():
    return {
        "parent": {"id": "parent-1", "email": "parent@example.com", "name": "Parent"},
        "student": {"id": "student-1", "email": "student@example.com", "name": "Student", "grade": "6"},
        "week": {"start": "2026-06-01", "end": "2026-06-07"},
        "metrics": {
            "questionsAsked": 1,
            "aiResolved": 1,
            "teacherHelpRequests": 0,
            "practiceLessonsCompleted": 0,
            "mistakesLogged": 0,
        },
        "weakTopics": [],
        "activities": [],
        "sourceCounts": {"questions": 1, "practiceProgress": 0, "mistakes": 0, "conversations": 0},
    }


def _generated_report_content():
    return {
        "summary": "Student made steady progress this week.",
        "strengths": ["Asked a thoughtful question."],
        "weakTopics": [],
        "recommendations": ["Continue the next practice activity."],
        "teacherNote": None,
    }
