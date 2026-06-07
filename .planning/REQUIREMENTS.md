# Requirements: v2.9 Retention Governance And Legal Hold Operations

**Milestone:** v2.9
**Status:** Active
**Created:** 2026-06-07

## Goal

Make immutable evidence retention and legal-hold operations governable: define the approval packet, owner model, runbook, review cadence, break-glass policy, backend metadata recording, admin evidence workflow, and release gate needed before broad compliance claims are made.

## Requirements

### GOV-01 Retention Policy And Legal Hold Governance Readiness

Implementers and operators have a precise governance contract before recording retention-policy approval or legal-hold operating decisions.

Acceptance criteria:

- Contract defines retention policy owner, legal/compliance approver roles, approval evidence fields, review cadence, expiry/reapproval behavior, emergency break-glass expectations, and audit requirements.
- Contract distinguishes technical proof of S3 Object Lock behavior from formal legal/compliance approval.
- Approval packet includes v2.8 deploy evidence, Object Lock mode/days, immutable manifest privacy guarantees, smoke evidence, residual risk statements, and required signoff fields.
- Runbook specification covers applying/releasing legal holds, reviewing active holds, handling refused/destructive actions, incident escalation, and evidence export.
- Privacy boundary forbids raw report artifacts, S3 keys, presigned URLs, raw JSON/HTML, auth tokens, cookies, passwords, AWS secrets, and broad compliance claims not backed by approval evidence.

### GOV-02 Backend Retention Approval And Legal Hold Review Metadata

Admins can record and inspect metadata-only retention approval and legal-hold review evidence.

Acceptance criteria:

- Backend models retention approval status, approver metadata, policy version, approval evidence references, review due dates, and approval/refusal reasons.
- Backend models legal-hold review records, owner assignment, review cadence, break-glass metadata, and append-only audit events.
- APIs are admin-only and metadata-only; they never return private storage identifiers, raw object payloads, raw report artifacts, S3 keys, presigned URLs, raw JSON/HTML, tokens, cookies, passwords, or AWS secrets.
- Tests cover authorization, schema validation, stale/conflicting updates, privacy denylist, refusal behavior, and append-only audit rows.

### UI-15 Admin Retention Governance And Legal Hold Runbook UI

Admin report operations UI exposes retention approval status, legal-hold review status, and runbook evidence controls.

Acceptance criteria:

- UI displays approval state, policy version, review due date, owner metadata, legal-hold review status, refusal reasons, and runbook links using allowlisted fields only.
- UI separates read-only governance status from explicit state-changing actions.
- UI requires operator reasons and confirmation for approval recording, review completion, and break-glass metadata actions.
- UI does not render raw artifacts, S3 keys, presigned URLs, raw JSON/HTML, secrets, cookies, or tokens.
- Playwright covers status rendering, admin gating, refusal states, reason validation, and privacy denylist.

### VERIFY-12 v2.9 Release Gate And Governance Verification

v2.9 closes with release evidence proving retention governance and legal-hold operations are documented, metadata-only, and correctly gated.

Acceptance criteria:

- Release evidence records backend/frontend deploy evidence, commit SHAs, timestamps, local quality gates, admin-only API request IDs, browser smoke, and privacy denylist results.
- Evidence includes the retention approval packet template and clearly marks whether formal legal/compliance approval has or has not been recorded.
- Production smoke is read-only by default; any state-changing verification uses only approved metadata-only governance records or a named non-customer safe fixture.
- Evidence proves no audit deletion, no customer report artifact mutation, no immutable object deletion, no external support-system write, and no private marker exposure.
- Final audit records residual legal/compliance gaps and future requirements without overstating compliance coverage.

## Future Requirements

- Formal legal/compliance approval of exact retention periods if not completed during v2.9.
- Direct support ticket/evidence retention integrations after an approved connector or secret-backed credential path exists.
- Dedicated Step Functions/SQS orchestration if immutable verification or legal-hold workflows become asynchronous.
- Rich/WYSIWYG report editor.
- PDF/multilingual report delivery.
- Billing and analytics product expansion.

## Out of Scope

- Providing legal advice or fabricating legal/compliance approval.
- Manual AWS console changes.
- Deleting audit rows or immutable evidence objects.
- Mutating customer report artifacts during smoke.
- Direct third-party support-system writes.
- Broad compliance claims beyond recorded approval and verified technical behavior.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| GOV-01 | Phase 83 | Complete |
| GOV-02 | Phase 84 | Complete |
| UI-15 | Phase 85 | Planned |
| VERIFY-12 | Phase 86 | Planned |
