# Phase 252 Product Readiness Evidence Matrix

## Status Legend

- `covered-local`: implemented and covered by local tests/specs.
- `phase-253-gate`: covered by frontend specs, pending focused e2e execution in Phase 253.
- `phase-254-gate`: backend smoke/support evidence must be verified in Phase 254.
- `phase-255-gate`: cross-surface journey must be verified in Phase 255.
- `external-blocked`: requires credentials, provider activation, or rollout approval outside local execution.

## Release-Critical Surfaces

| Surface | Backend evidence | Frontend evidence | Focused tests/specs | Status | Notes |
|---------|------------------|-------------------|---------------------|--------|-------|
| Auth and email verification | `src/stoa/routers/auth.py`; account lifecycle tests | `RegisterPage.tsx`; `EmailVerificationPanel.tsx`; auth store and auth API hooks | `tests/test_auth_account_lifecycle.py`; `/Users/zhdeng/stoa-frontend/tests/e2e/auth.spec.ts` | `covered-local`, `phase-253-gate` | v5.14 backend/build evidence exists; focused frontend e2e must now be rerun. Live email delivery remains external-blocked. |
| Parent account operations | `src/stoa/routers/parents.py`; `src/stoa/services/account_operations_service.py`; billing/usage support fields | `ParentAccountOperationsPage.tsx`; parent account operations hooks/components | `tests/test_subscription_operations.py`; `/Users/zhdeng/stoa-frontend/tests/e2e/parent-account-operations.spec.ts` | `covered-local`, `phase-253-gate`, `phase-255-gate` | Must show verification recovery, subscription, usage, and support-safe explanations without demo fallback. |
| Admin account operations | `src/stoa/routers/admin.py`; `src/stoa/services/account_operations_service.py`; core smoke service | `AdminAccountOperationsPage.tsx`; admin account operations hooks | `tests/test_subscription_operations.py`; `tests/test_core_smoke.py`; `/Users/zhdeng/stoa-frontend/tests/e2e/admin-account-operations.spec.ts` | `covered-local`, `phase-253-gate`, `phase-254-gate` | Admin must distinguish user/action status from external/provider blockers. |
| Billing, subscriptions, and paid access | `src/stoa/services/subscription_service.py`; `src/stoa/routers/parents.py`; `src/stoa/routers/admin.py` | billing pages, billing hooks, subscription operation cards | `tests/test_subscription_operations.py`; `/Users/zhdeng/stoa-frontend/tests/e2e/subscription-operations.spec.ts`; `/Users/zhdeng/stoa-frontend/tests/e2e/billing-pricing.spec.ts` | `covered-local`, `phase-253-gate`, `external-blocked` | Local paid-state and support evidence are complete; live Stripe/TWINT activation is external-blocked. |
| Usage ledger and quota reconciliation | `src/stoa/services/usage_ledger_service.py`; `src/stoa/db/repositories/usage_ledger_repo.py`; parent/admin support summaries | account operations pages, usage summary cards, quota/support explanations | `tests/test_usage_ledger.py`; `tests/test_core_smoke.py`; account operations e2e specs | `covered-local`, `phase-254-gate`, `phase-255-gate` | v5.15 closed local ledger/quota stability; release gate must prove support-safe evidence is still visible across parent/admin flows. |
| Curriculum read and admin operations | `src/stoa/routers/practice.py`; curriculum services and repos | `AdminCurriculumPage.tsx`; `CurriculumRolloutPanel.tsx`; curriculum graph pages/hooks | `tests/test_curriculum_rollout.py`; `tests/test_curriculum_ops.py`; `tests/test_curriculum_migration.py`; `tests/test_curriculum_analytics.py`; `/Users/zhdeng/stoa-frontend/tests/e2e/admin-curriculum.spec.ts` | `covered-local`, `phase-253-gate`, `phase-255-gate` | v5.12 closed local curriculum buildout; Phase 255 verifies parent/student/admin journey integration. |
| Questions, practice, and teacher help | `src/stoa/routers/questions.py`; `src/stoa/routers/conversations.py`; `src/stoa/routers/practice.py`; governed usage ledger events | teacher help cards, practice teacher support CTA, chat support status | `tests/test_questions.py`; `tests/test_conversations.py`; `tests/test_usage_ledger.py`; `tests/test_curriculum_analytics.py` | `covered-local`, `phase-255-gate` | Student journey must prove curriculum/practice/question/teacher-help behavior together, including quota explanations. |
| Core smoke and support triage | `src/stoa/services/core_smoke_service.py`; `src/stoa/routers/admin.py` | admin operations/smoke visibility through admin support surfaces | `tests/test_core_smoke.py` | `covered-local`, `phase-254-gate` | Phase 254 verifies output remains support-safe and separates expected external blocks from regressions. |

## v5.12-v5.15 Reconciliation

| Milestone | Local completion evidence | v5.16 implication |
|-----------|---------------------------|-------------------|
| v5.12 Curriculum buildout | Backend-authorized curriculum editor/content migration and focused backend/frontend coverage are locally complete. | Treat curriculum as locally implemented; verify admin curriculum e2e and student read/practice journey. |
| v5.13 Payment and entitlement | Paid access, canonical parent billing APIs, webhook reconciliation hardening, frontend paid-state integration, and billing support evidence are locally complete. | Treat local billing/entitlement as implemented; carry live Stripe/TWINT activation as external-blocked. |
| v5.14 Verification/login reliability | Backend verification/login reliability and frontend build passed, but focused frontend e2e was not executed at that point. | Preserve as Phase 253 release gate until `auth.spec.ts` and account operations specs pass or fail with exact classification. |
| v5.15 Usage/quota/product stability | Ledger coverage, idempotency hardening, quota reconciliation explanations, account-operations usage support fields, and admin core smoke are locally complete. | Treat backend usage stability as implemented; verify product-readiness smoke/support evidence in Phase 254 and cross-surface journey in Phase 255. |

## External Blockers

These are not local implementation defects unless credentials and explicit approval are supplied and the check still fails:

- Live Stripe/TWINT charging, settlement, and production webhook activation.
- Live Cognito/email delivery mutation and production verification-code delivery.
- Notification providers, external support provider, APNS/FCM, BI/warehouse, APM, and native app activation.
- Production mutation outside an approved safe fixture or explicit external activation path.

## Phase 253 Focused Frontend E2E Contract

Run the release-critical frontend specs:

```bash
npm run test:e2e -- auth.spec.ts admin-account-operations.spec.ts parent-account-operations.spec.ts subscription-operations.spec.ts billing-pricing.spec.ts admin-curriculum.spec.ts
```

Classify each failure as one of:

- product regression,
- frontend/API contract mismatch,
- e2e fixture or platform problem,
- external provider blocker,
- unrelated dirty-worktree interference.

## Phase 254 Backend Contract

Verify these focused backend tests at minimum:

```bash
.venv/bin/pytest tests/test_core_smoke.py tests/test_usage_ledger.py tests/test_subscription_operations.py tests/test_auth_account_lifecycle.py tests/test_curriculum_rollout.py tests/test_curriculum_ops.py tests/test_curriculum_migration.py tests/test_curriculum_analytics.py tests/test_questions.py tests/test_conversations.py
```

## Release Gate Decision Rule

v5.16 can close as locally product-ready only if:

- focused backend tests pass,
- frontend build/lint/e2e evidence passes or has only non-product external blockers,
- parent/student/admin journeys have support-safe evidence and no production-like demo fallback dependency,
- all live-provider gaps are recorded as external-blocked with exact prerequisite.
