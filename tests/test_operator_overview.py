"""#386: the read-only overview an agent may ask for - teacher applications, review
queues and weekly-report email delivery - and nothing a stored row holds besides."""

from __future__ import annotations

from typing import Any

import pytest

from stoa.db.repositories import security_audit_repo
from stoa.operator_calls import catalog, entry


ACCOUNT_ID = "562923011260"
FUNCTION_ARN = f"arn:aws:lambda:eu-central-2:{ACCOUNT_ID}:function:stoa-api:production"
OPERATOR_ARN = (
    f"arn:aws:sts::{ACCOUNT_ID}:assumed-role/"
    "AWSReservedSSO_AdministratorAccess_0123456789abcdef/operator@stoa.test"
)
AUDIT_KEY = security_audit_repo.AuthorizationAuditKey("test-key", b"k" * 16 + b"0123456789abcdef")
AUDIT_PK = f"SECURITY_AUDIT#{catalog.OPERATOR_ACTOR_ID}"
OVERVIEW = ("list_teacher_applications", "count_review_queues", "report_email_stats")
WEEK = "2026-11-02"

# What a stored application row may hold besides what the queue shows. None of it
# may leave through an operator call: not a credential document, an attachment
# link, a phone number or address, nor the free-text statement.
APPLICATION_SECRETS = {
    "statement": "I taught at Kantonsschule X; call me on +41 79 000 00 00",
    "documents": ["s3://stoa-private/teacher/diploma.pdf"],
    "attachment_url": "https://stoa-private.s3.amazonaws.com/teacher/id-card.png?X-Amz-Signature=abc",
    "credential_reference": "diploma-2019-ZH-0042",
    "phone": "+41 79 111 22 33",
    "address": "Bahnhofstrasse 1, 8001 Zürich",
    "date_of_birth": "1990-04-01",
    "decision_reason": "internal reviewer note",
    "reviewer_id": "admin-7",
}
APPLICATION_FIELDS = {
    "applicationId",
    "version",
    "status",
    "reviewState",
    "createdAt",
    "fullName",
    "subjects",
    "verifiedEmail",
}


def _call(operation: str, arguments: dict[str, Any] | None = None) -> dict:
    return entry.handle(
        {
            "operation": operation,
            "arguments": arguments or {},
            "callerIdentity": {"authorization": "signed"},
            "agent": "claude-code",
        },
        invoked_function_arn=FUNCTION_ARN,
        region="eu-central-2",
        verify=lambda *_args, **_kwargs: OPERATOR_ARN,
        audit_key=lambda: AUDIT_KEY,
    )


def _application(application_id: str, review_state: str, created_at: str, **fields: Any) -> dict:
    return {
        "PK": f"TEACHER_APPLICATION#{application_id}",
        "SK": "VERSION#00000001",
        "entity_type": "teacher_application_version",
        "application_id": application_id,
        "version": 1,
        "status": "submitted",
        "review_state": review_state,
        "created_at": created_at,
        "verified_email": f"{application_id}@teacher.test",
        "email_verified": True,
        "full_name": f"Teacher {application_id}",
        "subjects": ["math"],
        **APPLICATION_SECRETS,
        **fields,
    }


def _case(case_id: str, status: str, **fields: Any) -> dict:
    return {
        "PK": f"MODERATION_CASE#{case_id}",
        "SK": "CASE",
        "entity_type": "moderation_case",
        "case_id": case_id,
        "status": status,
        "created_at": f"2026-11-0{len(case_id) % 9 + 1}T10:00:00+00:00",
        "reporter_id": "student-9",
        "message_preview": "the reported message",
        **fields,
    }


def _report(report_id: str, email_status: str | None, *, week: str = WEEK, **fields: Any) -> dict:
    row = {
        "PK": f"REPORT#{report_id}",
        "SK": "SUMMARY",
        "report_id": report_id,
        "parent_id": f"parent-{report_id}",
        "student_id": f"student-{report_id}",
        "student_name": "Mia Muster",
        "week_start": week,
        "created_at": f"{week}T06:00:00+00:00",
        "status": {"sent": "email_sent", "failed": "email_failed"}.get(
            str(email_status), "generated"
        ),
        "parent_email": f"parent-{report_id}@family.test",
        "email_error_message": "550 mailbox parent@family.test unavailable",
        **fields,
    }
    if email_status is not None:
        row["email_status"] = email_status
    return row


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return {str(key) for key in value} | {k for item in value.values() for k in _keys(item)}
    if isinstance(value, list):
        return {k for item in value for k in _keys(item)}
    return set()


