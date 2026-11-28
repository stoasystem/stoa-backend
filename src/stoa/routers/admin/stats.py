"""Admin platform statistics: how fast teachers answer help requests (#697)."""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from stoa.db import table as db_table
from stoa.security.admin_authorization import admin_operation
from stoa.security.identity import Actor
from stoa.services import (
    help_requests,
    teacher_reply_service,
)


router = APIRouter()

# The period `teacher_sla` measures: requests asked in the last 30 days (#697),
# so the card shows how teachers answer now and the read follows the requests
# of the period, not every request ever asked.
TEACHER_SLA_PERIOD_DAYS = 30


class StatsResponse(BaseModel):
    teacher_sla: dict[str, Any]
    # How many days back `teacher_sla` counts, for the card to say so.
    period_days: int


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/stats", response_model=StatsResponse)
async def get_stats(actor: Actor = Depends(admin_operation)):
    """How fast teachers answered the help requests asked in the period.

    Only help requests count: the legacy question rows have no writer and come
    from early test accounts. The account and question totals this answered
    before had no reader and were retired (#697).
    """
    since = _now() - timedelta(days=TEACHER_SLA_PERIOD_DAYS)
    metrics = [
        help_requests.sla_metrics(record)
        for record in help_requests.list_asked_since(since, table=db_table.table())
    ]
    return StatsResponse(
        teacher_sla=teacher_reply_service.aggregate_teacher_sla(metrics),
        period_days=TEACHER_SLA_PERIOD_DAYS,
    )
