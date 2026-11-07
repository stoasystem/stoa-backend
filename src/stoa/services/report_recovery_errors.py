"""Why report recovery refused a request or a target, and each code's contract (#285).

Two services refuse with these codes. `report_recovery_service` resends one
report's email or retries its generation, and raises `ReportRecoveryError`.
`report_recovery_job_service` previews, creates, resumes and cancels the
bounded async jobs, and raises `RecoveryJobError`. Both are rule violations,
and `stoa.rule_violation` renders them as `{detail: {code, message,
correlationId}}` (#211). Before #285 the admin router turned them into
`HTTPException(detail=<English sentence>)`.

A recovery job's worker does not answer a request: it records an outcome on
each target. The target result stores the code and its params beside the old
English `detail`, so the admin console renders the message in the reader's
language and old results stay readable. `report_not_found` (an account code)
and the last three codes below are recorded only there.

Nothing a param carries may name a private report artifact: a raise site passes
values through `redact_private_artifact_text`, and keeps whatever explains the
refusal further in `internal_detail`, which is logged and never sent.

Each code's message is the catalog's `error.<code>`
(`stoa.services.message_catalog.errors.report_recovery`).
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from stoa.rule_violation import RuleContract, RuleViolation, register_codes
from stoa.security.errors import SecurityClientAction


class ReportRecoveryErrorCode(StrEnum):
    # One report: resend its email, retry its generation (`report_recovery_service`).
    REPORT_DELIVERY_NOT_FAILED = "report_delivery_not_failed"
    REPORT_HTML_ARTIFACT_MISSING = "report_html_artifact_missing"
    REPORT_RECIPIENT_UNLINKED = "report_recipient_unlinked"
    REPORT_RECIPIENT_EMAIL_MISSING = "report_recipient_email_missing"
    REPORT_RESEND_FAILED = "report_resend_failed"
    REPORT_GENERATION_NOT_FAILED = "report_generation_not_failed"
    REPORT_GENERATION_RETRY_IN_PROGRESS = "report_generation_retry_in_progress"
    REPORT_GENERATION_RETRY_FAILED = "report_generation_retry_failed"

    # A recovery job: preview, create, resume, cancel (`report_recovery_job_service`).
    RECOVERY_REASON_REQUIRED = "recovery_reason_required"
    RECOVERY_STATUS_FILTER_UNSUPPORTED = "recovery_status_filter_unsupported"
    RESUME_RESULT_FILTER_REQUIRED = "resume_result_filter_required"
    RESUME_RESULT_FILTER_UNSUPPORTED = "resume_result_filter_unsupported"
    RECOVERY_PREVIEW_STALE = "recovery_preview_stale"
    RECOVERY_JOB_NO_ELIGIBLE_TARGETS = "recovery_job_no_eligible_targets"
    RECOVERY_JOB_NOT_FOUND = "recovery_job_not_found"
    RECOVERY_JOB_ALREADY_TERMINAL = "recovery_job_already_terminal"
    RECOVERY_JOB_NOT_CANCELLABLE = "recovery_job_not_cancellable"
    SOURCE_RECOVERY_JOB_NOT_TERMINAL = "source_recovery_job_not_terminal"
    SOURCE_RECOVERY_JOB_INCOMPLETE = "source_recovery_job_incomplete"
    RECOVERY_JOB_TYPE_NOT_RESUMABLE = "recovery_job_type_not_resumable"
    RECOVERY_JOB_RECORD_INCOMPLETE = "recovery_job_record_incomplete"
    RECOVERY_PAGE_INCOMPLETE = "recovery_page_incomplete"

    # Recorded on a job's target result only; never an HTTP refusal.
    REPORT_RECORD_INCOMPLETE = "report_record_incomplete"
    REPORT_NO_LONGER_ELIGIBLE = "report_no_longer_eligible"
    RECOVERY_TARGET_CANCELLED = "recovery_target_cancelled"

    @property
    def contract(self) -> RuleContract:
        return REPORT_RECOVERY_ERROR_REGISTRY[self]


_C = ReportRecoveryErrorCode
_A = SecurityClientAction


def _conflict() -> RuleContract:
    """The report or job is not in the state the command needs."""
    return RuleContract(409)


def _invalid() -> RuleContract:
    """The request itself is wrong; the operator can correct it."""
    return RuleContract(422, _A.CORRECT_INPUT)


def _needs_repair() -> RuleContract:
    """A stored record is malformed; an operator repairs it before anything retries."""
    return RuleContract(422, _A.CONTACT_SUPPORT)


def _delivery_failed() -> RuleContract:
    """The attempt ran and failed downstream; the report stays failed and can be retried."""
    return RuleContract(502, _A.RETRY_LATER)


# The statuses are the ones the routes have always answered with.
REPORT_RECOVERY_ERROR_REGISTRY: dict[ReportRecoveryErrorCode, RuleContract] = {
    _C.REPORT_DELIVERY_NOT_FAILED: _conflict(),
    _C.REPORT_HTML_ARTIFACT_MISSING: _needs_repair(),
    _C.REPORT_RECIPIENT_UNLINKED: RuleContract(403),
    _C.REPORT_RECIPIENT_EMAIL_MISSING: _needs_repair(),
    _C.REPORT_RESEND_FAILED: _delivery_failed(),
    _C.REPORT_GENERATION_NOT_FAILED: _conflict(),
    _C.REPORT_GENERATION_RETRY_IN_PROGRESS: _conflict(),
    _C.REPORT_GENERATION_RETRY_FAILED: _delivery_failed(),
    _C.RECOVERY_REASON_REQUIRED: _invalid(),
    # `{required_status}` names the one status the job type recovers.
    _C.RECOVERY_STATUS_FILTER_UNSUPPORTED: _invalid(),
    _C.RESUME_RESULT_FILTER_REQUIRED: _invalid(),
    # `{result_filter}` is the first filter value refused, redacted.
    _C.RESUME_RESULT_FILTER_UNSUPPORTED: _invalid(),
    _C.RECOVERY_PREVIEW_STALE: _conflict(),
    _C.RECOVERY_JOB_NO_ELIGIBLE_TARGETS: _invalid(),
    _C.RECOVERY_JOB_NOT_FOUND: RuleContract(404),
    _C.RECOVERY_JOB_ALREADY_TERMINAL: _conflict(),
    _C.RECOVERY_JOB_NOT_CANCELLABLE: _conflict(),
    _C.SOURCE_RECOVERY_JOB_NOT_TERMINAL: _conflict(),
    _C.SOURCE_RECOVERY_JOB_INCOMPLETE: _needs_repair(),
    _C.RECOVERY_JOB_TYPE_NOT_RESUMABLE: _invalid(),
    _C.RECOVERY_JOB_RECORD_INCOMPLETE: _needs_repair(),
    _C.RECOVERY_PAGE_INCOMPLETE: _needs_repair(),
    _C.REPORT_RECORD_INCOMPLETE: _needs_repair(),
    _C.REPORT_NO_LONGER_ELIGIBLE: _conflict(),
    _C.RECOVERY_TARGET_CANCELLED: _conflict(),
}

register_codes("report_recovery", ReportRecoveryErrorCode, REPORT_RECOVERY_ERROR_REGISTRY)


class ReportRecoveryError(RuleViolation):
    """Recovering one report was refused or failed.

    `result` is the outcome a recovery job records for the target (`refused`
    or `failed`); `error_class` names the underlying failure for the audit.
    """

    code: ReportRecoveryErrorCode

    def __init__(
        self,
        code: ReportRecoveryErrorCode,
        *,
        result: str = "failed",
        error_class: str | None = None,
        internal_detail: str | None = None,
        params: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(code, internal_detail=internal_detail, params=params)
        self.result = result
        self.error_class = error_class


class RecoveryJobError(RuleViolation):
    """A recovery job command was refused: `RecoveryJobError(code, params=...)`."""

    code: ReportRecoveryErrorCode
