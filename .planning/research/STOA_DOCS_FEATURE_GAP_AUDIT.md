# STOA Docs Feature Gap Audit

**Created:** 2026-06-07
**Sources:** `/Users/zhdeng/stoa-docs/PRD.md`, `/Users/zhdeng/stoa-docs/HLD.md`, `/Users/zhdeng/stoa-docs/PLAN.md`, current `stoa-backend` routes, and completed `.planning` milestones.

## Summary

The MVP backend surface from `stoa_docs` is mostly implemented: auth register/login/refresh/logout, file presign, question submit/get/request-teacher/feedback, teacher queue/takeover/reply/resolve, student summary/history, parent children/report access, weekly report automation, admin user/stat APIs, production report operations, and immutable evidence/governance workflows exist.

The highest-priority remaining gaps are account lifecycle hardening, explicit parent-student binding, OCR correction before final submission, robust daily question quota enforcement, and production deployment/live smoke for the locally completed v2.9 governance UI/API.

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

## Open MVP Gaps

| Gap | Source | Current evidence | Priority |
|-----|--------|------------------|----------|
| Forgot password/reset flow | `PRD.md` 3.1 P1 | Auth routes do not expose forgot/reset endpoints. | High |
| Real email verification decision | `PRD.md` 3.1 P0 | Register suppresses Cognito message and sets `email_verified=true`; this is operationally convenient but not real verification. | High |
| Formal parent-student binding | `PRD.md` 3.1 P1 | Registration stores parent profile fields and parent routes resolve linked children, but explicit binding/invite/repair workflow is not clearly productized. | High |
| OCR correction before submit | `PRD.md` 3.2 P1 | Submit path auto-appends OCR text to content; no preview/correct-before-AI flow is visible. | High |
| Robust daily question limit | `PRD.md` 3.2 P0 | Question quota lists up to 200 recent questions and filters by date; `.planning/codebase/CONCERNS.md` flags pagination/miss risk. | High |
| v2.9 production governance verification | `.planning/STATE.md` | v2.9 closed local-only; backend/frontend production deploy and live smoke are deferred. | High |
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

v3.0 should not start broad Phase 2 expansion yet. Recommended scope:

1. Close v2.9 production deploy/live-smoke gap.
2. Implement or explicitly decide account lifecycle gaps: forgot password, email verification, parent-student binding.
3. Implement OCR correction and harden daily question quota.
4. Update this gap audit and release evidence after verification.
