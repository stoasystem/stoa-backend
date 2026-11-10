from html import escape
import json
from datetime import date, datetime, timezone

import pytest

from fakes import student_evidence as fake_evidence
from fakes.links import LinkRows
from stoa import aws
from stoa import config
from stoa.aws import Kind
from stoa.db import table as db_table
from stoa.config import Settings
from stoa.services import message_catalog, report_service


@pytest.fixture(autouse=True)
def _fenced_report_provider_compat(monkeypatch):
    # Delivery judges the recipient again; the judge has its own tests in
    # test_current_relationship.py, so here the parent is simply current.
    monkeypatch.setattr(
        report_service.current_relationship,
        "current_parent_recipient",
        lambda _parent_id, _student_id: report_service.current_relationship.ParentRecipient(
            email="parent@example.com"
        ),
    )
    monkeypatch.setattr(
        report_service.account_deletion_repo,
        "require_active_account_fence",
        lambda _owner: {"status": "active", "generation": 7},
    )
    monkeypatch.setattr(
        report_service.report_artifact_service,
        "write_fenced_report_artifacts",
        lambda keys, json_artifact, html_artifact, **kwargs: report_service.report_artifact_service.write_report_artifacts(
            keys, json_artifact, html_artifact
        ),
    )
    monkeypatch.setattr(
        report_service.notify_service,
        "send_fenced_weekly_report_email",
        lambda parent_email, report_html, **kwargs: (
            report_service.notify_service.send_weekly_report_email(
                parent_email,
                report_html,
                subject=kwargs.get("subject"),
            )
            or "accepted"
        ),
    )


class FakeTable:
    """The report's own reads; any other read goes to the link table, when there is one.

    The link rows and the report's rows are read through the same table gateway
    (#327), so one double answers both.
    """

    def __init__(self, children=None, conversations=None, links=None):
        self.children = children or []
        self.conversations = conversations or []
        self.links = links

    def scan(self, **kwargs):
        return {"Items": self.children}

    def query(self, **kwargs):
        if self.links is not None and "IndexName" not in kwargs:
            return self.links.query(**kwargs)
        return {"Items": self.conversations}

    def get_item(self, **kwargs):
        return self.links.get_item(**kwargs)

    def transact_write_items(self, **kwargs):
        return self.links.transact_write_items(**kwargs)


class FakeBody:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()