def _written_partitions(table) -> list[str]:
    """The partition of every row any write request touched."""
    partitions: list[str] = []
    for operation, request in table.requests:
        if operation in {"put_item", "update_item", "delete_item"}:
            row = request.get("Item") or request.get("Key")
            partitions.append(str(row["PK"]))
        elif operation == "transact_write_items":
            for item in request["TransactItems"]:
                for action in item.values():
                    row = action.get("Item") or action.get("Key")
                    partitions.append(str(row["PK"]))
        elif operation not in {"get_item", "query", "scan"}:
            partitions.append(f"<{operation}>")
    return partitions


# -- the catalog ----------------------------------------------------------------------


def test_the_overview_tools_are_declared_read_only() -> None:
    for name in OVERVIEW:
        spec = catalog.OPERATIONS_BY_NAME[name]
        assert spec.effect is catalog.Effect.READ, name
        assert spec.destructive is False, name
        assert spec.description.startswith("Read only."), name
        assert "dryRun" not in spec.input_schema().get("properties", {}), name
        assert name in entry.RUNNERS, name


# -- teacher applications -------------------------------------------------------------


def test_teacher_applications_show_only_the_named_fields(fake_table) -> None:
    fake_table.seed(
        _application("teacherapp_a", "pending_review", "2026-11-01T09:00:00+00:00"),
        _application("teacherapp_b", "pending_review", "2026-11-03T09:00:00+00:00"),
        _application("teacherapp_c", "approved", "2026-10-01T09:00:00+00:00"),
    )

    answer = _call("list_teacher_applications")

    assert answer["ok"] is True, answer
    result = answer["result"]
    assert result["reviewState"] == "pending_review"
    assert result["count"] == 2
    # Oldest first, as the reviewer queue reads them.
    assert [item["applicationId"] for item in result["items"]] == ["teacherapp_a", "teacherapp_b"]
    first = result["items"][0]
    assert set(first) == APPLICATION_FIELDS
    assert first["fullName"] == "Teacher teacherapp_a"
    assert first["verifiedEmail"] == "teacherapp_a@teacher.test"
    assert first["subjects"] == ["math"]
    assert first["version"] == 1
    assert _keys(result) <= APPLICATION_FIELDS | {"reviewState", "items", "count", "more"}


def test_no_document_attachment_or_other_private_detail_leaves(fake_table) -> None:
    fake_table.seed(
        _application(
            "teacherapp_a",
            "pending_review",
            "2026-11-01T09:00:00+00:00",
            files=[{"url": "https://stoa-private.s3.amazonaws.com/f.pdf"}],
        )
    )

    answer = _call("list_teacher_applications")

    assert answer["ok"] is True, answer
    assert answer["result"]["count"] == 1
    text = str(answer)
    for value in APPLICATION_SECRETS.values():
        for part in value if isinstance(value, list) else [value]:
            assert part not in text
    for word in ("statement", "document", "attachment", "credential", "phone", "address",
                 "files", "s3", "http", "birth", "reviewer"):
        assert word not in text.lower(), word


def test_teacher_applications_by_review_state_and_limit(fake_table) -> None:
    fake_table.seed(
        *(
            _application(f"teacherapp_{n}", "rejected", f"2026-11-0{n}T09:00:00+00:00")
            for n in range(1, 5)
        ),
        _application("teacherapp_p", "pending_review", "2026-11-01T09:00:00+00:00"),
    )

    answer = _call("list_teacher_applications", {"reviewState": "rejected", "limit": 3})

    result = answer["result"]
    assert result["reviewState"] == "rejected"
    assert [item["applicationId"] for item in result["items"]] == [
        "teacherapp_1",
        "teacherapp_2",
        "teacherapp_3",
    ]
    assert result["more"] is True


@pytest.mark.parametrize(
    "arguments",
    [{"reviewState": "draft"}, {"limit": 0}, {"limit": 51}, {"statement": True}],
)
def test_teacher_application_arguments_the_console_refuses_are_refused(
    fake_table, arguments
) -> None:
    answer = _call("list_teacher_applications", arguments)

    assert answer["ok"] is False
    assert answer["error"]["code"] == "invalid_arguments"


