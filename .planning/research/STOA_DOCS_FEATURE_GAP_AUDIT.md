# STOA Docs Feature Gap Audit

**Created:** 2026-06-07
**Updated:** 2026-06-12 after completing v4.5 support integration release gate
**Sources:** `/Users/zhdeng/stoa-docs/PRD.md`, `/Users/zhdeng/stoa-docs/HLD.md`, `/Users/zhdeng/stoa-docs/PLAN.md`, current `stoa-backend` routes, and completed `.planning` milestones.

## Summary

The MVP backend surface from `stoa_docs` is mostly implemented: auth register/login/refresh/logout, file presign, question submit/get/request-teacher/feedback, teacher queue/takeover/reply/resolve, student summary/history, parent children/report access, weekly report automation, admin user/stat APIs, production report operations, and immutable evidence/governance workflows exist.

v3.0 closed the highest-priority account/intake MVP gaps identified in this audit: account lifecycle hardening, explicit parent-student binding, OCR correction before final submission, robust daily question quota enforcement, and production deployment/live smoke for the v2.9 governance UI/API.

v3.1 closed the remaining teacher-takeover MVP gaps selected for that cycle: safe rich text/formula teacher replies, response-time SLA tracking, teacher queue/session visibility, admin aggregate SLA visibility, and production-safe release verification.

v3.2 closed the remaining visible MVP admin workflow gap: content moderation for reported or abnormal learning content. The release added report actions, moderation cases, admin queue/detail/actions, deploy evidence, and production-safe smoke.

v3.3 completed the MVP manual subscription process before Stripe/TWINT: parent plan/request UI, admin processing queue, tier application workflow, and focused backend/frontend verification. Payment-provider integration remains future scope.

v3.4 completed the Phase 2 learning expansion foundation: subject taxonomy, subject-specific prompt behavior, topic seeds, student/parent learning profile APIs, and learning profile UI. Full curriculum rollout was later promoted to v3.8; automatic exercise generation was later promoted to v3.7.

v3.5 completed the realtime notification and AI teacher assistance foundation scope with bounded notification events, recipient list/read/archive behavior, admin operational notifications, and teacher summary seeds. Full WebSocket rollout was completed locally in v3.6, automatic exercise generation was promoted to v3.7, and push notifications plus email digests remain future scope.

v3.6 completed the local functional WebSocket realtime notification scope: authenticated connection/subscription service behavior, connection storage, notification fanout with delivery attempt metadata, frontend WebSocket client behavior, notification center cache sync, reconnect/offline states, and polling fallback. Production live rollout still requires API Gateway WebSocket/CDK route wiring and deploy/live-smoke evidence outside this repo's current infrastructure surface.

v3.7 completed the local functional AI teacher tools / automatic summaries / exercise generation scope. The milestone defined reviewed-draft contracts for session summaries, misconception summaries, suggested teaching focus, draft follow-up explanations, and practice exercise drafts; added backend persistence and tutor/admin lifecycle APIs; added tutor UI; and captured functional release-gate evidence. AI-generated replies and exercises remain reviewed drafts; automatic student assignment remains future scope.

v3.8 completed the local functional full multi-subject curriculum rollout scope. The milestone defined curriculum hierarchy and content states, added backend curriculum catalog and exercise bank APIs, exposed student/parent curriculum UX plus tutor/admin curriculum signals, and closed with backend/frontend/browser release-gate evidence. Long-term adaptive sequencing, automatic student assignment, rich authoring workflow, and production content QA remain future scope.

v3.9 completed the local functional payment-provider integration MVP. The milestone defined a Stripe-first provider contract, added backend checkout/status/webhook APIs, exposed parent checkout/status UX and admin provider billing visibility, and closed with backend/frontend/browser release-gate evidence. Live production charges, provider credentials, TWINT production validation, refunds/invoices, tax/accounting, and dunning remain future scope.

