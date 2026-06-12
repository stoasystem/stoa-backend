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
- Frontend mobile and visual localization rollout with selected responsive core-flow polish and English/German language preference UI.
- Adaptive learning memory, reviewed assignment workflows, next-practice recommendations, and parent/tutor progress signals.
- Mobile/multilingual backend foundation with durable locale preferences, language-safe response metadata, and explicit deferred frontend/native scope.

## Remaining Feature Build Queue

1. **v4.6 Rich Curriculum Authoring And Analytics Foundation** - planned.
   Add authoring, content QA, learning analytics, and operational curriculum insights.

2. **Payment Production Activation And Provider Automation**.
   Complete approved live Stripe credentials, TWINT account validation, webhook endpoint registration, direct refund execution, provider-readiness API checks, and accounting/support destination integrations.

3. **Support Provider Expansion And CRM Automation**.
   Add approved third-party support adapters, retry workers, two-way ticket synchronization, support SLA analytics, and broader CRM/customer messaging beyond the v4.5 internal queue path.

4. **Later Product Expansion**.
   Rich curriculum authoring workflow, production content QA/analytics, native apps, full autonomous tutoring decisions, long-term adaptive sequencing, and deeper operations reporting.

## Current Planning Decision

v4.5 is complete after research-first planning and local backend release-gate verification. The shipped scope is controlled support handoff integration: approved destination contract, credential readiness, metadata-only payload rules, one narrow `internal_queue` delivery path, operator-visible handoff status, and imported support handoff frontend evidence. Real customer charging remains blocked on approved Stripe live credentials, webhook endpoint registration, TWINT capability confirmation, finance acceptance, and explicit rollout approval.
