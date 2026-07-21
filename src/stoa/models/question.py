from enum import Enum, StrEnum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime

from stoa.models.attachment import AttachmentReference, AttachmentSummary


class QuestionStatus(str, Enum):
    PENDING = "pending"
    SUBMISSION_FAILED = "submission_failed"
    AI_ANSWERED = "ai_answered"
    ESCALATED = "escalated"
    TEACHER_ACTIVE = "teacher_active"
    RESOLVED = "resolved"


class QuestionSubmissionErrorCode(StrEnum):
    PAYLOAD_MISMATCH = "question_submission_payload_mismatch"
    QUOTA_EXCEEDED = "question_quota_exceeded"
    ADMISSION_UNAVAILABLE = "question_submission_temporarily_unavailable"


class AIResponse(BaseModel):
    steps: List[str] = []
    answer: str = ""
    hints: List[str] = []
    similar_exercises: List[str] = []
    knowledge_points: List[str] = []


class SubmitQuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(..., min_length=5, max_length=2000)
    subject: str = Field(..., pattern="^(math|physics|german|english)$")
    attachment: AttachmentReference | None = None
    corrected_text: Optional[str] = Field(default=None, min_length=5, max_length=2000)
    idempotency_key: Optional[str] = Field(default=None, alias="idempotencyKey", min_length=8, max_length=200)


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
    has_image: bool = False
    attachment: AttachmentSummary | None = None
    ocr_metadata: QuestionOcrMetadata = Field(default_factory=QuestionOcrMetadata)
    status: QuestionStatus
    ai_response: Optional[AIResponse]
    teacher_id: Optional[str]
    teacher_response: Optional[str]
    knowledge_points: List[str]
    topic_seeds: List[dict] = Field(default_factory=list)
    student_feedback: Optional[int]
    created_at: datetime
    resolved_at: Optional[datetime]


class FeedbackRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
