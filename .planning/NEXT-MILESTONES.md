# Next Three Milestones

**Updated:** 2026-06-11 after completing v4.1
**Mode:** product functionality first

## v4.2 Production Notification Delivery Readiness

Goal: promote the local realtime notification foundation toward deployable production delivery and durable user preferences.

Candidate phases:

- Phase 136: Production Notification Infrastructure Contract.
- Phase 137: API Gateway WebSocket And Delivery Operations Readiness.
- Phase 138: Push/Email Notification Preference And Digest Readiness.
- Phase 139: v4.2 Functional Release Gate And Notification Delivery Audit.

Scope:

- Add CDK/API Gateway WebSocket route wiring, deploy readiness, live-smoke protocol, and rollback evidence for production realtime delivery.
- Add notification preference and digest readiness for push/email channels where approved provider credentials exist.
- Keep broad native-app push rollout and notification marketing automation out of scope.

## v4.3 Frontend Mobile And Visual Localization Rollout

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
