# Requirements: v4.7 Payment Production Activation And Provider Automation

**Milestone:** v4.7
**Status:** Active planning
**Created:** 2026-06-12

## Goal

Turn the v4.4 Stripe/TWINT readiness foundation into controlled production payment activation. v4.7 focuses on approved live provider credentials, TWINT capability validation, webhook endpoint registration, direct refund execution, provider readiness checks, finance acceptance, and rollout evidence.

This is still an internal development milestone. Prioritize feature construction and provider automation. Keep checks focused on payment activation boundaries and do not broaden into unrelated security/compliance work.

## Requirements

### PAYACT-01 Payment Production Activation Contract And Provider Readiness

Implementers have a concrete production activation contract before enabling live payment operations.

Acceptance criteria:

- Contract identifies live Stripe credential ownership, injection path, runtime validation, and redacted readiness evidence.
- Contract identifies live Standard/Premium price IDs, CHF currency expectations, TWINT customer-location requirements, 5,000 CHF maximum amount, no-manual-capture behavior, and `twint_payments` capability checks.
- Contract defines TWINT merchant onboarding requirements for public website availability, visible legal/contact information, and CHF checkout pricing.
- Contract defines HTTPS webhook endpoint registration requirements, webhook secret ownership, quick 2xx handler expectations, and event set required for launch.
- Contract defines finance acceptance requirements for invoices, refunds, tax/accounting handoff, dunning, and reconciliation evidence.
- Contract defines explicit rollout gates for live checkout, direct refund execution, and provider-readiness automation.

### PAYACT-02 Live Provider Readiness API Checks

Operators can verify provider readiness without exposing secrets or creating real customer charges by default.

Acceptance criteria:

- Backend exposes admin-only provider readiness checks for credential mode, price mapping, webhook endpoint readiness, TWINT eligibility, refund capability, and accounting metadata availability.
- Readiness checks use provider APIs or controlled adapters where credentials are present, including `twint_payments` capability status where available, and return fail-closed blocker states when credentials are absent, test-mode only, pending, inactive, or provider calls fail.
- Responses redact secrets, raw provider payloads, card/payment details, and customer-sensitive payment data.
- Tests cover missing credentials, test credentials, live-ready blocked state, provider API failure, and readiness success fixtures.

### PAYACT-03 Direct Refund Execution And Finance Handoff

Operators can execute approved refund flows and export finance handoff evidence under explicit controls.

Acceptance criteria:

- Refund execution requires eligible billing state, provider reference, operator reason, idempotency key, and admin authorization.
- Refund execution respects provider remaining-amount rules, TWINT's 180-day refund window, and full/partial refund behavior.
- Refund execution persists request, result, provider reference, lifecycle status, and audit evidence.
- Parent/admin billing views reflect refund status without exposing sensitive provider payloads.
- Finance handoff export includes invoice, refund, tax/accounting, payment method, reconciliation, and dunning metadata needed for Swiss operations.
- Tests cover approved refund, ineligible refund refusal, duplicate/idempotent refund request, provider failure, and handoff export shape.

### PAYACT-04 Production Webhook Registration And Rollout Controls

Live webhook and checkout rollout controls are ready for production activation.

Acceptance criteria:

- Webhook registration/readiness checks verify HTTPS endpoint mode, secret availability, required event subscriptions, quick 2xx handler readiness, and last observed event status.
- Live checkout remains blocked until explicit rollout approval and provider readiness checks pass.
- Rollout controls can enable/disable live checkout and refund execution independently.
- Release evidence captures live-readiness status, blockers, and whether any approved live smoke occurred.

### VERIFY-30 v4.7 Payment Activation Release Gate

v4.7 closes with payment activation evidence and updated remaining-feature planning.

Acceptance criteria:

- Focused backend tests and relevant static checks pass or isolate documented pre-existing failures.
- Provider readiness, refund execution, finance handoff, webhook registration, and rollout controls are verified.
- Requirements, roadmap, state, feature gap docs, and remaining-feature queue reflect completed v4.7 work.
- Final audit records live activation state: activated, blocked, deferred, or approved canary-only.
- Next milestone recommendation is updated from the remaining feature queue.

## Future Requirements

- Support provider expansion and CRM automation beyond the v4.5 internal queue path.
- Production notification and native delivery rollout.
- Rich curriculum editor UI and production content migration.
- Native mobile app rollout and full localization governance.
- Long-term adaptive sequencing and warehouse-backed analytics.

## Out of Scope

- Unapproved real customer charges.
- Broad CRM or marketing automation.
- Multi-provider billing beyond Stripe-backed subscription operations unless a later milestone selects it.
- Full accounting system replacement.
- Native app payment flow changes.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PAYACT-01 | Phase 156 | Planned |
| PAYACT-02 | Phase 157 | Planned |
| PAYACT-03 | Phase 158 | Planned |
| PAYACT-04 | Phase 159 | Planned |
| VERIFY-30 | Phase 160 | Planned |
