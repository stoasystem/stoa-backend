"""Admin teacher-support allowances."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from stoa.db import table as db_table
from stoa.security.admin_authorization import admin_operation
from stoa.security.identity import Actor
from stoa.services import teacher_support_allowance_service


router = APIRouter()


class TeacherSupportAllowanceCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Text answers a week.
    weekly_cases: int = Field(ge=0, le=teacher_support_allowance_service.ASSIGNED_WEEKLY_CASES_MAXIMUM)
    # Online classrooms a week (#482); left out, the figure stays as it was.
    weekly_classroom_cases: int | None = Field(
        default=None, ge=0, le=teacher_support_allowance_service.ASSIGNED_WEEKLY_CASES_MAXIMUM
    )
    reason: str = Field(min_length=1, max_length=1000)


@router.get("/teacher-support/allowances/{student_id}")
async def read_teacher_support_allowance(
    student_id: str,
    actor: Actor = Depends(admin_operation),
):
    """How many teacher-support cases this student has in a week, and from where.

    `weeklyCases` is text answers, `weeklyClassroomCases` online classrooms.
    """
    del actor
    assigned = teacher_support_allowance_service.read_administered_weekly_cases(
        student_id, table=db_table.table()
    )
    return {
        "studentId": student_id,
        "weeklyCases": assigned.weekly_cases,
        "weeklyClassroomCases": assigned.weekly_classroom_cases,
        "source": assigned.source,
        "default": teacher_support_allowance_service.ASSIGNED_WEEKLY_TEACHER_SUPPORT_CASES,
        "classroomDefault": teacher_support_allowance_service.ASSIGNED_WEEKLY_CLASSROOM_CASES,
        "maximum": teacher_support_allowance_service.ASSIGNED_WEEKLY_CASES_MAXIMUM,
    }


@router.put("/teacher-support/allowances/{student_id}")
async def set_teacher_support_allowance(
    student_id: str,
    body: TeacherSupportAllowanceCommand,
    actor: Actor = Depends(admin_operation),
):
    """Set this student's weekly figures, replacing whatever they were.

    The write carries the version it read, so two administrators changing the
    same student at once cannot both believe they set it. The admission path
    fences the same version, so a case can never be spent against a figure that
    was replaced between reading it and writing the case.
    """
    target = db_table.table()
    next_version = teacher_support_allowance_service.administer_weekly_cases(
        student_id,
        body.weekly_cases,
        weekly_classroom_cases=body.weekly_classroom_cases,
        actor=actor,
        table=target,
    )
    written = teacher_support_allowance_service.read_assigned_weekly_cases(
        student_id, table=target
    )
    return {
        "studentId": student_id,
        "weeklyCases": body.weekly_cases,
        "weeklyClassroomCases": written.weekly_classroom_cases,
        "source": "administrator",
        "stateVersion": next_version,
    }