After checking `stoa_docs` again on 2026-06-11, v4.1 completed the local backend foundation for mobile-friendly and multilingual polish: mobile/backend contract documentation, durable locale preferences, language-safe adaptive route metadata, and explicit deferred frontend/native UI scope.

v4.2 completed the backend-local production notification delivery readiness scope: production WebSocket delivery contracts, durable notification preferences, preference-aware delivery state/status behavior, email digest preview readiness, push-ready preference metadata, and clean local release-gate evidence. Remaining notification work is now provider/infrastructure/frontend rollout scope: CDK/API Gateway WebSocket deployment, live endpoint smoke, frontend/native notification visuals, native push token/provider integration, production email digest templates/scheduling, and broader notification analytics.

v4.3 completed the selected frontend mobile and English/German visual localization rollout in `/Users/zhdeng/stoa-frontend`: frontend workspace contract, shared mobile shell/action polish, targeted mobile Playwright coverage, backend-backed language preference UI, `/auth/me` locale refresh behavior, and release-gate evidence. Remaining mobile/localization work is now broader native app, translation management, RTL, broad copy QA, and production deploy scope rather than the selected core-flow frontend rollout.

v4.4 completed the local live payment provider rollout foundation for Stripe/TWINT readiness, invoice/receipt metadata, non-mutating refund handoff, dunning projections, Swiss accounting export metadata, and release-gate evidence. Real customer charging remains gated on approved live credentials and explicit rollout approval.

v4.5 completed the local backend support integration and operations handoff scope: support destination contract/credential readiness, fail-closed `internal_queue` delivery behind `SUPPORT_INTERNAL_QUEUE_APPROVED`, admin-only delivery queue/detail visibility, provider-failure lifecycle evidence, imported support handoff frontend evidence, and release-gate documentation. Approved third-party provider adapters, retry workers, two-way sync, support SLA analytics, and broader CRM/customer messaging remain future scope.

## Completed Or Largely Complete

- Auth basics: `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/me`.
- File upload presign: `/files/presign`.
- Question flow: `/questions`, `/questions/{id}`, `/questions/{id}/request-teacher`, `/questions/{id}/feedback`.
- OCR and AI path: `ocr_service`, `ai_service`, and synchronous question submission path.
- Teacher takeover: `/teachers/queue`, `/teachers/questions/{id}/takeover`, `/reply`, `/resolve`.
- Parent portal: `/parents/me/children`, child summary/history/report, legacy parent report routes.
- Weekly report automation: scheduled generation, S3 artifacts, SES delivery, parent report view, and extensive report operations recovery.
- Admin basics: `/admin/users`, `/admin/users/{id}`, `/admin/stats`.
- Report operations hardening: recovery jobs, evidence export, support handoff, artifact editing/rollback, immutable evidence, retention governance.
- Teacher reply quality and SLA operations: versioned rich reply/formula payload, backend sanitization/refusal, first-reply/takeover/resolve SLA fields, tutor SLA badges/composer, and admin aggregate Teacher SLA stats.
- Content moderation operations: user/tutor report actions, moderation case storage/history, admin list/detail/update/note APIs, admin moderation queue/detail/actions UI, and production-safe verification.
- Manual subscription operations: parent subscription plan/request APIs, admin request processing/apply APIs, parent plan/request UI, admin subscription queue/detail/actions UI, and focused local verification.
- Learning expansion foundation: subject taxonomy, subject-specific prompt context, topic seeds, student/parent learning profile APIs, and student/parent learning profile UI.
- Notification and teacher assistance foundation: durable in-product notification events, recipient list/read/archive APIs, admin operational notification list, tutor assistance summary seed API, notification center UI, admin operational notification card, and tutor assistance seed panel.
- Full WebSocket realtime notification functional scope: WebSocket transport contract, backend connection records and fanout helpers, delivery attempt metadata, frontend WebSocket notification client, live/fallback notification center UX, and browser fixture coverage.
- AI teacher tools and exercise generation: reviewed-draft output contract, backend summary/exercise draft APIs, tutor AI teacher tools UI, and release-gate evidence for automatic summaries, suggested focus, draft explanations, and bounded practice exercise drafts.
- Full curriculum rollout: curriculum hierarchy, content states, lesson/exercise bank contract, backend catalog/exercise/progress APIs, student/parent/tutor UI signals, and release-gate evidence for math, physics, German, and English.
- Payment provider integration MVP: Stripe-first provider scope, STOA tier mapping, billing state model, checkout session creation, signed webhook lifecycle, parent checkout/status UX, admin billing visibility, and release-gate evidence.
- Adaptive learning memory and assignment foundation: durable memory fields, source inputs, reviewed assignment lifecycle, recommendation boundaries, student/tutor/parent visibility requirements, backend APIs, and route contracts.
- Mobile and multilingual backend foundation: mobile-ready route contracts, durable `en`/`de` locale preferences, language-safe adaptive response metadata, and release evidence with deferred frontend/native ownership.
- Production notification delivery readiness: production WebSocket/API Gateway contract, durable notification preferences, preference-aware delivery decisions, admin delivery status, digest preview readiness, metadata-safe digest payloads, push-ready preference flags, and clean local release evidence.
- Frontend mobile and visual localization rollout: selected student, parent, tutor, and admin mobile viewport polish, targeted Playwright coverage, English/German language preference UI backed by locale APIs, `/auth/me` locale refresh behavior, and local frontend release-gate evidence.
- Support integration and operations handoff: destination contract, controlled `internal_queue` delivery, admin-only delivery queue/detail visibility, provider-failure lifecycle coverage, imported frontend evidence, and local backend release-gate evidence.

