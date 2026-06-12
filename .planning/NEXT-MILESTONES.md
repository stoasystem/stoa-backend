# Next Three Milestones

**Updated:** 2026-06-12 after completing v4.6
**Mode:** product functionality first

## v4.4 Live Payment Provider Rollout

**Status:** Completed local release gate 2026-06-11

Goal: move the local Stripe-first payment provider MVP toward controlled production charging and operator readiness.

Completed phases:

- Phase 144: Live Payment Rollout Contract And Credential Readiness.
- Phase 145: Production Checkout/Webhook Verification.
- Phase 146: Refunds Invoices Tax And Dunning Readiness.
- Phase 147: v4.4 Payment Release Gate And Support Audit.

Closed scope:

- Validate approved production provider credentials, webhook endpoints, production-safe smoke, and rollback procedures.
- Add operational readiness for invoices, refunds, tax/accounting handoff, and dunning.
- Keep broad multi-provider billing automation out of scope until live Stripe/TWINT fundamentals are verified.
- Real customer charging remains deferred pending external approval and live provider setup.

## v4.5 Support Evidence Integrations And Operations Handoff

**Status:** Completed local release gate 2026-06-12
**Roadmap:** `.planning/milestones/v4.5-ROADMAP.md`
**Requirements:** `.planning/milestones/v4.5-REQUIREMENTS.md`

Goal: connect the existing support-safe evidence packages to approved operational destinations and close the remaining manual handoff gap.

Completed phases:

- Phase 148: Support Destination Contract And Credential Readiness.
- Phase 149: Support Evidence Export Destination Integration.
- Phase 150: Operator Queue And Handoff Status Visibility.
- Phase 151: v4.5 Support Integration Release Gate.

Scope:

- Requires approved connector, credential, or destination policy.
- Starts with destination contract and credential readiness before any provider write.
- Preserve metadata-only evidence boundaries and refusal behavior for unapproved external writes.
- Keep broad CRM automation and customer messaging campaigns out of scope until support handoff basics are verified.

## v4.6 Rich Curriculum Authoring And Analytics Foundation

**Status:** Completed local release gate 2026-06-12
**Roadmap:** `.planning/milestones/v4.6-ROADMAP.md`
**Requirements:** `.planning/milestones/v4.6-REQUIREMENTS.md`

Goal: turn the curriculum catalog and exercise-bank foundation into a more operable authoring, QA, and insight workflow.

Completed phases:

- Phase 152: Curriculum Authoring Contract And QA Workflow.
- Phase 153: Admin Lesson And Exercise Authoring MVP.
- Phase 154: Learning Analytics And Content Quality Signals.
- Phase 155: v4.6 Curriculum Operations Release Gate.

Scope:

- Build on the v3.8 curriculum hierarchy and v4.0 adaptive learning signals.
- Prioritize author review, content QA, and actionable learning analytics before deeper compliance automation.
- Full production notification rollout remains an eligible alternative next milestone if infrastructure/provider/frontend ownership becomes available first.

## Recommended Next: Payment Production Activation And Provider Automation

**Status:** Recommended next milestone

Goal: turn the v4.4 Stripe/TWINT readiness foundation into approved production activation.

Candidate phases:

- Credential and provider capability verification for live Stripe and TWINT.
- Webhook endpoint registration and production readiness smoke.
- Direct refund execution and provider-readiness API checks.
- Finance/accounting acceptance and explicit rollout approval.
