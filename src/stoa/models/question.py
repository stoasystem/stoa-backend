from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


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
    corrected_text: Optional[str] = Field(default=None, min_length=5, max_length=2000)


class QuestionOcrMetadata(BaseModel):
    status: str = "not_requested"
    source: str | None = None
    text_length: int = 0
    correction_applied: bool = False
    failure_class: str | None = None


class QuestionResponse(BaseModel):
    question_id: str
    student_id: str
    subject: str
    content: str
    image_s3_key: Optional[str] = None
    has_image: bool = False
    ocr_metadata: QuestionOcrMetadata = Field(default_factory=QuestionOcrMetadata)
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
