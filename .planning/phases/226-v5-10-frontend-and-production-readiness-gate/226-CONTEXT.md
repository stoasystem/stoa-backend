---
phase: 226
name: v5.10 Frontend And Production Readiness Gate
status: active
created: 2026-07-03
---

# Phase 226 Context: v5.10 Frontend And Production Readiness Gate

## Goal

Close v5.10 with local frontend/backend evidence and a production read-only verification plan.

## Scope

- Re-run frontend lint/build.
- Re-run focused frontend e2e for:
  - email verification UX,
  - parent account operations,
  - admin account operations.
- Re-run backend focused contract tests for v5.6-v5.9 routes consumed by the frontend.
- Write release evidence and production read-only smoke checklist.
- Update active and milestone snapshot planning docs.

## Local Verification Targets

- `/Users/zhdeng/stoa-frontend`: `npm run lint`
- `/Users/zhdeng/stoa-frontend`: `npm run build`
- `/Users/zhdeng/stoa-frontend`: `npx playwright test tests/e2e/auth.spec.ts tests/e2e/parent-account-operations.spec.ts tests/e2e/admin-account-operations.spec.ts`
- `/Users/zhdeng/stoa-backend`: `pytest tests/test_subscription_operations.py`

## Production Read-Only Smoke Boundaries

- Do not create live customers, payments, children, or support tickets.
- Use existing approved test/admin/parent accounts only.
- Prefer read-only routes and state inspection.
- Email verification smoke may inspect visible pending/verified states but must not spam real users.
- Account operations smoke may inspect support state but must not mutate subscription status.

## Residual Scope

- Live Stripe/TWINT activation remains externally gated.
- Passwordless login-code implementation remains deferred.
- Additional usage ledger actions beyond question submissions remain future work.
- Native/mobile account operations clients remain future work.
