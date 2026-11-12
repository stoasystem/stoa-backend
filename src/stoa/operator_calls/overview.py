"""The read-only overview an agent may ask for: teacher applications, review queues
and weekly-report email delivery (#386).

Each reads through the function the console's own route uses
(`teacher_application_repo.list_applications_by_review_state` behind
`GET /teacher-applications`,
`moderation_repo.list_cases` behind `GET /admin/moderation/cases`,
`report_repo.list_reports_for_admin` behind `GET /admin/reports/ops`), and then
names every field it hands back. A stored row may hold more - an applicant's
statement, a document or attachment reference, a parent's address, an email
error text - and none of it can leave through here, because nothing is copied
that is not listed below.

The console guards these routes with an admin's grant; an operator call is
guarded by the SSO identity `entry.handle` verifies before any operation runs,
and holds no product role of its own (#380, decision 3).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from stoa.db.repositories import moderation_repo, report_repo, teacher_application_repo
from stoa.operator_calls.catalog import (
    CountReviewQueuesArguments,
    ListTeacherApplicationsArguments,
    ReportEmailStatsArguments,
)
from stoa.operator_calls.outcome import Outcome


# The most applications one count reads: the review-state index answers at most
# this many in one page, so a larger queue is reported as "at least".
PENDING_COUNT_CAP = 200

# How far one email count reads, a hundred reports a page: a runaway table ends
# the count early (and says so) instead of timing the call out.
REPORT_PAGE_SIZE = 100
REPORT_PAGE_BUDGET = 50

# A report's `email_status`, and the name the count gives it.
_EMAIL_STATES = {
    "sent": "sent",
    "failed": "failed",
    "pending": "pending",
    "not_started": "notStarted",
}


def _application(row: Mapping[str, Any]) -> dict[str, object]:
    """One stored application version, as the reviewer queue lists it, field by field:
    whatever else the row holds stays behind."""
    subjects = row.get("subjects")
    return {
        "applicationId": row.get("application_id"),
        "version": int(row.get("version") or 0),
        "status": row.get("status"),
        "reviewState": row.get("review_state"),
        "createdAt": row.get("created_at"),
        "fullName": row.get("full_name"),
        "subjects": [str(subject) for subject in subjects] if isinstance(subjects, list) else [],
        "verifiedEmail": row.get("verified_email"),
    }


def list_teacher_applications(arguments: ListTeacherApplicationsArguments) -> Outcome:
    # One more than asked for, to say whether there are others.
    # The review state is one of the queue's three: the arguments admit no other.
    rows = teacher_application_repo.list_applications_by_review_state(
        arguments.reviewState, limit=arguments.limit + 1
    )
    items = [_application(row) for row in rows]
    shown = items[: arguments.limit]
    return Outcome(
        {
            "reviewState": arguments.reviewState,
            "items": shown,
            "count": len(shown),
            "more": len(items) > arguments.limit,
        },
        "teacher_application_list",
        arguments.reviewState,
        f"returned:{len(shown)}",
    )


def count_review_queues(_arguments: CountReviewQueuesArguments) -> Outcome:
    pending = len(
        teacher_application_repo.list_applications_by_review_state(
            "pending_review", limit=PENDING_COUNT_CAP
        )
    )
    statuses = [str(case.get("status") or "") for case in moderation_repo.list_cases(limit=None)]
    result: dict[str, object] = {
        "teacherApplications": {
            "pendingReview": pending,
            "countIsLowerBound": pending >= PENDING_COUNT_CAP,
        },
        "moderationCases": {
            "open": statuses.count("open"),
            "inReview": statuses.count("in_review"),
        },
    }
    return Outcome(result, "review_queues", "counts")


def report_email_stats(arguments: ReportEmailStatsArguments) -> Outcome:
    counts = dict.fromkeys((*_EMAIL_STATES.values(), "other"), 0)
    reports = 0
    last_key: dict[str, Any] | None = None
    complete = False
    for _page in range(REPORT_PAGE_BUDGET):
        page = report_repo.list_reports_for_admin(
            week_start=arguments.weekStart, limit=REPORT_PAGE_SIZE, last_key=last_key
        )
        for report in page.get("Items") or []:
            reports += 1
            state = report.get("email_status") or "not_started"
            counts[_EMAIL_STATES.get(str(state), "other")] += 1
        last_key = page.get("LastEvaluatedKey")
        if not last_key:
            complete = True
            break
    return Outcome(
        {
            "weekStart": arguments.weekStart,
            "reports": reports,
            "emailStatus": counts,
            "complete": complete,
        },
        "report_email_stats",
        arguments.weekStart,
        f"counted:{reports}",
    )
