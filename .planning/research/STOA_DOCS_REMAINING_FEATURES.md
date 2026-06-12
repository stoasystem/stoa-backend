# STOA Docs Remaining Feature Build Queue

**Updated:** 2026-06-12
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
- Frontend mobile and visual localization rollout with selected responsive core-flow polish and English/German language preference UI.
- Adaptive learning memory, reviewed assignment workflows, next-practice recommendations, and parent/tutor progress signals.
- Mobile/multilingual backend foundation with durable locale preferences, language-safe response metadata, and explicit deferred frontend/native scope.

## Remaining Feature Build Queue

1. **Support Provider Expansion And CRM Automation**.
   Add approved third-party support adapters, retry workers, two-way ticket synchronization, support SLA analytics, and broader CRM/customer messaging beyond the v4.5 internal queue path.

2. **Production Notification And Native Delivery Rollout**.
   Complete live WebSocket/API Gateway deployment, provider-backed push/email delivery, frontend/native notification visuals, and live smoke evidence.

3. **Final Live Payment Activation Operations**.
   Execute operational activation once external prerequisites are ready: approved live Stripe credentials, registered production webhook endpoint, TWINT capability approval, finance acceptance, and explicit rollout enablement.

4. **Later Product Expansion**.
   Rich curriculum editor UI, production content migration, native apps, full autonomous tutoring decisions, long-term adaptive sequencing, warehouse-backed analytics, and deeper operations reporting.

## Current Planning Decision

v4.7 is complete after research-first planning and full backend release-gate verification. The shipped scope is payment production activation automation: activation contract, live Stripe/TWINT provider readiness checks, webhook readiness evidence, direct refund execution, finance handoff export updates, and independent rollout controls. Final live activation status is `deferred` because real customer charging still requires approved Stripe live credentials, registered production webhook endpoint, TWINT capability approval, finance acceptance, and explicit rollout enablement. The next recommended milestone is support provider expansion and CRM automation beyond the v4.5 internal queue path.
