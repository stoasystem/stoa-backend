# Requirements: v2.5 Production Support Handoff Verification Closeout

**Milestone:** v2.5
**Status:** Complete
**Created:** 2026-06-07

## Goal

Close the v2.4 production verification gap by deploying the support handoff backend/frontend changes, recording deploy/runtime/CDK evidence, and running read-only production API/browser smoke for support handoff without mutating report artifacts or writing to external support systems.

## Requirements

### PRODVERIFY-01 v2.4 Deploy Evidence

Operators have deploy evidence proving the v2.4 backend and frontend support handoff changes reached production.

Acceptance criteria:

- Backend deploy workflow run ID, URL, job ID, commit SHA, timestamps, and status are recorded.
- Frontend deploy workflow run ID, URL, job ID, commit SHA, timestamps, and status are recorded.
- Lambda build manifest and live runtime metadata are recorded for the deployed backend commit.
- CDK diff/deploy classification is recorded, including whether drift is expected Lambda code asset drift only.

### PRODVERIFY-02 Read-Only Production Support Handoff API Smoke

Production API smoke verifies support handoff auth, privacy, and refusal behavior without customer-impacting mutation.

Acceptance criteria:

- Smoke uses the approved secret-backed production admin credential path without printing passwords or tokens.
- `/health` passes.
- Unauthenticated support handoff package request is rejected.
- Authenticated admin support handoff preview using safe metadata returns a metadata-only package.
- Authenticated admin `external_write` package returns a refused result and performs no external write.
- Request IDs and privacy denylist results are recorded.

### PRODVERIFY-03 Read-Only Production Browser Smoke

Production browser smoke verifies deployed support handoff UI markers and privacy boundary.

Acceptance criteria:

- `/admin/report-operations` loads with admin auth.
- Support handoff panel/markers are visible.
- Browser guard blocks report mutation endpoints and external write attempts.
- Visible text and captured responses do not expose S3 keys, presigned URLs, raw report JSON/HTML, tokens, or raw artifact payloads.
- Screenshot or textual marker evidence is recorded.

### VERIFY-08 v2.5 Closeout Audit

v2.5 closes with an audit proving the deferred production verification gap is resolved or explicitly blocked.

Acceptance criteria:

- Release gate, live verification, and final audit docs are completed.
- Any failed/skipped production check records reason, owner, and follow-up.
- v2.4 audit residual risk is updated or cross-referenced.
- No production report artifact mutation or external support-system write occurs.

## Out of Scope

- New support handoff features.
- Direct external support-system writes.
- Customer-data production mutation smoke.
- Raw report artifact export.
- New AWS resources unless production deploy verification proves an unexpected infrastructure blocker.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PRODVERIFY-01 | Phase 70 | Complete |
| PRODVERIFY-02 | Phase 70 | Complete |
| PRODVERIFY-03 | Phase 70 | Complete |
| VERIFY-08 | Phase 70 | Complete |
