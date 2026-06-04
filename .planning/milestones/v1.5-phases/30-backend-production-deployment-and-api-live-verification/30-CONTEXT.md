---
phase: 30
phase_name: Backend Production Deployment and API Live Verification
status: ready_for_planning
gathered: 2026-06-04
---

# Phase 30: Backend Production Deployment and API Live Verification - Context

## Phase Boundary

Verify backend report operations production state without mutating report recovery records.

This phase may run AWS identity checks, Lambda configuration checks, CDK diff, backend tests, API health checks, unauthenticated rejection checks, and authenticated admin read-only list/detail checks if a production admin token is available.

This phase does not run retry generation, single resend, or bulk resend mutations.

## Locked Decisions

### D-01 Production identifiers

- AWS profile: `stoa`
- AWS region: `eu-central-2`
- API base URL: `https://api.stoaedu.ch`
- API Lambda: `stoa-api`
- Weekly report Lambda: `stoa-weekly-report`
- Reports bucket: `stoa-reports-562923011260`

### D-02 Admin-auth token handling

Admin-authenticated live API checks require a real production admin access token. The demo/local account `admin@test.com / password123` is not assumed to exist in production. If it does not authenticate, record the exact blocker and do not fake admin-auth list/detail evidence.

### D-03 Mutation boundary

Only read-only live checks are allowed in Phase 30:

- `GET /health`
- `GET /admin/reports/ops`
- `GET /admin/reports/{parent_id}/{student_id}/{week_start}/ops`

No `POST /retry-generation`, `POST /resend`, or `POST /bulk-resend` calls are allowed in Phase 30.

## Canonical References

- `.planning/REQUIREMENTS.md` - LIVE-01, LIVE-02, LIVE-04, and VERIFY-02.
- `.planning/ROADMAP.md` - Phase 30 success criteria.
- `.planning/phases/28-release-readiness-and-deployment-contract/28-RELEASE-READINESS.md` - live verification and stop-condition contract.
- `.planning/phases/29-frontend-production-deployment-verification/29-VERIFICATION.md` - frontend production route evidence.
- `.planning/milestones/v1.4-phases/27-report-recovery-verification-and-live-evidence/27-VERIFICATION.md` - previous Lambda/API/CDK evidence.

## Specific Ideas

Phase 30 should produce a verification artifact that separates:

- Passed infrastructure/runtime evidence.
- Passed unauthenticated rejection evidence.
- Passed or blocked admin-auth list/detail evidence.
- CDK diff classification.
- Exact recovery instructions for missing admin token.

## Deferred Ideas

- Recovery mutation smoke belongs to Phase 31 and must remain blocked until Phase 30 admin-auth read-only checks pass and safe smoke target criteria are available.
- Operator runbook belongs to Phase 32.

---
*Phase: 30-backend-production-deployment-and-api-live-verification*
*Context gathered: 2026-06-04*
