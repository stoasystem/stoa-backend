"""An account's own refusals, and the contract each is sent under (#275).

Opening an account (invite, assign, claim), a teacher's application and
activation, a privileged identity's lifecycle, the administrator's account
console and an account holder's own password change all refuse with these
codes. Refusals that are sign-in or authorization decisions stay
`SecurityErrorCode`s (`action_not_allowed`, `identity_provider_unavailable`,
...) and are raised as `SecurityDecisionError`.

The strings are the ones the routes have always sent, so they never change.
Each code's message is the catalog's `error.<code>`
(`stoa.services.message_catalog.errors.account`).
"""

from __future__ import annotations

from enum import StrEnum

from stoa.rule_violation import RuleContract, RuleViolation, register_codes
from stoa.security.errors import SecurityClientAction


class AccountErrorCode(StrEnum):
    # Opening an account: invite, assign, claim (`account_provisioning_service`).
    INVITATION_INVALID = "invitation_invalid"
    INVITATION_EXPIRED = "invitation_expired"
    INVITATION_ALREADY_USED = "invitation_already_used"
    INVITATION_NOT_FOUND = "invitation_not_found"
    INVITATION_NOT_REVOCABLE = "invitation_not_revocable"
    INVITATION_NOT_REISSUABLE = "invitation_not_reissuable"
    INVITATION_STATE_INVALID = "invitation_state_invalid"
    ACCOUNT_NOT_INVITED = "account_not_invited"
    ACCOUNT_EXISTS = "account_exists"
    ACCOUNT_STATE_INVALID = "account_state_invalid"
    ACCOUNT_PROFILE_MISSING = "account_profile_missing"
    ACCOUNT_STATUS_UNEXPECTED = "account_status_unexpected"
    ACCOUNT_NUMBER_ALREADY_ASSIGNED = "account_number_already_assigned"
    ACCOUNT_NUMBER_UNAVAILABLE = "account_number_unavailable"
    ROLE_NOT_PROVISIONABLE = "role_not_provisionable"
    VALID_EMAIL_REQUIRED = "valid_email_required"
    DATE_OF_BIRTH_INVALID = "date_of_birth_invalid"
    PASSWORD_REJECTED = "password_rejected"
    PROVISIONING_UNAVAILABLE = "provisioning_unavailable"
    PROVISIONING_TEMPORARILY_UNAVAILABLE = "provisioning_temporarily_unavailable"

    # A teacher's application and activation (`teacher_application_service`).
    CREDENTIAL_DOCUMENTS_DEFERRED = "credential_documents_deferred"
    APPLICATION_FIELDS_NOT_ALLOWED = "application_fields_not_allowed"
    INVALID_APPLICATION_FIELD = "invalid_application_field"
    VERIFIED_EMAIL_REQUIRED = "verified_email_required"
    INVALID_REVIEW_DECISION = "invalid_review_decision"
    INVALID_REVIEW_STATE = "invalid_review_state"
    APPLICATION_NOT_FOUND = "application_not_found"
    APPLICATION_VERSION_NOT_FOUND = "application_version_not_found"
    APPLICATION_NOT_APPROVED = "application_not_approved"
    APPLICATION_STATE_INVALID = "application_state_invalid"
    INVITATION_APPLICATION_STATE_INVALID = "invitation_application_state_invalid"
    ACTIVATION_COMMAND_STATE_INVALID = "activation_command_state_invalid"
    INVITATION_EMAIL_MISMATCH = "invitation_email_mismatch"
    ACTIVATION_RESUME_REQUIRED = "activation_resume_required"
    ACTIVATION_TEMPORARILY_UNAVAILABLE = "activation_temporarily_unavailable"

    # A privileged identity's lifecycle (`privileged_identity_service`).
    REQUIRED_FIELD = "required_field"
    INVALID_IDENTITY_OPERATION = "invalid_identity_operation"
    INVALID_PRIVILEGED_IDENTITY_COMMAND = "invalid_privileged_identity_command"
    PRIVILEGED_IDENTITY_NOT_FOUND = "privileged_identity_not_found"
    IDENTITY_RESTORE_NOT_ALLOWED = "identity_restore_not_allowed"
    IDENTITY_CHANGE_TEMPORARILY_UNAVAILABLE = "identity_change_temporarily_unavailable"
    CAPABILITY_REGRANT_REQUIRED = "capability_regrant_required"
    CAPABILITY_SELF_GRANT_FORBIDDEN = "capability_self_grant_forbidden"

    # The administrator's account console (`routers/admin.py`).
    ACCOUNT_NOT_FOUND = "account_not_found"
    ACCOUNT_NOT_A_STUDENT = "account_not_a_student"
    ACCOUNT_EMAIL_MISSING = "account_email_missing"
    ACCOUNT_STATUS_UNCHANGED = "account_status_unchanged"
    ACCOUNT_STATUS_TRANSITION_INVALID = "account_status_transition_invalid"
    ACCOUNT_STATUS_TRANSITION_CONFLICT = "account_status_transition_conflict"
    ACCOUNT_SELF_DEACTIVATION_FORBIDDEN = "account_self_deactivation_forbidden"
    ACCOUNT_LAST_ACTIVE_ADMIN = "account_last_active_admin"
    ACCOUNT_PEER_ADMIN_PASSWORD_RESET_FORBIDDEN = "account_peer_admin_password_reset_forbidden"
    ACCOUNT_PASSWORD_RESET_CONFLICT = "account_password_reset_conflict"
    ALLOWANCE_VERSION_CONFLICT = "allowance_version_conflict"
    CURSOR_INVALID = "cursor_invalid"
    PAGE_TOKEN_INVALID = "page_token_invalid"
    REPORT_NOT_FOUND = "report_not_found"

    # Sign-up, recovery and an account holder's own password (`routers/auth.py`).
    PUBLIC_AUTHENTICATION_UNAVAILABLE = "public_authentication_unavailable"
    PUBLIC_REGISTRATION_CLOSED = "public_registration_closed"
    PUBLIC_REGISTRATION_NOT_IMPLEMENTED = "public_registration_not_implemented"
    PASSWORD_RECOVERY_CLOSED = "password_recovery_closed"
    PASSWORD_RECOVERY_NOT_IMPLEMENTED = "password_recovery_not_implemented"
    LOCALE_NOT_SUPPORTED = "locale_not_supported"
    PASSWORD_CHANGE_CREDENTIALS_INVALID = "password_change_credentials_invalid"
    PASSWORD_CHANGE_VERIFICATION_FAILED = "password_change_verification_failed"
    PASSWORD_CHANGE_CODE_RATE_LIMITED = "password_change_code_rate_limited"
    PASSWORD_CHANGE_CODE_DELIVERY_FAILED = "password_change_code_delivery_failed"
    PASSWORD_CHANGE_STATE_NOT_CLEARED = "password_change_state_not_cleared"

    @property
    def contract(self) -> RuleContract:
        return ACCOUNT_ERROR_REGISTRY[self]


