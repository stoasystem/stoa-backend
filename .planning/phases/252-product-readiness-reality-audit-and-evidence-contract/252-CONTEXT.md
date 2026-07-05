# Phase 252 Context

## Milestone

v5.16 End-To-End Product Readiness And Release Evidence

## Requirement

READINESS-01 Product Readiness Reality Audit

## Starting Point

v5.12 through v5.15 closed major local product buildouts: curriculum operations, paid access and entitlement enforcement, verification/login reliability, and usage/quota stability. The remaining problem is not another isolated feature. The release gate needs one current evidence contract that shows which backend routes, services, tests, frontend pages, and frontend e2e specs prove each product surface.

Phase 252 is intentionally an audit and evidence-contract phase. It does not change runtime behavior.

## Files Reviewed

Backend:

- `src/stoa/routers/auth.py`
- `src/stoa/routers/parents.py`
- `src/stoa/routers/admin.py`
- `src/stoa/routers/practice.py`
- `src/stoa/routers/questions.py`
- `src/stoa/routers/conversations.py`
- `src/stoa/services/account_operations_service.py`
- `src/stoa/services/subscription_service.py`
- `src/stoa/services/usage_ledger_service.py`
- `src/stoa/services/core_smoke_service.py`
- `src/stoa/services/curriculum_service.py`
- `src/stoa/services/curriculum_ops_service.py`
- `src/stoa/services/curriculum_migration_service.py`
- `src/stoa/services/curriculum_analytics_service.py`
- `tests/test_auth_account_lifecycle.py`
- `tests/test_subscription_operations.py`
- `tests/test_usage_ledger.py`
- `tests/test_core_smoke.py`
- `tests/test_curriculum_rollout.py`
- `tests/test_curriculum_ops.py`
- `tests/test_curriculum_migration.py`
- `tests/test_curriculum_analytics.py`
- `tests/test_questions.py`
- `tests/test_conversations.py`

Frontend:

- `/Users/zhdeng/stoa-frontend/tests/e2e/auth.spec.ts`
- `/Users/zhdeng/stoa-frontend/tests/e2e/admin-account-operations.spec.ts`
- `/Users/zhdeng/stoa-frontend/tests/e2e/parent-account-operations.spec.ts`
- `/Users/zhdeng/stoa-frontend/tests/e2e/subscription-operations.spec.ts`
- `/Users/zhdeng/stoa-frontend/tests/e2e/billing-pricing.spec.ts`
- `/Users/zhdeng/stoa-frontend/tests/e2e/admin-curriculum.spec.ts`
- `/Users/zhdeng/stoa-frontend/src/pages/auth/RegisterPage.tsx`
- `/Users/zhdeng/stoa-frontend/src/components/auth/EmailVerificationPanel.tsx`
- `/Users/zhdeng/stoa-frontend/src/pages/admin/AdminAccountOperationsPage.tsx`
- `/Users/zhdeng/stoa-frontend/src/pages/parent/ParentAccountOperationsPage.tsx`
- `/Users/zhdeng/stoa-frontend/src/pages/billing/BillingPage.tsx`
- `/Users/zhdeng/stoa-frontend/src/pages/billing/PaymentSettingsPage.tsx`
- `/Users/zhdeng/stoa-frontend/src/pages/admin/AdminCurriculumPage.tsx`
- `/Users/zhdeng/stoa-frontend/src/components/practice/CurriculumRolloutPanel.tsx`
- `/Users/zhdeng/stoa-frontend/src/components/practice/PracticeTeacherSupportCTA.tsx`
- `/Users/zhdeng/stoa-frontend/src/components/chat/TeacherHelpStatusCard.tsx`

## Current Constraints

- Frontend execution and edits happen in `/Users/zhdeng/stoa-frontend`, outside this backend workspace write root.
- Live Stripe/TWINT, Cognito/email delivery, notification provider, external support provider, BI/warehouse, APM, and native-provider checks remain external activation work without credentials and explicit rollout approval.
- Release evidence must stay support-safe: no raw learning content, provider payloads, token material, verification codes, or private artifact data.
