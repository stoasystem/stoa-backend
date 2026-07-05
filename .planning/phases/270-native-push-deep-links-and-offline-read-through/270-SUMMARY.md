# Phase 270 Summary: Native Push Deep Links And Offline Read-Through

## Completed

- Added notification API adapter for push token registration/revocation, preferences, read, archive, and list operations.
- Added Expo push permission/token service.
- Added notification deep-link route validation after sign-in, account readiness, and role checks.
- Added offline read-through cache policies, forbidden sensitive cache categories, online-only mutation guards, and SQLite helper.
- Added push/offline docs and static tests.

## Deferred

- Physical-device push smoke is blocked until Expo/EAS project configuration and FCM/APNs credentials are available.
- Runtime cache table migrations can be finalized when mobile dependency install/build is run.