## v3.0 Closed MVP Gaps

| Gap | Source | Current evidence | Priority |
|-----|--------|------------------|----------|
| Forgot password/reset flow | `PRD.md` 3.1 P1 | Phase 89 added Cognito-backed `/auth/forgot-password` and `/auth/reset-password`; Phase 91 deployed API Gateway public routes and production-smoked unknown-account behavior. | Closed |
| Real email verification decision | `PRD.md` 3.1 P0 | Phase 89 made the current operational decision explicit through profile metadata and `emailVerificationStatus=admin_marked_verified`; real user email verification remains a future policy option, not hidden behavior. | Closed |
| Formal parent-student binding | `PRD.md` 3.1 P1 | Phase 89 added formal binding rows, parent portal preference for bindings, weekly report binding discovery, one-sided claim pending states, and admin inspection/repair endpoints. | Closed |
| OCR correction before submit | `PRD.md` 3.2 P1 | Phase 90 added edit-before-AI `corrected_text`, stored original/corrected/OCR metadata, and preserved OCR append behavior when no correction is provided. | Closed |
| Robust daily question limit | `PRD.md` 3.2 P0 | Phase 90 replaced bounded latest-question scans with atomic daily usage counters. | Closed |
| v2.9 production governance verification | `.planning/STATE.md` | Phase 88 deployed backend/frontend governance changes and recorded API/browser smoke evidence. | Closed |

## v3.1 Closed MVP Gaps

| Gap | Source | Current evidence | Priority |
|-----|--------|------------------|----------|
| Teacher rich text/formula reply polish | `PRD.md` 3.3 P0 | Phase 92 defined the contract; Phase 93 added backend normalized rich reply/formula payloads and refusal rules; Phase 94 added the active tutor composer and safe formula renderer; Phase 95 deployed and production-smoked read-only surfaces. | Closed |
| SLA response tracking | `PRD.md` 3.3 P1 | Phase 93 added request/takeover/first-reply/resolve SLA fields and admin `teacher_sla` aggregates; Phase 94 added tutor SLA badges and admin Teacher SLA card. | Closed |

## v3.2 Closed MVP Gap

