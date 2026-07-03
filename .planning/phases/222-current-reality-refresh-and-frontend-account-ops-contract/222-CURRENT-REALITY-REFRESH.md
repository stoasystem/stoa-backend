# Phase 222 Current Reality Refresh

**Date:** 2026-07-03
**Purpose:** Reconcile shipped code, planning docs, and `stoa_docs` expectations before starting v5.10.

## Backend Current Reality

| Area | Current evidence | Status |
|------|------------------|--------|
| Effective entitlement | `src/stoa/services/entitlement_service.py`; `tests/test_entitlements.py` | Complete for linked-student question quota. |
| Question quota enforcement | `src/stoa/routers/questions.py` uses entitlement output in `_check_daily_limit` | Complete for question submissions. |
| Usage ledger | `src/stoa/services/usage_ledger_service.py`; `tests/test_usage_ledger.py` | Complete for question submissions; other governed actions remain future scope. |
| Email verification | `src/stoa/routers/auth.py` confirm/resend routes; `tests/test_auth_account_lifecycle.py` | Backend complete for Cognito sign-up confirmation lifecycle. |
| Login code policy | `src/stoa/routers/auth.py` login-code request/confirm policy routes | Explicitly deferred; no fake token minting. |
| Parent account operations | `GET /parents/me/account-operations`; `account_operations_service` | Backend complete. |
| Admin account operations | `GET /admin/account-operations/parents/{parent_id}`; focused subscription operation tests | Backend complete. |

## Frontend Current Reality

| Area | Current evidence | Gap |
|------|------------------|-----|
| Parent account operations client | `src/services/parent/parentApi.ts` has children/subscription/billing calls only | Missing typed client/query key/page. |
| Admin account operations client | `src/services/admin/adminApi.ts` has subscription billing calls only | Missing typed client/query key/page. |
| Account operations routes | `src/app/router/AppRouter.tsx` has parent/admin routes, but none for account operations | Missing parent/admin route surfaces. |
| Email verification client | `src/services/auth/authApi.ts` has login/register/me/locale only | Missing resend/confirm verification calls. |
| Verification UX | `RegisterPage` and `LoginPage` render forms only | Missing pending/resend/confirm flow. |

## Planning Docs Reality

- `.planning/STATE.md` correctly says v5.9 is complete and next milestone is not started.
- Before this update, `.planning/ROADMAP.md` and `.planning/REQUIREMENTS.md` still represented the v5.9 closeout view.
- `.planning/NEXT-MILESTONES.md` and the `stoa_docs` gap queue still described v5.6-v5.9 as future/planned work and need correction.

## Decision

Start v5.10 as a frontend-first account operations and verification usability milestone.

Do not restart entitlement, usage, email verification, or account operations backend work unless frontend integration exposes a concrete backend contract bug.
