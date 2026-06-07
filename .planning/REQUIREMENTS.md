# Requirements: v3.0 STOA Docs Gap Closeout And Account Intake Hardening

**Milestone:** v3.0
**Status:** Active
**Created:** 2026-06-07

## Goal

Reconcile `stoa_docs` with the shipped backend/frontend state, close the highest-priority MVP product gaps that remain, and production-verify the v2.9 governance work before taking on broader Phase 2 expansion.

## Requirements

### DOCGAP-01 STOA Docs Feature Gap Audit And Scope Readiness

Implementers have a current, source-linked feature gap audit that maps `stoa_docs` PRD/HLD/PLAN requirements to shipped code, completed milestones, active gaps, and future scope.

Acceptance criteria:

- Audit lists completed MVP capabilities, partially complete capabilities, open MVP gaps, and Phase 2/future expansion items.
- Audit cites the relevant `stoa_docs` files and current backend route/service evidence.
- Audit identifies v2.9 production deploy/live-smoke deferral as a release gap separate from product feature gaps.
- Scope recommendation selects a small v3.0 implementation slice and defers Stripe, broad multi-subject rollout, WebSocket, student memory, AI tutor tools, rich WYSIWYG editor, PDF/multilingual delivery, billing, analytics, and support-ticket integrations unless separately approved.

### PRODVERIFY-13 v2.9 Governance Production Verification Closeout

v2.9 retention governance backend/frontend changes are deployed and production-verified before v3.0 claims production readiness.

Acceptance criteria:

- Backend/frontend deploy evidence, commit SHAs, timestamps, Lambda runtime state, admin API request IDs, and browser smoke results are recorded.
- Production smoke verifies retention governance status, approval metadata, legal-hold review controls, privacy denylist, and admin-only gating.
- Smoke does not delete audit rows, delete immutable objects, mutate customer report artifacts, write external support-system data, expose private storage identifiers, or fabricate legal/compliance approval.

### AUTH-05 Account Lifecycle And Parent Binding Gap Closeout

The auth/account lifecycle covers remaining `stoa_docs` MVP gaps without weakening Cognito security.

Acceptance criteria:

- Forgot-password/reset flow is implemented or explicitly integrated through Cognito-hosted/secret-backed approved flow.
- Email verification behavior is made explicit: either real verification is enabled, or registration response/docs/admin status clearly record the operational decision and risk.
- Parent-student binding is formalized beyond best-effort registration profile fields, with admin-safe repair/inspection behavior where needed.
- Tests cover auth edge cases, parent-child binding authorization, and no credential/token leakage.

### QUESTION-07 OCR Correction And Daily Question Quota Hardening

Question intake matches `stoa_docs` more closely and daily quota enforcement is robust.

Acceptance criteria:

- OCR correction flow is defined and implemented as either preview-before-submit or edit-before-AI behavior.
- Question submission preserves the final corrected text and the OCR source metadata needed for audit/debug without exposing private image keys to unauthorized users.
- Daily question limit no longer depends on a bounded question-history scan that can miss records beyond pagination.
- Tests cover OCR correction, image/text submission, quota boundaries, and authorization.

### VERIFY-13 v3.0 Release Gate And Docs Alignment

v3.0 closes with deploy/test evidence and an updated feature gap ledger.

Acceptance criteria:

- Local quality gates, backend/frontend deploy evidence, production smoke, commit SHAs, request IDs, and timestamps are recorded.
- `stoa_docs` gap audit is updated with v3.0 outcomes and remaining future requirements.
- Final audit confirms no production customer data mutation beyond explicitly approved flows and no private marker exposure.

## Future Requirements

- Stripe/TWINT subscription payments.
- Broad multi-subject rollout beyond current subject fields/content.
- Student memory/personalization.
- AI teacher assistance tools such as summaries and exercise generation.
- WebSocket realtime notifications.
- Mobile responsive polish and frontend multilingual rollout.
- Content moderation workflow.
- Direct support ticket/evidence integrations after an approved connector or credential path exists.

## Out of Scope

- Legal advice or fabricated compliance approval.
- Direct production customer data mutation without named approval and rollback/cleanup path.
- Direct third-party support-system writes.
- Broad Phase 2 expansion in the same milestone.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DOCGAP-01 | Phase 87 | Complete |
| PRODVERIFY-13 | Phase 88 | Planned |
| AUTH-05 | Phase 89 | Planned |
| QUESTION-07 | Phase 90 | Planned |
| VERIFY-13 | Phase 91 | Planned |
