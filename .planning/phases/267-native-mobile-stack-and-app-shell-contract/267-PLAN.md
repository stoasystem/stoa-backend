# Phase 267 Plan: Native Mobile Stack And App Shell Contract

## Plan

1. Add mobile Expo/React Native package metadata and config files.
2. Add Expo Router shell routes for auth, student, parent, notifications, and blocked states.
3. Add mobile config and route contract modules.
4. Document stack and environment policy.
5. Add static tests validating stack, deep-link, route, and no-demo-fallback contracts.

## Verification

- Run `pytest tests/mobile/test_mobile_stack_contract.py`.
- Confirm `node gsd-tools query roadmap.analyze` still finds Phase 267.