| Gap | Source | Current evidence | Priority |
|-----|--------|------------------|----------|
| Content moderation | `PRD.md` 3.5 P2 | Phase 96 defined the contract; Phase 97 added backend report creation/admin APIs; Phase 98 added student/tutor report actions and admin moderation UI; Phase 99 deployed and production-smoked read-only/auth-gated surfaces. | Closed |

## v3.3 Closed MVP Gap

| Gap | Source | Current evidence | Priority |
|-----|--------|------------------|----------|
| Manual subscription operations before payment-provider integration | `PLAN.md` manual paid onboarding model | Phase 100 defined plan/lifecycle/entitlement contract; Phase 101 added backend parent/admin APIs; Phase 102 added parent/admin UI and E2E; Phase 103 captured local release-gate evidence. | Closed |

## v3.4 Closed Phase 2 Foundation Gap

| Gap | Source | Current evidence | Priority |
|-----|--------|------------------|----------|
| Multi-subject foundation and student profile seeds | `PRD.md` / `PLAN.md` Phase 2 learning expansion | Phase 104 defined subject/topic/prompt contract; Phase 105 added backend subject/topic/profile seed APIs; Phase 106 added student/parent UI and E2E; Phase 107 captured local release-gate evidence. | Closed for foundation scope |

## v3.5 Closed Phase 2 Foundation Gap

| Gap | Source | Current evidence | Priority |
|-----|--------|------------------|----------|
| Realtime notification and AI teacher assistance foundation | `PRD.md` / `PLAN.md` Phase 2 teacher support and realtime expansion | Phase 108 defined notification event and assistance seed contracts; Phase 109 added backend notification events, list/read/archive/admin APIs, and tutor summary seeds; Phase 110 added notification center, admin operational notification, and tutor assistance seed UI; Phase 111 captured local release-gate evidence. | Closed for foundation scope |

## v3.6 Closed Phase 2 Functional Gap

| Gap | Source | Current evidence | Priority |
|-----|--------|------------------|----------|
| Full WebSocket realtime notifications | `PRD.md` / `PLAN.md` Phase 2 realtime expansion | Phase 112 defined the WebSocket lifecycle/auth/channel/fallback contract; Phase 113 added backend connection records, authorized subscriptions, notification fanout, and delivery metadata; Phase 114 added the feature-flagged frontend WebSocket client, cache sync, reconnect/offline/fallback UX, and browser fixture coverage; Phase 115 captured local release-gate evidence. | Closed for local functional scope |

## v3.7 Closed Phase 2 Functional Gap

| Gap | Source | Current evidence | Priority |
|-----|--------|------------------|----------|
| AI teacher tools, automatic summaries, and exercise generation | `PRD.md` / `PLAN.md` Phase 2 teacher support and learning expansion | Phase 116 defined reviewed-draft output/input/lifecycle contracts; Phase 117 added backend summary and exercise draft APIs; Phase 118 added tutor UI; Phase 119 captured functional release-gate and residual-scope audit evidence. | Closed for local functional scope |

## v3.8 Closed Phase 2 Functional Gap

| Gap | Source | Current evidence | Priority |
|-----|--------|------------------|----------|
| Full multi-subject curriculum rollout and exercise banks | `PRD.md` / `PLAN.md` Phase 2 learning expansion | Phase 120 defined curriculum hierarchy/content states/backfill behavior; Phase 121 added backend curriculum catalog and exercise bank APIs; Phase 122 added student/parent/tutor UI; Phase 123 captured functional release-gate and residual adaptive sequencing/automatic assignment audit evidence. | Closed for local functional scope |

## v3.9 Closed Phase 2 Functional Gap

| Gap | Source | Current evidence | Priority |
|-----|--------|------------------|----------|
| Stripe/TWINT subscription payment integration | `PRD.md` subscription management and `PLAN.md` Phase 2 growth features | Phase 124 defined provider/tier/billing/webhook contract; Phase 125 added backend checkout/status/webhook APIs; Phase 126 added parent payment UX and admin billing operations; Phase 127 captured functional billing release-gate evidence. | Closed for local functional scope |

