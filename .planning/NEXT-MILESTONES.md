# Next Three Milestones

**Updated:** 2026-06-13 after selecting v4.9
**Mode:** product functionality first

## v4.7 Payment Production Activation And Provider Automation

**Status:** Completed backend release gate 2026-06-12
**Roadmap:** `.planning/milestones/v4.7-ROADMAP.md`
**Requirements:** `.planning/milestones/v4.7-REQUIREMENTS.md`

Goal: turn the v4.4 Stripe/TWINT readiness foundation into approved production activation automation.

Closed scope:

- Added live Stripe/TWINT provider readiness checks, webhook readiness evidence, direct refund execution, finance handoff export updates, and independent checkout/refund rollout controls.
- Final live activation status is `deferred` pending approved live Stripe credentials, registered production webhook endpoint, TWINT capability approval, finance acceptance, and explicit rollout enablement.

## v4.8 Support Provider Expansion And CRM Automation

**Status:** Completed backend release gate 2026-06-12
**Roadmap:** `.planning/milestones/v4.8-ROADMAP.md`
**Requirements:** `.planning/milestones/v4.8-REQUIREMENTS.md`

Goal: expand the v4.5 internal support queue into approved provider-backed support operations and controlled CRM/customer messaging.

Closed scope:

- Added adapter readiness, provider delivery workers, bounded retry, provider ticket sync, support SLA analytics, and template-gated support messaging.
- Final provider activation state is `provider-ready`; real external provider and CRM/customer writes remain gated on approved provider selection, credentials, destination policy, templates, and rollout approval.

## v4.9 Production Notification And Native Delivery Rollout

**Status:** Active planning
**Roadmap:** `.planning/milestones/v4.9-ROADMAP.md`
**Requirements:** `.planning/milestones/v4.9-REQUIREMENTS.md`

Goal: complete live notification delivery beyond backend readiness.

Candidate phases:

- Phase 166: Production Notification Rollout Contract And Ownership.
- Phase 167: Live WebSocket API Gateway Deployment Readiness.
- Phase 168: Provider-Backed Email Digest And Push Delivery.
- Phase 169: Frontend And Native Notification UX Handoff.
- Phase 170: v4.9 Production Notification Release Gate And Live Smoke.

Scope:

- Add live WebSocket/API Gateway readiness, provider-backed email/push delivery, frontend/native notification handoff, token registration contract, and live smoke evidence.
- Keep existing durable notification fallback behavior and preference gates.
- Avoid broad marketing/campaign automation and unrelated security/compliance expansion during internal development.

## Candidate v5.0 Native Mobile And Full Localization Governance

**Status:** Candidate after v4.9

Goal: move beyond selected responsive frontend/localization polish into native mobile and complete localization operations.

Candidate scope:

- Native app architecture and push-token integration.
- Full localization governance, translation management, broad copy QA, and RTL readiness.
- Production mobile smoke and app release handoff.

## Candidate v5.1 Product Expansion Or Final External Activation

**Status:** Candidate after v5.0 or when external prerequisites unblock

Potential scope:

- Final live payment activation operations once external provider prerequisites are ready.
- Real external support provider and CRM/customer transport activation after approved provider prerequisites are ready.
- Rich curriculum editor UI and production content migration.
- Long-term adaptive sequencing, autonomous tutoring, and warehouse-backed analytics.
