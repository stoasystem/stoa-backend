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
- Frontend mobile and visual localization rollout with selected responsive core-flow polish and English/German language preference UI.
- Adaptive learning memory, reviewed assignment workflows, next-practice recommendations, and parent/tutor progress signals.
- Mobile/multilingual backend foundation with durable locale preferences, language-safe response metadata, and explicit deferred frontend/native scope.

## Remaining Feature Build Queue

1. **v4.5 Support Integrations And Operations Handoff** - active.
   Add support-ticket/evidence destination integrations after an approved connector or credential path exists, starting with destination contract and credential readiness.

2. **v4.6 Rich Curriculum Authoring And Analytics Foundation** - planned.
   Add authoring, content QA, learning analytics, and operational curriculum insights.

3. **Payment Production Activation And Provider Automation**.
   Complete approved live Stripe credentials, TWINT account validation, webhook endpoint registration, direct refund execution, provider-readiness API checks, and accounting/support destination integrations.

4. **Later Product Expansion**.
   Rich curriculum authoring workflow, production content QA/analytics, native apps, full autonomous tutoring decisions, long-term adaptive sequencing, and deeper operations reporting.

## Current Planning Decision

v4.5 is active after research-first planning. The selected scope is controlled support handoff integration: approved destinations, credential readiness, metadata-only payload rules, one narrow delivery path, and operator-visible handoff status. Real customer charging remains blocked on approved Stripe live credentials, webhook endpoint registration, TWINT capability confirmation, finance acceptance, and explicit rollout approval.
