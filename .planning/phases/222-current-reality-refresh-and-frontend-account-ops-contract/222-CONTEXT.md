# Phase 222 Context: Reality Refresh And Frontend Account Operations Contract

## Milestone

v5.10 Account Operations Frontend And Production Readiness

## Why This Phase Exists

The old Phase 201 current-reality audit is no longer the true current state. Since then:

- v5.6 completed effective entitlement and paid access enforcement.
- v5.7 completed question usage ledger and reconciliation.
- v5.8 completed backend email verification lifecycle and login-code policy gating.
- v5.9 completed backend parent/admin account operations visibility.

The next product gap is frontend usability and production-readiness evidence for these backend capabilities.

## Backend Reality To Preserve

- `/parents/me/account-operations` returns parent account operations summary.
- `/admin/account-operations/parents/{parent_id}` returns admin support detail.
- `/auth/email-verification/resend` and `/auth/email-verification/confirm` exist.
- `/auth/login-code/request` and `/auth/login-code/confirm` intentionally return deferred policy responses.
- Question submission uses effective entitlement and records privacy-safe usage ledger events.

## Frontend Reality To Fix

Readonly frontend scan found:

- `src/services/parent/parentApi.ts` lacks `/parents/me/account-operations`.
- `src/services/parent/parentQueryKeys.ts` lacks account operations query keys.
- `src/services/admin/adminApi.ts` lacks `/admin/account-operations/parents/{parent_id}`.
- `src/app/router/AppRouter.tsx` lacks parent/admin account operations routes.
- `src/services/auth/authApi.ts` lacks email verification resend/confirm clients.
- `RegisterPage` and `LoginPage` do not yet expose the full pending verification, resend, and confirm workflow.

## Planning Boundary

Phase 222 is planning and contract work. It should not implement frontend pages yet. The implementation starts in Phase 223.