_C = AccountErrorCode
_A = SecurityClientAction


def _conflict() -> RuleContract:
    """The state is not the one the command needs; nothing a client can retry."""
    return RuleContract(409)


def _invalid() -> RuleContract:
    """The request itself is wrong; the person can correct it."""
    return RuleContract(422, _A.CORRECT_INPUT)


def _not_found() -> RuleContract:
    return RuleContract(404)


def _unavailable() -> RuleContract:
    """A dependency failed part-way; the same command may be sent again later."""
    return RuleContract(503, _A.RETRY_LATER)


ACCOUNT_ERROR_REGISTRY: dict[AccountErrorCode, RuleContract] = {
    # One answer for every unusable token: a missing digest and a burned digest
    # must not be told apart, or the difference says which tokens existed.
    _C.INVITATION_INVALID: _conflict(),
    _C.INVITATION_EXPIRED: _conflict(),
    _C.INVITATION_ALREADY_USED: _conflict(),
    _C.INVITATION_NOT_FOUND: _not_found(),
    _C.INVITATION_NOT_REVOCABLE: _conflict(),
    _C.INVITATION_NOT_REISSUABLE: _conflict(),
    _C.INVITATION_STATE_INVALID: _conflict(),
    _C.ACCOUNT_NOT_INVITED: _conflict(),
    _C.ACCOUNT_EXISTS: _conflict(),
    _C.ACCOUNT_STATE_INVALID: _conflict(),
    _C.ACCOUNT_PROFILE_MISSING: _conflict(),
    _C.ACCOUNT_STATUS_UNEXPECTED: _conflict(),
    _C.ACCOUNT_NUMBER_ALREADY_ASSIGNED: _conflict(),
    _C.ACCOUNT_NUMBER_UNAVAILABLE: _unavailable(),
    _C.ROLE_NOT_PROVISIONABLE: _invalid(),
    _C.VALID_EMAIL_REQUIRED: _invalid(),
    _C.DATE_OF_BIRTH_INVALID: _invalid(),
    _C.PASSWORD_REJECTED: _invalid(),
    _C.PROVISIONING_UNAVAILABLE: _unavailable(),
    _C.PROVISIONING_TEMPORARILY_UNAVAILABLE: _unavailable(),
    _C.CREDENTIAL_DOCUMENTS_DEFERRED: _invalid(),
    _C.APPLICATION_FIELDS_NOT_ALLOWED: _invalid(),
    # `{field}` names the field in the message; it is not a body field.
    _C.INVALID_APPLICATION_FIELD: _invalid(),
    _C.VERIFIED_EMAIL_REQUIRED: _invalid(),
    _C.INVALID_REVIEW_DECISION: _invalid(),
    _C.INVALID_REVIEW_STATE: _invalid(),
    _C.APPLICATION_NOT_FOUND: _not_found(),
    _C.APPLICATION_VERSION_NOT_FOUND: _not_found(),
    _C.APPLICATION_NOT_APPROVED: _conflict(),
    _C.APPLICATION_STATE_INVALID: _conflict(),
    _C.INVITATION_APPLICATION_STATE_INVALID: _conflict(),
    _C.ACTIVATION_COMMAND_STATE_INVALID: _conflict(),
    _C.INVITATION_EMAIL_MISMATCH: _conflict(),
    _C.ACTIVATION_RESUME_REQUIRED: _conflict(),
    _C.ACTIVATION_TEMPORARILY_UNAVAILABLE: _unavailable(),
    _C.REQUIRED_FIELD: _invalid(),
    _C.INVALID_IDENTITY_OPERATION: _invalid(),
    _C.INVALID_PRIVILEGED_IDENTITY_COMMAND: _conflict(),
    _C.PRIVILEGED_IDENTITY_NOT_FOUND: _not_found(),
    _C.IDENTITY_RESTORE_NOT_ALLOWED: _conflict(),
    _C.IDENTITY_CHANGE_TEMPORARILY_UNAVAILABLE: _unavailable(),
    _C.CAPABILITY_REGRANT_REQUIRED: _conflict(),
    _C.CAPABILITY_SELF_GRANT_FORBIDDEN: _conflict(),
    _C.ACCOUNT_NOT_FOUND: _not_found(),
    _C.ACCOUNT_NOT_A_STUDENT: _conflict(),
    _C.ACCOUNT_EMAIL_MISSING: _conflict(),
    _C.ACCOUNT_STATUS_UNCHANGED: _conflict(),
    _C.ACCOUNT_STATUS_TRANSITION_INVALID: _conflict(),
    _C.ACCOUNT_STATUS_TRANSITION_CONFLICT: _conflict(),
    _C.ACCOUNT_SELF_DEACTIVATION_FORBIDDEN: _conflict(),
    _C.ACCOUNT_LAST_ACTIVE_ADMIN: _conflict(),
    _C.ACCOUNT_PEER_ADMIN_PASSWORD_RESET_FORBIDDEN: _conflict(),
    _C.ACCOUNT_PASSWORD_RESET_CONFLICT: _conflict(),
    _C.ALLOWANCE_VERSION_CONFLICT: _conflict(),
    _C.CURSOR_INVALID: _invalid(),
    _C.PAGE_TOKEN_INVALID: RuleContract(400, _A.CORRECT_INPUT),
    _C.REPORT_NOT_FOUND: _not_found(),
    _C.PUBLIC_AUTHENTICATION_UNAVAILABLE: _unavailable(),
    # Gone, not missing: an old client is told the command was withdrawn.
    _C.PUBLIC_REGISTRATION_CLOSED: RuleContract(410, _A.CONTACT_SUPPORT),
    _C.PASSWORD_RECOVERY_CLOSED: RuleContract(410, _A.CONTACT_SUPPORT),
    _C.PUBLIC_REGISTRATION_NOT_IMPLEMENTED: RuleContract(501),
    _C.PASSWORD_RECOVERY_NOT_IMPLEMENTED: RuleContract(501),
    _C.LOCALE_NOT_SUPPORTED: RuleContract(400, _A.CORRECT_INPUT),
    # 400, not 401: the session is valid, the password in the body is not. A
    # 401 would read as an expired session and sign the caller out.
    _C.PASSWORD_CHANGE_CREDENTIALS_INVALID: RuleContract(400, _A.CORRECT_INPUT),
    # A wrong, expired, spent or never-issued code all answer the same.
    _C.PASSWORD_CHANGE_VERIFICATION_FAILED: RuleContract(400, _A.REQUEST_NEW_CODE),
    _C.PASSWORD_CHANGE_CODE_RATE_LIMITED: RuleContract(429, _A.RETRY_LATER),
    # Nothing was spent and any live code still works.
    _C.PASSWORD_CHANGE_CODE_DELIVERY_FAILED: _unavailable(),
    # The password did change; signing in again finishes the change.
    _C.PASSWORD_CHANGE_STATE_NOT_CLEARED: RuleContract(503, _A.REAUTHENTICATE),
}

register_codes("account", AccountErrorCode, ACCOUNT_ERROR_REGISTRY)


class AccountViolation(RuleViolation):
    """An account's lifecycle refused a request: `AccountViolation(code, params=...)`."""

    code: AccountErrorCode
