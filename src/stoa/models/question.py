from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import uuid


class QuestionStatus(str, Enum):
    PENDING = "pending"
    AI_ANSWERED = "ai_answered"
    ESCALATED = "escalated"
    TEACHER_ACTIVE = "teacher_active"
    RESOLVED = "resolved"


class AIResponse(BaseModel):
    steps: List[str] = []
    answer: str = ""
    hints: List[str] = []
    similar_exercises: List[str] = []


class SubmitQuestionRequest(BaseModel):
    content: str = Field(..., min_length=5, max_length=2000)
    subject: str = Field(..., pattern="^(math|physics|german|english|french)$")
    image_s3_key: Optional[str] = None


class QuestionResponse(BaseModel):
    question_id: str
    student_id: str
    subject: str
    content: str
    image_s3_key: Optional[str]
    status: QuestionStatus
    ai_response: Optional[AIResponse]
    teacher_id: Optional[str]
    teacher_response: Optional[str]
    knowledge_points: List[str]
    student_feedback: Optional[int]
    created_at: datetime
    resolved_at: Optional[datetime]


class FeedbackRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
