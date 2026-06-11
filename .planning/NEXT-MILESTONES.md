# Next Three Milestones

**Updated:** 2026-06-11 after selecting v4.2
**Mode:** product functionality first

## v4.2 Production Notification Delivery Readiness

**Status:** Active

Goal: promote the local realtime notification foundation toward deployable production delivery and durable user preferences.

Planned phases:

- Phase 136: Production Notification Infrastructure Contract.
- Phase 137: WebSocket Delivery Operations And Preference APIs.
- Phase 138: Email Digest And Push Preference Readiness.
- Phase 139: v4.2 Functional Release Gate And Notification Delivery Audit.

Scope:

- Define production API Gateway WebSocket route/integration expectations, deployment ownership, rollback, and live-smoke protocol.
- Add durable notification preferences and delivery decision/status behavior for realtime, in-app fallback, digest-ready, and push-ready channels.
- Add email digest selection/preview readiness and push/native preference metadata without requiring provider credentials during internal development.
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
