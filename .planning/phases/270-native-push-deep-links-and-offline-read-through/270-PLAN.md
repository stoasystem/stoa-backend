# Phase 270 Plan: Native Push Deep Links And Offline Read-Through

## Plan

1. Add notification API adapter for list, preferences, push-token register/revoke, read, and archive.
2. Add Expo push permission and token acquisition service.
3. Add authenticated notification deep-link route validation.
4. Add offline read-through cache policy and SQLite helper.
5. Document push/offline boundaries and live provider blockers.
6. Add static tests.

## Verification

- Run `pytest tests/mobile/test_mobile_push_offline_contract.py tests/mobile/test_mobile_journey_contract.py tests/mobile/test_mobile_auth_contract.py tests/mobile/test_mobile_stack_contract.py`.
