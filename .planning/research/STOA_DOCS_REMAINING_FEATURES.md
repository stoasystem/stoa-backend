# STOA Docs Remaining Feature Build Queue

**Updated:** 2026-06-13
**Sources:** `/Users/zhdeng/stoa-docs/PRD.md`, `/Users/zhdeng/stoa-docs/HLD.md`, `/Users/zhdeng/stoa-docs/PLAN.md`, `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`

## Completed Product Areas

- MVP auth, question submission, OCR correction, AI answer, feedback, quota, teacher takeover, rich replies, SLA tracking, parent dashboard/report, weekly report automation, admin users/stats, and content moderation.
- Manual subscription operations with parent request UI and admin tier processing.
- Multi-subject foundation, full curriculum rollout, learning profile seeds, and curriculum UX.
- AI teacher tools: summaries, suggested focus, draft explanations, and reviewed exercise drafts.
- Local functional WebSocket notification delivery and notification center fallback.
- Production notification delivery readiness with durable preferences, delivery status, digest preview readiness, and push-ready metadata.
- Payment provider integration MVP with checkout/status/webhook APIs and parent/admin billing UX.
- Live payment rollout foundation with Stripe/TWINT readiness gates, invoice/receipt metadata, non-mutating refund handoff, dunning projections, and Swiss accounting export metadata.
- Support integration and operations handoff with destination contract, controlled `internal_queue` delivery, admin-only queue/detail visibility, provider-failure lifecycle coverage, and local backend release-gate evidence.
- Rich curriculum authoring and analytics foundation with stable public/version IDs, admin/tutor authoring lifecycle, publish/rollback/archive safety, bounded aggregate content-quality analytics, and local backend release-gate evidence.
- Payment production activation automation with live Stripe/TWINT provider readiness checks, webhook readiness evidence, controlled direct refund execution, finance handoff export updates, and independent checkout/refund rollout controls.
- Support provider expansion and CRM automation with provider-neutral adapter readiness, approved/configured third-party delivery, bounded retry, two-way ticket synchronization, support SLA analytics, controlled message evidence, and provider activation state `provider-ready`.
- Frontend mobile and visual localization rollout with selected responsive core-flow polish and English/German language preference UI.
- Adaptive learning memory, reviewed assignment workflows, next-practice recommendations, and parent/tutor progress signals.
- Mobile/multilingual backend foundation with durable locale preferences, language-safe response metadata, and explicit deferred frontend/native scope.

## Remaining Feature Build Queue

1. **Production Notification And Native Delivery Rollout**.
   Complete live WebSocket/API Gateway deployment, provider-backed push/email delivery, frontend/native notification visuals, and live smoke evidence.
   Status: selected as active v4.9 planning scope.

2. **Final Live Payment Activation Operations**.
   Execute operational activation once external prerequisites are ready: approved live Stripe credentials, registered production webhook endpoint, TWINT capability approval, finance acceptance, and explicit rollout enablement.

3. **Later Product Expansion**.
   Rich curriculum editor UI, production content migration, native apps, full autonomous tutoring decisions, long-term adaptive sequencing, warehouse-backed analytics, and deeper operations reporting.

## Current Planning Decision

v4.8 is complete after backend release-gate verification. The shipped scope is support provider expansion and CRM automation beyond the v4.5 internal queue path: provider-neutral contract/readiness, approved third-party support delivery, bounded retry, two-way ticket synchronization, support SLA analytics, and controlled CRM/customer message evidence. Final provider activation state is `provider-ready`; real external provider and CRM/customer writes remain gated on approved provider selection, credentials, destination policy, templates, and rollout approval.

v4.9 is selected as the active next milestone: production notification and native delivery rollout. The planned scope is live WebSocket/API Gateway readiness, provider-backed email/push delivery, frontend/native notification UX handoff, native token registration, preference-aware delivery behavior, and live smoke evidence. The next likely milestone after v4.9 is native mobile and full localization governance unless final payment or support external activation prerequisites become available first.
