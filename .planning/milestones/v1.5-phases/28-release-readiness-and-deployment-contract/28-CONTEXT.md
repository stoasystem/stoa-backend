---
phase: 28
phase_name: Release Readiness and Deployment Contract
status: ready_for_planning
gathered: 2026-06-04
---

# Phase 28: Release Readiness and Deployment Contract - Context

## Phase Boundary

Define the release checklist, deployment contract, rollback points, and mutation safety gate needed before v1.5 performs production report recovery smoke.

This phase delivers documentation and evidence structure only. It does not deploy code, invoke live recovery mutations, or create smoke fixture data.

## Locked Decisions

### D-01 Deployment repositories

The release checklist must cover all three repositories that participate in report operations rollout:

- Backend: `/Users/zhdeng/stoa-backend`
- Frontend: `/Users/zhdeng/stoa-frontend`
- Infrastructure/CDK: `/Users/zhdeng/stoa-infra`

### D-02 Production environment contract

The deployment contract must record these concrete production identifiers:

- AWS profile: `stoa`
- AWS region: `eu-central-2`
- API Lambda: `stoa-api`
- Weekly report Lambda: `stoa-weekly-report`
- Reports bucket: `stoa-reports-562923011260`
- Frontend app URL: `https://app.stoaedu.ch`
- Report operations route: `https://app.stoaedu.ch/admin/report-operations`

### D-03 CDK diff classification

CDK diff evidence for this milestone must classify Lambda code asset hash changes separately from infrastructure drift. Expected-only Lambda `Code.S3Key` changes are acceptable; unexpected IAM, bucket, API route, DynamoDB, or policy changes must block live mutation smoke until reviewed.

### D-04 Mutation safety gate

No production `generation_failed` retry, `email_failed` single resend, or selected bulk resend may run before a safe non-customer smoke target is documented with parent ID, student ID, week start, original status, expected terminal status, cleanup/restore expectation, and confirmation that it contains no customer PII.

### D-05 Rollback readiness

Rollback points must be documented before deployment verification starts:

- Backend Lambda code rollback path for `stoa-api` and `stoa-weekly-report`.
- Frontend asset or deployment rollback path for `app.stoaedu.ch`.
- Infra/CDK rollback or stop condition for unexpected stack drift.

## Canonical References

Downstream agents MUST read these before executing Phase 28:

- `.planning/REQUIREMENTS.md` - v1.5 REL requirements and closeout constraints.
- `.planning/ROADMAP.md` - Phase 28 success criteria and dependency chain.
- `.planning/STATE.md` - active milestone state and prior live verification constraints.
- `.planning/v1.4-MILESTONE-AUDIT.md` - residual risks from v1.4 closeout.
- `.planning/milestones/v1.4-phases/27-report-recovery-verification-and-live-evidence/27-VERIFICATION.md` - latest live Lambda/API/CDK evidence.
- `.planning/debug/update-lambda-function-code-failed-resolved.md` - backend deploy IAM and Lambda update failure history.

## Specific Ideas

Phase 28 should produce one release readiness document that later phases can fill with live outputs. It should include checklists and placeholders rather than fragile prose:

- Repository and commit SHA ledger.
- Required commands and expected output categories.
- CDK diff classification matrix.
- Production identifiers and environment variables.
- Rollback and stop-condition checklist.
- Safe smoke target acceptance criteria.

## Deferred Ideas

- Actual frontend deployment verification belongs to Phase 29.
- Actual backend deployment and authenticated API verification belongs to Phase 30.
- Actual retry/resend/bulk resend mutation smoke belongs to Phase 31.
- Full operator runbook and observability links belong to Phase 32.

---
*Phase: 28-release-readiness-and-deployment-contract*
*Context gathered: 2026-06-04*
