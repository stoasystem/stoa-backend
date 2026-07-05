# Phase 268 Plan: Auth Session And Account State

## Plan

1. Add typed auth flow/session/error contracts.
2. Add Amplify Auth configuration and Cognito flow wrappers.
3. Add SecureStore metadata-only session boundary.
4. Add account-state mapper for support-safe mobile states.
5. Add authenticated API client wrapper and sign-out cleanup contract.
6. Add auth policy documentation and static tests.

## Verification

- Run `pytest tests/mobile/test_mobile_auth_contract.py tests/mobile/test_mobile_stack_contract.py`.
