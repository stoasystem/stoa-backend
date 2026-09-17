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


MIN_REGISTRATION_AGE = 1
MAX_REGISTRATION_AGE = 120
# Single source of truth for the minor/adult split used by registration rules.
ADULT_AGE = 18

_AGE_MESSAGE = (
    f"Age must be a whole number between {MIN_REGISTRATION_AGE} and {MAX_REGISTRATION_AGE}."
)
_PARENT_CONTACT_MESSAGE = (
    f"Parent name and parent email are required for students under {ADULT_AGE}."
)


def normalize_registration_age(raw: Any) -> int:
    """Accept only a plain in-range integer, rejecting leading zeros and oversized input."""

    if isinstance(raw, bool) or not isinstance(raw, (int, str)):
        raise ValueError(_AGE_MESSAGE)
    text = str(raw).strip()
    if not text.isdigit() or len(text) > 3:
        raise ValueError(_AGE_MESSAGE)
    if len(text) > 1 and text.startswith("0"):
        raise ValueError(_AGE_MESSAGE)
    age = int(text)
    if age < MIN_REGISTRATION_AGE or age > MAX_REGISTRATION_AGE:
        raise ValueError(_AGE_MESSAGE)
    return age


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
    acceptedTerms: Optional[bool] = None
    termsVersion: Optional[str] = None
    acceptedAt: Optional[str] = None
    referralCode: Optional[str] = None
    utm: Optional[dict[str, Any]] = None

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_onboarding_profile(self) -> "RegisterRequest":
        """Normalize the declared age and require parent contact for minors."""

        if self.role is PublicRegistrationRole.STUDENT:
            profile = self.profile if self.profile is not None else self.studentProfile
            age_key = "age"
        else:
            profile = self.profile if self.profile is not None else self.parentProfile
            age_key = "childAge"
        if not isinstance(profile, dict):
            return self

        raw_age = profile.get(age_key)
        age = None
        if isinstance(raw_age, str) and not raw_age.strip():
            # A blank field means the age was left empty, not that it is "".
            # Carrying the empty string through reached int() in the route and
            # raised there, after the account had already been created.
            profile.pop(age_key, None)
        elif raw_age is not None:
            age = normalize_registration_age(raw_age)
            profile[age_key] = age

        if self.role is PublicRegistrationRole.STUDENT and age is not None and age < ADULT_AGE:
            parent_name = str(profile.get("parentName") or "").strip()
            parent_email = str(profile.get("parentEmail") or "").strip()
            if not parent_name or not parent_email:
                raise ValueError(_PARENT_CONTACT_MESSAGE)
        return self

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
