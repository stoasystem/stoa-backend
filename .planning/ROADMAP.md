# Roadmap: v5.15 Usage, Quota, And Product Stability

**Status:** Active
**Created:** 2026-07-05
**Prior milestone:** v5.14 Verification And Login Reliability

## Goal

Make usage accounting and core product stability trustworthy: real usage events, quota reconciliation, user/admin explanations, health checks, smoke tests, and regression gates for the flows that matter most.

## Why This Is The Current Milestone

Usage and quota behavior affect access, billing explanations, parent trust, and support decisions. Prior milestones expanded the usage ledger and account operations contract, but v5.15 must verify real app behavior against the code and close gaps in observability, reconciliation, and smoke coverage.

v5.14 is not treated as fully closed: backend gate and frontend build passed, but focused frontend e2e was blocked by platform usage-limit approval. v5.15 keeps that as explicit residual evidence instead of hiding it.

## Implementation Strategy

- Audit real flow coverage instead of assuming all usage actions are correctly metered.
- Define canonical consume/skip/idempotency rules before adding instrumentation.
- Reconcile ledger rows, counters, entitlement limits, and account operations summaries.
- Add local health/smoke checks for auth, entitlement, curriculum, question, teacher-help, and admin-support surfaces.
- Keep observability support-safe: request IDs, status codes, action names, counters, and timestamps, not raw learning content.

## Phases

- [x] **Phase 247: Usage Flow Reality Audit And Stability Contract** - Map usage-bearing flows, current metering behavior, skip rules, and priority stability gaps.
- [x] **Phase 248: Ledger Coverage And Idempotency Closure** - Harden governed usage event coverage, duplicate handling, mismatched intent behavior, and privacy-safe metadata.
- [x] **Phase 249: Quota Reconciliation And Support Explanations** - Reconcile ledger/counter/entitlement state and expose bounded parent/admin quota explanations.
- [x] **Phase 250: Core Health Smoke And Regression Checks** - Add deterministic local smoke checks for the critical product flows and classify failures.
- [ ] **Phase 251: v5.15 Usage Stability Release Gate** - Verify backend/frontend evidence, document residual blockers, and close the milestone.

## Phase Details

### Phase 247: Usage Flow Reality Audit And Stability Contract

**Goal**: Define the exact usage/quota stability contract from current backend/frontend behavior.
**Depends on**: v5.14 Phase 246 partial gate evidence.
**Requirements**: STABILITY-01
**Status**: Complete.
**Success Criteria**:

1. Usage-bearing backend/frontend flows are mapped to concrete files, routes, services, and tests.
2. Each flow is classified as ledger event, aggregate counter, both, intentionally skipped, missing, future-only, or externally blocked.
3. Consume/skip rules for failed, preview, dry-run, admin, duplicate, and provider-blocked flows are documented.
4. Phase 248-250 priority fixes are derived from the audit and separated from BI/APM/live-provider work.

### Phase 248: Ledger Coverage And Idempotency Closure

**Goal**: Ensure major successful usage flows emit governed, privacy-safe, idempotent usage events or explicit skip decisions.
**Depends on**: Phase 247.
**Requirements**: LEDGER-01
**Status**: Complete.
**Success Criteria**:

1. Missing high-priority ledger coverage discovered in Phase 247 is implemented or explicitly deferred with evidence.
2. Duplicate request/action identifiers do not double-charge quota.
3. Mismatched duplicate intent is rejected, flagged, or surfaced support-safely.
4. Focused tests cover duplicate IDs, repeated submissions, failed operations, partial failures, and metadata privacy.

### Phase 249: Quota Reconciliation And Support Explanations

**Goal**: Make quota state reconcilable and explainable across ledger rows, counters, entitlements, and support summaries.
**Depends on**: Phase 248.
**Requirements**: QUOTA-01
**Status**: Complete.
**Success Criteria**:

1. Reconciliation compares ledger rows, aggregate counters, entitlement limits, and account operations usage summaries for a student/action/day.
2. Drift, stale, partial, over-limit, no-usage, and matched states are support-safe and test-covered.
3. Parent/admin account operations expose remaining quota, reconciliation status, and support action without raw content.
4. Repair recommendations are explicit and non-mutating unless a future phase adds a guarded repair action.

### Phase 250: Core Health Smoke And Regression Checks

**Goal**: Add deterministic local smoke checks for product flows most likely to break access or support decisions.
**Depends on**: Phase 249.
**Requirements**: HEALTH-01
**Status**: Complete.
**Success Criteria**:

1. Smoke checks cover login, entitlement resolution, curriculum read, question submit, teacher help, and admin/account support.
2. Checks separate service availability from product-flow readiness and return route/status/request metadata.
3. Expected auth/provider/external blocks are classified separately from regressions.
4. Smoke behavior has focused tests and release-gate documentation.

### Phase 251: v5.15 Usage Stability Release Gate

**Goal**: Close v5.15 with evidence that local usage/quota stability is complete and external blockers are explicit.
**Depends on**: Phase 250.
**Requirements**: VERIFY-49
**Status**: Active.
**Success Criteria**:

1. Focused backend tests pass for usage coverage, idempotency, reconciliation, support summaries, and smoke checks.
2. Frontend build and focused usage/account-operations visibility checks pass when execution permission is available.
3. v5.14 residual focused frontend e2e blocker is recorded separately.
4. Docs, roadmap, requirements, state, milestone snapshots, research summary, and release evidence are updated.
5. Remaining BI/APM/live-provider dependencies are explicit future work.

## Future Milestone Directions

- **Warehouse/BI Activation**: deploy aggregate analytics warehouse/BI only after usage semantics are stable.
- **External Provider Smoke Completion**: live Stripe/TWINT, Cognito/email, notification, and support provider activation when credentials and rollout approval unblock.
- **Frontend Usage Polish**: broader usage/quota visual design if Phase 249 identifies product-facing gaps beyond account operations.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 247 Usage Flow Reality Audit And Stability Contract | v5.15 | 1/1 | Complete | 2026-07-05 |
| 248 Ledger Coverage And Idempotency Closure | v5.15 | 1/1 | Complete | 2026-07-05 |
| 249 Quota Reconciliation And Support Explanations | v5.15 | 1/1 | Complete | 2026-07-05 |
| 250 Core Health Smoke And Regression Checks | v5.15 | 1/1 | Complete | 2026-07-05 |
| 251 v5.15 Usage Stability Release Gate | v5.15 | 0/1 | Active | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| STABILITY-01 | Phase 247 | Complete |
| LEDGER-01 | Phase 248 | Complete |
| QUOTA-01 | Phase 249 | Complete |
| HEALTH-01 | Phase 250 | Complete |
| VERIFY-49 | Phase 251 | Active |
