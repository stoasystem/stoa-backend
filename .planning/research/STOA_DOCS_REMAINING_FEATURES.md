# STOA Docs Remaining Feature Build Queue

**Updated:** 2026-06-15 after selecting v5.5 automatic teacher dispatch and SLA load balancing
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
- Production notification and native delivery backend rollout with live WebSocket readiness/status, provider-gated email digest and push delivery, push token lifecycle records, frontend/native handoff, and release state `deferred` pending external activation.
- Native mobile and full localization governance with mobile API/client handoff, native notification/offline contracts, translation governance, English/German key parity evidence, broad copy QA scope, and rollout state `contract-ready`.
- Rich curriculum editor and production content migration readiness with UI/API handoff, migration manifests, dry-run/apply validation, rollback evidence, reviewed assignment readiness, adaptive sequencing readiness, and rollout state readiness-complete.
- Adaptive sequencing and warehouse analytics backend/API readiness with multi-signal recommendations, assignment outcome feedback, aggregate warehouse schemas, and operator dashboard contracts.
- Controlled assignment automation backend/API readiness with policy-bounded candidate preview, approved-batch execution, deterministic source idempotency, result evidence, and role-safe automation metadata.
- Frontend learning operations dashboards with no-demo-fallback API integration, tutor/admin automation review console, operator analytics dashboard, and student/parent assignment explanations.

## Remaining Feature Build Queue

1. **Final Live Payment Activation Operations**.
   Execute operational activation once external prerequisites are ready: approved live Stripe credentials, registered production webhook endpoint, TWINT capability approval, finance acceptance, and explicit rollout enablement.

2. **Later Product Expansion**.
   Frontend rich curriculum editor implementation, production source import, migration API/UI, native apps, fully unreviewed autonomous tutoring decisions, live notification delivery, live warehouse/BI deployment, and deeper operations reporting.
   Status: v5.5 selects automatic teacher/tutor dispatch for student teacher requests.

## Current Planning Decision

v5.1 is complete as a curriculum product readiness milestone because final payment/support/provider activation remains blocked on external prerequisites. The completed scope defines rich curriculum editor readiness, production content migration manifests and dry-run/apply validation, rollback evidence, reviewed assignment automation readiness, and adaptive sequencing readiness.

v5.2 is complete as a backend/API readiness milestone. It turned the v4.0 adaptive learning memory foundation, v4.6 curriculum analytics foundation, and v5.1 readiness contracts into deeper adaptive sequencing recommendations, assignment outcome feedback, warehouse-ready analytics schemas, and operator dashboards. Final live warehouse/BI deployment remains deferred.

v5.3 is complete as an automation-ready backend/API milestone. It converted v5.2 recommendations into controlled assignment automation from accepted AI drafts, published curriculum exercises, and reviewed recommendation candidates. The completed scope includes autonomy levels, policy-bounded candidate batches, idempotent assignment creation/delivery, tutor/admin review contracts, and family-visible explanation metadata while keeping unreviewed autonomous tutoring out of scope.

v5.4 is complete as a frontend-ready milestone. It made v5.2/v5.3 backend learning operations usable in frontend tutor/admin/student/parent workflows through a no-demo-fallback API client, automation review console, learning operations dashboard, and family-safe assignment explanations. v5.4 did not implement automatic assignment of human teachers/tutors to student help requests.

v5.5 is now the active milestone. Its purpose is automatic teacher/tutor dispatch for student help requests: route escalated questions to eligible teachers/tutors, prevent double assignment, reassign timed-out work, and expose queue/SLA health. The implementation strategy is to build on existing request-teacher, teacher queue, takeover, reply, resolve, notification, and SLA code, adding dispatch planning, conditional claim metadata, timeout/reassignment, and operator visibility. It is not AI auto-answering.
