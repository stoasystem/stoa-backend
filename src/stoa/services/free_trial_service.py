"""Immutable first-activation state for the 14-day student free trial."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping

from stoa.db.repositories import account_deletion_repo, user_repo


FREE_TRIAL_SCHEMA_VERSION = "free-trial.v1"
FREE_TRIAL_DURATION = timedelta(days=14)
CHOOSE_PAID_PLAN_ACTION = "choose_paid_plan"
_MAX_ACTIVATION_ATTEMPTS = 3
_PAID_PLANS = frozenset({"student", "teacher_supported", "family"})


class FreeTrialDependencyError(RuntimeError):
    """The activation write could not converge on authoritative profile state."""


@dataclass(frozen=True, slots=True)
class FreeTrialState:
    """Safe trial projection; missing evidence never contains inferred timestamps."""

    status: str
    first_student_activation_at: datetime | None
    free_trial_expires_at: datetime | None
    action: str | None

    @property
    def allows_new_usage(self) -> bool:
        return self.status == "active"

    def public_projection(self) -> dict[str, object]:
        return {
            "status": self.status,
            "firstStudentActivationAt": (
                self.first_student_activation_at.isoformat()
                if self.first_student_activation_at is not None
                else None
            ),
            "expiresAt": (
                self.free_trial_expires_at.isoformat()
                if self.free_trial_expires_at is not None
                else None
            ),
            "allowsNewUsage": self.allows_new_usage,
            "action": self.action,
        }


def utc_now() -> datetime:
    """Return one aware UTC observation; activation timestamps never use this clock."""
    return datetime.now(UTC)


def activate_student_free_trial(
    student_id: str,
    *,
    student_profile: Mapping[str, object] | None = None,
) -> FreeTrialState:
    """Persist the trusted first-activation instant once and replay its exact bytes.

    The existing email-verification activation timestamp is the evidence source.
    This function never substitutes request time for missing historical evidence.
    """
    candidate = dict(student_profile) if student_profile is not None else None
    for _attempt in range(_MAX_ACTIVATION_ATTEMPTS):
        profile = candidate if candidate is not None else user_repo.get_user(student_id)
        candidate = None
        if not isinstance(profile, Mapping) or not _active_student_profile(
            profile, student_id
        ):
            return _review_required()

        existing = _persisted_state(profile, observed_at=utc_now())
        if existing is not None:
            return existing
        if _requires_migration_review(profile):
            return _review_required()

        start = _parse_utc(profile.get("email_verified_at"))
        version = _positive_int(profile.get("version"))
        if start is None or version is None:
            return _review_required()
        expiry = start + FREE_TRIAL_DURATION

        try:
            fence = account_deletion_repo.require_active_account_fence(student_id)
            generation = _positive_int(fence.get("generation"))
            if generation is None:
                return _review_required()
            operation = user_repo.profile_update_operation(
                student_id,
                update_expression=(
                    "SET first_student_activation_at=:trial_start, "
                    "free_trial_expires_at=:trial_expiry, "
                    "free_trial_schema_version=:trial_schema_version"
                ),
                expression_attribute_names={
                    "#role": "role",
                    "#account_status": "account_status",
                    "#trial_start_field": "first_student_activation_at",
                    "#trial_expiry_field": "free_trial_expires_at",
                    "#trial_schema_field": "free_trial_schema_version",
                },
                expression_attribute_values={
                    ":trial_start": start.isoformat(),
                    ":trial_expiry": expiry.isoformat(),
                    ":trial_schema_version": FREE_TRIAL_SCHEMA_VERSION,
                    ":student_role": "student",
                    ":active_status": "active",
                },
                expected_version=version,
                additional_condition_expression=(
                    "#role=:student_role AND #account_status=:active_status AND "
                    "attribute_not_exists(#trial_start_field) AND "
                    "attribute_not_exists(#trial_expiry_field) AND "
                    "attribute_not_exists(#trial_schema_field)"
                ),
            )
            account_deletion_repo.transact(
                [
                    account_deletion_repo.active_fence_condition(
                        student_id, generation
                    ),
                    operation,
                ]
            )
        except account_deletion_repo.AccountDeletionConflict:
            current = user_repo.get_user(student_id)
            replay = _persisted_state(current, observed_at=utc_now())
            if replay is not None:
                return replay
            continue

        current = user_repo.get_user(student_id)
        replay = _persisted_state(current, observed_at=utc_now())
        if replay is not None:
            return replay

    raise FreeTrialDependencyError("student free-trial activation did not converge")


def get_free_trial_state(
    student_profile: Mapping[str, object] | None,
    *,
    observed_at: datetime | None = None,
) -> FreeTrialState:
    """Project immutable trial evidence without writing or initializing it."""
    observation = _required_aware_utc(observed_at or utc_now())
    persisted = _persisted_state(student_profile, observed_at=observation)
    return persisted if persisted is not None else _review_required()


def free_trial_allows_new_usage(state: FreeTrialState) -> bool:
    """Return the admission decision for new AI or teacher-support use."""
    if not isinstance(state, FreeTrialState):
        raise TypeError("free-trial state is required")
    return state.allows_new_usage


def plan_allows_new_usage(effective_plan: object, state: FreeTrialState) -> bool:
    """Paid plans admit independently; free-trial admission uses immutable evidence."""
    plan = str(effective_plan or "free_trial")
    return plan in _PAID_PLANS or free_trial_allows_new_usage(state)


def _persisted_state(
    profile: Mapping[str, object] | None,
    *,
    observed_at: datetime,
) -> FreeTrialState | None:
    if not isinstance(profile, Mapping) or _requires_migration_review(profile):
        return None
    present = tuple(
        field in profile
        for field in (
            "first_student_activation_at",
            "free_trial_expires_at",
            "free_trial_schema_version",
        )
    )
    if not any(present):
        return None
    if not all(present):
        return _review_required()
    start = _parse_utc(profile.get("first_student_activation_at"))
    expiry = _parse_utc(profile.get("free_trial_expires_at"))
    if (
        start is None
        or expiry is None
        or profile.get("free_trial_schema_version") != FREE_TRIAL_SCHEMA_VERSION
        or expiry != start + FREE_TRIAL_DURATION
    ):
        return _review_required()
    observation = _required_aware_utc(observed_at)
    active = observation < expiry
    return FreeTrialState(
        status="active" if active else "expired",
        first_student_activation_at=start,
        free_trial_expires_at=expiry,
        action=None if active else CHOOSE_PAID_PLAN_ACTION,
    )


def _active_student_profile(
    profile: Mapping[str, object] | None, student_id: str
) -> bool:
    return bool(
        isinstance(profile, Mapping)
        and profile.get("user_id") == student_id
        and profile.get("role") == "student"
        and profile.get("account_status") == "active"
    )


def _requires_migration_review(profile: Mapping[str, object]) -> bool:
    value = profile.get("migration_review_required")
    return value is True or value not in (None, False)


def _parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        return None
    return parsed.astimezone(UTC)


def _required_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    return value.astimezone(UTC)


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def _review_required() -> FreeTrialState:
    return FreeTrialState(
        status="migration_review_required",
        first_student_activation_at=None,
        free_trial_expires_at=None,
        action=CHOOSE_PAID_PLAN_ACTION,
    )
