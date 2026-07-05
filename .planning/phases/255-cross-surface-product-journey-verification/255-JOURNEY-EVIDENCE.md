# Phase 255 Cross-Surface Journey Evidence

## Parent Journey

| Capability | Frontend evidence | Backend evidence | Status |
|------------|-------------------|------------------|--------|
| Verification and account readiness | `auth.spec.ts`; `parent-account-operations.spec.ts` | `tests/test_auth_account_lifecycle.py`; `tests/test_subscription_operations.py` | Passed locally |
| Paid state and entitlement | `subscription-operations.spec.ts`; `billing-pricing.spec.ts`; `parent-account-operations.spec.ts` | `tests/test_subscription_operations.py`; `src/stoa/services/subscription_service.py` | Passed locally; live Stripe/TWINT external-blocked |
| Child binding and parent visibility | `parent-account-operations.spec.ts`; `parent-dashboard.spec.ts`; `learning-profile.spec.ts` | `tests/test_subscription_operations.py`; `src/stoa/services/account_operations_service.py` | Passed locally |
| Usage/quota explanation | `parent-account-operations.spec.ts`; `parent-dashboard.spec.ts` | `tests/test_usage_ledger.py`; `tests/test_subscription_operations.py` | Passed locally |
| Support state and failures without fallback | `parent-account-operations.spec.ts`; `billing-pricing.spec.ts` | `tests/test_subscription_operations.py`; `tests/test_usage_ledger.py` | Passed locally |

Evidence result:

- Parent journey can show ready, attention, blocked, and API-error states.
- Parent-facing support explanations include verification, billing, child binding, and usage reconciliation.
- Billing API failure tests assert visible error handling instead of silent demo fallback.

## Student Journey

| Capability | Frontend evidence | Backend evidence | Status |
|------------|-------------------|------------------|--------|
| Login and protected route landing | `auth.spec.ts` | `tests/test_auth_account_lifecycle.py` | Passed locally |
| Curriculum/profile read | `learning-profile.spec.ts`; `admin-curriculum.spec.ts` | `tests/test_curriculum_rollout.py`; `tests/test_curriculum_ops.py`; `tests/test_curriculum_migration.py`; `tests/test_curriculum_analytics.py` | Passed locally |
| Question/chat flow | `student-chat.spec.ts`; `learning-profile.spec.ts` | `tests/test_questions.py`; `tests/test_conversations.py` | Passed locally |
| Quota and usage accounting | account operations and usage e2e surfaces | `tests/test_usage_ledger.py`; `tests/test_questions.py` | Passed locally |
| Teacher-help request and handoff | `student-chat.spec.ts`; `tutor-workflow.spec.ts` | `tests/test_questions.py`; `tests/test_conversations.py`; `tests/test_usage_ledger.py` | Passed locally; external live support provider activation out of scope |

Evidence result:

- Student can use chat and request tutor support in the local e2e environment.
- Curriculum/profile signals are visible across student and parent views.
- Backend ledger coverage includes question, chat, practice, and teacher-help usage classes.

## Admin Journey

| Capability | Frontend evidence | Backend evidence | Status |
|------------|-------------------|------------------|--------|
| Account operations support console | `admin-account-operations.spec.ts` | `tests/test_subscription_operations.py`; `src/stoa/services/account_operations_service.py` | Passed locally |
| Billing support and request lifecycle | `subscription-operations.spec.ts`; `billing-pricing.spec.ts` | `tests/test_subscription_operations.py`; `src/stoa/services/subscription_service.py` | Passed locally; live provider activation external-blocked |
| Usage reconciliation | account operations e2e surfaces | `tests/test_usage_ledger.py`; `/admin/usage/reconciliation` test coverage | Passed locally |
| Curriculum operations | `admin-curriculum.spec.ts`; `learning-operations.spec.ts` evidence exists | `tests/test_curriculum_ops.py`; `tests/test_curriculum_migration.py`; `tests/test_curriculum_analytics.py` | Passed locally |
| Teacher SLA and support visibility | `tutor-workflow.spec.ts` | teacher-help/conversation usage tests | Passed locally |
| Core smoke output | backend endpoint evidence | `tests/test_core_smoke.py`; `src/stoa/services/core_smoke_service.py` | Passed locally |

Evidence result:

- Admin can inspect ready, warning, missing, and API-error states for account operations.
- Admin can hand off from subscription requests to account operations.
- Core smoke separates local readiness, expected auth/provider blocks, and regressions.

## Supplemental E2E Run

```bash
npm run test:e2e -- student-chat.spec.ts learning-profile.spec.ts parent-dashboard.spec.ts tutor-workflow.spec.ts
```

Result:

- `11 passed (10.7s)`

## Demo/Mock Boundary

Local Playwright e2e uses `VITE_ENABLE_DEMO_API=true`, `VITE_ENABLE_MOCK_CHECKOUT=true`, and `VITE_ENABLE_PAYMENT=false` from `playwright.config.ts`. This is valid for local UI and journey behavior, but it is not evidence of live provider activation.

Production-like readiness rule:

- Local e2e can prove the app renders and handles local API contracts.
- Backend tests can prove support-safe API behavior and provider-blocker classification.
- Live charging, delivery, notification, support-provider, BI/APM, and native activation remain external-blocked until credentials and rollout approval exist.

## Residual External Blocks

- Live Stripe/TWINT payment and webhook activation.
- Live Cognito/email verification delivery.
- Notification provider and external support provider activation.
- BI/warehouse/APM/native activation.

These are not implementation-incomplete findings in v5.16.
