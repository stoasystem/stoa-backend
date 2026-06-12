# Next Three Milestones

**Updated:** 2026-06-12 after completing v4.8
**Mode:** product functionality first

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

Closed scope:

- Build on the v3.8 curriculum hierarchy and v4.0 adaptive learning signals.
- Add internal authoring, review, publish, rollback, archive, and aggregate quality analytics.
- Leave rich editor UI, production content migration, and warehouse BI for later product expansion.

## v4.7 Payment Production Activation And Provider Automation

**Status:** Completed backend release gate 2026-06-12
**Roadmap:** `.planning/milestones/v4.7-ROADMAP.md`
**Requirements:** `.planning/milestones/v4.7-REQUIREMENTS.md`

Goal: turn the v4.4 Stripe/TWINT readiness foundation into approved production activation automation.

Completed phases:

- Phase 156: Payment Production Activation Contract And Provider Readiness.
- Phase 157: Live Provider Readiness API Checks.
- Phase 158: Direct Refund Execution And Finance Handoff.
- Phase 159: Production Webhook Registration And Rollout Controls.
- Phase 160: v4.7 Payment Activation Release Gate.

Closed scope:

- Added live Stripe/TWINT provider readiness checks, webhook readiness evidence, direct refund execution, finance handoff export updates, and independent checkout/refund rollout controls.
- Final live activation status is `deferred` pending approved live Stripe credentials, registered production webhook endpoint, TWINT capability approval, finance acceptance, and explicit rollout enablement.

## v4.8 Support Provider Expansion And CRM Automation

**Status:** Completed backend release gate 2026-06-12
**Roadmap:** `.planning/milestones/v4.8-ROADMAP.md`
**Requirements:** `.planning/milestones/v4.8-REQUIREMENTS.md`

Goal: expand the v4.5 internal support queue into approved provider-backed support operations and controlled CRM/customer messaging.

Completed phases:

- Phase 161: Support Provider Expansion Contract And Adapter Readiness.
- Phase 162: Approved Third-Party Support Adapter And Delivery Worker.
- Phase 163: Retry Workers And Two-Way Ticket Synchronization.
- Phase 164: Support SLA Analytics And Controlled CRM Messaging.
- Phase 165: v4.8 Support Provider Release Gate And Operations Audit.

Closed scope:

- Add adapter readiness, provider delivery workers, bounded retry, provider ticket sync, support SLA analytics, and template-gated support messaging.
- Keep metadata-only support evidence boundaries and destination approval gates.
- Final provider activation state is `provider-ready`; real external provider and CRM/customer writes remain gated on approved provider selection, credentials, destination policy, templates, and rollout approval.

## Candidate v4.9 Production Notification And Native Delivery Rollout

**Status:** Recommended next after v4.8

Goal: complete live notification delivery beyond backend readiness.

Candidate scope:

- Live WebSocket/API Gateway deployment and smoke evidence.
- Provider-backed push/email delivery.
- Frontend/native notification visuals and token registration.
- Delivery analytics and operational visibility.

## Candidate v5.0 Product Expansion Or Final Payment Operations

**Status:** Candidate after v4.9 or when external prerequisites unblock

Potential scope:

- Final live payment activation operations once external provider prerequisites are ready.
- Native mobile app rollout and full localization governance.
- Rich curriculum editor UI and production content migration.
- Long-term adaptive sequencing, autonomous tutoring, and warehouse-backed analytics.
