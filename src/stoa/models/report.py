from typing import List
from pydantic import BaseModel
from datetime import datetime


class WeeklyReportResponse(BaseModel):
    report_id: str
    parent_id: str
    student_id: str
    week_start: datetime
    usage_count: int
    ai_resolved: int
    teacher_resolved: int
    weak_knowledge_points: List[str]
    recommendations: str
