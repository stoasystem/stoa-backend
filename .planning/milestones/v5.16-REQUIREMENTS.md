# Requirements: v5.16 End-To-End Product Readiness And Release Evidence

**Milestone:** v5.16
**Status:** Complete
**Created:** 2026-07-05
**Prior milestone:** v5.15 Usage, Quota, And Product Stability

## Purpose

Turn the locally completed feature and stability work from v5.12-v5.15 into a single end-to-end readiness story. This milestone should prove real product journeys across backend and frontend surfaces, close or precisely classify the residual v5.14 frontend e2e blocker, and separate implementation defects from external provider activation blockers.

This is a product readiness and stability milestone. It is not a broad compliance audit and not a live-provider rollout unless credentials and explicit approval are available.

## Requirements

### READINESS-01 Product Readiness Reality Audit

Acceptance criteria:

- Current backend routes, services, tests, and frontend e2e specs are mapped for auth, verification, billing, entitlement, usage/quota, curriculum, teacher help, parent account operations, and admin support.
- v5.12, v5.13, v5.14, and v5.15 evidence is reconciled against current docs.
- Stale or contradictory planning status is corrected.
- v5.14 partial e2e gate is recorded as either an execution blocker or a real product defect.
- External provider blockers are separated from implementation gaps.

### E2E-01 Focused Frontend E2E Gate

Acceptance criteria:

- Focused frontend e2e is run when permitted for `auth.spec.ts`, `admin-account-operations.spec.ts`, and `parent-account-operations.spec.ts`.
- Billing/subscription and curriculum e2e coverage is included if release-critical.
- Frontend test results include command, timestamp, pass/fail count, and blocker classification.
- Any real contract regressions are fixed or promoted to explicit follow-up requirements.
- Execution permission/platform blockers are not mislabeled as product completion.

### SMOKE-01 Backend Product Smoke Evidence

Acceptance criteria:

- `GET /admin/core-smoke` is verified against the release matrix.
- Account operations, billing support evidence, usage reconciliation, and curriculum readiness responses expose enough support-safe evidence for release triage.
- Smoke output distinguishes expected auth/provider/external blocks from regressions.
- No raw learning content, Cognito token material, provider payloads, or private artifact data is included in release evidence.
- Focused backend tests pass for any changed smoke/evidence contracts.

### JOURNEY-01 Cross-Surface Product Journey Verification

Acceptance criteria:

- Parent journey verifies verification state, billing state, entitlement, child binding, usage/quota explanations, and support state.
- Student journey verifies curriculum read, practice/question flow, quota behavior, and teacher-help request behavior.
- Admin journey verifies account operations, billing evidence, usage reconciliation, curriculum operations, and smoke evidence.
- No production-like journey relies on demo fallback.
- Residual provider/live-smoke gaps are listed as blocked with exact prerequisite.

### VERIFY-50 v5.16 Release Evidence Gate

Acceptance criteria:

- Backend focused tests, frontend build/lint/e2e evidence, and smoke evidence are recorded.
- v5.14 partial gate is either closed or carried forward with a precise blocker.
- Docs, roadmap, requirements, state, milestone snapshots, and next milestone recommendation are updated.
- Release evidence states whether the app is locally product-ready, externally blocked, or still implementation-incomplete.

## Out of Scope

- Live Stripe/TWINT charging without approved credentials and rollout approval.
- Live Cognito/email delivery mutation without approved production test path.
- Notification provider, support provider, BI/warehouse, APM, or native app activation.
- Broad redesign or new product feature expansion beyond small fixes discovered by the readiness gate.
- Production mutation outside an approved safe fixture or explicit external activation path.

## Current Reality Inputs

- v5.12 curriculum editor/content migration is locally complete.
- v5.13 payment and entitlement production completion is locally complete, with live payment smoke externally blocked.
- v5.14 verification/login reliability is partial: backend and frontend build passed, but focused frontend e2e remains blocked by execution approval.
- v5.15 usage/quota/product stability is locally complete and added backend core smoke evidence.
- Frontend e2e specs already exist for auth, account operations, subscriptions/billing, and curriculum.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| READINESS-01 | Phase 252 | Complete |
| E2E-01 | Phase 253 | Complete |
| SMOKE-01 | Phase 254 | Complete |
| JOURNEY-01 | Phase 255 | Complete |
| VERIFY-50 | Phase 256 | Complete |
