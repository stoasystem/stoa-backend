# Roadmap: v5.16 End-To-End Product Readiness And Release Evidence

**Status:** Active
**Created:** 2026-07-05
**Prior milestone:** v5.15 Usage, Quota, And Product Stability

## Goal

Verify the real product as an end-to-end system across auth, verification, billing, entitlement, usage/quota, curriculum, teacher help, and admin/parent support surfaces; close the residual v5.14 frontend e2e blocker; produce release evidence that separates implementation gaps from external provider blockers.

## Why This Is The Next Milestone

Current planning and code reality show that the major local feature buildouts are no longer isolated:

- v5.12 curriculum editor/content migration is complete locally.
- v5.13 payment and entitlement completion is complete locally, but live Stripe/TWINT activation remains externally gated.
- v5.14 verification/login reliability is a partial gate: backend and frontend build passed, but focused frontend e2e remains blocked by execution approval.
- v5.15 usage/quota/product stability is complete locally, including `GET /admin/core-smoke`.
- Frontend e2e specs exist for auth, account operations, billing/subscriptions, and curriculum, but the cross-surface evidence is not yet consolidated into one product-readiness gate.

The next development task is therefore not another single feature module. It is a stability/release milestone that proves the app's main journeys work together and documents exactly what still waits on external credentials or rollout approvals.

## Product Purpose

- A parent can understand account verification, billing, entitlement, usage, and child support state without demo fallback.
- A student can use curriculum/practice/question/help flows with usage and entitlement behavior explainable by support.
- An admin can inspect account operations, billing support evidence, usage reconciliation, curriculum operations, and core smoke results in one coherent readiness story.
- Internal developers know whether failures are product regressions, frontend e2e environment issues, or external provider blockers.

## Implementation Strategy

- Start with a current-reality audit of backend routes, frontend e2e coverage, and milestone evidence rather than trusting stale status labels.
- Close the v5.14 focused frontend e2e blocker as the first concrete gate when execution permission is available.
- Build a release evidence matrix from existing APIs and tests before adding new code.
- Add only small backend/frontend contract fixes if the end-to-end run finds real breakage.
- Treat live Stripe/TWINT, Cognito/email delivery, notification provider, external support provider, BI/warehouse, and APM activation as blockers unless credentials and rollout approval exist.
- Keep production checks read-only unless an explicit approved safe fixture or external activation path is available.

## Phases

- [x] **Phase 252: Product Readiness Reality Audit And Evidence Contract** - Reconcile current backend/frontend code, v5.12-v5.15 evidence, v5.14 partial gate, and external blockers into one release matrix.
- [x] **Phase 253: Focused Frontend E2E Gate Closure** - Run or unblock auth, admin-account-operations, parent-account-operations, billing, and curriculum e2e specs; fix real regressions discovered by those tests.
- [x] **Phase 254: Backend Product Smoke Evidence Expansion** - Verify `GET /admin/core-smoke`, account operations, billing support evidence, usage reconciliation, and curriculum readiness outputs are sufficient for release triage; add small contract fields only if evidence is incomplete.
- [ ] **Phase 255: Cross-Surface Product Journey Verification** - Validate the main parent/student/admin journeys across auth, paid state, usage/quota, curriculum, teacher help, and support views with no demo fallback.
- [ ] **Phase 256: v5.16 Release Evidence Gate And Next Milestone Decision** - Close docs, evidence, residual blockers, and choose the next feature/safety/stability milestone.

## Phase Details

### Phase 252: Product Readiness Reality Audit And Evidence Contract

**Goal**: Define the exact release evidence contract from current code and current milestone state.
**Depends on**: v5.15 completion and v5.14 partial gate evidence.
**Requirements**: READINESS-01
**Success Criteria**:

