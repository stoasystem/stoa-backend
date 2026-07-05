# Phase 249 Context

## Milestone

v5.15 Usage, Quota, And Product Stability

## Requirement

QUOTA-01 Quota Reconciliation And Support Explanations

## Inputs From Phase 248

Phase 248 closed practice teacher-help ledger coverage and mismatched question idempotency conflicts. It also documented an intentional partial state: question counter and ledger writes can exist even when question persistence later fails. Phase 249 makes that kind of drift explainable to parent/admin support without raw content or mutating repair behavior.

## Files Changed

Backend:

- `src/stoa/services/usage_ledger_service.py`
- `src/stoa/routers/admin.py`
- `src/stoa/routers/parents.py`
- `tests/test_usage_ledger.py`

Frontend:

- `/Users/zhdeng/stoa-frontend/src/types/parentAccountOperations.ts`
- `/Users/zhdeng/stoa-frontend/src/pages/admin/AdminAccountOperationsPage.tsx`
- `/Users/zhdeng/stoa-frontend/src/pages/parent/ParentAccountOperationsPage.tsx`

## Constraints

- Reconciliation remains read-only except for the existing explicit question counter repair path.
- Support explanations must use counts, status, action, quota period, and entitlement limit only.
- Raw learning content, provider payloads, and private artifact identifiers remain excluded.
