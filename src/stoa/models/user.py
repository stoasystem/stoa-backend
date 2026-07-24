from enum import Enum
from typing import Any, List, Optional
from pydantic import BaseModel, EmailStr, model_validator
from datetime import datetime


class UserRole(str, Enum):
    STUDENT = "student"
    PARENT = "parent"
    TEACHER = "teacher"
    ADMIN = "admin"


class PublicRegistrationRole(str, Enum):
    """Roles that may be created by the unauthenticated registration API."""

    STUDENT = "student"
    PARENT = "parent"


class SubscriptionTier(str, Enum):
    FREE_TRIAL = "free_trial"
    STUDENT = "student"
    TEACHER_SUPPORTED = "teacher_supported"
    FAMILY = "family"


class Grade(str, Enum):
    SEK1 = "Sek1"
    SEK2 = "Sek2"
    GYM1 = "Gym1"
    GYM2 = "Gym2"
    MATURA = "Matura"


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    role: PublicRegistrationRole
    name: Optional[str] = None
    preferredLanguage: str = "de"
    grade: Optional[Grade] = None
    subjects: Optional[List[str]] = None
    language: str = "de"
    parent_id: Optional[str] = None
    profile: Optional[dict[str, Any]] = None
    studentProfile: Optional[dict[str, Any]] = None
    parentProfile: Optional[dict[str, Any]] = None

    model_config = {"extra": "forbid"}

    @model_validator(mode="before")
    @classmethod
    def reject_nested_role_fields(cls, value: Any) -> Any:
        """Prevent alternate/nested role selectors from bypassing the exact field."""

        def contains_role_selector(candidate: Any) -> bool:
            if isinstance(candidate, dict):
                for key, nested in candidate.items():
                    if str(key).replace("_", "").lower() in {"role", "roles", "userrole"}:
                        return True
                    if contains_role_selector(nested):
                        return True
            elif isinstance(candidate, list):
                return any(contains_role_selector(item) for item in candidate)
            return False

        if isinstance(value, dict):
            for key, nested in value.items():
                if key != "role" and contains_role_selector({key: nested}):
                    raise ValueError("alternate role selectors are not allowed")
        return value


class UserProfile(BaseModel):
    user_id: str
    email: str
    role: UserRole
    grade: Optional[Grade]
    subjects: List[str]
    language: str
    subscription_tier: SubscriptionTier = SubscriptionTier.FREE_TRIAL
    created_at: datetime