## v4.0 Closed Phase 2 Functional Gap

| Gap | Source | Current evidence | Priority |
|-----|--------|------------------|----------|
| Personalized learning memory and reviewed assignments | `PLAN.md` Phase 2 growth feature: personalized learning memory / student profile | Phase 128 defined the memory/assignment contract; Phase 129 added backend memory and reviewed assignment APIs; Phase 130 added student/tutor/parent route contracts and backend-visible progress signals; Phase 131 captured functional personalization release-gate evidence. | Closed for backend foundation scope |

## v4.1 Closed Phase 2 Functional Gap

| Gap | Source | Current evidence | Priority |
|-----|--------|------------------|----------|
| Mobile-friendly backend contracts and multilingual preference foundation | `PLAN.md` Phase 2 growth feature: mobile responsive polish / multilingual frontend rollout | Phase 132 defined backend/client ownership, mobile-critical flow contract, supported locale policy, and gap-audit updates; Phase 133 added durable locale preference APIs; Phase 134 polished selected adaptive role route metadata and mobile contracts; Phase 135 captured verification and deferred frontend/native evidence. | Closed for backend foundation scope |

## v4.2 Closed Phase 2 Functional Gap

| Gap | Source | Current evidence | Priority |
|-----|--------|------------------|----------|
| Production notification delivery readiness | `PLAN.md` Phase 2 growth feature: push notifications / email notifications / production realtime rollout | Phase 136 defined WebSocket route/integration/config/fallback contracts and ownership boundaries; Phase 137 added durable preferences, delivery decisions, realtime preference gating, and admin status; Phase 138 added digest preview selection, metadata-safe payloads, and no-provider fallback metadata; Phase 139 captured full pytest/ruff release evidence and deferred provider/frontend/native rollout scope. | Closed for backend readiness scope |

## v4.3 Closed Phase 2 Functional Gap

| Gap | Source | Current evidence | Priority |
|-----|--------|------------------|----------|
| Selected frontend mobile responsive polish and English/German visual localization | `PLAN.md` Phase 2 growth feature: mobile responsive polish / multilingual frontend rollout | Phase 140 confirmed the frontend workspace and UAT plan; Phase 141 added shared mobile layout polish and targeted mobile Playwright coverage; Phase 142 wired language switching to the locale preference API and `/auth/me` refresh behavior; Phase 143 captured lint/build/browser release-gate evidence and updated remaining-feature docs. | Closed for selected frontend rollout scope |

## Phase 2 / Future Expansion

- Live payment-provider rollout with approved production credentials, TWINT production validation, invoices/receipts/refunds, tax/accounting, and dunning.
- Full production notification rollout beyond v4.2 readiness: CDK/API Gateway deployment, live endpoint smoke, real provider credentials, frontend/native visuals, native push token registration, email templates/scheduling, and broader notification analytics.
- Automatic student assignment of generated exercises and autonomous tutoring decisions.
- Long-term adaptive exercise sequencing beyond v3.8 curriculum catalog/progress scope.
- Native mobile apps, native push-token registration, and production mobile rollout.
- Translation management, broad copy QA, RTL support, and full localization governance beyond selected English/German frontend surfaces.
- Approved third-party support provider adapters, retry workers, two-way sync, support SLA analytics, and broader CRM/customer messaging automation beyond the v4.5 controlled internal queue path.

## Remaining Feature Build Order

1. v4.6 Rich curriculum authoring, production content QA, analytics, and deeper compliance operations.
2. Payment production activation and provider automation: approved live Stripe credentials, TWINT account validation, webhook registration, direct refund execution, provider-readiness checks, and finance acceptance.
3. Support provider expansion beyond v4.5: approved third-party adapters, retry workers, two-way sync, SLA analytics, and broader CRM/customer messaging.
4. Full production notification rollout beyond backend readiness once infrastructure/provider/frontend ownership is available.
5. Native mobile app rollout and full localization governance beyond the selected v4.3 frontend scope.

