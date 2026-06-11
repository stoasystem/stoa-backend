# Next Three Milestones

**Updated:** 2026-06-11 after completing v4.3
**Mode:** product functionality first

## v4.4 Live Payment Provider Rollout

**Status:** Recommended next

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

## v4.6 Rich Curriculum Authoring And Analytics Foundation

Goal: turn the curriculum catalog and exercise-bank foundation into a more operable authoring, QA, and insight workflow.

Candidate phases:

- Phase 152: Curriculum Authoring Contract And QA Workflow.
- Phase 153: Admin Lesson And Exercise Authoring MVP.
- Phase 154: Learning Analytics And Content Quality Signals.
- Phase 155: v4.6 Curriculum Operations Release Gate.

Scope:

- Build on the v3.8 curriculum hierarchy and v4.0 adaptive learning signals.
- Prioritize author review, content QA, and actionable learning analytics before deeper compliance automation.
- Full production notification rollout remains an eligible alternative next milestone if infrastructure/provider/frontend ownership becomes available first.
