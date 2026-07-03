# Roadmap: v5.9 Parent Admin Operations Visibility

**Status:** Complete
**Created:** 2026-07-03
**Prior milestone:** v5.8 Email Verification And Login Code Policy

## Goal

Provide bounded parent/admin operations visibility that composes entitlement, billing, usage, verification, and binding state into support-grade account summaries.

## Why This Is Its Own Milestone

The backend now has the necessary primitives: effective entitlements from v5.6, usage ledger/reconciliation from v5.7, and account verification state from v5.8. v5.9 closes the final backend operations gap by making those primitives visible together without waiting for a broad frontend console or external CRM integration.

## Current Reality

- Parent subscription and billing endpoints exist.
- Parent child usage endpoint exists for one child at a time.
- Admin billing, usage, reconciliation, and verification support endpoints exist as separate slices.
- No single bounded account operations view composes billing, entitlement, usage, verification, and binding state for parent/admin support.

## Implementation Strategy

- Add a shared account operations aggregation service.
- Reuse existing repository/service helpers instead of adding infrastructure.
- Add parent-facing summary first, then admin detail with bounded event visibility.
- Keep response privacy-safe: no raw learning content, private artifact keys, provider payload internals, auth tokens, or verification codes.
- Close with focused regression tests and release evidence.

## Phases

- [x] **Phase 217: Account Operations Visibility Contract** - Define shared account operations response contract, support states, privacy boundaries, and data sources.
- [x] **Phase 218: Parent Account Operations Summary** - Add parent-scoped consolidated account operations summary.
- [x] **Phase 219: Admin Parent Operations Detail** - Add admin support-grade parent operations detail and bounded attention states.
- [x] **Phase 220: Privacy Regression Tests And Operations Evidence** - Verify privacy boundaries and compatibility with existing auth/billing/usage behavior.
- [x] **Phase 221: v5.9 Operations Visibility Release Gate** - Close v5.9 with evidence, docs, audit, and handoff.

## Phase Details

### Phase 217: Account Operations Visibility Contract

**Goal**: Define the shared account operations aggregation model before exposing routes.
**Depends on**: v5.6 entitlement, v5.7 usage ledger, v5.8 verification.
**Requirements**: OPSVIS-01
**Success Criteria**:

1. Contract includes parent profile, billing, children, binding, entitlement, usage, verification, and support state.
2. Aggregation reuses existing services and introduces no new table/index/provider payload storage.
3. Support states include ready, attention, and blocked with bounded blocker/warning codes.
4. Privacy boundaries are documented.
5. Phase artifacts capture data sources and future handoff.

### Phase 218: Parent Account Operations Summary

**Goal**: Give parents one consolidated account operations summary.
**Depends on**: Phase 217.
**Requirements**: PARENTOPS-01
**Success Criteria**:

1. `GET /parents/me/account-operations` returns parent, billing, child, entitlement, usage, verification, and support state.
2. Parent identity is resolved through existing parent JWT/profile ownership logic.
3. Response omits admin-only billing event internals and private learning/provider data.
4. Focused test covers ready parent account operations state.

### Phase 219: Admin Parent Operations Detail

**Goal**: Give admins a bounded support-grade parent account operations detail.
**Depends on**: Phase 218.
**Requirements**: ADMINOPS-01
**Success Criteria**:

1. `GET /admin/account-operations/parents/{parent_id}` returns account operations detail for one parent.
2. Response includes bounded billing events and child binding/verification/usage state.
3. Missing/non-parent accounts return bounded 404.
4. Focused test covers blockers and warnings for unverified accounts and non-active bindings.

### Phase 220: Privacy Regression Tests And Operations Evidence

**Goal**: Verify account operations visibility without regressing prior account/payment/usage behavior.
**Depends on**: Phase 219.
**Requirements**: OPSVERIFY-01
**Success Criteria**:

1. Focused parent/admin account operations tests pass.
2. Adjacent subscription, usage, auth lifecycle, and parent authorization tests pass.
3. Ruff passes for new/modified modules.
4. Release evidence records residual production deploy/live smoke status.

### Phase 221: v5.9 Operations Visibility Release Gate

**Goal**: Close v5.9 as a completed backend operations visibility milestone.
**Depends on**: Phase 220.
**Requirements**: VERIFY-42
**Success Criteria**:

1. Account operations contract, parent summary, admin detail, tests, docs, and audit are complete.
2. Requirements, roadmap, state, and milestone history reflect v5.9 completion.
3. Release evidence identifies commit SHAs, focused tests, lint checks, and residual full-suite status.
4. Final audit records rollout state: `operations-visible`, `blocked`, or `deferred`.
5. Frontend/native/production smoke handoff is updated.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 217 Account Operations Visibility Contract | v5.9 | 1/1 | Complete | 2026-07-03 |
| 218 Parent Account Operations Summary | v5.9 | 1/1 | Complete | 2026-07-03 |
| 219 Admin Parent Operations Detail | v5.9 | 1/1 | Complete | 2026-07-03 |
| 220 Privacy Regression Tests And Operations Evidence | v5.9 | 1/1 | Complete | 2026-07-03 |
| 221 v5.9 Operations Visibility Release Gate | v5.9 | 1/1 | Complete | 2026-07-03 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| OPSVIS-01 | Phase 217 | Complete |
| PARENTOPS-01 | Phase 218 | Complete |
| ADMINOPS-01 | Phase 219 | Complete |
| OPSVERIFY-01 | Phase 220 | Complete |
| VERIFY-42 | Phase 221 | Complete |

---
*Last updated: 2026-07-03 after v5.9 operations visibility release gate.*
