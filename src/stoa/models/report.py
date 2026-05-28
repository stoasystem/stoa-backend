from typing import List
from pydantic import BaseModel


class WeeklyReportResponse(BaseModel):
    report_id: str
    parent_id: str
    student_id: str
    week_start: str  # ISO date string, e.g. "2026-05-25"
    usage_count: int
    ai_resolved: int
    teacher_resolved: int
    weak_knowledge_points: List[str]
    recommendations: str
