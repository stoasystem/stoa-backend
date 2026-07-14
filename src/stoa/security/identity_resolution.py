"""Named fail-closed identity cases retained for the Wave 0 contract inventory."""

from dataclasses import dataclass

from stoa.security.errors import SecurityErrorCode


@dataclass(frozen=True, slots=True)
class IdentityCaseDecision:
    allowed: bool
    code: SecurityErrorCode


def evaluate_identity_case(case: str) -> IdentityCaseDecision:
    code = (
        SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE
        if case == "authorization-store-outage"
        else SecurityErrorCode.IDENTITY_CONFLICT
    )
    return IdentityCaseDecision(False, code)
