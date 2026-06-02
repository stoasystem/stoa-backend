# Phase 15: Artifact Key Contract & Helper Hardening - Context

**Gathered:** 2026-06-03
**Status:** Ready for planning
**Source:** Autonomous smart-discuss path; backend helper hardening phase with existing research.

<domain>
## Phase Boundary

This phase locks the backend report artifact contract and makes it directly testable. It should not change the weekly report orchestration order, SES behavior, parent APIs, CDK resources, or deployed smoke mechanism.

In scope:
- Expose one helper module for report artifact keys and S3 artifact reads/writes.
- Enforce exact JSON/HTML key shape: `weekly-reports/{parent_id}/{student_id}/{week_start}/report.{json,html}`.
- Reject blank or unsafe parent/student/week key inputs instead of collapsing to `unknown`.
- Validate `week_start` as an ISO date and normalize it to `YYYY-MM-DD`.
- Keep keys limited to canonical backend IDs and dates, excluding emails, display names, and arbitrary text.
- Ensure JSON/HTML writes use the configured reports bucket, required content types, and no ACL parameters.
- Add a JSON read helper for Phase 17 smoke/future backend-mediated reads.

Out of scope:
- Changing the canonical `weekly-reports/` prefix.
- Changing DynamoDB metadata ordering or SES ordering.
- Adding public S3 access, presigned URLs, or frontend direct reads.
- Running deployed Lambda smoke.
</domain>

<decisions>
## Locked Decisions

- Continue blessing `weekly-reports/` as the only artifact prefix.
- Parent/student key segments must already be safe backend identifiers matching `[A-Za-z0-9_.=-]+`; unsafe values fail closed.
- `week_start` must parse via `date.fromisoformat()` and is emitted as the normalized ISO date.
- Artifact helpers should accept an optional S3 client for tests and Lambda smoke code.
- Artifact write helpers rely on bucket privacy and Lambda IAM; they must not pass S3 ACL fields.
</decisions>

<references>
## Canonical References

- `.planning/REQUIREMENTS.md` - ARTIFACT-01 through ARTIFACT-05 and STORAGE-01 through STORAGE-04/STORAGE-08.
- `.planning/research/SUMMARY.md` - recommendation to keep `weekly-reports/...` and add helper/read behavior.
- `.planning/phases/14-cdk-runtime-configuration-verification/14-VERIFICATION.md` - reports bucket configuration guard and synth evidence.
- `src/stoa/services/report_service.py` - current embedded key builder and S3 writes.
- `tests/test_report_service.py` - current report storage tests.
- `tests/test_report_flow.py` - weekly report integration flow tests.
</references>

<risks>
## Risks and Constraints

- Tightening key validation can surface bad existing test fixtures or unexpected stored IDs; keep allowed characters broad enough for UUID/Cognito-style IDs while rejecting slashes, emails, spaces, and blank values.
- Existing `_safe_s3_segment` also supports parent portal links; do not accidentally break portal link formatting while replacing artifact key behavior.
- Phase 16 owns failure ordering assertions; this phase should preserve current ordering and add only helper-level/read/write contract tests.
</risks>
