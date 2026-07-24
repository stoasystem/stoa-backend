"""Closed weekly allowance and provider-usage evidence contracts."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from stoa.models.billing import BillingPlanId


MAX_EXACT_COUNT = (1 << 63) - 1
ZURICH = ZoneInfo("Europe/Zurich")
OpaqueText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]
Sha256Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
ExactNonnegativeCount = Annotated[int, Field(strict=True, ge=0, le=MAX_EXACT_COUNT)]
PositiveVersion = Annotated[int, Field(strict=True, ge=1, le=MAX_EXACT_COUNT)]


class _AllowanceModel(BaseModel):
    """Closed model with snake_case storage names and explicit API aliases."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class TeacherSupportScope(StrEnum):
    NONE = "none"
    PER_BENEFICIARY = "per_beneficiary"
    SHARED_FAMILY = "shared_family"


class ZurichWeek(_AllowanceModel):
    iso_year: Annotated[int, Field(strict=True, ge=1, le=9999)] = Field(alias="isoYear")
    iso_week: Annotated[int, Field(strict=True, ge=1, le=53)] = Field(alias="isoWeek")
    window_start: datetime = Field(alias="windowStart")
    window_end: datetime = Field(alias="windowEnd")

    @model_validator(mode="after")
    def validate_zurich_calendar_week(self) -> "ZurichWeek":
        if self.window_start.tzinfo is None or self.window_end.tzinfo is None:
            raise ValueError("allowance windows require timezone-aware boundaries")
        local_start = self.window_start.astimezone(ZURICH)
        local_end = self.window_end.astimezone(ZURICH)
        if (
            local_start.weekday() != 0
            or local_end.weekday() != 0
            or local_start.hour != 0
            or local_end.hour != 0
            or local_start.minute != 0
            or local_end.minute != 0
            or local_start.second != 0
            or local_end.second != 0
            or local_start.microsecond != 0
            or local_end.microsecond != 0
        ):
            raise ValueError("allowance window must use Zurich Monday midnight boundaries")
        expected_end = local_start + timedelta(days=7)
        if local_end != expected_end:
            raise ValueError("allowance window must span exactly one Zurich calendar week")
        iso_calendar = local_start.date().isocalendar()
        if (self.iso_year, self.iso_week) != (iso_calendar.year, iso_calendar.week):
            raise ValueError("ISO week coordinates must match the Zurich window start")
        return self


_LOCKED_BUDGETS: dict[BillingPlanId, tuple[int, int, int, TeacherSupportScope]] = {
    BillingPlanId.FREE_TRIAL: (50_000, 10_000, 0, TeacherSupportScope.NONE),
    BillingPlanId.STUDENT: (500_000, 100_000, 0, TeacherSupportScope.NONE),
    BillingPlanId.TEACHER_SUPPORTED: (
        1_000_000,
        200_000,
        2,
        TeacherSupportScope.PER_BENEFICIARY,
    ),
    BillingPlanId.FAMILY: (
        1_000_000,
        200_000,
        10,
        TeacherSupportScope.SHARED_FAMILY,
    ),
}


class PlanAllowanceBudget(_AllowanceModel):
    plan_id: BillingPlanId = Field(alias="planId")
    input_tokens: ExactNonnegativeCount = Field(alias="inputTokens")
    output_tokens: ExactNonnegativeCount = Field(alias="outputTokens")
    teacher_support_cases: ExactNonnegativeCount = Field(alias="teacherSupportCases")
    teacher_support_scope: TeacherSupportScope = Field(alias="teacherSupportScope")
    allowance_version: PositiveVersion = Field(alias="allowanceVersion")

    @model_validator(mode="after")
    def validate_locked_budget(self) -> "PlanAllowanceBudget":
        actual = (
            self.input_tokens,
            self.output_tokens,
            self.teacher_support_cases,
            self.teacher_support_scope,
        )
        if actual != _LOCKED_BUDGETS[self.plan_id]:
            raise ValueError("allowance budget does not match the canonical plan")
        return self


