# STOA Docs Remaining Feature Build Queue

**Updated:** 2026-06-09
**Sources:** `/Users/zhdeng/stoa-docs/PRD.md`, `/Users/zhdeng/stoa-docs/HLD.md`, `/Users/zhdeng/stoa-docs/PLAN.md`, `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`

## Completed Product Areas

- MVP auth, question submission, OCR correction, AI answer, feedback, quota, teacher takeover, rich replies, SLA tracking, parent dashboard/report, weekly report automation, admin users/stats, and content moderation.
- Manual subscription operations with parent request UI and admin tier processing.
- Multi-subject foundation, full curriculum rollout, learning profile seeds, and curriculum UX.
- AI teacher tools: summaries, suggested focus, draft explanations, and reviewed exercise drafts.
- Local functional WebSocket notification delivery and notification center fallback.

## Remaining Feature Build Queue

1. **v3.9 Payment Provider Integration MVP** - active.
   Build Stripe-first checkout, subscription state, webhook billing updates, parent payment UX, and admin billing visibility. TWINT remains provider-configuration dependent.

2. **v4.0 Adaptive Learning Memory And Assignment** - next recommended.
   Extend learning profile seeds into durable student memory, reviewed assignment workflows, student next-practice UX, and parent progress signals.

3. **v4.1 Mobile And Multilingual Polish Foundation** - next recommended.
   Improve mobile ergonomics across student/parent/tutor flows and expand German-first multilingual coverage.

4. **Production Notification Delivery Readiness**.
   Finish production API Gateway WebSocket wiring, push/email preferences, notification digests, live-smoke expectations, and rollback surfaces.

5. **Support Integrations And Operations Handoff**.
   Add support-ticket/evidence destination integrations after an approved connector or credential path exists.

6. **Later Product Expansion**.
   Rich curriculum authoring workflow, production content QA/analytics, refund/accounting/tax/dunning operations, native apps, full autonomous tutoring decisions, and deeper compliance operations.

## Current Planning Decision

The next stage is v3.9 because `stoa_docs` explicitly lists Stripe subscription payment with credit card/TWINT in Phase 2, and the shipped manual subscription workflow already provides the local entitlement and admin override foundation needed for provider-backed billing.
