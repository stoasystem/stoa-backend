# Next Product Milestones

**Updated:** 2026-07-03 after promoting core operations phases into milestones
**Mode:** final polish, product functionality first

## Completed Planning Audit: Phase 201 Core Product Operations Gap Audit

**Status:** Complete 2026-07-02
**Evidence:** `.planning/phases/201-core-product-operations-gap-audit-and-contract/201-CURRENT-REALITY-AUDIT.md`

Key finding: the remaining work should not be treated as small phases. Entitlements, usage ledger, verification, and operations visibility are each complete product capabilities.

## Active: v5.6 Effective Entitlements And Paid Access Enforcement

**Status:** Active planning
**Roadmap:** `.planning/ROADMAP.md`
**Requirements:** `.planning/REQUIREMENTS.md`

Purpose:

- Make paid access real for linked students.
- Resolve entitlement from student profile, parent binding, parent billing, manual override, rollout controls, and billing state.
- Enforce effective entitlement in question quota.
- Provide enough entitlement visibility for parent/admin support.

Detailed build scope:

- Phase 202: Entitlement Contract And Access Policy.
- Phase 203: Entitlement Resolver Service And Parent Child Mapping.
- Phase 204: Student Paid Access Enforcement.
- Phase 205: Entitlement Visibility And Focused Tests.
- Phase 206: v5.6 Entitlement Release Gate.

## Planned: v5.7 Usage Ledger And Quota Reconciliation

**Status:** Planned after v5.6
**Roadmap:** `.planning/milestones/v5.7-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.7-REQUIREMENTS.md`

Purpose:

- Turn usage tracking from counter-only behavior into a durable, queryable ledger.
- Reconcile question/chat/hint counters with usage events.
- Enable admin and future parent usage summaries.

Detailed build scope:

- Phase 207: Usage Ledger Contract And Access Patterns.
- Phase 208: Usage Event Repository And Service.
- Phase 209: Plan-Governed Action Instrumentation.
- Phase 210: Quota Reconciliation And Admin Usage Query.
- Phase 211: v5.7 Usage Ledger Release Gate.

## Planned: v5.8 Email Verification And Login Code Policy

**Status:** Planned after v5.7
**Roadmap:** `.planning/milestones/v5.8-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.8-REQUIREMENTS.md`

Purpose:

- Replace `admin_marked_verified` placeholder behavior with real account verification lifecycle.
- Decide and implement a token-compatible login-code policy or explicitly keep login password-only.
- Keep Cognito forgot/reset password stable.

Detailed build scope:

- Phase 212: Verification Policy And Cognito Compatibility Contract.
- Phase 213: Email Verification Code Service.
- Phase 214: Registration And Account-State Integration.
- Phase 215: Login-Code Policy Implementation And UI/API Handoff.
- Phase 216: v5.8 Verification Release Gate.

## Planned: v5.9 Parent Admin Operations Visibility

**Status:** Planned after v5.8
**Roadmap:** `.planning/milestones/v5.9-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.9-REQUIREMENTS.md`

Purpose:

- Make entitlement, billing, usage, and verification state understandable to parents/customers and admins.
- Provide final support-grade polish before moving back to larger product expansion such as native apps or rich curriculum editor implementation.

Detailed build scope:

- Phase 217: Customer Account Operations Contract.
- Phase 218: Admin Support Operations Contract.
- Phase 219: Backend Aggregation APIs.
- Phase 220: Frontend/Admin Handoff And Focused Tests.
- Phase 221: v5.9 Core Operations Closeout.

## Later Candidates

- Native iOS/Android app buildout.
- Frontend rich curriculum editor implementation.
- Production content import and migration UI/API.
- Live warehouse/BI deployment.
- Final external payment/support activation when prerequisites unblock.