class AllowanceReservation(_AllowanceModel):
    reservation_id: OpaqueText = Field(alias="reservationId")
    effect_id: OpaqueText = Field(alias="effectId")
    beneficiary_id: OpaqueText = Field(alias="beneficiaryId")
    plan_id: BillingPlanId = Field(alias="planId")
    allowance_version: PositiveVersion = Field(alias="allowanceVersion")
    week: ZurichWeek
    input_tokens: ExactNonnegativeCount = Field(alias="inputTokens")
    output_tokens: ExactNonnegativeCount = Field(alias="outputTokens")
    state_version: PositiveVersion = Field(alias="stateVersion")
    expires_at: datetime = Field(alias="expiresAt")


class ProviderUsageEvidence(_AllowanceModel):
    evidence_id: OpaqueText = Field(alias="evidenceId")
    effect_id: OpaqueText = Field(alias="effectId")
    provider_request_id_digest: Sha256Digest = Field(alias="providerRequestIdDigest")
    model_id_digest: Sha256Digest = Field(alias="modelIdDigest")
    input_tokens: ExactNonnegativeCount = Field(alias="inputTokens")
    output_tokens: ExactNonnegativeCount = Field(alias="outputTokens")
    provider_cost_retained: bool = Field(alias="providerCostRetained")
    observed_at: datetime = Field(alias="observedAt")


class AllowanceFinalization(_AllowanceModel):
    reservation_id: OpaqueText = Field(alias="reservationId")
    evidence_id: OpaqueText = Field(alias="evidenceId")
    finalized_input_tokens: ExactNonnegativeCount = Field(alias="finalizedInputTokens")
    finalized_output_tokens: ExactNonnegativeCount = Field(alias="finalizedOutputTokens")
    restored_input_tokens: ExactNonnegativeCount = Field(alias="restoredInputTokens")
    restored_output_tokens: ExactNonnegativeCount = Field(alias="restoredOutputTokens")
    provider_cost_retained: bool = Field(alias="providerCostRetained")
    technical_validation_passed: bool = Field(alias="technicalValidationPassed")
    safety_check_passed: bool = Field(alias="safetyCheckPassed")
    durable_result_stored: bool = Field(alias="durableResultStored")
    stable_replay_readable: bool = Field(alias="stableReplayReadable")
    state_version: PositiveVersion = Field(alias="stateVersion")
    finalized_at: datetime = Field(alias="finalizedAt")

    @model_validator(mode="after")
    def validate_user_debit_outcome(self) -> "AllowanceFinalization":
        user_debit_is_final = (
            self.technical_validation_passed
            and self.safety_check_passed
            and self.durable_result_stored
            and self.stable_replay_readable
        )
        finalized = self.finalized_input_tokens + self.finalized_output_tokens
        restored = self.restored_input_tokens + self.restored_output_tokens
        if user_debit_is_final and restored != 0:
            raise ValueError("a delivered result cannot restore user allowance")
        if not user_debit_is_final and finalized != 0:
            raise ValueError("an undelivered result cannot finalize user allowance")
        return self


class TeacherSupportAdmission(_AllowanceModel):
    case_id: OpaqueText = Field(alias="caseId")
    effect_id: OpaqueText = Field(alias="effectId")
    beneficiary_id: OpaqueText = Field(alias="beneficiaryId")
    plan_id: Literal[
        BillingPlanId.TEACHER_SUPPORTED,
        BillingPlanId.FAMILY,
    ] = Field(alias="planId")
    grant_id: OpaqueText = Field(alias="grantId")
    allowance_version: PositiveVersion = Field(alias="allowanceVersion")
    week: ZurichWeek
    admitted_cases: Annotated[int, Field(strict=True, ge=1, le=1)] = Field(
        alias="admittedCases"
    )
    state_version: PositiveVersion = Field(alias="stateVersion")
    admitted_at: datetime = Field(alias="admittedAt")


__all__ = [
    "MAX_EXACT_COUNT",
    "AllowanceFinalization",
    "AllowanceReservation",
    "PlanAllowanceBudget",
    "ProviderUsageEvidence",
    "TeacherSupportAdmission",
    "TeacherSupportScope",
    "ZurichWeek",
]