## v3.0 Scope Recommendation

v3.0 scope was completed:

1. Closed v2.9 production deploy/live-smoke gap.
2. Implemented account lifecycle gaps: forgot password, reset password, explicit email verification policy metadata, and parent-student binding.
3. Implemented OCR correction and hardened daily question quota.
4. Updated this gap audit and release evidence after verification.

## v3.1 Scope Outcome

v3.1 completed the selected teacher-takeover MVP closeout:

1. Defined the safe rich text/formula reply contract.
2. Added backend metadata and sanitization/refusal for rich replies.
3. Added SLA timestamping and aggregate response metrics.
4. Exposed teacher/admin SLA visibility and updated release evidence.

## v3.2 Scope Outcome

v3.2 completed the remaining MVP admin moderation workflow before Phase 2 expansion:

1. Define the moderation case contract, status lifecycle, data model, and API/UI workflow.
2. Add backend report creation and admin moderation list/detail/action APIs.
3. Add student/teacher report actions and admin moderation queue/detail UI.
4. Close with lightweight functional checks and update this gap audit with the outcome.

## v3.3 Scope Outcome

v3.3 completed the manual subscription operations MVP before payment-provider integration:

1. Define plan tiers, entitlement effects, request lifecycle, and manual billing boundaries.
2. Add parent subscription plan/request APIs and admin subscription request processing APIs.
3. Add parent subscription management UI and admin subscription queue/detail UI.
4. Close with lightweight functional checks and keep Stripe/TWINT as a later provider integration.

## v3.4 Scope Outcome

v3.4 completed the learning expansion foundation before broad curriculum rollout:

1. Defined subject identifiers, rollout states, topic taxonomy, and prompt behavior by subject.
2. Added backend subject/topic support and student profile seed aggregation.
3. Added student/parent learning profile UI backed by backend-shaped data.
4. Closed with lightweight functional checks and recorded residual full-curriculum, AI teacher tooling, and personalization scope.

## v3.5 Scope Outcome

v3.5 completed notification and teacher-assistance foundations before full realtime rollout:

1. Defined notification event types, recipient rules, lifecycle, and API/UI behavior.
2. Defined teacher assistance summary seed inputs and output shape.
3. Added backend event list/read/archive, admin notification list, and tutor summary seed support.
4. Added tutor/admin notification and summary UI and recorded residual WebSocket, push/email, and exercise-generation scope.

## v3.6 Scope Recommendation

v3.6 should complete full WebSocket realtime notifications:

1. Define WebSocket connection lifecycle, auth/subscription model, event envelope, and fallback behavior.
2. Add backend connection records, authenticated WebSocket route handling, event fanout, and stale cleanup.
3. Add frontend realtime client, reconnect behavior, notification center sync, and fallback UX.
4. Close with functional realtime evidence and record residual push/native/email notification scope.

## v3.6 Scope Outcome

v3.6 completed the local functional WebSocket realtime notification gate:

1. Defined WebSocket connection lifecycle, auth/subscription model, event envelope, and fallback behavior.
2. Added backend connection records, authorized subscription operations, event fanout, stale cleanup, and delivery attempt metadata.
3. Added frontend realtime client behavior, reconnect/heartbeat/offline handling, notification center cache sync, and polling fallback UX.
4. Closed with backend pytest/Ruff evidence, frontend lint/build/browser fixture evidence, and explicit residual production WebSocket infrastructure plus push/native/email scope.

## v3.7 Scope Outcome

v3.7 completed reviewed AI teacher tools and bounded exercise generation:

1. Defined AI teacher tool output contracts, input sources, generation lifecycle, review boundary, and refusal/fallback behavior.
2. Added backend teacher summary, draft explanation, and practice exercise draft APIs using existing question, tutor, subject/topic, and learning profile context.
3. Added tutor UI for summaries, suggested focus, draft explanations, exercise draft review, regenerate, accept, reject, and archive actions.
4. Closed with backend pytest/focused Ruff evidence, frontend lint/build/browser evidence, and residual automatic assignment, full curriculum banks, long-term adaptive sequencing, and production AI cost/quality monitoring scope.

