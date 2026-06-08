# STOA Docs Feature Gap Audit

**Created:** 2026-06-07
**Updated:** 2026-06-08 after v3.0 closeout
**Sources:** `/Users/zhdeng/stoa-docs/PRD.md`, `/Users/zhdeng/stoa-docs/HLD.md`, `/Users/zhdeng/stoa-docs/PLAN.md`, current `stoa-backend` routes, and completed `.planning` milestones.

## Summary

The MVP backend surface from `stoa_docs` is mostly implemented: auth register/login/refresh/logout, file presign, question submit/get/request-teacher/feedback, teacher queue/takeover/reply/resolve, student summary/history, parent children/report access, weekly report automation, admin user/stat APIs, production report operations, and immutable evidence/governance workflows exist.

v3.0 closed the highest-priority remaining MVP gaps identified in this audit: account lifecycle hardening, explicit parent-student binding, OCR correction before final submission, robust daily question quota enforcement, and production deployment/live smoke for the v2.9 governance UI/API.

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

## v3.0 Closed MVP Gaps

| Gap | Source | Current evidence | Priority |
|-----|--------|------------------|----------|
| Forgot password/reset flow | `PRD.md` 3.1 P1 | Phase 89 added Cognito-backed `/auth/forgot-password` and `/auth/reset-password`; Phase 91 deployed API Gateway public routes and production-smoked unknown-account behavior. | Closed |
| Real email verification decision | `PRD.md` 3.1 P0 | Phase 89 made the current operational decision explicit through profile metadata and `emailVerificationStatus=admin_marked_verified`; real user email verification remains a future policy option, not hidden behavior. | Closed |
| Formal parent-student binding | `PRD.md` 3.1 P1 | Phase 89 added formal binding rows, parent portal preference for bindings, weekly report binding discovery, one-sided claim pending states, and admin inspection/repair endpoints. | Closed |
| OCR correction before submit | `PRD.md` 3.2 P1 | Phase 90 added edit-before-AI `corrected_text`, stored original/corrected/OCR metadata, and preserved OCR append behavior when no correction is provided. | Closed |
| Robust daily question limit | `PRD.md` 3.2 P0 | Phase 90 replaced bounded latest-question scans with atomic daily usage counters. | Closed |
| v2.9 production governance verification | `.planning/STATE.md` | Phase 88 deployed backend/frontend governance changes and recorded API/browser smoke evidence. | Closed |

## Remaining MVP/Future Gaps

| Gap | Source | Current evidence | Priority |
|-----|--------|------------------|----------|
| Teacher rich text/formula reply polish | `PRD.md` 3.3 P0 | Teacher reply endpoint exists; rich text/formula contract needs explicit verification. | Medium |
| SLA response tracking | `PRD.md` 3.3 P1 | Queue/takeover exists; SLA reporting should be verified in admin stats or added. | Medium |
| Content moderation | `PRD.md` 3.5 P2 | Not currently a visible admin workflow. | Low |

## Phase 2 / Future Expansion

- Stripe/TWINT subscription payments.
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
