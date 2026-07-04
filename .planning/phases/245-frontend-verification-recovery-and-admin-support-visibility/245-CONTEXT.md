# Phase 245 Context: Frontend Verification Recovery And Admin Support Visibility

## Milestone

v5.14 Verification And Login Reliability

## Requirement

SUPPORT-01 Verification Support Visibility And Recovery

## Starting Point

Prior phases made verification reliable and login-code policy explicit. Parent/admin account operations already surfaced basic verification state, but support recovery evidence was spread across raw fields and not presented as a clear next action.

## Files Touched

Backend:

- `src/stoa/services/account_verification_service.py`
- `src/stoa/routers/admin.py`
- `tests/test_auth_account_lifecycle.py`
- `tests/test_subscription_operations.py`

Frontend:

- `/Users/zhdeng/stoa-frontend/src/components/parent/VerificationRecoveryEvidence.tsx`
- `/Users/zhdeng/stoa-frontend/src/pages/admin/AdminAccountOperationsPage.tsx`
- `/Users/zhdeng/stoa-frontend/src/pages/parent/ParentAccountOperationsPage.tsx`
- `/Users/zhdeng/stoa-frontend/src/types/parentAccountOperations.ts`

## Safety Boundary

Phase 245 adds bounded recovery visibility only. It does not expose raw verification codes, Cognito secrets, access tokens, or add an admin mutation that can override verification state.