## v3.8 Scope Outcome

v3.8 completed the full curriculum rollout foundation:

1. Defined curriculum hierarchy, supported subjects, content lifecycle states, lesson fields, exercise fields, and compatibility with existing practice data.
2. Added backend curriculum catalog and exercise bank APIs for active content while preserving current progress, mistakes, and challenge attempts.
3. Added student/parent curriculum navigation and tutor/admin curriculum context signals.
4. Closed with focused functional checks and recorded residual automatic assignment, long-term adaptive sequencing, rich authoring workflow, and production content QA/analytics scope.

## v3.9 Scope Outcome

v3.9 completed the payment provider integration MVP:

1. Defined Stripe-first provider scope, STOA tier to provider product/price mapping, local billing states, webhook mapping, idempotency, and manual override behavior.
2. Added backend checkout session creation, subscription status, billing event persistence, and webhook lifecycle APIs.
3. Added parent checkout/status UX and admin billing visibility.
4. Closed with focused functional checks and recorded residual live-charge rollout, TWINT production validation, invoices/receipts/refunds, tax/accounting, and dunning scope.

## v4.0 Scope Recommendation

v4.0 completed adaptive learning memory and reviewed assignment workflows:

1. Define durable memory fields, input sources, freshness behavior, reviewed assignment lifecycle, recommendation boundaries, and role visibility.
2. Add backend memory snapshot, next-practice recommendation, and reviewed assignment APIs using question, curriculum, AI draft, feedback, and weekly report signals.
3. Add student next-practice/assignment UX, tutor assignment controls, and parent progress signals.
4. Close with focused functional checks and record residual fully autonomous tutoring, long-term sequencing, analytics dashboard, and native mobile scope.

## v4.1 Scope Outcome

v4.1 completed the backend mobile and multilingual polish foundation:

1. Defined backend/client ownership boundaries for mobile-critical flows and visual localization.
2. Added durable locale preference storage and authenticated profile/preference APIs.
3. Added language-safe route metadata while preserving canonical API values.
4. Closed with backend verification and explicit deferred frontend/native rollout scope.

## v4.2 Scope Outcome

v4.2 completed production notification delivery readiness:

1. Define production WebSocket route/integration, configuration, fallback, and channel mapping contracts.
2. Add durable notification preference APIs and backend delivery decision/status behavior.
3. Add digest-ready selection/preview behavior and push preference metadata without requiring live provider credentials during internal development.
4. Closed with full backend pytest/ruff evidence and updated the remaining-feature queue toward frontend/mobile localization, which v4.3 later completed for selected frontend flows.

## v4.1 Scope Recommendation

v4.1 completed the backend foundation for mobile and multilingual polish:

1. Define backend/client ownership, supported locales, fallback behavior, mobile-critical route contracts, and deferred UI scope.
2. Add durable locale preference APIs and shared normalization/fallback behavior.
3. Apply language metadata and mobile-friendly contract checks to selected student, parent, tutor, and admin routes while keeping canonical values stable.
4. Close with focused backend verification and record residual full responsive frontend/native and visual localization scope.

## v4.3 Scope Outcome

v4.3 completed the selected frontend mobile and visual localization rollout:

1. Confirmed the frontend workspace, route/API/i18n contracts, and mobile/localization UAT plan.
2. Improved shared mobile shell, buttons, page actions, and selected tutor AI tool layouts.
3. Added authenticated English/German language preference persistence through the backend locale API and `/auth/me` refresh behavior.
4. Closed with frontend lint/build evidence and targeted Playwright coverage for mobile student/parent/tutor/admin flows plus language persistence, leaving native apps, full translation governance, production frontend deploy smoke, live payments, support integrations, rich authoring, and production notification rollout in the remaining queue.
