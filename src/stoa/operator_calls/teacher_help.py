"""How many teacher-help requests a student has left this week, for an operator.

The figure the request route itself goes by: the student's weekly cases, how
many this Zurich week has admitted, and when the week starts over, read the way
admission reads them (`teacher_support_allowance_service`). Text answers at the
top level, online classrooms under `classroom` (#482: two weekly allowances). Beside it, the two
other things that decide whether a request made now is taken: the account's
status and the student's effective usage period. Nothing here writes.
"""

from __future__ import annotations

from typing import Any

from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo, user_repo
from stoa.operator_calls import accounts
from stoa.operator_calls.catalog import GetTeacherHelpAllowanceArguments
from stoa.operator_calls.outcome import OperatorCallRefused, Outcome
from stoa.services import teacher_support_allowance_service as allowance
from stoa.services import usage_period
from stoa.services.account_errors import AccountErrorCode, AccountViolation


def _student(number: str, *, table: object) -> tuple[str, dict[str, Any]]:
    """The student id and profile behind a number; refused for anyone else."""
    account_id = accounts.account_id_by_number(number, table=table)
    profile = user_repo.get_user(account_id, table=table) if account_id else None
    if not profile or account_deletion_repo.is_deletion_tombstone(profile):
        raise AccountViolation(AccountErrorCode.ACCOUNT_NOT_FOUND)
    if str(profile.get("role") or "") != "student":
        raise AccountViolation(AccountErrorCode.ACCOUNT_NOT_A_STUDENT)
    return account_id, dict(profile)


def get_teacher_help_allowance(arguments: GetTeacherHelpAllowanceArguments) -> Outcome:
    table = db_table.table()
    number = arguments.accountNumber.strip().upper()
    student_id, profile = _student(number, table=table)
    try:
        standing = allowance.get_student_teacher_support_standing(
            beneficiary_id=student_id, table=table
        )
        included = any(
            standing[mode]["blockedReason"] != "teacher_support_not_included"
            for mode in allowance.MODES
        )
        projection = (
            allowance.get_teacher_support_projection(beneficiary_id=student_id, table=table)
            if included
            else None
        )
        assigned = allowance.read_administered_weekly_cases(student_id, table=table)
    except ValueError:
        raise OperatorCallRefused(
            "temporarily_unavailable",
            f"The teacher-help allowance of {number} cannot be read right now; try again.",
            target_type="account",
            target_id=student_id,
        ) from None
    period = usage_period.effective_for_student(student_id, profile=profile, table=table)
    account_status = str(profile.get("account_status") or "")

    # Why a request made now would be refused, in the order the route checks.
    account_blocked: list[str] = []
    if account_status != "active":
        account_blocked.append("account_not_active")
    if not usage_period.allows_new_usage(period):
        account_blocked.append("usage_period_ended")

    def blocked_for(mode: str) -> list[str]:
        reason = standing[mode]["blockedReason"]
        return [*account_blocked, *([str(reason)] if reason else [])]

    blocked = blocked_for(allowance.TEXT)
    classroom_blocked = blocked_for(allowance.CLASSROOM)
    classroom_counts = projection["classroom"] if projection else {"admittedCases": 0}

    return Outcome(
        {
            "accountNumber": number,
            "userId": student_id,
            "accountStatus": account_status,
            "usagePeriod": {
                "endsOn": period.ends_on.isoformat() if period.ends_on else None,
                "state": period.state.value,
            },
            "weekIdentity": projection["weekIdentity"] if projection else None,
            "weeklyCases": standing["weeklyCases"],
            "usedCases": projection["admittedCases"] if projection else 0,
            "remainingCases": standing["remainingCases"],
            "resetsAt": standing["resetsAt"],
            # Where the weekly figure comes from: a parent's purchase (its plan)
            # or the figure assigned to the student, by default or by an administrator.
            "planId": projection["planId"] if projection else None,
            "assignedWeeklyCases": {
                "weeklyCases": assigned.weekly_cases,
                "weeklyClassroomCases": assigned.weekly_classroom_cases,
                "source": assigned.source,
            },
            "canRequestNow": not blocked,
            "blockedReasons": blocked,
            # Online classrooms, counted apart from the text answers above.
            "classroom": {
                "weeklyCases": standing["classroom"]["weeklyCases"],
                "usedCases": classroom_counts["admittedCases"],
                "remainingCases": standing["classroom"]["remainingCases"],
                "canRequestNow": not classroom_blocked,
                "blockedReasons": classroom_blocked,
            },
        },
        "account",
        student_id,
        f"week:{projection['weekIdentity'] if projection else '-'};"
        f"used:{projection['admittedCases'] if projection else 0}",
    )
