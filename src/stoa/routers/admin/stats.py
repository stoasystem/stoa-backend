"""Admin platform statistics."""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from stoa.db import table as db_table
from stoa.db.repositories import (
    question_repo,
    user_repo,
)
from stoa.security.admin_authorization import admin_operation
from stoa.security.identity import Actor
from stoa.models.question import QuestionStatus
from stoa.services import (
    help_requests,
    teacher_reply_service,
)


router = APIRouter()


class StatsResponse(BaseModel):
    total_users: int
    total_students: int
    total_parents: int
    total_teachers: int
    total_questions: int
    ai_resolved: int
    teacher_resolved: int
    escalated: int
    teacher_sla: dict[str, Any]
    # False when a census stopped at its page budget, so the counts below are a
    # floor rather than a total. Additive: absent means the walk finished.
    counts_complete: bool = True


# Each census below walks the whole table one megabyte at a time. The budget is
# what stops a runaway table turning the dashboard into a timeout.
ADMIN_STATS_MAX_PAGES = 50


@router.get("/stats", response_model=StatsResponse)
async def get_stats(actor: Actor = Depends(admin_operation)):
    """Return aggregate platform metrics (full-table scan — small scale only)."""
    table = db_table.table()

    # Count user profiles
    users, users_complete = user_repo.profile_role_census(
        page_budget=ADMIN_STATS_MAX_PAGES, table=table
    )

    counts = {"student": 0, "parent": 0, "teacher": 0}
    for u in users:
        r = u.get("role", "")
        if r in counts:
            counts[r] += 1

    # Count questions by status
    meta_rows, questions_complete = question_repo.question_meta_census(
        page_budget=ADMIN_STATS_MAX_PAGES, table=table
    )
    question_statuses = {status.value for status in QuestionStatus}
    questions = [
        question
        for question in meta_rows
        if isinstance(question_status := question.get("status"), str)
        and question_status in question_statuses
    ]

    # A help request is not a question row since #189; it is counted, and its
    # response times measured, from its own record.
    help_metrics = [help_requests.sla_metrics(record) for record in help_requests.list_all(table=table)]
    ai_resolved = sum(1 for q in questions if q.get("status") == QuestionStatus.AI_ANSWERED.value)
    teacher_resolved = sum(
        1 for q in (*questions, *help_metrics) if q.get("status") == QuestionStatus.RESOLVED.value
    )
    escalated = sum(
        1 for q in (*questions, *help_metrics)
        if q.get("status") in (QuestionStatus.ESCALATED.value, QuestionStatus.TEACHER_ACTIVE.value)
    )

    return StatsResponse(
        total_users=len(users),
        total_students=counts["student"],
        total_parents=counts["parent"],
        total_teachers=counts["teacher"],
        total_questions=len(questions),
        ai_resolved=ai_resolved,
        teacher_resolved=teacher_resolved,
        escalated=escalated,
        teacher_sla=teacher_reply_service.aggregate_teacher_sla([*questions, *help_metrics]),
        counts_complete=users_complete and questions_complete,
    )