1. Backend routes and frontend pages/specs for auth, billing, account operations, usage, curriculum, teacher help, and admin support are mapped.
2. v5.12-v5.15 completed evidence is reconciled against current docs.
3. v5.14 partial frontend e2e blocker is preserved as a first-class release risk.
4. External blockers are classified separately from implementation gaps.
5. v5.16 test/evidence matrix is written before fixes start.

### Phase 253: Focused Frontend E2E Gate Closure

**Goal**: Close or precisely classify the remaining focused frontend e2e blocker.
**Depends on**: Phase 252.
**Requirements**: E2E-01
**Success Criteria**:

1. `auth.spec.ts`, `admin-account-operations.spec.ts`, and `parent-account-operations.spec.ts` are run when frontend execution permission is available.
2. Billing/subscription and curriculum e2e specs are included if the Phase 252 matrix marks them release-critical.
3. Real frontend/API contract regressions are fixed or documented with exact file/test evidence.
4. Platform/execution blockers are recorded separately from product defects.

### Phase 254: Backend Product Smoke Evidence Expansion

**Goal**: Ensure backend smoke and support surfaces explain product readiness without raw private data.
**Depends on**: Phase 253.
**Requirements**: SMOKE-01
**Success Criteria**:

1. `GET /admin/core-smoke` output is verified against the product-readiness matrix.
2. Account operations, billing support evidence, usage reconciliation, and curriculum readiness are checked for support-safe request/status metadata.
3. Expected provider/external blocks are distinguishable from regressions.
4. Focused backend tests pass for any evidence contract changes.

### Phase 255: Cross-Surface Product Journey Verification

**Goal**: Prove the main role journeys work together rather than only inside isolated milestones.
**Depends on**: Phase 254.
**Requirements**: JOURNEY-01
**Success Criteria**:

1. Parent journey covers verification state, paid state, child binding, entitlement, usage, and support explanations.
2. Student journey covers curriculum read, practice/question flow, quota behavior, and teacher-help request behavior.
3. Admin journey covers account operations, billing evidence, usage reconciliation, curriculum operations, and core smoke output.
4. No critical journey depends on demo fallback for production-like state.
5. Residual live-provider gaps are documented as blocked, not complete.

### Phase 256: v5.16 Release Evidence Gate And Next Milestone Decision

**Goal**: Close v5.16 with a clear answer on what can ship locally and what must wait for external activation.
**Depends on**: Phase 255.
**Requirements**: VERIFY-50
**Success Criteria**:

1. Backend focused tests, frontend build/lint/e2e evidence, and smoke evidence are recorded.
2. v5.14 partial gate is either closed or carried forward with a precise blocker.
3. Release evidence distinguishes local implementation completeness from live provider activation.
4. Docs, roadmap, requirements, state, and milestone snapshots are updated.
5. Next milestone recommendation is selected from new feature, safety, or stability work.

## Future Milestone Directions

- **External Provider Activation Smoke**: live Stripe/TWINT, Cognito/email delivery, notification, and support provider smoke when credentials and approvals exist.
- **Warehouse/BI Activation**: deploy aggregate analytics only after v5.16 evidence proves operational semantics are stable.
- **Native/Mobile Implementation**: revisit after web product readiness is coherent and external-provider blockers are explicit.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 252 Product Readiness Reality Audit And Evidence Contract | v5.16 | 1/1 | Complete | 2026-07-05 |
| 253 Focused Frontend E2E Gate Closure | v5.16 | 1/1 | Complete | 2026-07-05 |
| 254 Backend Product Smoke Evidence Expansion | v5.16 | 1/1 | Complete | 2026-07-05 |
| 255 Cross-Surface Product Journey Verification | v5.16 | 0/1 | Active | - |
| 256 v5.16 Release Evidence Gate And Next Milestone Decision | v5.16 | 0/1 | Planned | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| READINESS-01 | Phase 252 | Complete |
| E2E-01 | Phase 253 | Complete |
| SMOKE-01 | Phase 254 | Complete |
| JOURNEY-01 | Phase 255 | Active |
| VERIFY-50 | Phase 256 | Planned |