class FakeBedrockClient:
    def __init__(self, text=None, error=None):
        self.text = text
        self.error = error
        self.calls = []

    def invoke_model(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return {"body": FakeBody({"content": [{"text": self.text}]})}


class FakeS3Client:
    def __init__(self, events=None):
        self.events = events if events is not None else []
        self.puts = []

    def put_object(self, **kwargs):
        self.events.append(("s3", kwargs["Key"]))
        self.puts.append(kwargs)


class FakeSESClient:
    def __init__(self, events=None, error=None):
        self.events = events if events is not None else []
        self.error = error
        self.emails = []

    def send_email(self, **kwargs):
        self.events.append(("ses", kwargs["Destination"]["ToAddresses"]))
        self.emails.append(kwargs)
        if self.error:
            raise self.error


def _production_settings(**overrides) -> Settings:
    values = {
        "environment": "production",
        "cognito_allowed_issuers": ["https://identity.test"],
        "cognito_access_client_ids": ["test-access-client"],
        "authorization_audit_active_key_id": "test-production-v1",
        "authorization_audit_active_key": "test-production-authorization-audit-key-32-bytes",
        "stripe_checkout_web_origins": ["https://app.stoaedu.ch"],
        **overrides,
    }
    return Settings(**values)


def patch_sources(monkeypatch, *, children=None, questions=None, progress=None, mistakes=None, conversations=None):
    # `children` seeds the link rows the judge reads, not a profile scan: a
    # child listed with a non-active `parent_binding_status` stays unlinked,
    # which is the point of the defect these cover.
    links = LinkRows()
    db_table.install(FakeTable(children=children, conversations=conversations, links=links.table))
    students = {}
    for child in children or []:
        student_id = child.get("user_id") or child.get("id")
        students[student_id] = {**child, "role": "student", "account_status": "active"}
        parent_id = child.get("parent_id")
        if parent_id and (child.get("parent_binding_status") or "active") == "active":
            links.link(parent_id, student_id)

    def _get_user(user_id, **_kwargs):
        if user_id in students:
            return dict(students[user_id])
        return {
            "user_id": user_id,
            "email": f"{user_id}@example.com",
            "name": "Parent",
            "role": "parent",
            "account_status": "active",
        }

    monkeypatch.setattr(report_service.user_repo, "get_user", _get_user)
    monkeypatch.setattr(
        report_service.question_repo,
        "list_by_student",
        lambda student_id, limit=500, last_key=None: {"Items": questions or []},
    )
    # Every student reads as these lessons and these wrong answers.
    monkeypatch.setattr(
        report_service.student_evidence,
        "for_student",
        lambda student_id, **_kwargs: fake_evidence.evidence(
            student_id, progress=progress or [], attempts=mistakes or []
        ),
    )


def test_report_week_window_accepts_iso_date():
    start, end = report_service.report_week_window("2026-06-01")

    assert start == date(2026, 6, 1)
    assert end == date(2026, 6, 8)


def test_report_week_window_rejects_invalid_date():
    with pytest.raises(ValueError):
        report_service.report_week_window("not-a-date")


def test_report_artifacts_bucket_allows_local_placeholder_in_development():
    settings = Settings(environment="development", s3_reports_bucket="stoa-reports")

    assert settings.report_artifacts_bucket == "stoa-reports"


def test_report_artifacts_bucket_rejects_production_placeholder():
    settings = _production_settings(s3_reports_bucket="stoa-reports")

    with pytest.raises(ValueError, match="S3_REPORTS_BUCKET"):
        _ = settings.report_artifacts_bucket


def test_report_artifacts_bucket_rejects_blank_production_value():
    settings = _production_settings(s3_reports_bucket=" ")

    with pytest.raises(ValueError, match="S3_REPORTS_BUCKET"):
        _ = settings.report_artifacts_bucket


def test_report_artifacts_bucket_returns_trimmed_cdk_value_in_production():
    settings = _production_settings(
        s3_reports_bucket=" stoa-reports-562923011260 ",
    )

    assert settings.report_artifacts_bucket == "stoa-reports-562923011260"


def test_empty_aggregation_returns_zero_payload(monkeypatch):
    patch_sources(
        monkeypatch,
        children=[
            {
                "user_id": "student-1",
                "parent_id": "parent-1",
                "role": "student",
                "email": "student@example.com",
                "name": "Student",
            }
        ],
    )

    payload = report_service.build_weekly_learning_payload("parent-1", "student-1", "2026-06-01")

    assert payload["metrics"] == {
        "questionsAsked": 0,
        "aiResolved": 0,
        "teacherHelpRequests": 0,
        "practiceLessonsCompleted": 0,
        "mistakesLogged": 0,
    }
    assert payload["weakTopics"] == []
    assert payload["activities"] == []
    assert payload["sourceCounts"] == {
        "questions": 0,
        "practiceProgress": 0,
        "mistakes": 0,
        "conversations": 0,
    }


def test_mixed_weekly_activity_aggregates_metrics_and_topics(monkeypatch):
    patch_sources(
        monkeypatch,
        children=[
            {
                "user_id": "student-1",
                "parent_id": "parent-1",
                "role": "student",
                "email": "student@example.com",
                "name": "Student",
                "grade": "6",
            }
        ],
        questions=[
            {
                "PK": "QUESTION#q1",
                "SK": "META",
                "question_id": "q1",
                "student_id": "student-1",
                "status": "ai_answered",
                "subject": "math",
                "knowledge_points": ["fractions"],
                "created_at": "2026-06-02T10:00:00Z",
                "summary": "Fractions question",
            },
            {
                "PK": "QUESTION#q2",
                "SK": "META",
                "question_id": "q2",
                "student_id": "student-1",
                "status": "teacher_requested",
                "subject": "math",
                "knowledge_points": ["fractions", "ratios"],
                "created_at": "2026-06-03T10:00:00Z",
            },
            {
                "PK": "QUESTION#old",
                "SK": "META",
                "question_id": "old",
                "student_id": "student-1",
                "status": "ai_answered",
                "created_at": "2026-05-20T10:00:00Z",
            },
        ],
        progress=[
            {
                "lesson_id": "lesson-1",
                "status": "completed",
                "subject_id": "math",
                "topic_id": "fractions",
                "completed_at": "2026-06-04T08:00:00Z",
            }
        ],
        mistakes=[
            {
                "challenge_id": "challenge-1",
                "subject_id": "math",
                "topic_id": "fractions",
                "created_at": "2026-06-05T08:00:00Z",
            }
        ],
        conversations=[
            {
                "conversation_id": "conv-1",
                "student_id": "student-1",
                "entity_type": "conversation",
                "escalated": True,
                "subject": "math",
                "updated_at": "2026-06-06T08:00:00Z",
                "last_message_preview": "Need help",
            }
        ],
    )

    payload = report_service.build_weekly_learning_payload("parent-1", "student-1", "2026-06-01")

    assert payload["student"]["grade"] == "6"
    assert payload["metrics"] == {
        "questionsAsked": 2,
        "aiResolved": 1,
        "teacherHelpRequests": 2,
        "practiceLessonsCompleted": 1,
        "mistakesLogged": 1,
    }
    assert payload["weakTopics"][:2] == [
        {"topic": "fractions", "count": 3},
        {"topic": "math", "count": 3},
    ]
    assert [activity["id"] for activity in payload["activities"]][:2] == ["conv-1", "challenge-1"]


def test_unlinked_student_raises(monkeypatch):
    patch_sources(monkeypatch, children=[])

    with pytest.raises(ValueError, match="student is not linked"):
        report_service.build_weekly_learning_payload("parent-1", "student-1", "2026-06-01")


def sample_report_payload():
    return {
        "parent": {"id": "parent-1", "email": "parent@example.com", "name": "Parent"},
        "student": {"id": "student-1", "email": "student@example.com", "name": "Student", "grade": "6"},
        "week": {"start": "2026-06-01", "end": "2026-06-07"},
        "metrics": {
            "questionsAsked": 3,
            "aiResolved": 2,
            "teacherHelpRequests": 1,
            "practiceLessonsCompleted": 1,
            "mistakesLogged": 2,
        },
        "weakTopics": [{"topic": f"topic-{idx}", "count": idx} for idx in range(8)],
        "activities": [
            {
                "id": f"activity-{idx}",
                "type": "question",
                "title": "Question answered",
                "summary": "x" * 220,
                "subject": "math",
                "createdAt": f"2026-06-0{idx + 1}T10:00:00Z",
            }
            for idx in range(8)
        ],
        "sourceCounts": {"questions": 3, "practiceProgress": 1, "mistakes": 2, "conversations": 1},
    }


def test_bedrock_report_input_is_compact_and_bounded():
    report_input = report_service.build_bedrock_report_input(sample_report_payload())

    assert report_input["student"] == {"name": "Student", "grade": "6"}
    assert "email" not in report_input["student"]
    assert len(report_input["weakTopics"]) == 5
    assert len(report_input["activities"]) == 6
    assert len(report_input["activities"][0]["summary"]) == 160
    assert report_input["metrics"]["questionsAsked"] == 3


def test_parse_generated_report_json_accepts_valid_strict_json():
    parsed = report_service.parse_generated_report_json(
        json.dumps(
            {
                "summary": "Student made steady progress this week.",
                "strengths": ["Asked thoughtful questions."],
                "weakTopics": [{"topic": "fractions", "note": "Needs another review."}],
                "recommendations": ["Practice fractions for ten minutes."],
                "teacherNote": None,
            }
        )
    )

    assert parsed == {
        "summary": "Student made steady progress this week.",
        "strengths": ["Asked thoughtful questions."],
        "weakTopics": [{"topic": "fractions", "note": "Needs another review."}],
        "recommendations": ["Practice fractions for ten minutes."],
        "teacherNote": None,
    }


def test_parse_generated_report_json_rejects_markdown_wrapped_json():
    with pytest.raises(ValueError, match="strict JSON"):
        report_service.parse_generated_report_json(
            '```json\n{"summary":"ok","strengths":["x"],"weakTopics":[],"recommendations":["x"]}\n```'
        )


def test_parse_generated_report_json_rejects_internal_terms():
    with pytest.raises(ValueError, match="internal terms"):
        report_service.parse_generated_report_json(
            json.dumps(
                {
                    "summary": "This was generated by Bedrock.",
                    "strengths": ["Asked questions."],
                    "weakTopics": [],
                    "recommendations": ["Keep practicing."],
                }
            )
        )
    with pytest.raises(ValueError, match="internal terms"):
        report_service.parse_generated_report_json(
            json.dumps(
                {
                    "summary": "The AI model identified these implementation details.",
                    "strengths": ["Asked questions."],
                    "weakTopics": [],
                    "recommendations": ["Keep practicing."],
                }
            )
        )
    with pytest.raises(ValueError, match="internal terms"):
        report_service.parse_generated_report_json(
            json.dumps(
                {
                    "summary": "An AWS foundation model prepared this report.",
                    "strengths": ["Asked questions."],
                    "weakTopics": [],
                    "recommendations": ["Keep practicing."],
                }
            )
        )


def test_parse_generated_report_json_rejects_invalid_list_items():
    with pytest.raises(ValueError, match="invalid item"):
        report_service.parse_generated_report_json(
            json.dumps(
                {
                    "summary": "Student made steady progress.",
                    "strengths": ["Asked questions.", {}],
                    "weakTopics": [],
                    "recommendations": ["Keep practicing."],
                }
            )
        )
    with pytest.raises(ValueError, match="invalid item"):
        report_service.parse_generated_report_json(
            json.dumps(
                {
                    "summary": "Student made steady progress.",
                    "strengths": ["Asked questions."],
                    "weakTopics": ["fractions"],
                    "recommendations": ["Keep practicing."],
                }
            )
        )
    with pytest.raises(ValueError, match="invalid note"):
        report_service.parse_generated_report_json(
            json.dumps(
                {
                    "summary": "Student made steady progress.",
                    "strengths": ["Asked questions."],
                    "weakTopics": [{"topic": "fractions"}],
                    "recommendations": ["Keep practicing."],
                }
            )
        )


def test_generate_weekly_report_content_invokes_bedrock_with_structured_input():
    client = FakeBedrockClient(
        text=json.dumps(
            {
                "summary": "Student made steady progress.",
                "strengths": ["Completed practice."],
                "weakTopics": [{"topic": "topic-1", "note": "Review this next."}],
                "recommendations": ["Do one review session."],
                "teacherNote": "Teacher help was requested.",
            }
        )
    )

    aws.install({Kind.BEDROCK_RUNTIME: client})
    content = report_service.generate_weekly_report_content(sample_report_payload())

    assert content["summary"] == "Student made steady progress."
    assert len(client.calls) == 1
    request_body = json.loads(client.calls[0]["body"])
    user_input = json.loads(request_body["messages"][0]["content"])
    assert client.calls[0]["modelId"] == config.settings().bedrock_model_id
    assert user_input["metrics"]["questionsAsked"] == 3
    assert len(user_input["activities"]) == 6


def test_generate_weekly_report_content_falls_back_on_malformed_output():
    client = FakeBedrockClient(text="not json")

    aws.install({Kind.BEDROCK_RUNTIME: client})
    content = report_service.generate_weekly_report_content(sample_report_payload())

    assert content["summary"].startswith("During 2026-06-01 to 2026-06-07")
    assert content["weakTopics"][0] == {"topic": "topic-0", "note": "Seen in 0 weekly signal(s)."}
    assert content["teacherNote"] is not None


def test_generate_weekly_report_content_falls_back_on_bedrock_error():
    client = FakeBedrockClient(error=RuntimeError("boom"))
    payload = sample_report_payload()
    payload["metrics"] = {
        "questionsAsked": 0,
        "aiResolved": 0,
        "teacherHelpRequests": 0,
        "practiceLessonsCompleted": 0,
        "mistakesLogged": 0,
    }
    payload["weakTopics"] = []

    aws.install({Kind.BEDROCK_RUNTIME: client})
    content = report_service.generate_weekly_report_content(payload)

    assert content == {
        "summary": "No weekly learning activity was recorded for Student during 2026-06-01 to 2026-06-07.",
        "strengths": ["No specific strengths were recorded from this week's activity."],
        "weakTopics": [],
        "recommendations": ["Encourage one short practice session before the next weekly report."],
        "teacherNote": None,
    }


def generated_report_content():
    return {
        "summary": "Student made steady progress this week.",
        "strengths": ["Completed practice."],
        "weakTopics": [{"topic": "fractions", "note": "Review this next."}],
        "recommendations": ["Practice fractions for ten minutes."],
        "teacherNote": "Teacher help was requested.",
    }


def test_store_and_send_weekly_report_writes_artifacts_before_email(monkeypatch):
    events = []
    stored_items = []
    status_updates = []

    config.install(config.settings().model_copy(update={"s3_reports_bucket": "reports-bucket"}))
    monkeypatch.setattr(
        report_service.report_repo,
        "put_report",
        lambda item: events.append(("put_report", item["status"])) or stored_items.append(item),
    )
    monkeypatch.setattr(
        report_service.report_repo,
        "update_report_status",
        lambda report_id, status, **fields: status_updates.append((report_id, status, fields)),
    )

    s3 = FakeS3Client(events)
    ses = FakeSESClient(events)
    aws.install({Kind.S3: s3, Kind.SES: ses})
    result = report_service.store_and_send_weekly_report(
        sample_report_payload(),
        generated_report_content(),
        now=datetime(2026, 6, 8, tzinfo=timezone.utc),
    )

    assert [event[0] for event in events] == ["s3", "s3", "put_report", "ses"]
    assert result["status"] == "email_sent"
    assert result["email_status"] == "sent"
    assert stored_items[0]["status"] == "generated"
    assert stored_items[0]["summary"] == "Student made steady progress this week."
    assert stored_items[0]["recommendations"] == "Practice fractions for ten minutes."
    assert (
        stored_items[0]["s3_key"]
        == "weekly-reports/parent-1/student-1/2026-06-01/report.html"
    )
    assert (
        stored_items[0]["json_s3_key"]
        == "weekly-reports/parent-1/student-1/2026-06-01/report.json"
    )
    assert len(s3.puts) == 2
    assert s3.puts[0]["Bucket"] == "reports-bucket"
    assert s3.puts[0]["ContentType"] == "application/json"
    assert s3.puts[1]["ContentType"] == "text/html; charset=utf-8"
    assert "ACL" not in s3.puts[0]
    assert "ACL" not in s3.puts[1]
    assert json.loads(s3.puts[0]["Body"].decode())["content"]["summary"] == generated_report_content()["summary"]
    assert status_updates[0][1] == "email_sent"


def test_store_and_send_weekly_report_rejects_production_placeholder_bucket(monkeypatch):
    events = []

    config.install(
        config.settings().model_copy(
            update={"environment": "production", "s3_reports_bucket": "stoa-reports"}
        )
    )
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

    s3 = FakeS3Client(events)
    with pytest.raises(ValueError, match="S3_REPORTS_BUCKET"):
        aws.install({Kind.S3: s3, Kind.SES: FakeSESClient(events)})
        report_service.store_and_send_weekly_report(
            sample_report_payload(),
            generated_report_content(),
        )

    assert events == []
    assert s3.puts == []


def test_store_and_send_weekly_report_emails_parent_only(monkeypatch):
    config.install(config.settings().model_copy(update={"s3_reports_bucket": "reports-bucket"}))
    monkeypatch.setattr(report_service.report_repo, "put_report", lambda item: None)
    monkeypatch.setattr(report_service.report_repo, "update_report_status", lambda report_id, status, **fields: None)

    ses = FakeSESClient()
    aws.install({Kind.S3: FakeS3Client(), Kind.SES: ses})
    report_service.store_and_send_weekly_report(
        sample_report_payload(),
        generated_report_content(),
    )

    email = ses.emails[0]
    assert email["Source"] == "noreply@stoaedu.ch"
    assert email["Destination"]["ToAddresses"] == ["parent@example.com"]
    body = email["Message"]["Body"]["Html"]["Data"]
    assert "Student" in body
    # A parent with no stored language reads the default one (#278).
    assert message_catalog.text(
        "email.weekly_report.week_range", "de", start="2026-06-01", end="2026-06-07"
    ) in body
    assert generated_report_content()["summary"] in body
    assert "Practice fractions for ten minutes." in body
    assert "https://app.stoaedu.ch/parent/children/student-1/reports/2026-06-01" in body


@pytest.mark.parametrize("locale", ["de", "en", "fr", "it"])
def test_the_weekly_report_email_is_in_the_parents_language(monkeypatch, locale):
    # Sent by a job, read by the parent: the parent's stored language (#278).
    from stoa.db.repositories import user_repo

    config.install(config.settings().model_copy(update={"s3_reports_bucket": "reports-bucket"}))
    monkeypatch.setattr(report_service.report_repo, "put_report", lambda item: None)
    monkeypatch.setattr(report_service.report_repo, "update_report_status", lambda report_id, status, **fields: None)
    monkeypatch.setattr(
        user_repo,
        "get_user",
        lambda user_id, **_k: {"user_id": user_id, "preferred_locale": locale},
    )

    ses = FakeSESClient()
    aws.install({Kind.S3: FakeS3Client(), Kind.SES: ses})
    report_service.store_and_send_weekly_report(
        sample_report_payload(),
        generated_report_content(),
    )

    def copy(key, **values):
        return escape(message_catalog.text(f"email.weekly_report.{key}", locale, **values))

    message = ses.emails[0]["Message"]
    body = message["Body"]["Html"]["Data"]
    assert message["Subject"]["Data"] == message_catalog.text(
        "email.weekly_report.subject", locale, student="Student"
    )
    assert f'<html lang="{locale}">' in body
    assert copy("title", student="Student") in body
    assert copy("week") in body
    assert copy("week_range", start="2026-06-01", end="2026-06-07") in body
    assert copy("recommendations") in body
    assert copy("weak_topics") in body
    assert copy("portal_link") in body
    assert copy("teacher_note") in body


def test_a_report_that_names_no_student_names_the_parents_child():
    payload = sample_report_payload()
    payload["student"]["name"] = ""
    body = report_service.render_weekly_report_html(
        payload, generated_report_content(), locale="fr"
    )
    child = message_catalog.text("email.weekly_report.student_fallback", "fr")
    assert escape(message_catalog.text("email.weekly_report.title", "fr", student=child)) in body


def test_store_and_send_weekly_report_marks_email_failed_after_storage(monkeypatch):
    events = []
    stored_items = []
    status_updates = []

    config.install(config.settings().model_copy(update={"s3_reports_bucket": "reports-bucket"}))
    monkeypatch.setattr(
        report_service.report_repo,
        "put_report",
        lambda item: events.append(("put_report", item["status"])) or stored_items.append(item),
    )
    monkeypatch.setattr(
        report_service.report_repo,
        "update_report_status",
        lambda report_id, status, **fields: events.append(("update", status))
        or status_updates.append((report_id, status, fields)),
    )

    aws.install({
        Kind.S3: FakeS3Client(events),
        Kind.SES: FakeSESClient(events, error=RuntimeError("ses unavailable")),
    })
    result = report_service.store_and_send_weekly_report(
        sample_report_payload(),
        generated_report_content(),
    )

    assert [event[0] for event in events] == ["s3", "s3", "put_report", "ses", "update"]
    assert stored_items[0]["status"] == "generated"
    assert result["status"] == "email_failed"
    assert result["email_status"] == "failed"
    assert result["email_error_class"] == "RuntimeError"
    assert result["email_error_message"] == "ses unavailable"
    assert status_updates[0][1] == "email_failed"
    assert status_updates[0][2]["email_status"] == "failed"
