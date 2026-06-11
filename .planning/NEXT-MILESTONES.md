# Next Three Milestones

**Updated:** 2026-06-11 after completing v4.2
**Mode:** product functionality first

## v4.3 Frontend Mobile And Visual Localization Rollout

**Status:** Recommended next

Goal: implement the responsive frontend/native-adjacent work that v4.1 intentionally left outside this backend repository.

Candidate phases:

- Phase 140: Frontend Workspace Contract And Mobile UAT Plan.
- Phase 141: Responsive Student Parent Tutor Core Flow Polish.
- Phase 142: Visual Localization And Language Preference UI.
- Phase 143: v4.3 Browser Release Gate And Localization Audit.

Scope:

- Requires the relevant frontend workspace.
- Verify real mobile viewports, touch targets, focus behavior, overflow, and translated UI copy.
- Keep backend canonical-value translation and machine translation out of scope unless a later product decision promotes it.

## v4.4 Live Payment Provider Rollout

Goal: move the local Stripe-first payment provider MVP toward controlled production charging and operator readiness.

Candidate phases:

- Phase 144: Live Payment Rollout Contract And Credential Readiness.
- Phase 145: Production Checkout/Webhook Verification.
- Phase 146: Refunds Invoices Tax And Dunning Readiness.
- Phase 147: v4.4 Payment Release Gate And Support Audit.

Scope:

- Validate approved production provider credentials, webhook endpoints, production-safe smoke, and rollback procedures.
- Add operational readiness for invoices, refunds, tax/accounting handoff, and dunning.
- Keep broad multi-provider billing automation out of scope until live Stripe/TWINT fundamentals are verified.

## v4.5 Support Evidence Integrations And Operations Handoff

Goal: connect the existing support-safe evidence packages to approved operational destinations and close the remaining manual handoff gap.

Candidate phases:

- Phase 148: Support Destination Contract And Credential Readiness.
- Phase 149: Support Evidence Export Destination Integration.
- Phase 150: Operator Queue And Handoff Status Visibility.
- Phase 151: v4.5 Support Integration Release Gate.

Scope:

- Requires approved connector, credential, or destination policy.
- Preserve metadata-only evidence boundaries and refusal behavior for unapproved external writes.
- Keep broad CRM automation and customer messaging campaigns out of scope until support handoff basics are verified.
