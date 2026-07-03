# Requirements: v5.6 Effective Entitlements And Paid Access Enforcement

**Milestone:** v5.6
**Status:** Active planning
**Created:** 2026-07-03
**Research:** `.planning/phases/201-core-product-operations-gap-audit-and-contract/201-CURRENT-REALITY-AUDIT.md`

## Purpose

Make paid access real. A parent payment or admin override must translate into deterministic linked-student access and quota behavior.

This milestone is intentionally narrower than the previous v5.6 core-operations bundle. Usage ledger, email/login verification, and broader parent/admin visibility are promoted to separate milestones.

## Requirements

### ENTITLE-01 Entitlement Contract And Access Policy

Acceptance criteria:

- Entitlement inputs are defined: student profile, parent binding, parent subscription tier, billing status, manual override, rollout controls, cancellation/expiry, and pending payment.
- Entitlement output shape is defined: effective plan, source, limits, billing state, period, blocking reason, and support explanation.
- State precedence is explicit for manual override, active provider billing, pending checkout, canceled/expired, failed payment, free tier, and missing binding.
- Question quota is the first enforced product area.
- Test matrix is documented before implementation.

### ENTITLE-02 Entitlement Resolver Service And Parent Child Mapping

Acceptance criteria:

- Resolver reads existing user, parent binding, parent profile, and billing rows using current single-table/repository patterns.
- Linked student entitlement can derive from active parent billing.
- Manual override remains supported and represented as an entitlement source.
- Missing/inactive parent binding falls back deterministically.
- Resolver returns a stable response shape for internal callers and future APIs.

### ENTITLE-03 Student Paid Access Enforcement

Acceptance criteria:

- Question submission quota uses effective entitlement instead of only the student's local `subscription_tier`.
- Free/standard/premium limits still map to existing settings.
- Access denial response is actionable and does not expose billing internals.
- Existing daily counter behavior remains stable.
- Tests cover free, standard, premium, pending, canceled/expired, manual override, and missing binding states.

### ENTITLE-04 Entitlement Visibility And Focused Tests

Acceptance criteria:

- Parent/customer subscription or account response includes an effective entitlement summary.
- Admin user or subscription response includes entitlement source and support explanation.
- Existing billing response shapes remain backward compatible.
- Focused tests cover parent/customer and admin response shapes.
- Remaining broader operations visibility is handed off to v5.9.

### VERIFY-39 v5.6 Entitlement Release Gate

Acceptance criteria:

- Entitlement contract, resolver, quota enforcement, visibility, and tests are complete.
- Requirements, roadmap, state, feature gap docs, and remaining-feature queue reflect v5.6 completion.
- Release evidence identifies commit SHAs and deferred items.
- Final audit records rollout state: entitlement-ready, blocked, or deferred.
- v5.7 usage ledger milestone handoff is updated.

## Future Milestones

- v5.7 Usage Ledger And Quota Reconciliation.
- v5.8 Email Verification And Login Code Policy.
- v5.9 Parent Admin Operations Visibility.
- Native iOS/Android app buildout after core account/payment/usage correctness.

## Out of Scope

- Durable usage ledger implementation beyond entitlement-summary fields.
- Email verification and login-code implementation.
- Full parent/admin operations console.
- Native app implementation.
- Final live Stripe/TWINT activation unless external prerequisites are ready.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ENTITLE-01 | Phase 202 | Planned |
| ENTITLE-02 | Phase 203 | Planned |
| ENTITLE-03 | Phase 204 | Planned |
| ENTITLE-04 | Phase 205 | Planned |
| VERIFY-39 | Phase 206 | Planned |
