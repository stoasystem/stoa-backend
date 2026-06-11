# STOA Docs Remaining Feature Build Queue

**Updated:** 2026-06-11
**Sources:** `/Users/zhdeng/stoa-docs/PRD.md`, `/Users/zhdeng/stoa-docs/HLD.md`, `/Users/zhdeng/stoa-docs/PLAN.md`, `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md`

## Completed Product Areas

- MVP auth, question submission, OCR correction, AI answer, feedback, quota, teacher takeover, rich replies, SLA tracking, parent dashboard/report, weekly report automation, admin users/stats, and content moderation.
- Manual subscription operations with parent request UI and admin tier processing.
- Multi-subject foundation, full curriculum rollout, learning profile seeds, and curriculum UX.
- AI teacher tools: summaries, suggested focus, draft explanations, and reviewed exercise drafts.
- Local functional WebSocket notification delivery and notification center fallback.
- Production notification delivery readiness with durable preferences, delivery status, digest preview readiness, and push-ready metadata.
- Payment provider integration MVP with checkout/status/webhook APIs and parent/admin billing UX.
- Frontend mobile and visual localization rollout with selected responsive core-flow polish and English/German language preference UI.
- Adaptive learning memory, reviewed assignment workflows, next-practice recommendations, and parent/tutor progress signals.
- Mobile/multilingual backend foundation with durable locale preferences, language-safe response metadata, and explicit deferred frontend/native scope.

## Remaining Feature Build Queue

1. **v4.4 Live Payment Rollout And Billing Operations** - active.
   Roll out real provider credentials, TWINT production validation, invoices, receipts, refunds, tax/accounting, and dunning.

2. **v4.5 Support Integrations And Operations Handoff** - planned.
   Add support-ticket/evidence destination integrations after an approved connector or credential path exists.

3. **v4.6 Rich Curriculum Authoring And Analytics Foundation** - planned.
   Add authoring, content QA, learning analytics, and operational curriculum insights.

4. **Later Product Expansion**.
   Rich curriculum authoring workflow, production content QA/analytics, native apps, full autonomous tutoring decisions, long-term adaptive sequencing, and deeper operations reporting.

## Current Planning Decision

The next stage is v4.4 because v4.3 closed the selected frontend mobile/localization gap, and `stoa_docs` still has a business-critical payment gap around live provider rollout, TWINT validation, invoices/receipts/refunds, tax/accounting, and dunning. v4.5 and v4.6 are now documented as the next feature-building milestones after payment rollout: support handoff integration first, then curriculum authoring and analytics.
