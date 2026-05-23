from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, EmailStr
from datetime import datetime


class UserRole(str, Enum):
    STUDENT = "student"
    PARENT = "parent"
    TEACHER = "teacher"
    ADMIN = "admin"


class SubscriptionTier(str, Enum):
    FREE = "free"
    STANDARD = "standard"
    PREMIUM = "premium"


class Grade(str, Enum):
    SEK1 = "Sek1"
    SEK2 = "Sek2"
    GYM1 = "Gym1"
    GYM2 = "Gym2"
    MATURA = "Matura"


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    role: UserRole
    grade: Optional[Grade] = None
    subjects: Optional[List[str]] = None
    language: str = "de"
    parent_id: Optional[str] = None


class UserProfile(BaseModel):
    user_id: str
    email: str
    role: UserRole
    grade: Optional[Grade]
    subjects: List[str]
    language: str
    subscription_tier: SubscriptionTier
    created_at: datetime
