# Roadmap: v5.6 Effective Entitlements And Paid Access Enforcement

**Status:** Active planning
**Created:** 2026-07-03
**Research:** `.planning/phases/201-core-product-operations-gap-audit-and-contract/201-CURRENT-REALITY-AUDIT.md`

## Goal

Make paid access actually affect student usage limits through a deterministic effective-entitlement layer.

## Why This Is Its Own Milestone

This is not a small phase. It is the core revenue/access control path:

- A parent can pay or receive a manual override.
- A child/student is linked to that parent.
- The student's actual quota and access must reflect the effective paid entitlement.
- Pending, failed, canceled, expired, missing-binding, and manual override states must behave predictably.
- Customers and admins need enough visibility to understand why access was allowed or blocked.

Without this milestone, later usage ledger, verification, and admin console work would still be built on an unclear entitlement source.

## Current Reality

Phase 201 found:

- Billing activation can update the parent profile `subscription_tier`.
- Student question quota reads the student's own `subscription_tier`.
- Parent-child binding exists, but quota enforcement does not currently resolve through parent billing.
- Admin can manually update user `subscription_tier`, but this is not yet represented as a clear entitlement source.

## Implementation Strategy

- Add an effective entitlement resolver before changing usage counters.
- Keep current billing, checkout, webhook, and manual subscription flows stable.
- Make question quota use effective entitlement instead of only local student tier.
- Preserve explicit fallback behavior for free, pending, canceled, expired, missing-binding, and manual override states.
- Add enough customer/admin visibility to explain entitlement decisions, but leave the full operations console to v5.9.

## Prerequisite Completed

- [x] **Phase 201: Core Product Operations Gap Audit And Contract** - Completed 2026-07-02.

## Phases

- [ ] **Phase 202: Entitlement Contract And Access Policy** - Define effective entitlement inputs, outputs, state precedence, fallback behavior, and test matrix.
- [ ] **Phase 203: Entitlement Resolver Service And Parent Child Mapping** - Implement resolver service using student profile, parent binding, parent profile, billing record, and manual override signals.
- [ ] **Phase 204: Student Paid Access Enforcement** - Integrate resolver into question quota and plan-governed access checks.
- [ ] **Phase 205: Entitlement Visibility And Focused Tests** - Expose effective entitlement summaries to customer/admin surfaces and add focused tests.
- [ ] **Phase 206: v5.6 Entitlement Release Gate** - Close v5.6 with evidence, docs, and v5.7 handoff.

## Phase Details

### Phase 202: Entitlement Contract And Access Policy

**Goal**: Define the entitlement state model and access policy before implementation.
**Depends on**: Phase 201 reality audit.
**Requirements**: ENTITLE-01
**Success Criteria**:

1. Entitlement inputs are defined: student profile, parent binding, parent subscription tier, billing status, manual override, rollout controls, cancellation/expiry, pending payment.
2. Entitlement output shape is defined: effective plan, source, limits, billing state, period, blocking reason, support explanation.
3. Precedence rules are explicit for manual override, active provider billing, pending checkout, canceled/expired, failed payment, free tier, and missing binding.
4. Access policy covers question quota first and leaves future product areas ready for extension.
5. Test matrix is documented before backend service implementation.

### Phase 203: Entitlement Resolver Service And Parent Child Mapping

**Goal**: Implement the backend service that resolves effective entitlement for a student or parent context.
**Depends on**: Phase 202.
**Requirements**: ENTITLE-02
**Success Criteria**:

1. Resolver reads the minimum required rows using existing repositories and single-table patterns.
2. Linked student entitlement can derive from active parent billing or manual override.
3. Missing or inactive parent binding falls back deterministically.
4. Resolver returns a stable response shape for internal callers and future API exposure.
5. Focused tests cover parent-paid linked student, free student, missing binding, manual override, and inactive billing.

### Phase 204: Student Paid Access Enforcement

**Goal**: Make real student usage limits depend on effective entitlement.
**Depends on**: Phase 203.
**Requirements**: ENTITLE-03
**Success Criteria**:

1. Question submission quota uses resolver output instead of only `student_profile.subscription_tier`.
2. Limit calculation remains compatible with current settings for free/standard/premium limits.
3. Failure response includes an actionable plan/limit explanation without exposing billing internals.
4. Existing daily counter behavior remains stable.
5. Tests cover quota allow/block for free, standard, premium, canceled, pending, and override states.

### Phase 205: Entitlement Visibility And Focused Tests

**Goal**: Make entitlement decisions explainable to customers/admins and verify behavior.
**Depends on**: Phase 204.
**Requirements**: ENTITLE-04
**Success Criteria**:

1. Parent/customer subscription or account response includes effective entitlement summary.
2. Admin user or subscription response includes effective entitlement source and support explanation.
3. Existing billing views remain backward compatible.
4. Focused tests cover customer/admin response shapes.
5. Docs record remaining visibility work for the broader v5.9 operations milestone.

### Phase 206: v5.6 Entitlement Release Gate

**Goal**: Close v5.6 as a complete functional milestone.
**Depends on**: Phase 205.
**Requirements**: VERIFY-39
**Success Criteria**:

1. Entitlement contract, resolver, quota enforcement, visibility, and tests are complete.
2. Requirements, roadmap, state, feature gap docs, and remaining-feature queue reflect v5.6 completion.
3. Release evidence identifies commit SHAs and deferred items.
4. Final audit records rollout state: entitlement-ready, blocked, or deferred.
5. v5.7 usage ledger milestone handoff is updated.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 201 Core Product Operations Gap Audit And Contract | Pre-v5.6 | 1/1 | Complete | 2026-07-02 |
| 202 Entitlement Contract And Access Policy | v5.6 | 0/1 | Active | - |
| 203 Entitlement Resolver Service And Parent Child Mapping | v5.6 | 0/1 | Planned | - |
| 204 Student Paid Access Enforcement | v5.6 | 0/1 | Planned | - |
| 205 Entitlement Visibility And Focused Tests | v5.6 | 0/1 | Planned | - |
| 206 v5.6 Entitlement Release Gate | v5.6 | 0/1 | Planned | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ENTITLE-01 | Phase 202 | Planned |
| ENTITLE-02 | Phase 203 | Planned |
| ENTITLE-03 | Phase 204 | Planned |
| ENTITLE-04 | Phase 205 | Planned |
| VERIFY-39 | Phase 206 | Planned |

---
*Last updated: 2026-07-03 after promoting core operations phases into full milestones.*
