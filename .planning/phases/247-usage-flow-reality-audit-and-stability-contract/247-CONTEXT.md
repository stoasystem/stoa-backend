# Phase 247 Context

## Milestone

v5.15 Usage, Quota, And Product Stability

## Requirement

STABILITY-01 Usage Reality Audit

## Starting Point

v5.11 introduced a governed usage ledger taxonomy, multi-action instrumentation, reconciliation helpers, and account operations compatibility. v5.14 left a residual frontend e2e blocker: backend gate and frontend build passed, but focused frontend e2e was blocked by platform usage-limit approval.

Phase 247 intentionally audits real code paths before changing runtime behavior. The goal is to separate existing trustworthy coverage from missing coverage, partial ordering risks, and future BI/APM work.

## Files Reviewed

- `src/stoa/services/usage_ledger_service.py`
- `src/stoa/db/repositories/question_repo.py`
- `src/stoa/services/rate_limit.py`
- `src/stoa/routers/questions.py`
- `src/stoa/routers/conversations.py`
- `src/stoa/routers/practice.py`
- `src/stoa/services/adaptive_learning_service.py`
- `tests/test_usage_ledger.py`
- `tests/test_questions.py`
- `tests/test_conversations.py`
- `tests/test_curriculum_analytics.py`
- `tests/test_adaptive_learning.py`
- `/Users/zhdeng/stoa-frontend/src/services/chat/chatApi.ts`
- `/Users/zhdeng/stoa-frontend/src/services/practice/practiceApi.ts`
- `/Users/zhdeng/stoa-frontend/src/pages/dashboard/StudentDashboardPage.tsx`
- `/Users/zhdeng/stoa-frontend/src/pages/admin/AdminAccountOperationsPage.tsx`
- `/Users/zhdeng/stoa-frontend/tests/e2e/admin-account-operations.spec.ts`
- `/Users/zhdeng/stoa-frontend/tests/e2e/parent-account-operations.spec.ts`

## Existing Contract Evidence

- `usage_ledger_service.USAGE_ACTION_DEFINITIONS` is the canonical action taxonomy.
- Question submission uses an atomic daily counter plus a specialized usage ledger row.
- Chat messages and hints use daily counters plus governed ledger events.
- Question teacher-help, conversation teacher-help, practice answers, lesson completion, assignment generation, and assignment transitions use governed ledger events without quota counters.
- Ledger metadata is filtered through an allowlist and blocks raw content, answers, prompts, provider payloads, tokens, verification codes, and private artifact keys.
- Student/parent/admin support summaries use reconciliation status and support-safe counts instead of raw learning content.

## Constraints

- Frontend repository is outside this backend workspace write root.
- Live provider smoke for Stripe/TWINT, Cognito/email, notifications, and external support providers remains out of scope unless separately approved.
- This phase should not rewrite usage semantics. Runtime fixes are assigned to Phase 248-250.
