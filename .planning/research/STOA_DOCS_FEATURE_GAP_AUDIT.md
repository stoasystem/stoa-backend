# STOA Docs Feature Gap Audit

**Created:** 2026-06-07
**Updated:** 2026-06-08 after completing v3.3
**Sources:** `/Users/zhdeng/stoa-docs/PRD.md`, `/Users/zhdeng/stoa-docs/HLD.md`, `/Users/zhdeng/stoa-docs/PLAN.md`, current `stoa-backend` routes, and completed `.planning` milestones.

## Summary

The MVP backend surface from `stoa_docs` is mostly implemented: auth register/login/refresh/logout, file presign, question submit/get/request-teacher/feedback, teacher queue/takeover/reply/resolve, student summary/history, parent children/report access, weekly report automation, admin user/stat APIs, production report operations, and immutable evidence/governance workflows exist.

v3.0 closed the highest-priority account/intake MVP gaps identified in this audit: account lifecycle hardening, explicit parent-student binding, OCR correction before final submission, robust daily question quota enforcement, and production deployment/live smoke for the v2.9 governance UI/API.

v3.1 closed the remaining teacher-takeover MVP gaps selected for that cycle: safe rich text/formula teacher replies, response-time SLA tracking, teacher queue/session visibility, admin aggregate SLA visibility, and production-safe release verification.

v3.2 closed the remaining visible MVP admin workflow gap: content moderation for reported or abnormal learning content. The release added report actions, moderation cases, admin queue/detail/actions, deploy evidence, and production-safe smoke.

v3.3 completed the MVP manual subscription process before Stripe/TWINT: parent plan/request UI, admin processing queue, tier application workflow, and focused backend/frontend verification. Payment-provider integration remains future scope.

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

## Phase 2 / Future Expansion

- Stripe/TWINT subscription payments after manual operations are usable.
- Multi-subject rollout for physics, German, English beyond current subject fields/content.
- Student memory/personalization.
- AI teacher assistance tools such as automatic summaries and exercise generation.
- WebSocket realtime notifications.
- Mobile responsive polish.
- Full frontend multilingual rollout.
- Support-ticket/evidence integrations after an approved connector or credential path exists.

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
