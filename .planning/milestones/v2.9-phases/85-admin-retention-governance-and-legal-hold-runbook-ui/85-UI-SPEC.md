# UI Spec: Phase 85 Admin Retention Governance And Legal Hold Runbook UI

**Phase:** 85
**Status:** Complete

## Surface

Extend the existing `/admin/report-operations` immutable evidence panel. Keep the dense operational layout and avoid a separate page or marketing-style flow.

## Controls

- Policy version input.
- Approval state selector.
- Policy owner, legal/compliance approver, and review due inputs.
- Approval reason textarea.
- Legal-hold review owner, reviewer, due date, and reason controls.
- Actions:
  - Check governance.
  - Record approval.
  - Record review.
  - Copy JSON.
  - Download JSON.

## Readback

- Retention approval state, policy version, owner, approver, next review due, and formal approval recorded/not recorded.
- Legal-hold review status, owner, reviewer, due date, and review version.
- Existing immutable storage and legal-hold status remain visible.

## Privacy

The UI may show metadata-only references and redacted evidence fields. It must not render raw report artifacts, S3 keys, presigned URLs, raw JSON/HTML, auth tokens, cookies, passwords, AWS secrets, private bucket/key identifiers, or broad compliance claims.

## Verification

- Frontend lint.
- Frontend build.
- Admin report-operations Playwright spec with governance route mocks and privacy assertions.