# -- review queues --------------------------------------------------------------------


def test_review_queues_are_counted_not_listed(fake_table) -> None:
    fake_table.seed(
        _application("teacherapp_a", "pending_review", "2026-11-01T09:00:00+00:00"),
        _application("teacherapp_b", "pending_review", "2026-11-02T09:00:00+00:00"),
        _application("teacherapp_c", "approved", "2026-11-03T09:00:00+00:00"),
        _case("c1", "open"),
        _case("c2", "open"),
        _case("c3", "in_review"),
        _case("c4", "closed"),
        _case("c5", "open", privacy_deleted=True),
    )

    answer = _call("count_review_queues")

    assert answer["ok"] is True, answer
    assert answer["result"] == {
        "teacherApplications": {"pendingReview": 2, "countIsLowerBound": False},
        "moderationCases": {"open": 2, "inReview": 1},
    }


# -- report email delivery ------------------------------------------------------------


def test_report_email_stats_count_one_week_by_delivery_state(fake_table) -> None:
    fake_table.seed(
        _report("r1", "sent"),
        _report("r2", "sent"),
        _report("r3", "failed"),
        _report("r4", "pending"),
        _report("r5", "not_started"),
        _report("r6", None),
        _report("r7", "bounced-somehow"),
        _report("r8", "sent", week="2026-10-26"),
    )

    answer = _call("report_email_stats", {"weekStart": WEEK})

    assert answer["ok"] is True, answer
    assert answer["result"] == {
        "weekStart": WEEK,
        "reports": 7,
        "emailStatus": {"sent": 2, "failed": 1, "pending": 1, "notStarted": 2, "other": 1},
        "complete": True,
    }
    text = str(answer)
    assert "family.test" not in text and "Mia" not in text and "parent-" not in text


def test_report_email_stats_read_every_page_and_say_when_they_stopped(
    fake_table, monkeypatch: pytest.MonkeyPatch
) -> None:
    from stoa.operator_calls import overview

    fake_table.seed(*(_report(f"r{n}", "sent") for n in range(5)))
    fake_table.page_item_cap = 2

    whole = _call("report_email_stats", {"weekStart": WEEK})["result"]
    monkeypatch.setattr(overview, "REPORT_PAGE_BUDGET", 1)
    cut = _call("report_email_stats", {"weekStart": WEEK})["result"]

    assert (whole["reports"], whole["complete"]) == (5, True)
    assert (cut["reports"], cut["complete"]) == (2, False)


@pytest.mark.parametrize("arguments", [{}, {"weekStart": "2026/11/02"}, {"weekStart": "last week"}])
def test_report_email_stats_need_a_week(fake_table, arguments) -> None:
    answer = _call("report_email_stats", arguments)

    assert answer["ok"] is False
    assert answer["error"]["code"] == "invalid_arguments"


# -- nothing is written ---------------------------------------------------------------


def test_the_overview_writes_nothing_but_its_audit_rows(fake_table) -> None:
    fake_table.seed(
        _application("teacherapp_a", "pending_review", "2026-11-01T09:00:00+00:00"),
        _case("c1", "open"),
        _report("r1", "failed"),
    )
    before = {key: dict(row) for key, row in fake_table.rows.items()}

    answers = [
        _call("list_teacher_applications"),
        _call("count_review_queues"),
        _call("report_email_stats", {"weekStart": WEEK}),
    ]

    assert all(answer["ok"] for answer in answers), answers
    assert {key: fake_table.rows[key] for key in before} == before
    added = [key for key in fake_table.rows if key not in before]
    assert {pk for pk, _sk in added} == {AUDIT_PK}
    assert len(added) == 3
    assert set(_written_partitions(fake_table)) == {AUDIT_PK}

    rows = sorted(
        (fake_table.rows[key] for key in added), key=lambda row: str(row["action"])
    )
    assert [(row["action"], row["result_code"], row["dry_run"]) for row in rows] == [
        ("count_review_queues", "ok", False),
        ("list_teacher_applications", "ok", False),
        ("report_email_stats", "ok", False),
    ]
