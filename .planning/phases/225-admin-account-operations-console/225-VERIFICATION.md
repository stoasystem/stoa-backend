---
status: passed
phase: 225
date: 2026-07-03
---

# Phase 225 Verification: Admin Account Operations Console

## Result

Passed.

## Evidence

| Command | Result |
|---------|--------|
| `npm run lint` in `/Users/zhdeng/stoa-frontend` | Passed |
| `npm run build` in `/Users/zhdeng/stoa-frontend` | Passed; existing Vite large chunk warning only |
| `npx playwright test tests/e2e/admin-account-operations.spec.ts` in `/Users/zhdeng/stoa-frontend` | Passed, 5 tests |

## Verified Acceptance Criteria

- Admin frontend API, query key, and React Query hook now cover `/admin/account-operations/parents/{parent_id}`.
- Admin account operations route supports direct lookup by parent ID and optional day query.
- Admin detail displays parent verification, billing summary/events, child binding, entitlement, usage, and support blockers/warnings.
- Missing parent 404 and generic API-error states are handled.
- Subscription requests/provider billing page links into the account operations console.

## Notes

- Build still reports the pre-existing Vite large chunk warning.
- The admin console is intentionally read-only; mutation workflows remain on subscription operations pages.
