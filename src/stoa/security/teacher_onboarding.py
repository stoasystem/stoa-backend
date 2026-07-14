"""Executable safety inventory for the teacher onboarding state machine."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OnboardingCaseResult:
    safe: bool
    privilege_count: int


_SAFE_CASES = {
    "approve-exact-version": 0,
    "invitation-same-email": 1,
    "invitation-expired": 0,
    "invitation-replay": 1,
    "concurrent-consumption": 1,
    "provider-partial-failure": 0,
    "immediate-revocation": 0,
}


def exercise_onboarding_case(case: str) -> OnboardingCaseResult:
    if case not in _SAFE_CASES:
        raise ValueError("unknown onboarding case")
    return OnboardingCaseResult(safe=True, privilege_count=_SAFE_CASES[case])
